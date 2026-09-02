"""Scan tools refuse a workspace-free fleet request (TAP-6062, Story 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp import types
from mcp.server.fastmcp import FastMCP

import tapps_core.config.settings as settings_mod
from tapps_core.http.request_context import (
    PROJECT_ROOT_HEADER,
    WORKSPACE_FREE_ROOT,
    mark_http_request,
    reset_http_request,
    reset_request_project_root,
    set_request_project_root,
)
from tapps_mcp.http_fleet_scope import install_fleet_request_guards, workspace_refusal_for
from tapps_mcp.platform.nlt_profiles import WORKSPACE_REQUIRED_TOOLS
from tapps_mcp.server_helpers import workspace_free_refusal
from tapps_mcp.server_pipeline_tools import _session_start_cache_root


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    settings_mod._cached_settings = None
    yield
    settings_mod._cached_settings = None


class TestWorkspaceRequiredDeclaration:
    def test_the_two_scanners_need_a_tree(self) -> None:
        expected = {"tapps_security_scan", "tapps_dependency_scan"}
        assert set(WORKSPACE_REQUIRED_TOOLS) == expected

    def test_docs_and_research_tools_do_not(self) -> None:
        assert "tapps_lookup_docs" not in WORKSPACE_REQUIRED_TOOLS
        assert "tapps_research" not in WORKSPACE_REQUIRED_TOOLS


class TestWorkspaceFreeRefusalHelper:
    def test_stdio_never_refuses(self) -> None:
        assert workspace_free_refusal("tapps_security_scan") is None

    def test_scoped_request_never_refuses(self, tmp_path: Path) -> None:
        http_token = mark_http_request()
        root_token = set_request_project_root(tmp_path)
        try:
            assert workspace_free_refusal("tapps_security_scan") is None
        finally:
            reset_request_project_root(root_token)
            reset_http_request(http_token)

    def test_workspace_free_refusal_is_structured(self) -> None:
        token = mark_http_request()
        try:
            refusal = workspace_free_refusal("tapps_dependency_scan")
        finally:
            reset_http_request(token)

        assert refusal is not None
        assert refusal["success"] is False
        error = refusal["error"]
        assert error["code"] == "workspace_required"
        # Names the missing root rather than returning an empty scan.
        assert error["missing"] == PROJECT_ROOT_HEADER
        assert error["retryable"] is False
        assert PROJECT_ROOT_HEADER in error["remediation"]

    def test_tools_that_need_no_tree_are_never_refused(self) -> None:
        token = mark_http_request()
        try:
            assert workspace_refusal_for("tapps_lookup_docs") is None
            assert workspace_refusal_for("tapps_research") is None
            assert workspace_refusal_for("tapps_security_scan") is not None
        finally:
            reset_http_request(token)


def _guarded_server() -> tuple[FastMCP, list[str]]:
    """A server whose tool bodies record that they ran, so refusals are visible."""
    ran: list[str] = []
    mcp = FastMCP("WorkspaceGuardTest")

    @mcp.tool()
    def tapps_security_scan(file_path: str = "x.py") -> dict[str, Any]:
        ran.append("tapps_security_scan")
        return {"findings": []}

    @mcp.tool()
    def tapps_lookup_docs(library: str = "fastapi") -> dict[str, Any]:
        ran.append("tapps_lookup_docs")
        return {"docs": "..."}

    install_fleet_request_guards(mcp, runtime_scope=False)
    return mcp, ran


async def _call(mcp: FastMCP, name: str) -> types.CallToolResult:
    handler = mcp._mcp_server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments={}),
    )
    return (await handler(request)).root


@pytest.mark.asyncio
class TestWorkspaceGuard:
    async def test_scanner_refused_before_its_body_runs(self) -> None:
        mcp, ran = _guarded_server()
        token = mark_http_request()
        try:
            result = await _call(mcp, "tapps_security_scan")
        finally:
            reset_http_request(token)

        assert ran == []
        assert result.structuredContent is not None
        assert result.structuredContent["error"]["code"] == "workspace_required"

    async def test_docs_tool_runs_workspace_free(self) -> None:
        mcp, ran = _guarded_server()
        token = mark_http_request()
        try:
            result = await _call(mcp, "tapps_lookup_docs")
        finally:
            reset_http_request(token)

        assert ran == ["tapps_lookup_docs"]
        assert result.isError is not True

    async def test_scanner_runs_when_the_request_names_a_root(self, tmp_path: Path) -> None:
        mcp, ran = _guarded_server()
        http_token = mark_http_request()
        root_token = set_request_project_root(tmp_path)
        try:
            await _call(mcp, "tapps_security_scan")
        finally:
            reset_request_project_root(root_token)
            reset_http_request(http_token)

        assert ran == ["tapps_security_scan"]

    async def test_stdio_call_is_untouched(self) -> None:
        """No HTTP request in flight: the guard must not fire at all."""
        mcp, ran = _guarded_server()
        await _call(mcp, "tapps_security_scan")
        assert ran == ["tapps_security_scan"]


class TestSessionStartCacheRoot:
    def test_stdio_falls_back_to_cwd(self, tmp_path: Path, monkeypatch: Any) -> None:
        monkeypatch.delenv("TAPPS_MCP_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)

        assert _session_start_cache_root() == str(Path.cwd().resolve())

    def test_workspace_free_request_uses_the_sentinel_not_cwd(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))

        token = mark_http_request()
        try:
            root = _session_start_cache_root()
        finally:
            reset_http_request(token)

        assert root == str(WORKSPACE_FREE_ROOT.resolve())

    def test_scoped_request_uses_the_header_root(self, tmp_path: Path) -> None:
        http_token = mark_http_request()
        root_token = set_request_project_root(tmp_path)
        try:
            root = _session_start_cache_root()
        finally:
            reset_request_project_root(root_token)
            reset_http_request(http_token)

        assert root == str(tmp_path.resolve())
