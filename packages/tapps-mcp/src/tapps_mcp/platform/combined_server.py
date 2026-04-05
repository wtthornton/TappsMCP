"""Combined TappsPlatform MCP server.

Composes TappsMCP (code quality, 28+ tools) and DocsMCP (documentation, 19 tools)
into a single MCP server instance. Both tool sets are registered without namespace
prefixes since they already use distinct ``tapps_`` and ``docs_`` prefixes.

If ``docs-mcp`` is not installed, the server falls back to TappsMCP-only mode
with a warning logged.

Usage::

    # stdio (default)
    tapps-platform serve

    # Streamable HTTP
    tapps-platform serve --transport http --port 8000
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger: Any = structlog.get_logger(__name__)

# Detect docs-mcp availability at import time
_DOCS_MCP_AVAILABLE = True
try:
    from docs_mcp.server import mcp as docs_server
except ImportError:
    _DOCS_MCP_AVAILABLE = False
    docs_server = None  # type: ignore[assignment]


def _copy_tools(
    source_tools: dict[str, Any],
    target_tools: dict[str, Any],
    source_name: str,
) -> list[str]:
    """Copy tools from source to target, returning list of collision names."""
    collisions: list[str] = []
    for name, tool in source_tools.items():
        if name in target_tools:
            collisions.append(name)
            logger.warning(
                "tool_name_collision",
                tool_name=name,
                source=source_name,
                msg="Skipping - already registered",
            )
            continue
        target_tools[name] = tool
    return collisions


def _copy_resources(source: dict[str, Any], target: dict[str, Any]) -> None:
    """Copy resources from source to target, skipping duplicates."""
    for name, resource in source.items():
        if name not in target:
            target[name] = resource


def _copy_prompts(source: dict[str, Any], target: dict[str, Any]) -> None:
    """Copy prompts from source to target, skipping duplicates."""
    for name, prompt in source.items():
        if name not in target:
            target[name] = prompt


def create_combined_server() -> FastMCP:
    """Create a combined FastMCP server with tools from both TappsMCP and DocsMCP.

    If ``docs-mcp`` is not installed, returns TappsMCP-only with a warning.

    Returns:
        A FastMCP instance with all available tools.

    Raises:
        RuntimeError: If tool name collisions are detected.
    """
    from mcp.server.fastmcp import FastMCP

    from tapps_mcp.server import mcp as tapps_server

    combined = FastMCP("TappsPlatform")

    # Copy TappsMCP tools
    for name, tool in tapps_server._tool_manager._tools.items():
        combined._tool_manager._tools[name] = tool

    # Copy TappsMCP resources and prompts
    _copy_resources(
        tapps_server._resource_manager._resources,
        combined._resource_manager._resources,
    )
    _copy_prompts(
        tapps_server._prompt_manager._prompts,
        combined._prompt_manager._prompts,
    )

    tapps_tool_count = len(tapps_server._tool_manager._tools)
    docs_tool_count = 0

    # Graceful degradation: skip DocsMCP if not installed
    if not _DOCS_MCP_AVAILABLE or docs_server is None:
        logger.warning(
            "docs_mcp_not_available",
            msg="docs-mcp is not installed; running in TappsMCP-only mode",
        )
    else:
        collisions = _copy_tools(
            docs_server._tool_manager._tools,
            combined._tool_manager._tools,
            source_name="docs_mcp",
        )
        if collisions:
            msg = f"Tool name collisions detected: {', '.join(collisions)}"
            raise RuntimeError(msg)

        _copy_resources(
            docs_server._resource_manager._resources,
            combined._resource_manager._resources,
        )
        _copy_prompts(
            docs_server._prompt_manager._prompts,
            combined._prompt_manager._prompts,
        )
        docs_tool_count = len(docs_server._tool_manager._tools)

    total_tools = len(combined._tool_manager._tools)
    total_resources = len(combined._resource_manager._resources)
    total_prompts = len(combined._prompt_manager._prompts)

    logger.info(
        "combined_server_created",
        tapps_tools=tapps_tool_count,
        docs_tools=docs_tool_count,
        total_tools=total_tools,
        total_resources=total_resources,
        total_prompts=total_prompts,
        docs_available=_DOCS_MCP_AVAILABLE,
    )

    return combined


def health_check() -> dict[str, Any]:
    """Return server health information.

    Returns:
        Dict with server name, tool/resource/prompt counts, and sub-server
        availability.
    """
    from tapps_mcp import __version__ as tapps_version

    result: dict[str, Any] = {
        "server": "TappsPlatform",
        "tapps_mcp": {
            "available": True,
            "version": tapps_version,
        },
        "docs_mcp": {
            "available": _DOCS_MCP_AVAILABLE,
            "version": None,
        },
    }

    if _DOCS_MCP_AVAILABLE:
        try:
            from docs_mcp import __version__ as docs_version

            result["docs_mcp"]["version"] = docs_version
        except ImportError:
            pass

    # Tool counts from source servers (without creating a combined instance)
    try:
        from tapps_mcp.server import mcp as tapps_server

        result["tapps_mcp"]["tool_count"] = len(tapps_server._tool_manager._tools)
    except Exception:
        result["tapps_mcp"]["tool_count"] = 0

    if _DOCS_MCP_AVAILABLE and docs_server is not None:
        try:
            result["docs_mcp"]["tool_count"] = len(docs_server._tool_manager._tools)
        except Exception:
            result["docs_mcp"]["tool_count"] = 0
    else:
        result["docs_mcp"]["tool_count"] = 0

    result["total_tool_count"] = (
        result["tapps_mcp"]["tool_count"] + result["docs_mcp"]["tool_count"]
    )

    return result


def run_combined_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start the combined TappsPlatform MCP server."""
    from tapps_core.common.logging import setup_logging
    from tapps_core.config.settings import load_settings

    settings = load_settings()
    setup_logging(level=settings.log_level, json_output=settings.log_json)

    combined = create_combined_server()

    logger.info(
        "tapps_platform_starting",
        transport=transport,
        project_root=str(settings.project_root),
    )

    if transport == "stdio":
        combined.run(transport="stdio")
    elif transport == "http":
        import uvicorn

        app = combined.streamable_http_app()
        uvicorn.run(app, host=host, port=port)
    else:
        msg = f"Unknown transport: {transport}"
        raise ValueError(msg)
