"""Auto-capture runner: extract durable facts and save to memory (Epic 65.5).

Invoked by Stop/SessionEnd hooks. Reads JSON from stdin, extracts context,
calls extract_durable_facts, and saves via :class:`BrainBridge` (TAP-414 /
EPIC-95.5). When ``TAPPS_BRAIN_DATABASE_URL`` is unset, the run silently
skips with ``degraded=True`` instead of attempting a SQLite write.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any


def _text_from_message_content(content: Any) -> str:
    """Extract plain text from a transcript row's ``message.content``.

    ``content`` is either a plain string or a list of blocks (``text``,
    ``tool_use``, ``tool_result``). Only ``text`` blocks are kept — tool
    input/output is not durable-fact material and can be arbitrarily large.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            blk["text"].strip()
            for blk in content
            if isinstance(blk, dict)
            and blk.get("type") == "text"
            and isinstance(blk.get("text"), str)
        ]
        return "\n".join(p for p in parts if p)
    return ""


def _iter_transcript_text_turns(
    transcript_path: Path,
    *,
    transcript_turns: int,
    transcript_max_bytes: int,
) -> list[str]:
    """Read the last N user/assistant text turns from a Claude Code transcript JSONL.

    Walks the file newest-first so the turn and byte caps bound the most
    recent conversation, then returns the turns in chronological order.
    """
    try:
        with transcript_path.open(encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return []

    turns: list[str] = []
    total_bytes = 0
    for raw_line in reversed(lines):
        if len(turns) >= transcript_turns or total_bytes >= transcript_max_bytes:
            break
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("type") not in ("user", "assistant"):
            continue
        msg = row.get("message")
        if not isinstance(msg, dict):
            continue
        text = _text_from_message_content(msg.get("content"))
        if not text:
            continue
        total_bytes += len(text.encode("utf-8"))
        turns.append(text)

    turns.reverse()
    return turns


def _extract_context_from_payload(
    payload: dict[str, Any],
    *,
    transcript_turns: int = 40,
    transcript_max_bytes: int = 32 * 1024,
) -> str:
    """Extract text context from Stop hook JSON payload.

    Prefers inline ``transcript`` / ``context`` / ``messages`` keys. When none
    are present, falls back to reading ``transcript_path`` (the shape Claude
    Code's Stop hook actually sends: ``{"transcript_path", "cwd",
    "hook_event_name": "Stop", ...}``). Never falls back to dumping the raw
    payload — an unusable context must return "" so the length gate fails
    honestly instead of "succeeding" on hook metadata.
    """
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
                    parts.extend(
                        c["text"].strip()
                        for c in content
                        if isinstance(c, dict) and isinstance(c.get("text"), str)
                    )
    if not parts:
        transcript_path = payload.get("transcript_path")
        if isinstance(transcript_path, str) and transcript_path:
            path = Path(transcript_path)
            if path.is_file():
                parts.extend(
                    _iter_transcript_text_turns(
                        path,
                        transcript_turns=transcript_turns,
                        transcript_max_bytes=transcript_max_bytes,
                    )
                )
    return "\n\n".join(p for p in parts if p)


async def run_auto_capture(
    stdin_text: str,
    project_root: Path,
    *,
    max_facts: int = 5,
    min_context_length: int = 100,
    capture_prompt: str = "",
    transcript_turns: int | None = None,
    transcript_max_bytes: int | None = None,
) -> dict[str, Any]:
    """Extract durable facts from context and save via BrainBridge.

    Args:
        stdin_text: Raw JSON from Stop hook stdin.
        project_root: Project root for settings + bridge construction.
        max_facts: Maximum facts to extract (default 5).
        min_context_length: Skip if context shorter (default 100).
        capture_prompt: Optional capture prompt from config (Epic 65.3).
        transcript_turns: Max turns read from transcript_path. ``None`` (the
            default) falls back to ``memory_hooks.auto_capture.transcript_turns``.
        transcript_max_bytes: Byte cap on transcript_path text. ``None`` (the
            default) falls back to ``memory_hooks.auto_capture.transcript_max_bytes``.

    Returns:
        Dict with saved, skipped, errors, extracted keys, facts, session_id,
        and reason (set whenever saved==0: "disabled", "stop_hook_active",
        "no_context", "no_facts", "bridge_unavailable", or "save_failed").
        Includes ``degraded=True`` when no bridge is available.
    """
    from tapps_brain.extraction import extract_durable_facts

    from tapps_core.brain_bridge import BRAIN_PROFILE_WRITE_HOOK, create_brain_bridge
    from tapps_core.config.settings import load_settings

    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError:
        payload = {"context": stdin_text[:10000]}

    result: dict[str, Any] = {
        "saved": 0,
        "skipped": 0,
        "errors": [],
        "extracted_keys": [],
        "facts": 0,
        "session_id": payload.get("session_id") if isinstance(payload, dict) else None,
        "reason": None,
    }

    settings = load_settings(project_root=project_root)
    auto_capture_settings = settings.memory_hooks.auto_capture
    if not auto_capture_settings.enabled:
        result["reason"] = "disabled"
        return result

    # Check stop_hook_active to avoid recursion
    if payload.get("stop_hook_active") in (True, "true", "True"):
        result["reason"] = "stop_hook_active"
        return result

    context = _extract_context_from_payload(
        payload,
        transcript_turns=(
            transcript_turns
            if transcript_turns is not None
            else auto_capture_settings.transcript_turns
        ),
        transcript_max_bytes=(
            transcript_max_bytes
            if transcript_max_bytes is not None
            else auto_capture_settings.transcript_max_bytes
        ),
    )
    if len(context) < min_context_length:
        result["reason"] = "no_context"
        return result

    facts = extract_durable_facts(
        context,
        capture_prompt,
        max_facts=max_facts,
        max_value_chars=4096,
    )
    result["facts"] = len(facts)
    if not facts:
        result["reason"] = "no_facts"
        return result

    # TAP-6733: this path writes via bridge.save() (memory_save), which the
    # "coder" profile hides (ADR-0012's own tool table excludes memory_save
    # from "coder"). "seeder" is the least-privilege profile that exposes it.
    # settings.memory.brain_profile / TAPPS_BRAIN_PROFILE still override this.
    bridge = create_brain_bridge(settings, default_profile=BRAIN_PROFILE_WRITE_HOOK)
    if bridge is None:
        result["degraded"] = True
        result["reason"] = "bridge_unavailable"
        result["errors"].append("TAPPS_BRAIN_DATABASE_URL not configured; skipping auto-capture.")
        return result

    try:
        for entry in facts:
            key = entry.get("key", "")
            value = entry.get("value", "")
            tier = entry.get("tier", "pattern")
            if not key or not value:
                result["skipped"] += 1
                continue
            try:
                out = await bridge.save(
                    key=key,
                    value=value,
                    tier=tier,
                    scope="session",
                    source="system",
                    source_agent="auto-capture",
                )
                if isinstance(out, dict) and out.get("degraded"):
                    result["errors"].append(
                        f"{key}: bridge degraded ({out.get('reason', 'unknown')})"
                    )
                    result["skipped"] += 1
                else:
                    result["saved"] += 1
                    result["extracted_keys"].append(key)
            except Exception as exc:
                result["errors"].append(f"{key}: {exc}")
                result["skipped"] += 1
    finally:
        bridge.close()

    # Reaching here means facts were extracted (the "no_facts" return above
    # already handled the empty case) but every save attempt was skipped or
    # errored -- label it distinctly so "no_facts" always means extraction
    # found nothing, not that a save failed after extraction succeeded.
    if result["saved"] == 0 and result["reason"] is None:
        result["reason"] = "save_failed"

    return result


def main() -> int:
    """CLI entry point: read stdin, run auto-capture, exit 0."""
    import os

    raw = sys.stdin.read()
    project_root_str = (
        os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("TAPPS_MCP_PROJECT_ROOT") or "."
    )
    project_root = Path(project_root_str).resolve()
    res = asyncio.run(run_auto_capture(raw, project_root))
    import structlog

    log = structlog.get_logger(__name__)
    if res.get("degraded"):
        log.info("auto_capture_degraded", reason="no_brain_url")
    if res.get("errors"):
        for e in res["errors"][:3]:
            log.warning("auto_capture_error", error=str(e))
    if res.get("saved"):
        log.info("auto_capture_saved", saved=res["saved"])
    return 0
