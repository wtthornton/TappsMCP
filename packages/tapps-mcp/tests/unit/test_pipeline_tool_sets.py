"""Tests for shared pipeline tool sets (TAP-3922)."""

from __future__ import annotations

from tapps_mcp.tools.pipeline_tool_sets import (
    GATE_SHORT_NAMES,
    is_gate_tool,
    matches_pipeline_tool,
)


class TestPipelineToolSets:
    def test_matches_bare_gate_tool(self) -> None:
        assert is_gate_tool("tapps_quick_check")

    def test_matches_nlt_build_mcp_prefix(self) -> None:
        assert is_gate_tool("mcp__nlt-build__tapps_quick_check")

    def test_matches_legacy_code_quality_prefix(self) -> None:
        assert is_gate_tool("mcp__nlt-code-quality__tapps_validate_changed")

    def test_matches_project_scoped_cursor_server(self) -> None:
        assert is_gate_tool(
            "mcp__project-0-tapps-mcp-nlt-code-quality__tapps_quality_gate"
        )

    def test_rejects_unrelated_tool(self) -> None:
        assert not matches_pipeline_tool("Read", GATE_SHORT_NAMES)
