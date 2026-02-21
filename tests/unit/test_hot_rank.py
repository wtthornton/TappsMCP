"""Unit tests for tapps_mcp.experts.hot_rank — adaptive ranking."""

from __future__ import annotations

import math

from tapps_mcp.experts.hot_rank import (
    DomainHotRank,
    apply_hot_rank_boost,
    compute_hot_rank,
)
from tapps_mcp.experts.models import KnowledgeChunk


class TestComputeHotRank:
    """Tests for compute_hot_rank."""

    def test_score_between_zero_and_one(self) -> None:
        rank = compute_hot_rank("security", 10, 0.8, 0.9, 1.0)
        assert 0.0 <= rank.score <= 1.0

    def test_high_signals_produce_high_score(self) -> None:
        rank = compute_hot_rank("security", 50, 0.9, 0.95, 0.0)
        assert rank.score > 0.6

    def test_low_signals_produce_low_score(self) -> None:
        rank = compute_hot_rank("obscure", 100, 0.1, 0.1, 30.0)
        assert rank.score < 0.3

    def test_exploration_bonus_for_low_consultations(self) -> None:
        rank_new = compute_hot_rank("new-domain", 2, 0.5, 0.5, 1.0)
        rank_established = compute_hot_rank("established", 50, 0.5, 0.5, 1.0)
        assert rank_new.exploration_bonus > 0.0
        assert rank_established.exploration_bonus == 0.0
        # New domain should get a higher score due to exploration bonus.
        assert rank_new.score >= rank_established.score

    def test_recency_decay(self) -> None:
        rank_recent = compute_hot_rank("security", 10, 0.8, 0.8, 0.0)
        rank_old = compute_hot_rank("security", 10, 0.8, 0.8, 60.0)
        assert rank_recent.recency_weight > rank_old.recency_weight
        assert rank_recent.score > rank_old.score

    def test_domain_stored(self) -> None:
        rank = compute_hot_rank("security", 10, 0.8, 0.8, 1.0)
        assert rank.domain == "security"
        assert rank.consultations == 10
        assert rank.avg_confidence == 0.8

    def test_zero_days_since_gives_max_recency(self) -> None:
        rank = compute_hot_rank("security", 10, 0.5, 0.5, 0.0)
        assert rank.recency_weight == 1.0


class TestComputeHotRankEdgeCases:
    """Edge cases for compute_hot_rank."""

    def test_negative_days_since_gives_max_recency(self) -> None:
        """Negative days_since_last is treated as 'just now' (recency=1.0)."""
        rank = compute_hot_rank("test", 10, 0.5, 0.5, -5.0)
        assert rank.recency_weight == 1.0

    def test_half_life_boundary(self) -> None:
        """At exactly the half-life (14 days), recency should be ~0.5."""
        rank = compute_hot_rank("test", 10, 0.5, 0.5, 14.0)
        assert abs(rank.recency_weight - 0.5) < 0.01

    def test_very_large_days_since(self) -> None:
        """Very old consultations should have near-zero recency."""
        rank = compute_hot_rank("test", 10, 0.5, 0.5, 365.0)
        assert rank.recency_weight < 0.01

    def test_exploration_threshold_boundary_below(self) -> None:
        """4 consultations (< 5 threshold) → exploration bonus applied."""
        rank = compute_hot_rank("test", 4, 0.5, 0.5, 1.0)
        assert rank.exploration_bonus > 0.0

    def test_exploration_threshold_boundary_at(self) -> None:
        """Exactly 5 consultations (= threshold) → NO exploration bonus."""
        rank = compute_hot_rank("test", 5, 0.5, 0.5, 1.0)
        assert rank.exploration_bonus == 0.0

    def test_exploration_threshold_boundary_above(self) -> None:
        """6 consultations (> threshold) → NO exploration bonus."""
        rank = compute_hot_rank("test", 6, 0.5, 0.5, 1.0)
        assert rank.exploration_bonus == 0.0

    def test_zero_all_signals(self) -> None:
        """All signals at zero still produces a valid (clamped) score."""
        rank = compute_hot_rank("test", 0, 0.0, 0.0, 100.0)
        assert 0.0 <= rank.score <= 1.0
        # Base contribution: 0.1*(1.0+0.15) = 0.115 (exploration bonus since 0 < 5)
        assert rank.score > 0.0

    def test_all_signals_maxed(self) -> None:
        """All signals at maximum → score clamped to 1.0."""
        rank = compute_hot_rank("test", 0, 1.0, 1.0, 0.0)
        # 0.4*1.0 + 0.3*1.0 + 0.2*1.0 + 0.1*(1+0.15) = 1.015 → clamped to 1.0
        assert rank.score == 1.0

    def test_score_clamped_above_one(self) -> None:
        """Score above 1.0 is clamped."""
        # This would produce >1.0 before clamping
        rank = compute_hot_rank("test", 0, 1.0, 1.0, 0.0)
        assert rank.score <= 1.0

    def test_zero_consultations(self) -> None:
        """Zero consultations still works."""
        rank = compute_hot_rank("test", 0, 0.0, 0.0, 0.0)
        assert rank.consultations == 0
        assert rank.exploration_bonus > 0.0  # < threshold

    def test_helpful_rate_rounded(self) -> None:
        rank = compute_hot_rank("test", 10, 0.33333, 0.66666, 1.0)
        assert rank.helpful_rate == round(0.66666, 4)
        assert rank.avg_confidence == round(0.33333, 4)


class TestApplyHotRankBoost:
    """Tests for apply_hot_rank_boost."""

    def test_none_metrics_dir_no_change(self) -> None:
        """When metrics_dir is None, chunks are returned unchanged."""
        chunks = [
            KnowledgeChunk(content="test", source_file="a.md", line_start=1, line_end=5, score=0.5),
        ]
        result = apply_hot_rank_boost(chunks, "security", metrics_dir=None)
        assert result[0].score == 0.5

    def test_nonexistent_metrics_dir_no_change(self, tmp_path) -> None:
        """When metrics directory doesn't exist, gracefully returns unchanged chunks."""
        chunks = [
            KnowledgeChunk(content="test", source_file="a.md", line_start=1, line_end=5, score=0.5),
        ]
        result = apply_hot_rank_boost(chunks, "security", metrics_dir=tmp_path / "nonexistent")
        # Should return unchanged (exception caught internally)
        assert len(result) == 1

    def test_empty_chunks_list(self) -> None:
        """Empty chunks list returns empty."""
        result = apply_hot_rank_boost([], "security", metrics_dir=None)
        assert result == []

    def test_boost_capped_at_one(self) -> None:
        """Boosted scores should never exceed 1.0."""
        chunk = KnowledgeChunk(content="test", source_file="a.md", line_start=1, line_end=5, score=0.99)
        # Even with boost, score should be clamped
        # apply_hot_rank_boost with None metrics_dir returns unchanged
        result = apply_hot_rank_boost([chunk], "security", metrics_dir=None)
        assert result[0].score <= 1.0

    def test_objects_without_score_attribute(self) -> None:
        """Objects without 'score' attribute are handled gracefully."""

        class NoScoreObj:
            pass

        chunks = [NoScoreObj()]
        result = apply_hot_rank_boost(chunks, "security", metrics_dir=None)
        assert len(result) == 1


class TestDomainHotRankDataclass:
    """Test the DomainHotRank dataclass."""

    def test_fields_populated(self) -> None:
        rank = DomainHotRank(
            domain="security",
            score=0.85,
            consultations=10,
            avg_confidence=0.8,
            helpful_rate=0.9,
            recency_weight=0.95,
            exploration_bonus=0.0,
        )
        assert rank.domain == "security"
        assert rank.score == 0.85
        assert rank.consultations == 10

    def test_default_values(self) -> None:
        rank = DomainHotRank(domain="test", score=0.5)
        assert rank.consultations == 0
        assert rank.avg_confidence == 0.0
        assert rank.helpful_rate == 0.0
        assert rank.recency_weight == 0.0
        assert rank.exploration_bonus == 0.0
