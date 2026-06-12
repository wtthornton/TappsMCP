"""Tests for Epic 109.3: docs-mcp ``nlt-project-docs`` profile."""

from __future__ import annotations

from docs_mcp.server import (
    ALL_DOCS_TOOL_NAMES,
    DOCS_TOOL_PRESET_NLT_PROJECT_DOCS,
    _resolve_allowed_tools,
)

# Tools assigned to other NLT servers (must not appear on nlt-project-docs).
_LINEAR_DOCS_TOOLS = {
    "docs_generate_epic",
    "docs_generate_story",
    "docs_generate_prompt",
    "docs_validate_epic",
    "docs_lint_linear_issue",
    "docs_validate_linear_issue",
    "docs_save_linear_issue",
    "docs_linear_triage",
}

_RELEASE_DOCS_TOOLS = {
    "docs_generate_changelog",
    "docs_generate_release_notes",
    "docs_generate_release_update",
    "docs_validate_release_update",
    "docs_release_gate",
}


class TestNltProjectDocsProfile:
    def test_profile_has_twenty_seven_tools(self) -> None:
        assert len(DOCS_TOOL_PRESET_NLT_PROJECT_DOCS) == 27

    def test_resolve_allowed_tools_matches_preset(self) -> None:
        allowed = _resolve_allowed_tools(None, [], "nlt-project-docs")
        assert allowed == DOCS_TOOL_PRESET_NLT_PROJECT_DOCS

    def test_all_tools_exist_in_registry(self) -> None:
        assert DOCS_TOOL_PRESET_NLT_PROJECT_DOCS <= ALL_DOCS_TOOL_NAMES

    def test_excludes_planner_linear_tools(self) -> None:
        """Linear workflow tools live on nlt-linear-issues, not project-docs."""
        assert DOCS_TOOL_PRESET_NLT_PROJECT_DOCS.isdisjoint(_LINEAR_DOCS_TOOLS)

    def test_excludes_release_tools(self) -> None:
        assert DOCS_TOOL_PRESET_NLT_PROJECT_DOCS.isdisjoint(_RELEASE_DOCS_TOOLS)

    def test_includes_project_doc_eager_tools(self) -> None:
        eager = {
            "docs_session_start",
            "docs_project_scan",
            "docs_check_drift",
            "docs_generate_readme",
            "docs_check_completeness",
            "docs_check_links",
        }
        assert eager <= DOCS_TOOL_PRESET_NLT_PROJECT_DOCS
