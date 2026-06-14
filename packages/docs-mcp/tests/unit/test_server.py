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


class TestExecutionMetrics:
    def test_success_response_writes_docs_metric_jsonl(self, tmp_path) -> None:
        from docs_mcp.config.settings import DocsMCPSettings
        from docs_mcp.server_helpers import (
            _reset_metrics_collector,
            _reset_settings_cache,
            success_response,
        )

        _reset_settings_cache()
        _reset_metrics_collector()
        import docs_mcp.server_helpers as sh

        sh._settings = DocsMCPSettings(project_root=tmp_path)

        success_response("docs_project_scan", 12, {"ok": True})

        jsonl_files = list((tmp_path / ".tapps-mcp" / "metrics").glob("tool_calls_*.jsonl"))
        assert len(jsonl_files) == 1
        line = jsonl_files[0].read_text(encoding="utf-8").strip()
        assert '"tool_name": "docs_project_scan"' in line
        assert '"status": "success"' in line

    def test_error_response_writes_failed_metric_when_timed(self, tmp_path) -> None:
        from docs_mcp.config.settings import DocsMCPSettings
        from docs_mcp.server_helpers import (
            _reset_metrics_collector,
            _reset_settings_cache,
            error_response,
        )

        _reset_settings_cache()
        _reset_metrics_collector()
        import docs_mcp.server_helpers as sh

        sh._settings = DocsMCPSettings(project_root=tmp_path)

        error_response("docs_config", "BAD", "nope", elapsed_ms=5)

        jsonl_files = list((tmp_path / ".tapps-mcp" / "metrics").glob("tool_calls_*.jsonl"))
        assert len(jsonl_files) == 1
        assert '"tool_name": "docs_config"' in jsonl_files[0].read_text(encoding="utf-8")
        assert '"status": "failed"' in jsonl_files[0].read_text(encoding="utf-8")


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
