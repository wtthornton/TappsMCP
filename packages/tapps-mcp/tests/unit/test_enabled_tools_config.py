"""Tests for Epic 79.1: server-side enabled_tools / disabled_tools / tool_preset."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestResolveAllowedTools:
    """Test _resolve_allowed_tools with various settings."""

    def test_default_all_tools(self) -> None:
        from tapps_mcp.server import ALL_TOOL_NAMES, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = None
        allowed = _resolve_allowed_tools(settings)
        assert allowed == ALL_TOOL_NAMES
        assert len(allowed) == len(ALL_TOOL_NAMES)

    def test_enabled_tools_subset(self) -> None:
        from tapps_mcp.server import _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = ["tapps_session_start", "tapps_quick_check", "tapps_checklist"]
        settings.disabled_tools = []
        settings.tool_preset = None
        allowed = _resolve_allowed_tools(settings)
        assert allowed == frozenset({"tapps_session_start", "tapps_quick_check", "tapps_checklist"})

    def test_disabled_tools_excludes_from_full(self) -> None:
        from tapps_mcp.server import ALL_TOOL_NAMES, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = ["tapps_doctor", "tapps_dashboard"]
        settings.tool_preset = None
        allowed = _resolve_allowed_tools(settings)
        assert allowed == ALL_TOOL_NAMES - frozenset({"tapps_doctor", "tapps_dashboard"})
        assert "tapps_doctor" not in allowed
        assert "tapps_dashboard" not in allowed

    def test_preset_core(self) -> None:
        from tapps_mcp.server import TOOL_PRESET_CORE, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "core"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PRESET_CORE
        assert len(allowed) == 8

    def test_preset_pipeline(self) -> None:
        from tapps_mcp.server import TOOL_PRESET_PIPELINE, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "pipeline"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PRESET_PIPELINE
        assert len(allowed) == 12

    def test_preset_full(self) -> None:
        from tapps_mcp.server import ALL_TOOL_NAMES, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "full"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == ALL_TOOL_NAMES

    def test_preset_reviewer(self) -> None:
        from tapps_mcp.server import TOOL_PRESET_REVIEWER, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "reviewer"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PRESET_REVIEWER
        assert len(allowed) == 9

    def test_preset_planner(self) -> None:
        from tapps_mcp.server import TOOL_PRESET_PLANNER, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "planner"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PRESET_PLANNER
        assert len(allowed) == 6

    def test_preset_frontend(self) -> None:
        from tapps_mcp.server import TOOL_PRESET_FRONTEND, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "frontend"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PRESET_FRONTEND
        assert len(allowed) == 5

    def test_preset_developer(self) -> None:
        from tapps_mcp.server import TOOL_PRESET_DEVELOPER, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "developer"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PRESET_DEVELOPER
        assert len(allowed) == 10

    def test_enabled_tools_invalid_names_ignored(self) -> None:
        from tapps_mcp.server import _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = ["tapps_session_start", "not_a_tool", "tapps_quick_check"]
        settings.disabled_tools = []
        settings.tool_preset = None
        allowed = _resolve_allowed_tools(settings)
        assert allowed == frozenset({"tapps_session_start", "tapps_quick_check"})
        assert "not_a_tool" not in allowed

    def test_disabled_applied_after_preset(self) -> None:
        from tapps_mcp.server import TOOL_PRESET_CORE, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = ["tapps_checklist"]
        settings.tool_preset = "core"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PRESET_CORE - frozenset({"tapps_checklist"})
        assert "tapps_checklist" not in allowed


class TestConditionalRegistration:
    """Test that register() only registers tools in allowed_tools."""

    def test_scoring_register_subset(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from tapps_mcp import server_scoring_tools

        mcp = FastMCP("test")
        allowed = frozenset({"tapps_quality_gate"})
        server_scoring_tools.register(mcp, allowed)
        names = list(mcp._tool_manager._tools.keys())
        assert names == ["tapps_quality_gate"]

    def test_pipeline_register_subset(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from tapps_mcp import server_pipeline_tools

        mcp = FastMCP("test")
        allowed = frozenset({"tapps_session_start", "tapps_validate_changed"})
        server_pipeline_tools.register(mcp, allowed)
        names = sorted(mcp._tool_manager._tools.keys())
        assert names == ["tapps_session_start", "tapps_validate_changed"]

    def test_core_tools_register_subset(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from tapps_mcp.server import _register_core_tools

        mcp = FastMCP("test")
        allowed = frozenset({"tapps_server_info", "tapps_checklist"})
        _register_core_tools(mcp, allowed)
        names = sorted(mcp._tool_manager._tools.keys())
        assert names == ["tapps_checklist", "tapps_server_info"]


class TestToolPresetConstants:
    """Validate preset definitions match TOOL-TIER-RANKING."""

    def test_core_has_seven_tier1_tools(self) -> None:
        from tapps_mcp.server import TOOL_PRESET_CORE

        expected = {
            "tapps_session_start",
            "tapps_quick_check",
            "tapps_validate_changed",
            "tapps_quality_gate",
            "tapps_checklist",
            "tapps_lookup_docs",
            "tapps_security_scan",
            "tapps_pipeline",
        }
        assert expected == TOOL_PRESET_CORE

    def test_pipeline_includes_core_and_tier2(self) -> None:
        from tapps_mcp.server import TOOL_PRESET_CORE, TOOL_PRESET_PIPELINE

        assert TOOL_PRESET_CORE <= TOOL_PRESET_PIPELINE
        tier2 = {
            "tapps_score_file",
            "tapps_memory",
            "tapps_impact_analysis",
            "tapps_validate_config",
        }
        assert tier2 <= TOOL_PRESET_PIPELINE
        assert len(TOOL_PRESET_PIPELINE) == 12

    def test_all_tool_names_count(self) -> None:
        from tapps_mcp.server import ALL_TOOL_NAMES

        # 26 core + 3 linear-snapshot (TAP-964, shipped 3.3.0) + 1 release_update
        # + 1 tapps_linear_count (TAP-1847) = 31.
        assert len(ALL_TOOL_NAMES) == 31
