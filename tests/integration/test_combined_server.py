"""Integration tests for combined TappsPlatform server (Epic 12.3 + 12.4).

Story 12.3: Namespace collision testing -- verifies no tool/resource/prompt
name collisions between TappsMCP and DocsMCP when composed.

Story 12.4: Shared singleton verification -- confirms both servers share
the same tapps-core singletons and graceful degradation works.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from docs_mcp.server import mcp as docs_server
from tapps_mcp.platform.combined_server import create_combined_server
from tapps_mcp.server import mcp as tapps_server

# ---------------------------------------------------------------------------
# Expected tool sets (authoritative lists)
# ---------------------------------------------------------------------------

EXPECTED_TAPPS_TOOLS: set[str] = {
    "tapps_server_info",
    "tapps_session_start",
    "tapps_score_file",
    "tapps_quality_gate",
    "tapps_quick_check",
    "tapps_security_scan",
    "tapps_lookup_docs",
    "tapps_validate_config",
    "tapps_consult_expert",
    "tapps_checklist",
    "tapps_validate_changed",
    "tapps_init",
    "tapps_set_engagement_level",
    "tapps_upgrade",
    "tapps_doctor",
    "tapps_dashboard",
    "tapps_stats",
    "tapps_feedback",
    "tapps_research",
    "tapps_memory",
    "tapps_session_notes",
    "tapps_impact_analysis",
    "tapps_report",
    "tapps_dead_code",
    "tapps_dependency_scan",
    "tapps_dependency_graph",
}

EXPECTED_DOCS_TOOLS: set[str] = {
    "docs_session_start",
    "docs_project_scan",
    "docs_config",
    "docs_module_map",
    "docs_api_surface",
    "docs_git_summary",
    "docs_generate_readme",
    "docs_generate_api",
    "docs_generate_changelog",
    "docs_generate_release_notes",
    "docs_generate_diagram",
    "docs_check_drift",
    "docs_check_completeness",
    "docs_check_links",
    "docs_check_freshness",
    "docs_generate_adr",
    "docs_generate_onboarding",
    "docs_generate_contributing",
    "docs_generate_prd",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tapps_tool_names() -> set[str]:
    """Return all tool names registered on TappsMCP."""
    return set(tapps_server._tool_manager._tools.keys())


@pytest.fixture()
def docs_tool_names() -> set[str]:
    """Return all tool names registered on DocsMCP."""
    return set(docs_server._tool_manager._tools.keys())


@pytest.fixture()
def combined():
    """Create a combined server instance."""
    return create_combined_server()


# ===========================================================================
# Story 12.3: Namespace Collision Testing
# ===========================================================================


@pytest.mark.integration
class TestNoToolNameCollisions:
    """Verify TappsMCP and DocsMCP tool names are disjoint."""

    def test_no_tool_name_collisions(
        self,
        tapps_tool_names: set[str],
        docs_tool_names: set[str],
    ) -> None:
        """TappsMCP and DocsMCP must have zero overlapping tool names."""
        overlap = tapps_tool_names & docs_tool_names
        assert overlap == set(), f"Tool name collision: {overlap}"

    def test_tapps_tools_have_prefix(self, tapps_tool_names: set[str]) -> None:
        """All TappsMCP tools must use the tapps_ prefix."""
        for name in tapps_tool_names:
            assert name.startswith("tapps_"), f"TappsMCP tool missing prefix: {name}"

    def test_docs_tools_have_prefix(self, docs_tool_names: set[str]) -> None:
        """All DocsMCP tools must use the docs_ prefix."""
        for name in docs_tool_names:
            assert name.startswith("docs_"), f"DocsMCP tool missing prefix: {name}"


@pytest.mark.integration
class TestAllTappsToolsRegistered:
    """Verify every expected TappsMCP tool is present in the combined server."""

    def test_all_expected_tapps_tools_present(self, combined) -> None:
        """Combined server contains all expected TappsMCP tools."""
        combined_names = set(combined._tool_manager._tools.keys())
        missing = EXPECTED_TAPPS_TOOLS - combined_names
        assert missing == set(), f"Missing TappsMCP tools: {missing}"

    def test_tapps_tool_count(self, tapps_tool_names: set[str]) -> None:
        """TappsMCP registers at least 26 tools."""
        assert len(tapps_tool_names) >= len(EXPECTED_TAPPS_TOOLS), (
            f"Expected >= {len(EXPECTED_TAPPS_TOOLS)} tapps tools, got {len(tapps_tool_names)}"
        )

    def test_no_unexpected_tapps_tools_missing(
        self,
        tapps_tool_names: set[str],
    ) -> None:
        """Every tool from the expected list is registered on the standalone server."""
        missing = EXPECTED_TAPPS_TOOLS - tapps_tool_names
        assert missing == set(), f"Expected tools not on standalone server: {missing}"


@pytest.mark.integration
class TestAllDocsToolsRegistered:
    """Verify every expected DocsMCP tool is present in the combined server."""

    def test_all_expected_docs_tools_present(self, combined) -> None:
        """Combined server contains all 19 expected DocsMCP tools."""
        combined_names = set(combined._tool_manager._tools.keys())
        missing = EXPECTED_DOCS_TOOLS - combined_names
        assert missing == set(), f"Missing DocsMCP tools: {missing}"

    def test_docs_tool_count(self, docs_tool_names: set[str]) -> None:
        """DocsMCP registers at least 19 tools."""
        assert len(docs_tool_names) >= len(EXPECTED_DOCS_TOOLS), (
            f"Expected >= {len(EXPECTED_DOCS_TOOLS)} docs tools, got {len(docs_tool_names)}"
        )

    def test_no_unexpected_docs_tools_missing(
        self,
        docs_tool_names: set[str],
    ) -> None:
        """Every tool from the expected list is registered on the standalone server."""
        missing = EXPECTED_DOCS_TOOLS - docs_tool_names
        assert missing == set(), f"Expected tools not on standalone server: {missing}"


@pytest.mark.integration
class TestResourcesNoCollision:
    """Verify resources from both servers don't collide (tapps:// vs docs://)."""

    def test_tapps_resources_use_tapps_uri(self) -> None:
        """All TappsMCP resources use the tapps:// URI scheme."""
        for uri in tapps_server._resource_manager._resources:
            assert str(uri).startswith("tapps://"), f"TappsMCP resource with unexpected URI: {uri}"

    def test_docs_resources_use_docs_uri(self) -> None:
        """All DocsMCP resources use the docs:// URI scheme."""
        for uri in docs_server._resource_manager._resources:
            assert str(uri).startswith("docs://"), f"DocsMCP resource with unexpected URI: {uri}"

    def test_no_resource_uri_collisions(self) -> None:
        """Resource URIs from both servers must be disjoint."""
        tapps_uris = set(tapps_server._resource_manager._resources.keys())
        docs_uris = set(docs_server._resource_manager._resources.keys())
        overlap = tapps_uris & docs_uris
        assert overlap == set(), f"Resource URI collision: {overlap}"

    def test_combined_has_all_resources(self, combined) -> None:
        """Combined server contains all resources from both servers."""
        tapps_uris = set(tapps_server._resource_manager._resources.keys())
        docs_uris = set(docs_server._resource_manager._resources.keys())
        combined_uris = set(combined._resource_manager._resources.keys())
        expected = tapps_uris | docs_uris
        assert combined_uris == expected


@pytest.mark.integration
class TestPromptsNoCollision:
    """Verify prompts from both servers don't collide."""

    def test_no_prompt_name_collisions(self) -> None:
        """Prompt names from TappsMCP and DocsMCP must be disjoint."""
        tapps_prompts = set(tapps_server._prompt_manager._prompts.keys())
        docs_prompts = set(docs_server._prompt_manager._prompts.keys())
        overlap = tapps_prompts & docs_prompts
        assert overlap == set(), f"Prompt name collision: {overlap}"

    def test_combined_has_all_prompts(self, combined) -> None:
        """Combined server contains all prompts from both servers."""
        tapps_prompts = set(tapps_server._prompt_manager._prompts.keys())
        docs_prompts = set(docs_server._prompt_manager._prompts.keys())
        combined_prompts = set(combined._prompt_manager._prompts.keys())
        expected = tapps_prompts | docs_prompts
        assert combined_prompts == expected


# ===========================================================================
# Story 12.4: Shared Singleton Verification
# ===========================================================================


@pytest.mark.integration
class TestSettingsSingletonShared:
    """Both servers must share the same settings singleton from tapps-core."""

    def test_settings_singleton_identity(self) -> None:
        """load_settings() returns the same object from core and mcp import paths."""
        from tapps_core.config.settings import load_settings as core_load
        from tapps_mcp.config.settings import load_settings as mcp_load

        assert core_load() is mcp_load()

    def test_settings_function_identity(self) -> None:
        """The load_settings function itself is the same object via re-export."""
        from tapps_core.config.settings import load_settings as core_fn
        from tapps_mcp.config.settings import load_settings as mcp_fn

        assert core_fn is mcp_fn

    def test_cross_server_project_root_matches(self) -> None:
        """TappsMCP and DocsMCP resolve to the same project root."""
        from docs_mcp.server_helpers import _get_settings as docs_get
        from tapps_core.config.settings import load_settings

        core_settings = load_settings()
        docs_settings = docs_get()
        assert str(docs_settings.project_root) == str(core_settings.project_root)


@pytest.mark.integration
class TestCombinedToolCount:
    """Verify total tool count equals tapps + docs (no tools lost)."""

    def test_combined_tool_count_equals_sum(
        self,
        combined,
        tapps_tool_names: set[str],
        docs_tool_names: set[str],
    ) -> None:
        """Combined count must equal tapps + docs (nothing lost in merge)."""
        expected = len(tapps_tool_names) + len(docs_tool_names)
        total = len(combined._tool_manager._tools)
        assert total == expected, f"Expected {expected} tools, got {total}"

    def test_combined_has_all_tools(
        self,
        combined,
        tapps_tool_names: set[str],
        docs_tool_names: set[str],
    ) -> None:
        """Combined tool set is the exact union of both servers."""
        combined_names = set(combined._tool_manager._tools.keys())
        expected = tapps_tool_names | docs_tool_names
        assert combined_names == expected


@pytest.mark.integration
class TestGracefulDegradationWithoutDocsMCP:
    """When docs_mcp is unavailable, combined server falls back to tapps-only."""

    def test_combined_works_without_docs_mcp(self) -> None:
        """If docs_mcp is unavailable, create_combined_server returns tapps-only."""
        with (
            patch(
                "tapps_mcp.platform.combined_server._DOCS_MCP_AVAILABLE",
                False,
            ),
            patch(
                "tapps_mcp.platform.combined_server.docs_server",
                None,
            ),
        ):
            combined = create_combined_server()

        # Should have all tapps tools
        combined_names = set(combined._tool_manager._tools.keys())
        assert combined_names >= EXPECTED_TAPPS_TOOLS

        # Should have zero docs tools
        docs_in_combined = {n for n in combined_names if n.startswith("docs_")}
        assert docs_in_combined == set()

    def test_tapps_tools_independent_of_docs(self) -> None:
        """TappsMCP tool registration is not affected by DocsMCP presence."""
        tapps_names = set(tapps_server._tool_manager._tools.keys())
        assert tapps_names >= EXPECTED_TAPPS_TOOLS


# ===========================================================================
# Tool behavior parity (composition preserves metadata)
# ===========================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_metadata_preserved(combined) -> None:
    """Tool descriptions and parameters survive composition."""
    combined_tools = {t.name: t for t in await combined.list_tools()}
    tapps_tools = {t.name: t for t in await tapps_server.list_tools()}
    docs_tools = {t.name: t for t in await docs_server.list_tools()}

    # TappsMCP tool
    assert combined_tools["tapps_server_info"].description == (
        tapps_tools["tapps_server_info"].description
    )

    # DocsMCP tool
    assert combined_tools["docs_project_scan"].description == (
        docs_tools["docs_project_scan"].description
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_schemas_preserved(combined) -> None:
    """Input schemas are identical between standalone and combined."""
    combined_tools = {t.name: t for t in await combined.list_tools()}
    tapps_tools = {t.name: t for t in await tapps_server.list_tools()}

    assert (
        tapps_tools["tapps_score_file"].inputSchema
        == combined_tools["tapps_score_file"].inputSchema
    )


@pytest.mark.integration
def test_combined_server_name(combined) -> None:
    """Combined server is named TappsPlatform."""
    assert combined.name == "TappsPlatform"
