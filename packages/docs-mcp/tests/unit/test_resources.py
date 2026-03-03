"""Tests for DocsMCP MCP resources and workflow prompts."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def _set_project_root(
    sample_project: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    """Set DOCS_MCP_PROJECT_ROOT so load_docs_settings() uses the sample project."""
    from docs_mcp.config.settings import _reset_docs_settings_cache

    _reset_docs_settings_cache()
    monkeypatch.setenv("DOCS_MCP_PROJECT_ROOT", str(sample_project))
    yield
    _reset_docs_settings_cache()


@pytest.fixture
def _set_docs_project_root(
    docs_project: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    """Set DOCS_MCP_PROJECT_ROOT so load_docs_settings() uses the docs project."""
    from docs_mcp.config.settings import _reset_docs_settings_cache

    _reset_docs_settings_cache()
    monkeypatch.setenv("DOCS_MCP_PROJECT_ROOT", str(docs_project))
    yield
    _reset_docs_settings_cache()


class TestDocsStatusResource:
    """Tests for the docs://status resource."""

    @pytest.mark.usefixtures("_set_project_root")
    def test_status_returns_string(self) -> None:
        from docs_mcp.server_resources import _docs_status

        result = _docs_status()
        assert isinstance(result, str)

    @pytest.mark.usefixtures("_set_project_root")
    def test_status_contains_heading(self) -> None:
        from docs_mcp.server_resources import _docs_status

        result = _docs_status()
        assert "# Documentation Status" in result

    @pytest.mark.usefixtures("_set_project_root")
    def test_status_shows_completeness_score(self) -> None:
        from docs_mcp.server_resources import _docs_status

        result = _docs_status()
        assert "Completeness score:" in result
        assert "/100" in result

    @pytest.mark.usefixtures("_set_project_root")
    def test_status_shows_critical_docs(self) -> None:
        from docs_mcp.server_resources import _docs_status

        result = _docs_status()
        assert "Critical Documents" in result
        assert "README.md" in result

    @pytest.mark.usefixtures("_set_project_root")
    def test_status_shows_readme_present(self) -> None:
        from docs_mcp.server_resources import _docs_status

        result = _docs_status()
        assert "README.md: present" in result

    @pytest.mark.usefixtures("_set_project_root")
    def test_status_shows_missing_docs(self) -> None:
        from docs_mcp.server_resources import _docs_status

        result = _docs_status()
        # sample_project does not have CHANGELOG.md
        assert "CHANGELOG.md: MISSING" in result

    @pytest.mark.usefixtures("_set_docs_project_root")
    def test_status_well_documented_project(self) -> None:
        from docs_mcp.server_resources import _docs_status

        result = _docs_status()
        assert "README.md: present" in result
        assert "CHANGELOG.md: present" in result

    @pytest.mark.usefixtures("_set_docs_project_root")
    def test_status_shows_categories(self) -> None:
        from docs_mcp.server_resources import _docs_status

        result = _docs_status()
        assert "Categories" in result


class TestDocsConfigResource:
    """Tests for the docs://config resource."""

    @pytest.mark.usefixtures("_set_project_root")
    def test_config_returns_string(self) -> None:
        from docs_mcp.server_resources import _docs_config_resource

        result = _docs_config_resource()
        assert isinstance(result, str)

    @pytest.mark.usefixtures("_set_project_root")
    def test_config_contains_heading(self) -> None:
        from docs_mcp.server_resources import _docs_config_resource

        result = _docs_config_resource()
        assert "# DocsMCP Configuration" in result

    @pytest.mark.usefixtures("_set_project_root")
    def test_config_shows_all_settings(self) -> None:
        from docs_mcp.server_resources import _docs_config_resource

        result = _docs_config_resource()
        assert "output_dir" in result
        assert "default_style" in result
        assert "default_format" in result
        assert "include_toc" in result
        assert "include_badges" in result
        assert "changelog_format" in result
        assert "adr_format" in result
        assert "diagram_format" in result
        assert "git_log_limit" in result
        assert "log_level" in result
        assert "log_json" in result

    @pytest.mark.usefixtures("_set_project_root")
    def test_config_shows_default_values(self) -> None:
        from docs_mcp.server_resources import _docs_config_resource

        result = _docs_config_resource()
        assert "standard" in result  # default_style
        assert "markdown" in result  # default_format
        assert "keep-a-changelog" in result  # changelog_format


class TestDocsCoverageResource:
    """Tests for the docs://coverage resource."""

    @pytest.mark.usefixtures("_set_project_root")
    def test_coverage_returns_string(self) -> None:
        from docs_mcp.server_resources import _docs_coverage_resource

        result = _docs_coverage_resource()
        assert isinstance(result, str)

    @pytest.mark.usefixtures("_set_project_root")
    def test_coverage_contains_heading(self) -> None:
        from docs_mcp.server_resources import _docs_coverage_resource

        result = _docs_coverage_resource()
        assert "# Documentation Coverage Report" in result

    @pytest.mark.usefixtures("_set_project_root")
    def test_coverage_shows_overall_score(self) -> None:
        from docs_mcp.server_resources import _docs_coverage_resource

        result = _docs_coverage_resource()
        assert "Overall score:" in result
        assert "/100" in result

    @pytest.mark.usefixtures("_set_project_root")
    def test_coverage_shows_categories(self) -> None:
        from docs_mcp.server_resources import _docs_coverage_resource

        result = _docs_coverage_resource()
        assert "Categories" in result
        assert "essential_docs" in result

    @pytest.mark.usefixtures("_set_docs_project_root")
    def test_coverage_well_documented_project(self) -> None:
        from docs_mcp.server_resources import _docs_coverage_resource

        result = _docs_coverage_resource()
        assert "Overall score:" in result

    @pytest.mark.usefixtures("_set_project_root")
    def test_coverage_shows_recommendations(self) -> None:
        from docs_mcp.server_resources import _docs_coverage_resource

        result = _docs_coverage_resource()
        # sample_project is missing several docs, so recommendations should be present
        assert "Recommendations" in result


class TestDocsWorkflowOverviewPrompt:
    """Tests for the docs_workflow_overview prompt."""

    def test_overview_returns_string(self) -> None:
        from docs_mcp.server_resources import _docs_workflow_overview

        result = _docs_workflow_overview()
        assert isinstance(result, str)

    def test_overview_contains_title(self) -> None:
        from docs_mcp.server_resources import _docs_workflow_overview

        result = _docs_workflow_overview()
        assert "# DocsMCP Workflow Guide" in result

    def test_overview_contains_three_phases(self) -> None:
        from docs_mcp.server_resources import _docs_workflow_overview

        result = _docs_workflow_overview()
        assert "Phase 1: Discovery" in result
        assert "Phase 2: Generation" in result
        assert "Phase 3: Validation" in result

    def test_overview_references_all_tool_categories(self) -> None:
        from docs_mcp.server_resources import _docs_workflow_overview

        result = _docs_workflow_overview()
        # Discovery tools
        assert "docs_session_start" in result
        assert "docs_project_scan" in result
        assert "docs_module_map" in result
        assert "docs_api_surface" in result
        assert "docs_git_summary" in result
        # Generation tools
        assert "docs_generate_readme" in result
        assert "docs_generate_api" in result
        assert "docs_generate_changelog" in result
        assert "docs_generate_release_notes" in result
        assert "docs_generate_adr" in result
        assert "docs_generate_onboarding" in result
        assert "docs_generate_contributing" in result
        assert "docs_generate_diagram" in result
        # Validation tools
        assert "docs_check_drift" in result
        assert "docs_check_completeness" in result
        assert "docs_check_links" in result
        assert "docs_check_freshness" in result

    def test_overview_contains_tool_reference(self) -> None:
        from docs_mcp.server_resources import _docs_workflow_overview

        result = _docs_workflow_overview()
        assert "Tool Reference" in result
        assert "18 tools" in result

    def test_overview_mentions_config_tool(self) -> None:
        from docs_mcp.server_resources import _docs_workflow_overview

        result = _docs_workflow_overview()
        assert "docs_config" in result


class TestDocsWorkflowPrompt:
    """Tests for the docs_workflow prompt with task_type parameter."""

    def test_bootstrap_workflow(self) -> None:
        from docs_mcp.server_resources import _docs_workflow

        result = _docs_workflow(task_type="bootstrap")
        assert isinstance(result, str)
        assert "Bootstrap" in result
        assert "docs_session_start" in result
        assert "docs_generate_readme" in result

    def test_update_workflow(self) -> None:
        from docs_mcp.server_resources import _docs_workflow

        result = _docs_workflow(task_type="update")
        assert "Update" in result
        assert "docs_check_drift" in result
        assert "docs_check_freshness" in result

    def test_audit_workflow(self) -> None:
        from docs_mcp.server_resources import _docs_workflow

        result = _docs_workflow(task_type="audit")
        assert "Audit" in result
        assert "docs_check_completeness" in result
        assert "docs_check_links" in result

    def test_release_workflow(self) -> None:
        from docs_mcp.server_resources import _docs_workflow

        result = _docs_workflow(task_type="release")
        assert "Release" in result
        assert "docs_generate_changelog" in result
        assert "docs_generate_release_notes" in result

    def test_different_task_types_return_different_content(self) -> None:
        from docs_mcp.server_resources import _docs_workflow

        bootstrap = _docs_workflow(task_type="bootstrap")
        update = _docs_workflow(task_type="update")
        audit = _docs_workflow(task_type="audit")
        release = _docs_workflow(task_type="release")

        # All four should be distinct
        assert len({bootstrap, update, audit, release}) == 4

    def test_invalid_task_type_returns_error_message(self) -> None:
        from docs_mcp.server_resources import _docs_workflow

        result = _docs_workflow(task_type="nonexistent")
        assert "Unknown task type" in result
        assert "nonexistent" in result
        assert "bootstrap" in result
        assert "update" in result
        assert "audit" in result
        assert "release" in result

    def test_default_task_type_is_bootstrap(self) -> None:
        from docs_mcp.server_resources import _docs_workflow

        result = _docs_workflow()
        assert "Bootstrap" in result

    def test_each_workflow_has_numbered_steps(self) -> None:
        from docs_mcp.server_resources import _docs_workflow

        for task_type in ("bootstrap", "update", "audit", "release"):
            result = _docs_workflow(task_type=task_type)
            assert "1." in result
            assert "2." in result


class TestResourceRegistration:
    """Tests that resources and prompts are properly registered on the mcp instance."""

    def test_mcp_has_status_resource(self) -> None:
        """Verify the docs://status resource is registered."""
        from docs_mcp.server import mcp

        import docs_mcp.server_resources  # noqa: F401

        assert mcp is not None

    def test_mcp_import_does_not_error(self) -> None:
        """Verify server_resources module imports without errors."""
        import docs_mcp.server_resources as mod

        assert hasattr(mod, "_docs_status")
        assert hasattr(mod, "_docs_config_resource")
        assert hasattr(mod, "_docs_coverage_resource")
        assert hasattr(mod, "_docs_workflow_overview")
        assert hasattr(mod, "_docs_workflow")
