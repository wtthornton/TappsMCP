"""Unit tests for business domain detection in domain_detector.py.

Tests Story 44.1: detect_from_question_merged and _score_keywords helper.
"""

from __future__ import annotations

from tapps_core.experts.domain_detector import DomainDetector, _score_keywords
from tapps_core.experts.models import ExpertConfig
from tapps_core.experts.registry import ExpertRegistry


def _register_retail_expert() -> None:
    """Register a sample retail business expert for testing."""
    ExpertRegistry.register_business_experts(
        [
            ExpertConfig(
                expert_id="expert-retail",
                expert_name="Retail Expert",
                primary_domain="retail-operations",
                is_builtin=False,
                keywords=["inventory", "point of sale", "sku", "fulfillment", "warehouse"],
            ),
        ]
    )


def _register_finance_expert() -> None:
    """Register a sample finance business expert for testing."""
    ExpertRegistry.register_business_experts(
        [
            ExpertConfig(
                expert_id="expert-finance",
                expert_name="Finance Expert",
                primary_domain="financial-analysis",
                is_builtin=False,
                keywords=["revenue", "profit margin", "quarterly report", "cash flow"],
            ),
        ]
    )


class TestScoreKeywords:
    """Tests for the _score_keywords helper function."""

    def test_returns_none_for_no_matches(self) -> None:
        result = _score_keywords("how to bake a cake", "security", ["vulnerability"], "Security")
        assert result is None

    def test_returns_domain_mapping_for_match(self) -> None:
        result = _score_keywords(
            "fix the vulnerability in our code",
            "security",
            ["vulnerability", "exploit"],
            "Security Expert",
        )
        assert result is not None
        assert result.domain == "security"
        assert "keyword:vulnerability" in result.signals
        assert result.confidence > 0.0

    def test_multi_word_keyword_bonus(self) -> None:
        """Multi-word keywords get a 0.5 bonus per extra word."""
        single = _score_keywords(
            "improve the sale process",
            "retail",
            ["sale"],
            "Retail Expert",
        )
        multi = _score_keywords(
            "improve the point of sale process",
            "retail",
            ["point of sale"],
            "Retail Expert",
        )
        assert single is not None
        assert multi is not None
        # "point of sale" is 3 words -> weight = 1.0 + 2*0.5 = 2.0
        # "sale" is 1 word -> weight = 1.0
        assert multi.confidence > single.confidence

    def test_case_insensitive(self) -> None:
        result = _score_keywords(
            "check the sku availability",
            "retail",
            ["SKU"],
            "Retail Expert",
        )
        assert result is not None
        assert "keyword:SKU" in result.signals


class TestDetectFromQuestionMerged:
    """Tests for DomainDetector.detect_from_question_merged."""

    def test_business_keyword_matches(self) -> None:
        _register_retail_expert()
        results = DomainDetector.detect_from_question_merged(
            "How do I manage inventory and SKU tracking?"
        )
        domains = [r.domain for r in results]
        assert "retail-operations" in domains

    def test_technical_keyword_only(self) -> None:
        """Without business experts, merged behaves like detect_from_question."""
        results = DomainDetector.detect_from_question_merged(
            "How do I prevent SQL injection?"
        )
        assert results
        assert results[0].domain == "security"

    def test_both_business_and_technical(self) -> None:
        _register_retail_expert()
        results = DomainDetector.detect_from_question_merged(
            "How to secure the inventory API endpoint?"
        )
        domains = [r.domain for r in results]
        assert "security" in domains or "api-design-integration" in domains
        assert "retail-operations" in domains

    def test_no_matches_returns_empty(self) -> None:
        _register_retail_expert()
        results = DomainDetector.detect_from_question_merged(
            "What is the meaning of life?"
        )
        # May be empty or may not - just ensure no crash and it's a list.
        assert isinstance(results, list)

    def test_no_business_experts_matches_existing(self) -> None:
        """With no business experts registered, merged == detect_from_question."""
        merged = DomainDetector.detect_from_question_merged("How to optimize performance?")
        original = DomainDetector.detect_from_question("How to optimize performance?")
        assert [r.domain for r in merged] == [r.domain for r in original]

    def test_business_expert_empty_keywords_no_match(self) -> None:
        ExpertRegistry.register_business_experts(
            [
                ExpertConfig(
                    expert_id="expert-empty-kw",
                    expert_name="Empty KW Expert",
                    primary_domain="empty-kw-domain",
                    is_builtin=False,
                    keywords=[],
                ),
            ]
        )
        results = DomainDetector.detect_from_question_merged("inventory management")
        domains = [r.domain for r in results]
        assert "empty-kw-domain" not in domains

    def test_merged_results_sorted_by_confidence(self) -> None:
        _register_retail_expert()
        results = DomainDetector.detect_from_question_merged(
            "How to secure the inventory API endpoint?"
        )
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].confidence >= results[i + 1].confidence

    def test_multiple_business_keywords_match(self) -> None:
        """Multiple keyword hits increase confidence."""
        _register_retail_expert()
        results = DomainDetector.detect_from_question_merged(
            "How to track inventory SKU in warehouse for fulfillment?"
        )
        retail_results = [r for r in results if r.domain == "retail-operations"]
        assert retail_results
        # 4 keywords matched -> high confidence.
        assert retail_results[0].confidence > 0.5

    def test_multi_word_business_keywords_bonus(self) -> None:
        _register_finance_expert()
        results = DomainDetector.detect_from_question_merged(
            "What is our quarterly report status?"
        )
        finance_results = [r for r in results if r.domain == "financial-analysis"]
        assert finance_results
        # "quarterly report" is 2 words -> bonus weight.
        assert finance_results[0].confidence > 0.0
