"""Tests for MCP resources and the tapps_workflow prompt."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.server_resources import (
    _get_knowledge_resource as get_knowledge_resource,
    _get_quality_presets as get_quality_presets,
    _get_scoring_weights as get_scoring_weights,
    _list_knowledge_domains as list_knowledge_domains,
    _tapps_workflow as tapps_workflow,
)

# ---------------------------------------------------------------------------
# Knowledge resource — valid domain/topic
# ---------------------------------------------------------------------------


class TestGetKnowledgeResource:
    def test_valid_domain_and_topic(self):
        """Reading security/owasp-top10 should return real markdown content."""
        result = get_knowledge_resource("security", "owasp-top10")
        assert isinstance(result, str)
        assert len(result) > 100
        # Knowledge files are markdown — expect headings or content
        assert "#" in result or "OWASP" in result.upper() or "security" in result.lower()

    def test_invalid_domain(self):
        result = get_knowledge_resource("nonexistent-domain", "anything")
        assert "Unknown domain" in result
        assert "nonexistent-domain" in result
        # Should list valid domains
        assert "security" in result
        assert "Valid domains:" in result

    def test_invalid_topic_lists_available(self):
        """An invalid topic under a valid domain should list available topics."""
        result = get_knowledge_resource("security", "nonexistent-topic")
        assert "not found" in result.lower() or "Topic" in result
        assert "security" in result
        # Should list at least one known topic
        assert "owasp-top10" in result or "secure-coding" in result or "Available:" in result

    def test_all_17_domains_recognised(self):
        """Every domain in TECHNICAL_DOMAINS should not return 'Unknown domain'."""
        from tapps_mcp.experts.registry import ExpertRegistry

        for domain in ExpertRegistry.TECHNICAL_DOMAINS:
            result = get_knowledge_resource(domain, "__probe__")
            assert "Unknown domain" not in result, f"{domain} was not recognised"


# ---------------------------------------------------------------------------
# Knowledge domains listing
# ---------------------------------------------------------------------------


class TestListKnowledgeDomains:
    def test_returns_string(self):
        result = list_knowledge_domains()
        assert isinstance(result, str)

    def test_contains_header(self):
        result = list_knowledge_domains()
        assert "# TappsMCP Knowledge Domains" in result

    def test_contains_all_17_domain_dirs(self):
        """The knowledge directory has 17 subdirectories (one per domain).

        Note: some directories use short names (e.g. 'performance' for
        'performance-optimization'), so we check for the directory names
        rather than the TECHNICAL_DOMAINS set.
        """
        result = list_knowledge_domains()
        knowledge_base = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "tapps-core"
            / "src"
            / "tapps_core"
            / "experts"
            / "knowledge"
        )
        domain_dirs = [d.name for d in sorted(knowledge_base.iterdir()) if d.is_dir()]
        # There should be exactly 17 domain directories
        assert len(domain_dirs) == 17
        for dname in domain_dirs:
            assert dname in result, f"Domain directory '{dname}' missing from listing"

    def test_lists_topics(self):
        result = list_knowledge_domains()
        # At least one topic line should appear
        assert "  - " in result


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
        assert "tapps_project_profile" in result
        assert "tapps_quality_gate" in result
        assert "tapps_checklist" in result

    def test_feature_workflow_has_lookup_and_expert(self):
        result = tapps_workflow("feature")
        assert "tapps_lookup_docs" in result
        assert "tapps_consult_expert" in result
        assert "tapps_security_scan" in result

    def test_bugfix_workflow_has_impact_analysis(self):
        result = tapps_workflow("bugfix")
        assert "tapps_impact_analysis" in result

    def test_refactor_workflow_has_architecture(self):
        result = tapps_workflow("refactor")
        assert "tapps_impact_analysis" in result
        assert "software-architecture" in result

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
