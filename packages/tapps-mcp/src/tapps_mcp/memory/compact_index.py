"""Compact-index runner: index pre-compaction session state in brain.

Invoked by the PreCompact Claude Code hook via ``tapps-mcp compact-index``.
Reads the hook payload from stdin, extracts session context, and calls
``memory_index_session`` on the BrainBridge so the pre-compact state is
searchable in subsequent sessions via ``memory_search_sessions``.

Also writes ``.tapps-mcp/compaction-marker.json`` so ``tapps_session_start``
can detect a recent compaction on the next invocation and surface prior
session context as part of the response (TAP-2017).

Escape hatch: set ``TAPPS_MCP_COMPACTION_REHYDRATE=false`` to disable
all compaction indexing (marker file + brain call).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import structlog

_logger = structlog.get_logger(__name__)

COMPACTION_MARKER_FILENAME = "compaction-marker.json"
_COMPACTION_REHYDRATE_ENV = "TAPPS_MCP_COMPACTION_REHYDRATE"


def _is_disabled() -> bool:
    """Return True when the operator has disabled compaction rehydration."""
    return os.environ.get(_COMPACTION_REHYDRATE_ENV, "true").lower() == "false"


def _create_bridge(project_root: Path) -> Any:
    """Create a BrainBridge for indexing.  Importable name enables test patching.

    Returns the bridge instance or ``None`` when the brain is not configured.
    Raises on import or configuration errors so callers can log and proceed.
    """
    from tapps_core.brain_bridge import create_brain_bridge
    from tapps_core.config.settings import load_settings

    settings = load_settings(project_root=project_root)
    return create_brain_bridge(settings, default_profile="coder")


def _extract_session_id(payload: dict[str, Any]) -> str:
    """Extract session_id from PreCompact hook payload (best-effort).

    Claude Code's PreCompact payload may include ``session_id``, ``sessionId``,
    or similar fields.  Falls back to a timestamp-based ID when none are found.
    """
    for key in ("session_id", "sessionId", "session", "id"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    return f"compact-{int(time.time())}"


def _build_compaction_chunks(payload: dict[str, Any], session_id: str) -> list[str]:
    """Build indexable text chunks from the PreCompact payload.

    Produces a small, structured set of chunks:
    1. A boundary marker for querying by session.
    2. A trimmed summary/context extracted from the payload.
    3. The compaction trigger (auto vs manual).
    """
    chunks: list[str] = [f"compaction_boundary:{session_id}"]

    for key in ("summary", "context", "transcript"):
        text = payload.get(key)
        if isinstance(text, str) and text.strip():
            chunks.append(f"compaction_{key}:{text.strip()[:2000]}")
            break

    trigger = payload.get("trigger", "auto")
    if isinstance(trigger, str):
        chunks.append(f"compaction_trigger:{trigger}")

    return chunks


def _write_compaction_marker(
    project_root: Path,
    session_id: str,
    chunks: list[str],
    indexed: bool,
) -> Path:
    """Write ``.tapps-mcp/compaction-marker.json`` for session_start rehydration.

    Returns the path to the written marker file.
    """
    marker_dir = project_root / ".tapps-mcp"
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker: dict[str, Any] = {
        "session_id": session_id,
        "compacted_at": time.time(),
        "chunks": chunks,
        "indexed_in_brain": indexed,
    }
    marker_path = marker_dir / COMPACTION_MARKER_FILENAME
    marker_path.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return marker_path


async def run_compact_index(
    stdin_text: str,
    project_root: Path,
) -> dict[str, Any]:
    """Index pre-compaction session state in brain and write a rehydration marker.

    Args:
        stdin_text: Raw JSON from the PreCompact hook stdin.
        project_root: Project root directory (for settings and marker file).

    Returns:
        Summary dict with keys ``success``, ``session_id``, ``chunks``,
        ``indexed_in_brain``, and optionally ``error`` or ``skipped``.
    """
    if _is_disabled():
        _logger.info("compact_index_disabled", env=_COMPACTION_REHYDRATE_ENV)
        return {"success": False, "skipped": True, "reason": "disabled_by_env"}

    try:
        payload: dict[str, Any] = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError:
        payload = {"context": stdin_text[:8000]}

    session_id = _extract_session_id(payload)
    chunks = _build_compaction_chunks(payload, session_id)

    # Attempt brain indexing first (best-effort).
    indexed = False
    brain_error: str | None = None
    try:
        bridge = _create_bridge(project_root)
        if bridge is not None:
            try:
                if hasattr(bridge, "index_session"):
                    await bridge.index_session(session_id, chunks)
                    indexed = True
                else:
                    brain_error = "index_session_not_supported"
            finally:
                bridge.close()
        else:
            brain_error = "bridge_unavailable"
    except Exception as exc:
        brain_error = str(exc)
        _logger.warning(
            "compact_index_brain_failed",
            error=brain_error,
            session_id=session_id,
        )

    # Always write the marker file so session_start can rehydrate from it
    # even when the brain call failed.
    try:
        marker_path = _write_compaction_marker(project_root, session_id, chunks, indexed)
        _logger.info(
            "compact_index_marker_written",
            path=str(marker_path),
            session_id=session_id,
            indexed_in_brain=indexed,
        )
    except Exception as exc:
        _logger.warning("compact_index_marker_write_failed", error=str(exc))
        return {
            "success": False,
            "session_id": session_id,
            "chunks": len(chunks),
            "indexed_in_brain": indexed,
            "error": f"marker_write_failed: {exc}",
        }

    result: dict[str, Any] = {
        "success": True,
        "session_id": session_id,
        "chunks": len(chunks),
        "indexed_in_brain": indexed,
    }
    if brain_error:
        result["brain_error"] = brain_error
    return result
