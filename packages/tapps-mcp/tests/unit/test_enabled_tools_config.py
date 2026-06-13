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
        # TAP-1994: tapps_memory removed from catalog; was 12, now 11
        assert len(allowed) == 11

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
        # TAP-1994: tapps_memory removed from catalog; was 6, now 5
        assert len(allowed) == 5

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
        # TAP-1994: tapps_memory removed from catalog; was 10, now 9
        assert len(allowed) == 9

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

    def test_preset_nlt_build(self) -> None:
        from tapps_mcp.server import TOOL_PROFILE_NLT_BUILD, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "nlt-build"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PROFILE_NLT_BUILD
        assert len(allowed) == 16
        assert "tapps_dependency_scan" in allowed

    def test_preset_nlt_memory(self) -> None:
        from tapps_mcp.server import TOOL_PROFILE_NLT_MEMORY, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "nlt-memory"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PROFILE_NLT_MEMORY
        assert "tapps_memory" in allowed
        assert "tapps_session_notes" in allowed

    def test_preset_nlt_setup(self) -> None:
        from tapps_mcp.server import TOOL_PROFILE_NLT_SETUP, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "nlt-setup"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PROFILE_NLT_SETUP
        assert len(allowed) == 7

    def test_preset_nlt_code_quality_alias(self) -> None:
        from tapps_mcp.server import TOOL_PROFILE_NLT_BUILD, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "nlt-code-quality"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PROFILE_NLT_BUILD

    def test_preset_nlt_platform_admin_alias(self) -> None:
        from tapps_mcp.server import TOOL_PROFILE_NLT_SETUP, _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "nlt-platform-admin"
        allowed = _resolve_allowed_tools(settings)
        assert allowed == TOOL_PROFILE_NLT_SETUP

    def test_nlt_profiles_disjoint(self) -> None:
        from tapps_mcp.server import (
            TOOL_PROFILE_NLT_BUILD,
            TOOL_PROFILE_NLT_MEMORY,
            TOOL_PROFILE_NLT_SETUP,
        )

        assert TOOL_PROFILE_NLT_BUILD.isdisjoint(TOOL_PROFILE_NLT_MEMORY)
        assert TOOL_PROFILE_NLT_BUILD.isdisjoint(TOOL_PROFILE_NLT_SETUP)
        assert TOOL_PROFILE_NLT_MEMORY.isdisjoint(TOOL_PROFILE_NLT_SETUP)


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
            "tapps_impact_analysis",
            "tapps_validate_config",
        }
        assert tier2 <= TOOL_PRESET_PIPELINE
        # TAP-1994: tapps_memory removed from catalog; was 12, now 11
        assert len(TOOL_PRESET_PIPELINE) == 11

    def test_all_tool_names_count(self) -> None:
        from tapps_mcp.server import ALL_TOOL_NAMES

        # 26 core + 3 linear-snapshot (TAP-964, shipped 3.3.0) + 1 release_update
        # + 1 tapps_linear_count (TAP-1847) + 1 tapps_audit_campaign (TAP-2036)
        # + 1 tapps_session_end (TAP-2005) + 1 tapps_usage (v3.11.0)
        # -1 tapps_memory (TAP-1994) + 2 hive elevation tools (TAP-2014)
        # + 1 tapps_linear_list_issues (TAP-2010) + 1 tapps_finding_to_story (TAP-2717)
        # + 1 tapps_audit_close_coverage (TAP-2798) + 1 tapps_handoff_save (TAP-3792) = 39.
        assert len(ALL_TOOL_NAMES) == 40
