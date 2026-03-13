"""Tests for Epic 79.2: server-side enabled_tools / disabled_tools / tool_preset."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestResolveAllowedTools:
    """Test _resolve_allowed_tools with various settings."""

    def test_default_all_tools(self) -> None:
        from docs_mcp.server import ALL_DOCS_TOOL_NAMES, _resolve_allowed_tools

        allowed = _resolve_allowed_tools(None, [], None)
        assert allowed == ALL_DOCS_TOOL_NAMES
        assert len(allowed) == 31

    def test_enabled_tools_subset(self) -> None:
        from docs_mcp.server import _resolve_allowed_tools

        allowed = _resolve_allowed_tools(
            ["docs_session_start", "docs_project_scan", "docs_check_links"],
            [],
            None,
        )
        assert allowed == frozenset({
            "docs_session_start",
            "docs_project_scan",
            "docs_check_links",
        })

    def test_disabled_tools_excludes_from_full(self) -> None:
        from docs_mcp.server import ALL_DOCS_TOOL_NAMES, _resolve_allowed_tools

        allowed = _resolve_allowed_tools(
            None,
            ["docs_generate_diagram", "docs_validate_epic"],
            None,
        )
        assert allowed == ALL_DOCS_TOOL_NAMES - frozenset({
            "docs_generate_diagram",
            "docs_validate_epic",
        })
        assert "docs_generate_diagram" not in allowed
        assert "docs_validate_epic" not in allowed

    def test_preset_core(self) -> None:
        from docs_mcp.server import DOCS_TOOL_PRESET_CORE, _resolve_allowed_tools

        allowed = _resolve_allowed_tools(None, [], "core")
        assert allowed == DOCS_TOOL_PRESET_CORE
        assert len(allowed) == 6

    def test_preset_full(self) -> None:
        from docs_mcp.server import ALL_DOCS_TOOL_NAMES, _resolve_allowed_tools

        allowed = _resolve_allowed_tools(None, [], "full")
        assert allowed == ALL_DOCS_TOOL_NAMES

    def test_enabled_tools_invalid_names_ignored(self) -> None:
        from docs_mcp.server import _resolve_allowed_tools

        allowed = _resolve_allowed_tools(
            ["docs_session_start", "not_a_tool", "docs_quick_check"],
            [],
            None,
        )
        assert allowed == frozenset({"docs_session_start"})
        assert "not_a_tool" not in allowed
        assert "docs_quick_check" not in allowed

    def test_disabled_applied_after_preset(self) -> None:
        from docs_mcp.server import DOCS_TOOL_PRESET_CORE, _resolve_allowed_tools

        allowed = _resolve_allowed_tools(None, ["docs_check_links"], "core")
        assert allowed == DOCS_TOOL_PRESET_CORE - frozenset({"docs_check_links"})
        assert "docs_check_links" not in allowed


class TestConditionalRegistration:
    """Test that register() only registers tools in allowed_tools."""

    def test_analysis_register_subset(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from docs_mcp import server_analysis

        mcp = FastMCP("test")
        allowed = frozenset({"docs_module_map"})
        server_analysis.register(mcp, allowed)
        names = list(mcp._tool_manager._tools.keys())
        assert names == ["docs_module_map"]

    def test_val_tools_register_subset(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from docs_mcp import server_val_tools

        mcp = FastMCP("test")
        allowed = frozenset({"docs_check_drift", "docs_check_links"})
        server_val_tools.register(mcp, allowed)
        names = sorted(mcp._tool_manager._tools.keys())
        assert names == ["docs_check_drift", "docs_check_links"]

    def test_core_tools_register_subset(self) -> None:
        from mcp.server.fastmcp import FastMCP

        from docs_mcp.server import _register_core_tools

        mcp = FastMCP("test")
        allowed = frozenset({"docs_session_start", "docs_config"})
        _register_core_tools(mcp, allowed)
        names = sorted(mcp._tool_manager._tools.keys())
        assert names == ["docs_config", "docs_session_start"]


class TestToolPresetConstants:
    """Validate preset definitions match story 79.2."""

    def test_core_has_six_tools(self) -> None:
        from docs_mcp.server import DOCS_TOOL_PRESET_CORE

        expected = {
            "docs_session_start",
            "docs_project_scan",
            "docs_check_drift",
            "docs_generate_readme",
            "docs_check_completeness",
            "docs_check_links",
        }
        assert DOCS_TOOL_PRESET_CORE == expected

    def test_all_tool_names_count(self) -> None:
        from docs_mcp.server import ALL_DOCS_TOOL_NAMES

        assert len(ALL_DOCS_TOOL_NAMES) == 31
