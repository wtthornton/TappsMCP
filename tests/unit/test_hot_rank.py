"""Unit tests for tapps_mcp.experts.hot_rank — adaptive ranking."""

from __future__ import annotations

from tapps_mcp.experts.hot_rank import (
    DomainHotRank,
    compute_hot_rank,
)


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
