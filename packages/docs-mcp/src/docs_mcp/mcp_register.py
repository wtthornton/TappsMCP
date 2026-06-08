"""Register MCP tools with catalog-length descriptions (TAP-1963)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from docs_mcp.tool_descriptions import TOOL_DESCRIPTIONS


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
    )(fn)
