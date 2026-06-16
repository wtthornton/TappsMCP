"""Session-end helper functions for TappsMCP pipeline tools.

TAP-2005: calls ``flywheel_process(since=<session_start_iso>)`` on the brain
bridge so that session events are reconciled into adaptive weight updates.

TAP-1999: adds ``call_memory_search_sessions`` so ``tapps_session_end`` can
fetch the live brain-native session index written by
``call_memory_index_session_start`` at session start.

All operations are best-effort — a brain outage must not prevent session end
from completing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

_logger = structlog.get_logger(__name__)

_SESSION_START_ISO_REL = Path(".tapps-mcp") / ".session-start-iso"


def persist_session_start_iso(project_root: Path, iso: str) -> None:
    """Persist session start time for flywheel scope across MCP subprocess restarts."""
    if not iso.strip():
        return
    try:
        path = project_root / _SESSION_START_ISO_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(iso.strip(), encoding="utf-8")
    except OSError:
        _logger.debug("persist_session_start_iso_failed", exc_info=True)


def read_persisted_session_start_iso(project_root: Path) -> str:
    """Return ISO timestamp written at last ``tapps_session_start``, or ``''``."""
    path = project_root / _SESSION_START_ISO_REL
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


def resolve_session_start_iso(
    session_start_iso: str,
    project_root: Path | None = None,
) -> tuple[str, str]:
    """Return ``(iso, source)`` for ``flywheel_process(since=...)``."""
    since = session_start_iso.strip()
    if since:
        return since, "session_state"
    if project_root is not None:
        persisted = read_persisted_session_start_iso(project_root)
        if persisted:
            return persisted, "persisted_file"
    return "", "missing"


async def call_memory_search_sessions(
    query: str,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Search the brain-native session index via ``memory_search_sessions``.

    TAP-1999: counterpart to ``call_memory_index_session_start`` called at
    session end so the session summary response includes searchable prior
    context.

    Returns a structured dict.  Always succeeds — any exception is caught
    and surfaced as ``{"success": False, ...}``.
    """
    try:
        from tapps_mcp.server_helpers import _get_brain_bridge

        bridge = _get_brain_bridge()
    except Exception as exc:
        _logger.debug("memory_search_sessions_bridge_resolve_failed", error=str(exc))
        return {"success": False, "skipped": True, "reason": "bridge_unavailable"}

    if bridge is None:
        return {"success": False, "skipped": True, "reason": "bridge_unavailable"}

    if not hasattr(bridge, "search_sessions"):
        return {"success": False, "skipped": True, "reason": "search_sessions_not_supported"}

    try:
        result = await bridge.search_sessions(query, limit=limit)
    except Exception as exc:
        _logger.warning("memory_search_sessions_failed", error=str(exc), query=query)
        return {"success": False, "error": str(exc)}

    _logger.info(
        "memory_search_sessions_completed",
        query=query,
        result_count=len(result.get("results", [])) if isinstance(result, dict) else 0,
    )
    return {"success": True, "result": result, "query": query}


def build_session_search_query(
    session_start_iso: str,
    project_root: Path | None = None,
) -> tuple[str, str]:
    """Choose a retrievable ``memory_search_sessions`` query (TAP-3793).

    Prefers handoff Linear id, then Next (P0) prose, then ``session_start_iso``.
    Timestamps are poor semantic retrieval keys when the session index stores chunks.
    """
    if project_root is not None:
        from tapps_mcp.tools.handoff_schema import load_and_lint_handoff

        doc, _lint = load_and_lint_handoff(project_root)
        if doc is not None:
            if doc.linear_p0:
                return doc.linear_p0, "handoff_linear_p0"
            if doc.next_p0:
                return doc.next_p0[0], "handoff_next_p0"

    since = session_start_iso.strip()
    if since:
        return since, "session_start_iso"
    return "recent", "fallback_recent"


async def run_session_end(
    session_start_iso: str = "",
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Shared session-end logic for the MCP tool and CLI (TAP-3174).

    Best-effort — brain outages surface in the result dict, never as exceptions.
    """
    since, since_source = resolve_session_start_iso(session_start_iso, project_root)
    flywheel = await call_flywheel_process(since)
    query, query_source = build_session_search_query(since, project_root)
    session_search = await call_memory_search_sessions(query)
    if isinstance(session_search, dict):
        session_search = {**session_search, "query_source": query_source}

    flywheel_note: str | None = None
    if since_source == "missing":
        flywheel_note = (
            "session_start_iso missing — call tapps_session_start() at session open; "
            "flywheel may process unscoped events; session_search uses handoff or recent"
        )
    elif since_source == "persisted_file":
        flywheel_note = (
            "flywheel since= from persisted .session-start-iso (in-process state was empty)"
        )
    elif query_source != "session_start_iso":
        flywheel_note = (
            "session_search uses handoff-derived query instead of session_start_iso "
            "for better retrieval"
        )

    return {
        "flywheel": flywheel,
        "session_search": session_search,
        "session_start_iso": since or None,
        "session_start_iso_source": since_source,
        "session_search_query": query,
        "flywheel_note": flywheel_note,
    }


def run_session_end_sync(
    session_start_iso: str = "",
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for ``run_session_end`` (CLI entry point)."""
    import asyncio

    return asyncio.run(run_session_end(session_start_iso, project_root=project_root))


async def call_flywheel_process(session_start_iso: str) -> dict[str, Any]:
    """Call ``flywheel_process(since=session_start_iso)`` on the brain bridge.

    Returns a structured summary dict.  Always succeeds — any exception is
    caught and surfaced as ``{"success": False, "error": <msg>}``.
    """
    try:
        from tapps_mcp.server_helpers import _get_brain_bridge

        bridge = _get_brain_bridge()
    except Exception as exc:
        _logger.debug("flywheel_process_bridge_resolve_failed", error=str(exc))
        return {"success": False, "skipped": True, "reason": "bridge_unavailable"}

    if bridge is None:
        return {"success": False, "skipped": True, "reason": "bridge_unavailable"}

    if not hasattr(bridge, "flywheel_process"):
        return {"success": False, "skipped": True, "reason": "flywheel_process_not_supported"}

    try:
        result = await bridge.flywheel_process(since=session_start_iso)
    except Exception as exc:
        _logger.warning("flywheel_process_failed", error=str(exc), since=session_start_iso)
        return {"success": False, "error": str(exc)}

    _logger.info(
        "flywheel_process_completed",
        since=session_start_iso,
        result_keys=list(result.keys()) if isinstance(result, dict) else None,
    )
    return {"success": True, "result": result, "since": session_start_iso}
