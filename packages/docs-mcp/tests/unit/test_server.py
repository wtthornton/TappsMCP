"""Tests for the DocsMCP server module."""

from __future__ import annotations


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
    def test_should_skip_dir_git(self) -> None:
        from docs_mcp.server import _should_skip_dir

        assert _should_skip_dir(".git") is True

    def test_should_skip_dir_node_modules(self) -> None:
        from docs_mcp.server import _should_skip_dir

        assert _should_skip_dir("node_modules") is True

    def test_should_skip_dir_egg_info(self) -> None:
        from docs_mcp.server import _should_skip_dir

        assert _should_skip_dir("my_package.egg-info") is True

    def test_should_not_skip_docs(self) -> None:
        from docs_mcp.server import _should_skip_dir

        assert _should_skip_dir("docs") is False

    def test_should_not_skip_src(self) -> None:
        from docs_mcp.server import _should_skip_dir

        assert _should_skip_dir("src") is False
