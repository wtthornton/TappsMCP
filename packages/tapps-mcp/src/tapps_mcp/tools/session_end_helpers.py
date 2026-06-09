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

from typing import Any

import structlog

_logger = structlog.get_logger(__name__)


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


async def run_session_end(session_start_iso: str = "") -> dict[str, Any]:
    """Shared session-end logic for the MCP tool and CLI (TAP-3174).

    Best-effort — brain outages surface in the result dict, never as exceptions.
    """
    since = session_start_iso
    flywheel = await call_flywheel_process(since)
    session_search = await call_memory_search_sessions(since or "recent")
    return {
        "flywheel": flywheel,
        "session_search": session_search,
        "session_start_iso": since or None,
    }


def run_session_end_sync(session_start_iso: str = "") -> dict[str, Any]:
    """Synchronous wrapper for ``run_session_end`` (CLI entry point)."""
    import asyncio

    return asyncio.run(run_session_end(session_start_iso))


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
