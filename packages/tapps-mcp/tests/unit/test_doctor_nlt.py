"""Smoke tests for tapps_mcp.distribution.doctor_nlt (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_nlt import (
    _read_tool_budget,
    check_call_graph_index_cache,
    check_mcp_tool_budget,
    check_nlt_partial_enablement,
)


def test_read_tool_budget_defaults_when_no_yaml(tmp_path: Path) -> None:
    assert _read_tool_budget(tmp_path) == 20


def test_check_mcp_tool_budget_no_config_passes(tmp_path: Path) -> None:
    result = check_mcp_tool_budget(tmp_path)
    assert result.ok is True
    assert "No project MCP config" in result.message


def test_check_nlt_partial_enablement_no_servers_passes(tmp_path: Path) -> None:
    result = check_nlt_partial_enablement(tmp_path)
    assert result.ok is True
    assert "No nlt-* MCP servers" in result.message


def test_check_call_graph_index_cache_no_cache_passes(tmp_path: Path) -> None:
    result = check_call_graph_index_cache(tmp_path)
    assert result.ok is True
    assert "No cache yet" in result.message
