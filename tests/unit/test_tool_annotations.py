"""Tests for MCP tool annotations (Story 12.1).

Verifies that all 21 registered tools have correct ToolAnnotations set,
ensuring MCP clients can auto-approve read-only tools and skip destructive
action warnings.
"""

from __future__ import annotations

import pytest
from mcp.types import ToolAnnotations

from tapps_mcp.server import mcp

# ---------------------------------------------------------------------------
# Expected annotations per tool
# ---------------------------------------------------------------------------

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_READ_ONLY_OPEN = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

_SIDE_EFFECT_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_SIDE_EFFECT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

EXPECTED_ANNOTATIONS: dict[str, ToolAnnotations] = {
    # Read-only, idempotent, closed-world (16 tools)
    "tapps_server_info": _READ_ONLY,
    "tapps_security_scan": _READ_ONLY,
    "tapps_score_file": _READ_ONLY,
    "tapps_quality_gate": _READ_ONLY,
    "tapps_quick_check": _READ_ONLY,
    "tapps_validate_changed": _READ_ONLY,
    "tapps_validate_config": _READ_ONLY,
    "tapps_consult_expert": _READ_ONLY,
    "tapps_list_experts": _READ_ONLY,
    "tapps_checklist": _READ_ONLY,
    "tapps_project_profile": _READ_ONLY,
    "tapps_session_notes": _READ_ONLY,
    "tapps_impact_analysis": _READ_ONLY,
    "tapps_report": _READ_ONLY,
    "tapps_dashboard": _READ_ONLY,
    "tapps_stats": _READ_ONLY,
    # Read-only, open-world (2 tools)
    "tapps_lookup_docs": _READ_ONLY_OPEN,
    "tapps_research": _READ_ONLY_OPEN,
    # Side-effect, idempotent (2 tools)
    "tapps_session_start": _SIDE_EFFECT_IDEMPOTENT,
    "tapps_init": _SIDE_EFFECT_IDEMPOTENT,
    # Side-effect, non-idempotent (1 tool)
    "tapps_feedback": _SIDE_EFFECT,
}


class TestToolAnnotationsPresent:
    """Every registered tool must have annotations set (not None)."""

    def test_all_21_tools_registered(self) -> None:
        tools = mcp._tool_manager._tools
        assert len(tools) == 21, f"Expected 21 tools, got {len(tools)}: {sorted(tools)}"

    def test_all_tools_have_annotations(self) -> None:
        tools = mcp._tool_manager._tools
        missing = [name for name, tool in tools.items() if tool.annotations is None]
        assert not missing, f"Tools missing annotations: {missing}"

    def test_no_tools_marked_destructive(self) -> None:
        tools = mcp._tool_manager._tools
        destructive = [
            name
            for name, tool in tools.items()
            if tool.annotations and tool.annotations.destructiveHint
        ]
        assert not destructive, f"Tools incorrectly marked destructive: {destructive}"


class TestToolAnnotationValues:
    """Each tool's annotations must match the expected category."""

    @pytest.mark.parametrize("tool_name", sorted(EXPECTED_ANNOTATIONS))
    def test_annotation_matches(self, tool_name: str) -> None:
        tools = mcp._tool_manager._tools
        assert tool_name in tools, f"Tool {tool_name} not registered"
        actual = tools[tool_name].annotations
        expected = EXPECTED_ANNOTATIONS[tool_name]
        assert actual is not None, f"{tool_name} has no annotations"
        assert actual.readOnlyHint == expected.readOnlyHint, (
            f"{tool_name}: readOnlyHint={actual.readOnlyHint}, expected={expected.readOnlyHint}"
        )
        assert actual.destructiveHint == expected.destructiveHint, (
            f"{tool_name}: destructiveHint={actual.destructiveHint}, "
            f"expected={expected.destructiveHint}"
        )
        assert actual.idempotentHint == expected.idempotentHint, (
            f"{tool_name}: idempotentHint={actual.idempotentHint}, "
            f"expected={expected.idempotentHint}"
        )
        assert actual.openWorldHint == expected.openWorldHint, (
            f"{tool_name}: openWorldHint={actual.openWorldHint}, "
            f"expected={expected.openWorldHint}"
        )


class TestAnnotationCategories:
    """Verify the expected distribution of annotation categories."""

    def test_read_only_count(self) -> None:
        tools = mcp._tool_manager._tools
        read_only = [
            name
            for name, tool in tools.items()
            if tool.annotations and tool.annotations.readOnlyHint
        ]
        assert len(read_only) == 18, f"Expected 18 read-only tools, got {len(read_only)}"

    def test_side_effect_count(self) -> None:
        tools = mcp._tool_manager._tools
        side_effect = [
            name
            for name, tool in tools.items()
            if tool.annotations and not tool.annotations.readOnlyHint
        ]
        assert len(side_effect) == 3, f"Expected 3 side-effect tools, got {len(side_effect)}"

    def test_open_world_count(self) -> None:
        tools = mcp._tool_manager._tools
        open_world = [
            name
            for name, tool in tools.items()
            if tool.annotations and tool.annotations.openWorldHint
        ]
        assert len(open_world) == 2, f"Expected 2 open-world tools, got {len(open_world)}"

    def test_idempotent_count(self) -> None:
        tools = mcp._tool_manager._tools
        idempotent = [
            name
            for name, tool in tools.items()
            if tool.annotations and tool.annotations.idempotentHint
        ]
        assert len(idempotent) == 18, f"Expected 18 idempotent tools, got {len(idempotent)}"
