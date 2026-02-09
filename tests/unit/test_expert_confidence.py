"""Unit tests for tapps_mcp.experts.confidence."""

from __future__ import annotations

from tapps_mcp.experts.confidence import (
    compute_chunk_coverage,
    compute_confidence,
    compute_rag_quality,
)
from tapps_mcp.experts.models import ConfidenceFactors


class TestComputeConfidence:
    """Tests for compute_confidence."""

    def test_perfect_factors_technical_domain(self) -> None:
        factors = ConfidenceFactors(rag_quality=1.0, chunk_coverage=1.0)
        score = compute_confidence(factors, "security")
        assert score == 1.0
        assert factors.domain_relevance == 1.0

    def test_zero_factors(self) -> None:
        factors = ConfidenceFactors(rag_quality=0.0, chunk_coverage=0.0)
        score = compute_confidence(factors, "security")
        # Only domain_relevance contributes (1.0 * 0.3 = 0.3).
        assert score == 0.3

    def test_unknown_domain_lower_relevance(self) -> None:
        factors = ConfidenceFactors(rag_quality=1.0, chunk_coverage=1.0)
        score = compute_confidence(factors, "astrology")
        # 1.0*0.4 + 0.7*0.3 + 1.0*0.3 = 0.4 + 0.21 + 0.3 = 0.91
        assert 0.90 <= score <= 0.92

    def test_partial_factors(self) -> None:
        factors = ConfidenceFactors(rag_quality=0.5, chunk_coverage=0.5)
        score = compute_confidence(factors, "testing-strategies")
        # 0.5*0.4 + 1.0*0.3 + 0.5*0.3 = 0.2 + 0.3 + 0.15 = 0.65
        assert 0.64 <= score <= 0.66

    def test_score_clamped_to_one(self) -> None:
        # Even with factors > 1 somehow, result is clamped.
        factors = ConfidenceFactors(rag_quality=1.0, chunk_coverage=1.0, domain_relevance=1.0)
        score = compute_confidence(factors, "security")
        assert score <= 1.0


class TestComputeRagQuality:
    """Tests for compute_rag_quality."""

    def test_empty_scores(self) -> None:
        assert compute_rag_quality([]) == 0.0

    def test_single_score(self) -> None:
        assert compute_rag_quality([0.8]) == 0.8

    def test_top_three_averaged(self) -> None:
        scores = [0.9, 0.6, 0.3, 0.1]
        # Top 3: 0.9, 0.6, 0.3 → mean = 0.6
        result = compute_rag_quality(scores)
        assert result == 0.6

    def test_fewer_than_three(self) -> None:
        scores = [1.0, 0.5]
        result = compute_rag_quality(scores)
        assert result == 0.75


class TestComputeChunkCoverage:
    """Tests for compute_chunk_coverage."""

    def test_full_coverage(self) -> None:
        keywords = {"security", "injection", "prevention"}
        texts = ["security injection prevention in sql"]
        assert compute_chunk_coverage(keywords, texts) == 1.0

    def test_partial_coverage(self) -> None:
        keywords = {"security", "injection", "prevention"}
        texts = ["security best practices"]
        result = compute_chunk_coverage(keywords, texts)
        # Only "security" matches → 1/3.
        assert abs(result - 0.3333) < 0.01

    def test_no_coverage(self) -> None:
        keywords = {"zyxwvu"}
        texts = ["nothing matches here"]
        assert compute_chunk_coverage(keywords, texts) == 0.0

    def test_empty_keywords(self) -> None:
        assert compute_chunk_coverage(set(), ["any text"]) == 0.0

    def test_empty_texts(self) -> None:
        assert compute_chunk_coverage({"keyword"}, []) == 0.0
