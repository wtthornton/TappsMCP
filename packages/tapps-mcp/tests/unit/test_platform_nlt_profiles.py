"""Tests for tapps-platform NLT cross-package profiles (Epic 109.2)."""

from __future__ import annotations

import pytest

from tapps_mcp.platform.combined_server import _DOCS_MCP_AVAILABLE, create_combined_server
from tapps_mcp.platform.nlt_profiles import (
    PLATFORM_NLT_PROFILES,
    TOOL_PROFILE_NLT_LINEAR_ISSUES,
    TOOL_PROFILE_NLT_RELEASE_SHIP,
    resolve_platform_allowed_tools,
)
from tapps_mcp.server import (
    ALL_TOOL_NAMES,
    TOOL_PROFILE_NLT_BUILD,
    TOOL_PROFILE_NLT_MEMORY,
    TOOL_PROFILE_NLT_SETUP,
)

pytestmark = pytest.mark.skipif(
    not _DOCS_MCP_AVAILABLE,
    reason="docs-mcp required for cross-package NLT profiles",
)


class TestPlatformNltProfileDefinitions:
    def test_linear_issues_has_fifteen_tools(self) -> None:
        assert len(TOOL_PROFILE_NLT_LINEAR_ISSUES) == 15

    def test_release_ship_has_six_tools(self) -> None:
        assert len(TOOL_PROFILE_NLT_RELEASE_SHIP) == 6

    def test_all_tapps_tools_exist(self) -> None:
        tapps_names = {n for n in TOOL_PROFILE_NLT_LINEAR_ISSUES if n.startswith("tapps_")}
        tapps_names |= {n for n in TOOL_PROFILE_NLT_RELEASE_SHIP if n.startswith("tapps_")}
        assert tapps_names <= ALL_TOOL_NAMES

    def test_all_docs_tools_exist(self) -> None:
        from docs_mcp.server import ALL_DOCS_TOOL_NAMES

        docs_names = {n for n in TOOL_PROFILE_NLT_LINEAR_ISSUES if n.startswith("docs_")}
        docs_names |= {n for n in TOOL_PROFILE_NLT_RELEASE_SHIP if n.startswith("docs_")}
        assert docs_names <= ALL_DOCS_TOOL_NAMES

    def test_profiles_disjoint_from_build_memory_setup(self) -> None:
        tapps = TOOL_PROFILE_NLT_BUILD | TOOL_PROFILE_NLT_MEMORY | TOOL_PROFILE_NLT_SETUP
        assert TOOL_PROFILE_NLT_LINEAR_ISSUES.isdisjoint(tapps)
        assert TOOL_PROFILE_NLT_RELEASE_SHIP.isdisjoint(tapps)

    def test_linear_and_release_disjoint(self) -> None:
        assert TOOL_PROFILE_NLT_LINEAR_ISSUES.isdisjoint(TOOL_PROFILE_NLT_RELEASE_SHIP)

    def test_session_start_registered_on_exactly_one_profile(self) -> None:
        # TAP-7018: tapps_session_start used to be duplicated across all
        # three NLT presets. nlt-memory is the single owner (every fleet
        # consumer calls it there); nlt-build and nlt-setup resolve the
        # name via a pointer stub registered in
        # server_pipeline_tools.register() instead of their own frozenset
        # entry (see test_server_pipeline_tools.py for the pointer test).
        assert "tapps_session_start" not in TOOL_PROFILE_NLT_BUILD
        assert "tapps_session_start" in TOOL_PROFILE_NLT_MEMORY
        assert "tapps_session_start" not in TOOL_PROFILE_NLT_SETUP

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tapps-platform profile"):
            resolve_platform_allowed_tools("nlt-build")


class TestCreateCombinedServerProfiles:
    def test_linear_issues_registers_fifteen_tools(self) -> None:
        combined = create_combined_server(profile="nlt-linear-issues")
        names = set(combined._tool_manager._tools.keys())
        assert names == set(TOOL_PROFILE_NLT_LINEAR_ISSUES)
        assert len(names) == 15

    def test_release_ship_registers_six_tools(self) -> None:
        combined = create_combined_server(profile="nlt-release-ship")
        names = set(combined._tool_manager._tools.keys())
        assert names == set(TOOL_PROFILE_NLT_RELEASE_SHIP)
        assert len(names) == 6

    def test_nlt_profiles_have_no_prompts_or_resources(self) -> None:
        """Prompts/resources stay on nlt-build / nlt-project-docs — not hitchhikers."""
        for profile in ("nlt-linear-issues", "nlt-release-ship"):
            combined = create_combined_server(profile=profile)
            assert combined._prompt_manager._prompts == {}
            assert combined._resource_manager._resources == {}

    def test_full_mode_still_copies_prompts_and_resources(self) -> None:
        combined = create_combined_server(profile=None)
        assert len(combined._tool_manager._tools) > len(TOOL_PROFILE_NLT_LINEAR_ISSUES)
        assert len(combined._prompt_manager._prompts) > 0
        assert len(combined._resource_manager._resources) > 0

    def test_platform_profiles_match_yaml_keys(self) -> None:
        assert set(PLATFORM_NLT_PROFILES) == {"nlt-linear-issues", "nlt-release-ship"}
