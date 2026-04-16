"""Tests for MCP resources and the tapps_workflow prompt."""

from __future__ import annotations

import pytest

from tapps_mcp.server_resources import (
    _get_quality_presets as get_quality_presets,
)
from tapps_mcp.server_resources import (
    _get_scoring_weights as get_scoring_weights,
)
from tapps_mcp.server_resources import (
    _tapps_workflow as tapps_workflow,
)

# Note: TestGetKnowledgeResource and TestListKnowledgeDomains were removed
# when the get_knowledge_resource / list_knowledge_domains functions were
# removed from server_resources. The test classes have been deleted entirely.


# ---------------------------------------------------------------------------
# Quality presets resource
# ---------------------------------------------------------------------------


class TestGetQualityPresets:
    def test_returns_string(self):
        result = get_quality_presets()
        assert isinstance(result, str)

    def test_contains_header(self):
        result = get_quality_presets()
        assert "# Quality Gate Presets" in result

    def test_contains_standard_preset(self):
        result = get_quality_presets()
        assert "## standard" in result

    def test_contains_strict_preset(self):
        result = get_quality_presets()
        assert "## strict" in result

    def test_contains_framework_preset(self):
        result = get_quality_presets()
        assert "## framework" in result

    def test_contains_threshold_values(self):
        result = get_quality_presets()
        assert "overall_min" in result


# ---------------------------------------------------------------------------
# Scoring weights resource
# ---------------------------------------------------------------------------


class TestGetScoringWeights:
    def test_returns_string(self):
        result = get_scoring_weights()
        assert isinstance(result, str)

    def test_contains_header(self):
        result = get_scoring_weights()
        assert "# Scoring Weights" in result

    def test_contains_all_categories(self):
        result = get_scoring_weights()
        for cat in [
            "complexity",
            "security",
            "maintainability",
            "test_coverage",
            "performance",
            "structure",
            "devex",
        ]:
            assert cat in result, f"Category '{cat}' missing from weights"

    def test_contains_numeric_values(self):
        result = get_scoring_weights()
        # Default weights include 0.18, 0.27, etc.
        assert "0." in result


# ---------------------------------------------------------------------------
# tapps_workflow prompt
# ---------------------------------------------------------------------------


class TestTappsWorkflow:
    @pytest.mark.parametrize(
        "task_type",
        ["general", "feature", "bugfix", "refactor", "security", "review"],
    )
    def test_known_task_types(self, task_type: str):
        result = tapps_workflow(task_type)
        assert isinstance(result, str)
        assert "TappsMCP Workflow" in result
        # Every workflow should mention tapps_server_info or tapps_score_file
        assert "tapps_" in result

    def test_unknown_task_type_defaults_to_general(self):
        result = tapps_workflow("unknown-type")
        general = tapps_workflow("general")
        assert result == general

    def test_general_workflow_steps(self):
        result = tapps_workflow("general")
        assert "tapps_session_start" in result
        assert "tapps_quality_gate" in result
        assert "tapps_checklist" in result

    def test_feature_workflow_has_lookup(self):
        result = tapps_workflow("feature")
        assert "tapps_lookup_docs" in result
        assert "tapps_security_scan" in result

    def test_bugfix_workflow_has_impact_analysis(self):
        result = tapps_workflow("bugfix")
        assert "tapps_impact_analysis" in result

    def test_refactor_workflow_has_impact(self):
        result = tapps_workflow("refactor")
        assert "tapps_impact_analysis" in result

    def test_security_workflow_has_strict_gate(self):
        result = tapps_workflow("security")
        assert "tapps_security_scan" in result
        assert "strict" in result

    def test_review_workflow(self):
        result = tapps_workflow("review")
        assert "Code Review" in result
        assert "tapps_score_file" in result

    def test_default_parameter(self):
        """Calling with no arguments should return the general workflow."""
        result = tapps_workflow()
        assert "General" in result
