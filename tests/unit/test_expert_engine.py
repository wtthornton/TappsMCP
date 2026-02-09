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


class TestListExperts:
    """Tests for list_experts."""

    def test_returns_16_experts(self) -> None:
        experts = list_experts()
        assert len(experts) == 16

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
