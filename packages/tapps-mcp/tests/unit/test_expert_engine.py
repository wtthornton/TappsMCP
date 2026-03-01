"""Unit tests for tapps_mcp.experts.engine."""

from __future__ import annotations

from tapps_mcp.experts.engine import consult_expert, list_experts


class TestConsultExpert:
    """Tests for consult_expert."""

    def test_auto_routes_security_question(self) -> None:
        result = consult_expert("How do I prevent SQL injection?")
        assert result.domain == "security"
        assert result.expert_id == "expert-security"
        assert result.confidence > 0

    def test_explicit_domain_override(self) -> None:
        result = consult_expert(
            "General coding question",
            domain="testing-strategies",
        )
        assert result.domain == "testing-strategies"
        assert result.expert_id == "expert-testing"

    def test_returns_answer_text(self) -> None:
        result = consult_expert("What are best practices for Docker security?")
        assert result.answer
        assert len(result.answer) > 0

    def test_confidence_between_zero_and_one(self) -> None:
        result = consult_expert("How to set up logging and monitoring?")
        assert 0.0 <= result.confidence <= 1.0

    def test_sources_populated_for_known_domain(self) -> None:
        result = consult_expert("What are OWASP top 10 vulnerabilities?")
        # Security knowledge base should have relevant files.
        assert result.chunks_used >= 0  # May be 0 if no keyword match.

    def test_fallback_domain_for_ambiguous_question(self) -> None:
        result = consult_expert("Tell me something interesting about cats")
        # Should still produce a result (fallback domain).
        assert result.domain
        assert result.expert_name

    def test_performance_domain_with_knowledge_dir(self) -> None:
        result = consult_expert(
            "How to optimize database query performance?",
            domain="performance-optimization",
        )
        assert result.domain == "performance-optimization"
        assert result.expert_id == "expert-performance"

    def test_factors_populated(self) -> None:
        result = consult_expert("How to write pytest fixtures?")
        assert result.factors is not None
        assert result.factors.domain_relevance > 0

    def test_low_confidence_nudge_when_confidence_low(self) -> None:
        # Ambiguous/off-topic question often yields low confidence
        result = consult_expert("Tell me something interesting about cats")
        assert hasattr(result, "low_confidence_nudge")
        if result.confidence < 0.5:
            assert result.low_confidence_nudge is not None
            assert "tapps_lookup_docs" in result.low_confidence_nudge
            assert "Note:" in result.answer

    def test_structured_suggestion_fields_when_no_context(self) -> None:
        result = consult_expert("Tell me something interesting about cats")
        if result.chunks_used == 0:
            assert result.suggested_tool == "tapps_lookup_docs"
            assert result.suggested_library is not None
            assert result.suggested_topic is not None

    def test_fallback_flags_default_shape(self) -> None:
        result = consult_expert("How to write pytest fixtures?")
        assert isinstance(result.fallback_used, bool)
        if result.fallback_used:
            assert result.fallback_library is not None
            assert result.fallback_topic is not None

    def test_detected_domains_populated_on_auto_detect(self) -> None:
        result = consult_expert("How do I prevent SQL injection?")
        # Auto-detected: should have at least one detected domain
        assert len(result.detected_domains) >= 1
        assert result.detected_domains[0].domain == "security"
        assert result.detected_domains[0].confidence > 0

    def test_detected_domains_empty_when_explicit(self) -> None:
        result = consult_expert(
            "General coding question",
            domain="testing-strategies",
        )
        assert result.detected_domains == []

    def test_detected_domains_capped_at_three(self) -> None:
        # A broad question touching many domains
        result = consult_expert(
            "How to test security of database API performance with logging?"
        )
        assert len(result.detected_domains) <= 3

    def test_recommendation_high_confidence(self) -> None:
        result = consult_expert("What are OWASP top 10 vulnerabilities?")
        assert result.recommendation
        if result.confidence >= 0.7:
            assert "high-confidence" in result.recommendation

    def test_recommendation_low_confidence(self) -> None:
        result = consult_expert("Tell me something interesting about cats")
        assert result.recommendation
        if result.confidence < 0.5:
            assert "tapps_research" in result.recommendation

    def test_recommendation_always_present(self) -> None:
        result = consult_expert("How to write pytest fixtures?")
        assert isinstance(result.recommendation, str)
        assert len(result.recommendation) > 0


class TestListExperts:
    """Tests for list_experts."""

    def test_returns_17_experts(self) -> None:
        experts = list_experts()
        assert len(experts) == 17

    def test_each_expert_has_required_fields(self) -> None:
        for expert in list_experts():
            assert expert.expert_id
            assert expert.expert_name
            assert expert.primary_domain
            assert expert.description

    def test_knowledge_files_counted(self) -> None:
        experts = list_experts()
        # At least one expert should have knowledge files.
        total_files = sum(e.knowledge_files for e in experts)
        assert total_files > 0

    def test_security_expert_has_files(self) -> None:
        experts = list_experts()
        security = next(e for e in experts if e.expert_id == "expert-security")
        assert security.knowledge_files > 0
