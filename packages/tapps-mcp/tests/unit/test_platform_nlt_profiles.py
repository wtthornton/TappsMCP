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
    TOOL_PROFILE_NLT_CODE_QUALITY,
    TOOL_PROFILE_NLT_PLATFORM_ADMIN,
)

pytestmark = pytest.mark.skipif(
    not _DOCS_MCP_AVAILABLE,
    reason="docs-mcp required for cross-package NLT profiles",
)


class TestPlatformNltProfileDefinitions:
    def test_linear_issues_has_fifteen_tools(self) -> None:
        assert len(TOOL_PROFILE_NLT_LINEAR_ISSUES) == 15

    def test_release_ship_has_seven_tools(self) -> None:
        assert len(TOOL_PROFILE_NLT_RELEASE_SHIP) == 7

    def test_all_tapps_tools_exist(self) -> None:
        tapps_names = {n for n in TOOL_PROFILE_NLT_LINEAR_ISSUES if n.startswith("tapps_")}
        tapps_names |= {n for n in TOOL_PROFILE_NLT_RELEASE_SHIP if n.startswith("tapps_")}
        assert tapps_names <= ALL_TOOL_NAMES

    def test_all_docs_tools_exist(self) -> None:
        from docs_mcp.server import ALL_DOCS_TOOL_NAMES

        docs_names = {n for n in TOOL_PROFILE_NLT_LINEAR_ISSUES if n.startswith("docs_")}
        docs_names |= {n for n in TOOL_PROFILE_NLT_RELEASE_SHIP if n.startswith("docs_")}
        assert docs_names <= ALL_DOCS_TOOL_NAMES

    def test_profiles_disjoint_from_code_quality_and_admin(self) -> None:
        other = TOOL_PROFILE_NLT_CODE_QUALITY | TOOL_PROFILE_NLT_PLATFORM_ADMIN
        assert TOOL_PROFILE_NLT_LINEAR_ISSUES.isdisjoint(other)
        assert TOOL_PROFILE_NLT_RELEASE_SHIP.isdisjoint(other)

    def test_linear_and_release_disjoint(self) -> None:
        assert TOOL_PROFILE_NLT_LINEAR_ISSUES.isdisjoint(TOOL_PROFILE_NLT_RELEASE_SHIP)

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tapps-platform profile"):
            resolve_platform_allowed_tools("nlt-code-quality")


class TestCreateCombinedServerProfiles:
    def test_linear_issues_registers_fifteen_tools(self) -> None:
        combined = create_combined_server(profile="nlt-linear-issues")
        names = set(combined._tool_manager._tools.keys())
        assert names == set(TOOL_PROFILE_NLT_LINEAR_ISSUES)
        assert len(names) == 15

    def test_release_ship_registers_seven_tools(self) -> None:
        combined = create_combined_server(profile="nlt-release-ship")
        names = set(combined._tool_manager._tools.keys())
        assert names == set(TOOL_PROFILE_NLT_RELEASE_SHIP)
        assert len(names) == 7

    def test_full_mode_registers_more_than_nlt_profiles(self) -> None:
        combined = create_combined_server(profile=None)
        assert len(combined._tool_manager._tools) > len(TOOL_PROFILE_NLT_LINEAR_ISSUES)

    def test_platform_profiles_match_yaml_keys(self) -> None:
        assert set(PLATFORM_NLT_PROFILES) == {"nlt-linear-issues", "nlt-release-ship"}
