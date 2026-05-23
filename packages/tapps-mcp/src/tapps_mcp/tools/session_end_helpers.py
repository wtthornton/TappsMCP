"""Session-end helper functions for TappsMCP pipeline tools.

TAP-2005: calls ``flywheel_process(since=<session_start_iso>)`` on the brain
bridge so that session events are reconciled into adaptive weight updates.

The operation is best-effort — a brain outage must not prevent session end
from completing.
"""

from __future__ import annotations

from typing import Any

import structlog

_logger = structlog.get_logger(__name__)


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
