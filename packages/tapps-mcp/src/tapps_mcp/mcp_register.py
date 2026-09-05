"""Register MCP tools with catalog-length descriptions (TAP-1963).

FastMCP defaults to the handler docstring as the tool description. Those
docstrings carry full Args/When-to-call detail for maintainers; this module
passes concise ``description=`` strings at registration time instead.

This is also the single dispatch seam every registered tool passes through
(TAP-6615 round 2): ``register_tool`` wraps each handler so the per-session
ledger sees the final returned payload exactly once, regardless of which
response helper (``success_response``/``error_response``/``_with_nudges``)
built it. A handler bypassed *this* function -- e.g. registered straight on
``mcp_instance.tool()`` -- is not ledgered.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from tapps_mcp.tool_descriptions import TOOL_DESCRIPTIONS


def _with_ledger(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap *fn* so one ledger row is recorded per call (TAP-6615 round 2).

    Lazily imports ``_record_ledger_entry`` from ``tapps_mcp.server`` --
    that module is already fully loaded by the time any registered tool is
    actually invoked, since ``register_tool`` itself only runs from inside
    ``tapps_mcp.server._register_tool_modules()``.
    """
    name = fn.__name__

    def _ledger(response: Any) -> None:
        if not isinstance(response, dict):
            return
        from tapps_mcp.server import _record_ledger_entry

        _record_ledger_entry(name, response)

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            response = await fn(*args, **kwargs)
            _ledger(response)
            return response

        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        response = fn(*args, **kwargs)
        _ledger(response)
        return response

    return sync_wrapper


def register_tool(
    mcp_instance: FastMCP,
    fn: Callable[..., Any],
    *,
    annotations: ToolAnnotations,
    meta: dict[str, Any] | None = None,
) -> None:
    """Register *fn* on *mcp_instance* with a budgeted MCP description."""
    name = fn.__name__
    try:
        description = TOOL_DESCRIPTIONS[name]
    except KeyError as exc:
        msg = f"Missing TOOL_DESCRIPTIONS entry for {name!r}"
        raise KeyError(msg) from exc
    mcp_instance.tool(
        annotations=annotations,
        meta=meta,
        description=description,
    )(_with_ledger(fn))
