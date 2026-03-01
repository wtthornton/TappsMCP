"""Unit tests for tapps_mcp.experts.hot_rank — adaptive ranking."""

from __future__ import annotations

import pytest

from tapps_mcp.experts.hot_rank import (
    DomainHotRank,
    apply_hot_rank_boost,
    compute_hot_rank,
)
from tapps_mcp.experts.models import KnowledgeChunk


class TestComputeHotRank:
    """Core compute_hot_rank behaviour."""

    def test_score_between_zero_and_one(self) -> None:
        rank = compute_hot_rank("security", 10, 0.8, 0.9, 1.0)
        assert 0.0 <= rank.score <= 1.0

    def test_high_signals_produce_high_score(self) -> None:
        rank = compute_hot_rank("security", 50, 0.9, 0.95, 0.0)
        assert rank.score > 0.6

    def test_low_signals_produce_low_score(self) -> None:
        rank = compute_hot_rank("obscure", 100, 0.1, 0.1, 30.0)
        assert rank.score < 0.3

    def test_recency_decay(self) -> None:
        recent = compute_hot_rank("security", 10, 0.8, 0.8, 0.0)
        old = compute_hot_rank("security", 10, 0.8, 0.8, 60.0)
        assert recent.recency_weight > old.recency_weight
        assert recent.score > old.score

    def test_domain_and_fields_stored(self) -> None:
        rank = compute_hot_rank("security", 10, 0.8, 0.8, 1.0)
        assert rank.domain == "security"
        assert rank.consultations == 10
        assert rank.avg_confidence == 0.8

    def test_exploration_bonus_for_new_domains(self) -> None:
        new = compute_hot_rank("new-domain", 2, 0.5, 0.5, 1.0)
        established = compute_hot_rank("established", 50, 0.5, 0.5, 1.0)
        assert new.exploration_bonus > 0.0
        assert established.exploration_bonus == 0.0
        assert new.score >= established.score


class TestComputeHotRankEdgeCases:
    """Boundary conditions and edge cases."""

    @pytest.mark.parametrize(
        "days,expected_recency",
        [
            (0.0, 1.0),  # just now
            (-5.0, 1.0),  # negative treated as max
        ],
        ids=["zero-days", "negative-days"],
    )
    def test_max_recency(self, days, expected_recency) -> None:
        rank = compute_hot_rank("test", 10, 0.5, 0.5, days)
        assert rank.recency_weight == expected_recency

    def test_half_life_boundary(self) -> None:
        rank = compute_hot_rank("test", 10, 0.5, 0.5, 14.0)
        assert abs(rank.recency_weight - 0.5) < 0.01

    def test_very_large_days_since(self) -> None:
        rank = compute_hot_rank("test", 10, 0.5, 0.5, 365.0)
        assert rank.recency_weight < 0.01

    @pytest.mark.parametrize(
        "consultations,has_bonus",
        [
            (4, True),
            (5, False),
            (6, False),
        ],
        ids=["below-threshold", "at-threshold", "above-threshold"],
    )
    def test_exploration_threshold(self, consultations, has_bonus) -> None:
        rank = compute_hot_rank("test", consultations, 0.5, 0.5, 1.0)
        assert (rank.exploration_bonus > 0.0) == has_bonus

    def test_zero_all_signals(self) -> None:
        rank = compute_hot_rank("test", 0, 0.0, 0.0, 100.0)
        assert 0.0 <= rank.score <= 1.0
        assert rank.score > 0.0  # exploration bonus contributes

    def test_all_signals_maxed_clamped(self) -> None:
        """Score clamped to 1.0 when signals would push above."""
        rank = compute_hot_rank("test", 0, 1.0, 1.0, 0.0)
        assert rank.score == 1.0

    def test_rounding(self) -> None:
        rank = compute_hot_rank("test", 10, 0.33333, 0.66666, 1.0)
        assert rank.helpful_rate == round(0.66666, 4)
        assert rank.avg_confidence == round(0.33333, 4)


class TestApplyHotRankBoost:
    """Tests for apply_hot_rank_boost."""

    def test_none_metrics_dir_no_change(self) -> None:
        chunk = KnowledgeChunk(
            content="test", source_file="a.md", line_start=1, line_end=5, score=0.5
        )
        result = apply_hot_rank_boost([chunk], "security", metrics_dir=None)
        assert result[0].score == 0.5

    def test_nonexistent_metrics_dir_no_change(self, tmp_path) -> None:
        chunk = KnowledgeChunk(
            content="test", source_file="a.md", line_start=1, line_end=5, score=0.5
        )
        result = apply_hot_rank_boost([chunk], "security", metrics_dir=tmp_path / "nonexistent")
        assert len(result) == 1

    def test_empty_chunks_list(self) -> None:
        assert apply_hot_rank_boost([], "security", metrics_dir=None) == []

    def test_objects_without_score_attribute(self) -> None:
        class NoScoreObj:
            pass

        result = apply_hot_rank_boost([NoScoreObj()], "security", metrics_dir=None)
        assert len(result) == 1


class TestDomainHotRankDataclass:
    def test_default_values(self) -> None:
        rank = DomainHotRank(domain="test", score=0.5)
        assert rank.consultations == 0
        assert rank.avg_confidence == 0.0
        assert rank.helpful_rate == 0.0
        assert rank.recency_weight == 0.0
        assert rank.exploration_bonus == 0.0
