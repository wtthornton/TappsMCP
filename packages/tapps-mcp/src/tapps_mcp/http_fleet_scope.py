"""Per-request tool gates for HTTP fleet callers (TAP-6062).

``nlt-build`` registers its full profile at import time -- registration is
process-level, so it cannot express "this *request* may only reach four
tools". This module adds the missing per-request layer by re-registering the
low-level ``tools/list`` and ``tools/call`` handlers with guards that read the
auth scope bound by :mod:`tapps_core.http.middleware`.

Both directions matter. Filtering only ``tools/list`` would leave a hidden but
callable surface: a client that already knows a tool name would still reach
it. Filtering only ``tools/call`` would advertise 20 tools and refuse 16 of
them. So the guard covers both, and ``tools/call`` is the authoritative gate.

``tools/call`` carries a second gate for the same structural reason: tools that
read a repository tree must refuse a workspace-free request. Enforcing that
here rather than in each handler means the list of tools needing a workspace is
one declaration, not a check somebody forgets to add to the next scanner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from tapps_mcp.platform.nlt_profiles import (
    RUNTIME_SCOPE_SERVERS,
    WORKSPACE_REQUIRED_TOOLS,
    resolve_fleet_scope_tools,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcp.server.fastmcp import FastMCP
    from mcp.types import Tool as MCPTool

logger = structlog.get_logger(__name__)

_GUARD_INSTALLED_ATTR = "_tapps_fleet_request_guards"


class RuntimeScopeRefusedError(Exception):
    """Raised when a runtime-scoped request calls a tool outside its allowlist."""


def server_allows_runtime_scope(tool_preset: str | None) -> bool:
    """True when this server process may accept the fleet runtime token."""
    return tool_preset in RUNTIME_SCOPE_SERVERS


def allowed_tools_for_request() -> frozenset[str] | None:
    """Allowlist for the in-flight request, or ``None`` when unscoped."""
    from tapps_core.http.request_context import get_request_auth_scope

    return resolve_fleet_scope_tools(get_request_auth_scope())


def workspace_refusal_for(tool_name: str) -> dict[str, Any] | None:
    """Structured refusal when *tool_name* needs a tree this request has none of."""
    if tool_name not in WORKSPACE_REQUIRED_TOOLS:
        return None
    from tapps_mcp.server_helpers import workspace_free_refusal

    return workspace_free_refusal(tool_name)


def install_fleet_request_guards(mcp: FastMCP, *, runtime_scope: bool = True) -> None:
    """Re-register ``tools/list`` / ``tools/call`` with the per-request gates.

    FastMCP binds its handlers in ``_setup_handlers`` during construction, so
    reassigning ``mcp.list_tools`` after the fact would be a no-op -- the
    low-level server already holds the original bound method. Re-running the
    registration decorators replaces the entry in ``request_handlers``, which
    is the only hook that actually intercepts a live request.

    *runtime_scope* enables the trimmed-profile allowlist; the workspace gate
    is unconditional, because a workspace-free request is possible on any HTTP
    caller, token or not.
    """
    if getattr(mcp, _GUARD_INSTALLED_ATTR, False):
        return

    original_list_tools = mcp.list_tools
    original_call_tool = mcp.call_tool

    async def list_tools() -> list[MCPTool]:
        tools = await original_list_tools()
        allowed = allowed_tools_for_request() if runtime_scope else None
        if allowed is None:
            return tools
        return [tool for tool in tools if tool.name in allowed]

    async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
        allowed = allowed_tools_for_request() if runtime_scope else None
        if allowed is not None and name not in allowed:
            logger.warning("http.runtime_scope_refused", tool=name)
            msg = (
                f"Tool {name!r} is not available to this credential. The fleet "
                "runtime token is scoped to: " + ", ".join(sorted(allowed)) + "."
            )
            raise RuntimeScopeRefusedError(msg)
        refusal = workspace_refusal_for(name)
        if refusal is not None:
            return refusal
        return await original_call_tool(name, arguments)

    # The SDK's registration decorators are untyped; bind the low-level server
    # through an explicitly-Any local rather than silencing the checker.
    low_level: Any = mcp._mcp_server
    low_level.list_tools()(list_tools)
    low_level.call_tool(validate_input=False)(call_tool)
    setattr(mcp, _GUARD_INSTALLED_ATTR, True)
    logger.info("http.fleet_request_guards_installed", runtime_scope=runtime_scope)
