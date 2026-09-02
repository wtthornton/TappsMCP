"""Trimmed runtime profile for bearer-authed fleet callers (TAP-6062, Story 3)."""

from __future__ import annotations

from typing import Any

import pytest
from mcp import types
from mcp.server.fastmcp import FastMCP

from tapps_core.http.request_context import (
    reset_request_auth_scope,
    set_request_auth_scope,
)
from tapps_mcp.http_fleet_scope import (
    allowed_tools_for_request,
    install_runtime_scope_guard,
    server_allows_runtime_scope,
)
from tapps_mcp.platform.nlt_profiles import (
    TOOL_PROFILE_FLEET_RUNTIME,
    resolve_fleet_scope_tools,
)


class TestRuntimeProfile:
    def test_exact_membership(self) -> None:
        """The runtime surface is these four tools and nothing else."""
        assert (
            frozenset(
                {
                    "tapps_lookup_docs",
                    "tapps_research",
                    "tapps_security_scan",
                    "tapps_dependency_scan",
                }
            )
            == TOOL_PROFILE_FLEET_RUNTIME
        )

    def test_runtime_profile_is_a_strict_subset_of_nlt_build(self) -> None:
        from tapps_mcp.server import TOOL_PROFILE_NLT_BUILD

        assert TOOL_PROFILE_FLEET_RUNTIME < TOOL_PROFILE_NLT_BUILD

    def test_resolve_scope_tools(self) -> None:
        assert resolve_fleet_scope_tools("runtime") == TOOL_PROFILE_FLEET_RUNTIME
        assert resolve_fleet_scope_tools("operator") is None
        assert resolve_fleet_scope_tools(None) is None

    def test_only_nlt_build_accepts_the_runtime_token(self) -> None:
        assert server_allows_runtime_scope("nlt-build") is True
        for other in ("nlt-memory", "nlt-setup", "nlt-linear-issues", "nlt-release-ship", "full"):
            assert server_allows_runtime_scope(other) is False, other

    def test_allowed_tools_for_request_follows_the_bound_scope(self) -> None:
        assert allowed_tools_for_request() is None
        token = set_request_auth_scope("runtime")
        try:
            assert allowed_tools_for_request() == TOOL_PROFILE_FLEET_RUNTIME
        finally:
            reset_request_auth_scope(token)


def _guarded_server() -> FastMCP:
    mcp = FastMCP("ScopeTest")

    @mcp.tool()
    def tapps_lookup_docs(library: str = "x") -> dict[str, Any]:
        return {"ok": library}

    @mcp.tool()
    def tapps_upgrade() -> dict[str, Any]:
        return {"ok": "upgraded"}

    install_runtime_scope_guard(mcp)
    return mcp


async def _list_tools(mcp: FastMCP) -> list[str]:
    handler = mcp._mcp_server.request_handlers[types.ListToolsRequest]
    result = await handler(types.ListToolsRequest(method="tools/list"))
    return [tool.name for tool in result.root.tools]


async def _call_tool(mcp: FastMCP, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    handler = mcp._mcp_server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    return (await handler(request)).root


@pytest.mark.asyncio
class TestRuntimeScopeGuard:
    async def test_unscoped_list_is_unfiltered(self) -> None:
        mcp = _guarded_server()
        assert sorted(await _list_tools(mcp)) == ["tapps_lookup_docs", "tapps_upgrade"]

    async def test_runtime_scope_filters_tools_list(self) -> None:
        mcp = _guarded_server()
        token = set_request_auth_scope("runtime")
        try:
            assert await _list_tools(mcp) == ["tapps_lookup_docs"]
        finally:
            reset_request_auth_scope(token)

    async def test_runtime_scope_refuses_non_allowlisted_call(self) -> None:
        mcp = _guarded_server()
        token = set_request_auth_scope("runtime")
        try:
            result = await _call_tool(mcp, "tapps_upgrade", {})
        finally:
            reset_request_auth_scope(token)

        assert result.isError is True
        text = "".join(block.text for block in result.content if block.type == "text")
        assert "tapps_upgrade" in text
        assert "not available to this credential" in text

    async def test_runtime_scope_allows_allowlisted_call(self) -> None:
        mcp = _guarded_server()
        token = set_request_auth_scope("runtime")
        try:
            result = await _call_tool(mcp, "tapps_lookup_docs", {"library": "fastapi"})
        finally:
            reset_request_auth_scope(token)

        assert result.isError is not True
        assert result.structuredContent == {"ok": "fastapi"}

    async def test_operator_scope_reaches_every_tool(self) -> None:
        mcp = _guarded_server()
        token = set_request_auth_scope("operator")
        try:
            result = await _call_tool(mcp, "tapps_upgrade", {})
        finally:
            reset_request_auth_scope(token)

        assert result.isError is not True

    async def test_guard_is_idempotent(self) -> None:
        mcp = _guarded_server()
        install_runtime_scope_guard(mcp)
        install_runtime_scope_guard(mcp)
        token = set_request_auth_scope("runtime")
        try:
            assert await _list_tools(mcp) == ["tapps_lookup_docs"]
        finally:
            reset_request_auth_scope(token)
