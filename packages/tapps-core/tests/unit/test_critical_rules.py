"""Unit tests for Epic 71: Expert Critical Rules & Default Stance.

Tests cover:
- ExpertConfig and BusinessExpertEntry critical_rules field
- _build_answer with persona only, persona + rules, rules only, neither
- Pilot critical_rules in registry for Security, Testing, Accessibility
"""

from __future__ import annotations

from tapps_core.experts.engine import (
    _AnswerResult,
    _build_answer,
    _ConfidenceResult,
    _KnowledgeResult,
)
from tapps_core.experts.models import (
    ConfidenceFactors,
    ExpertConfig,
    ExpertInfo,
    KnowledgeChunk,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_expert(
    *,
    persona: str = "",
    critical_rules: str = "",
) -> ExpertConfig:
    return ExpertConfig(
        expert_id="expert-test",
        expert_name="Test Expert",
        primary_domain="testing-strategies",
        persona=persona,
        critical_rules=critical_rules,
    )


def _make_knowledge(*, with_context: bool = True) -> _KnowledgeResult:
    if with_context:
        return _KnowledgeResult(
            chunks=[
                KnowledgeChunk(
                    content="Always test edge cases.",
                    source_file="testing.md",
                    line_start=1,
                    line_end=1,
                    score=0.9,
                )
            ],
            context="Always test edge cases.",
            sources=["testing.md"],
        )
    return _KnowledgeResult(chunks=[], context="", sources=[])


def _make_conf(confidence: float = 0.8) -> _ConfidenceResult:
    return _ConfidenceResult(
        confidence=confidence,
        factors=ConfidenceFactors(rag_quality=0.8, source_count=1, chunk_coverage=0.7),
    )


# ---------------------------------------------------------------------------
# Story 71.1: ExpertConfig field
# ---------------------------------------------------------------------------


class TestExpertConfigCriticalRules:
    """ExpertConfig and ExpertInfo support the critical_rules field."""

    def test_default_empty_string(self) -> None:
        expert = ExpertConfig(
            expert_id="expert-x",
            expert_name="X Expert",
            primary_domain="x-domain",
        )
        assert expert.critical_rules == ""

    def test_explicit_critical_rules(self) -> None:
        expert = ExpertConfig(
            expert_id="expert-x",
            expert_name="X Expert",
            primary_domain="x-domain",
            critical_rules="Always assume breach.",
        )
        assert expert.critical_rules == "Always assume breach."

    def test_expert_info_includes_critical_rules(self) -> None:
        info = ExpertInfo(
            expert_id="expert-x",
            expert_name="X Expert",
            primary_domain="x-domain",
            critical_rules="Test all paths.",
        )
        assert info.critical_rules == "Test all paths."

    def test_expert_info_default_empty(self) -> None:
        info = ExpertInfo(
            expert_id="expert-x",
            expert_name="X Expert",
            primary_domain="x-domain",
        )
        assert info.critical_rules == ""


class TestBusinessExpertEntryCriticalRules:
    """BusinessExpertEntry supports the critical_rules field."""

    def test_default_empty(self) -> None:
        from tapps_core.experts.business_config import BusinessExpertEntry

        entry = BusinessExpertEntry(
            expert_id="expert-biz",
            expert_name="Biz Expert",
            primary_domain="biz-domain",
        )
        assert entry.critical_rules == ""

    def test_explicit_rules(self) -> None:
        from tapps_core.experts.business_config import BusinessExpertEntry

        entry = BusinessExpertEntry(
            expert_id="expert-biz",
            expert_name="Biz Expert",
            primary_domain="biz-domain",
            critical_rules="Revenue first.",
        )
        assert entry.critical_rules == "Revenue first."


# ---------------------------------------------------------------------------
# Story 71.2: _build_answer wiring
# ---------------------------------------------------------------------------


class TestBuildAnswerCriticalRules:
    """_build_answer includes critical_rules after persona when set."""

    def test_persona_only(self) -> None:
        """Existing behavior: persona appears, no rules line."""
        expert = _make_expert(persona="Senior tester with 10 years experience.")
        result = _build_answer(
            question="How to test?",
            expert=expert,
            resolved_domain="testing-strategies",
            knowledge=_make_knowledge(),
            conf=_make_conf(),
        )
        assert "*Senior tester with 10 years experience.*" in result.answer
        assert "**Critical rules:**" not in result.answer

    def test_persona_and_critical_rules(self) -> None:
        """Both persona and rules appear in answer."""
        expert = _make_expert(
            persona="Senior tester.",
            critical_rules="Always test edge cases first.",
        )
        result = _build_answer(
            question="How to test?",
            expert=expert,
            resolved_domain="testing-strategies",
            knowledge=_make_knowledge(),
            conf=_make_conf(),
        )
        assert "*Senior tester.*" in result.answer
        assert "**Critical rules:** Always test edge cases first." in result.answer
        # Rules appear after persona
        persona_pos = result.answer.index("*Senior tester.*")
        rules_pos = result.answer.index("**Critical rules:**")
        assert rules_pos > persona_pos

    def test_critical_rules_only(self) -> None:
        """Rules appear even without persona."""
        expert = _make_expert(critical_rules="Assume breach always.")
        result = _build_answer(
            question="How to secure?",
            expert=expert,
            resolved_domain="testing-strategies",
            knowledge=_make_knowledge(),
            conf=_make_conf(),
        )
        assert "**Critical rules:** Assume breach always." in result.answer

    def test_neither_persona_nor_rules(self) -> None:
        """No persona or rules: answer starts with header and knowledge."""
        expert = _make_expert()
        result = _build_answer(
            question="How to test?",
            expert=expert,
            resolved_domain="testing-strategies",
            knowledge=_make_knowledge(),
            conf=_make_conf(),
        )
        assert "**Critical rules:**" not in result.answer
        assert "## Test Expert" in result.answer
        assert "Based on domain knowledge" in result.answer

    def test_no_knowledge_with_rules(self) -> None:
        """When no knowledge context, rules do NOT appear (fallback branch)."""
        expert = _make_expert(critical_rules="Always test.")
        result = _build_answer(
            question="How to test?",
            expert=expert,
            resolved_domain="testing-strategies",
            knowledge=_make_knowledge(with_context=False),
            conf=_make_conf(confidence=0.3),
        )
        # The no-knowledge branch doesn't include persona/rules
        assert "No specific knowledge found" in result.answer


# ---------------------------------------------------------------------------
# Story 71.3: Pilot critical_rules in registry
# ---------------------------------------------------------------------------


class TestPilotCriticalRules:
    """Security, Testing, and Accessibility experts have critical_rules set."""

    def test_security_expert_has_rules(self) -> None:
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("security")
        assert expert is not None
        assert expert.critical_rules != ""
        assert "attacker" in expert.critical_rules.lower()
        assert "secure-by-default" in expert.critical_rules.lower()

    def test_testing_expert_has_rules(self) -> None:
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("testing-strategies")
        assert expert is not None
        assert expert.critical_rules != ""
        assert "explicit tests" in expert.critical_rules.lower()

    def test_accessibility_expert_has_rules(self) -> None:
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("accessibility")
        assert expert is not None
        assert expert.critical_rules != ""
        assert "wcag" in expert.critical_rules.lower()

    def test_other_experts_default_empty(self) -> None:
        """Experts without pilot rules still have empty critical_rules."""
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("performance-optimization")
        assert expert is not None
        assert expert.critical_rules == ""

    def test_security_rules_in_consultation_answer(self) -> None:
        """Security expert's critical rules appear in _build_answer output."""
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("security")
        assert expert is not None
        result = _build_answer(
            question="How to prevent SQL injection?",
            expert=expert,
            resolved_domain="security",
            knowledge=_make_knowledge(),
            conf=_make_conf(),
        )
        assert "**Critical rules:**" in result.answer
        assert "attacker" in result.answer.lower()
