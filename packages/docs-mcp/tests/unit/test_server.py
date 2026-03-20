"""Tests for the DocsMCP server module."""

from __future__ import annotations

import pytest


class TestMCPInstance:
    def test_mcp_instance_exists(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from docs_mcp.server import mcp

        assert isinstance(mcp, FastMCP)

    def test_server_name(self) -> None:
        from docs_mcp.server import mcp

        assert mcp.name == "DocsMCP"

    def test_run_server_callable(self) -> None:
        from docs_mcp.server import run_server

        assert callable(run_server)


class TestToolCallTracking:
    def test_record_call_increments(self) -> None:
        from docs_mcp.server import _record_call, _reset_tool_calls, _tool_calls

        _reset_tool_calls()
        _record_call("test_tool")
        assert _tool_calls["test_tool"] == 1

        _record_call("test_tool")
        assert _tool_calls["test_tool"] == 2

    def test_reset_tool_calls_clears(self) -> None:
        from docs_mcp.server import _record_call, _reset_tool_calls, _tool_calls

        _record_call("some_tool")
        assert len(_tool_calls) > 0

        _reset_tool_calls()
        assert len(_tool_calls) == 0


class TestHelperFunctions:
    @pytest.mark.parametrize(
        "dirname,expected",
        [
            (".git", True),
            ("node_modules", True),
            ("my_package.egg-info", True),
            ("docs", False),
            ("src", False),
        ],
        ids=["git", "node_modules", "egg-info", "docs", "src"],
    )
    def test_should_skip_dir(self, dirname: str, expected: bool) -> None:
        from docs_mcp.server import _should_skip_dir

        assert _should_skip_dir(dirname) is expected
