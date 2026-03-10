"""Auto-capture runner: extract durable facts and save to memory (Epic 65.5).

Invoked by Stop/SessionEnd hooks. Reads JSON from stdin, extracts context,
calls extract_durable_facts, and saves via MemoryStore.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _extract_context_from_payload(payload: dict[str, Any]) -> str:
    """Extract text context from Stop hook JSON payload."""
    parts: list[str] = []
    if isinstance(payload.get("transcript"), str):
        parts.append(payload["transcript"].strip())
    if isinstance(payload.get("context"), str):
        parts.append(payload["context"].strip())
    messages = payload.get("messages")
    if isinstance(messages, list):
        for m in messages[-50:]:  # Last 50 messages
            if isinstance(m, dict):
                content = m.get("content") or m.get("text") or m.get("message")
                if isinstance(content, str):
                    parts.append(content.strip())
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and isinstance(c.get("text"), str):
                            parts.append(c["text"].strip())
    # Fallback: use raw payload as string for structured data
    if not parts:
        raw = json.dumps(payload, default=str)[:8000]
        parts.append(raw)
    return "\n\n".join(p for p in parts if p)


def run_auto_capture(
    stdin_text: str,
    project_root: Path,
    *,
    max_facts: int = 5,
    min_context_length: int = 100,
    capture_prompt: str = "",
) -> dict[str, Any]:
    """Extract durable facts from context and save to memory.

    Args:
        stdin_text: Raw JSON from Stop hook stdin.
        project_root: Project root for MemoryStore.
        max_facts: Maximum facts to extract (default 5).
        min_context_length: Skip if context shorter (default 100).
        capture_prompt: Optional capture prompt from config (Epic 65.3).

    Returns:
        Dict with saved, skipped, errors, and extracted keys.
    """
    from tapps_core.memory.extraction import extract_durable_facts
    from tapps_core.memory.store import ConsolidationConfig, MemoryStore

    result: dict[str, Any] = {
        "saved": 0,
        "skipped": 0,
        "errors": [],
        "extracted_keys": [],
    }

    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError:
        payload = {"context": stdin_text[:10000]}

    # Check stop_hook_active to avoid recursion
    if payload.get("stop_hook_active") in (True, "true", "True"):
        return result

    context = _extract_context_from_payload(payload)
    if len(context) < min_context_length:
        return result

    facts = extract_durable_facts(
        context,
        capture_prompt,
        max_facts=max_facts,
        max_value_chars=4096,
    )
    if not facts:
        return result

    try:
        store = MemoryStore(
            project_root,
            consolidation_config=ConsolidationConfig(enabled=False),
        )
    except Exception as exc:
        result["errors"].append(f"Store init failed: {exc}")
        return result

    for entry in facts:
        key = entry.get("key", "")
        value = entry.get("value", "")
        tier = entry.get("tier", "pattern")
        if not key or not value:
            result["skipped"] += 1
            continue
        try:
            out = store.save(
                key=key,
                value=value,
                tier=tier,
                source="system",
                source_agent="auto-capture",
            )
            if isinstance(out, dict) and "error" in out:
                result["errors"].append(f"{key}: {out.get('message', out)}")
                result["skipped"] += 1
            else:
                result["saved"] += 1
                result["extracted_keys"].append(key)
        except Exception as exc:
            result["errors"].append(f"{key}: {exc}")
            result["skipped"] += 1

    return result


def main() -> int:
    """CLI entry point: read stdin, run auto-capture, exit 0."""
    import os

    raw = sys.stdin.read()
    project_root_str = (
        os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("TAPPS_MCP_PROJECT_ROOT") or "."
    )
    project_root = Path(project_root_str).resolve()
    res = run_auto_capture(raw, project_root)
    import structlog

    log = structlog.get_logger(__name__)
    if res.get("errors"):
        for e in res["errors"][:3]:
            log.warning("auto_capture_error", error=str(e))
    if res.get("saved"):
        log.info("auto_capture_saved", saved=res["saved"])
    return 0
