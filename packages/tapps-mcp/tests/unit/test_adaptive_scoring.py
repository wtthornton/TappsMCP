"""Tests for adaptive scoring engine and wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.adaptive.models import CodeOutcome
from tapps_mcp.adaptive.persistence import FileOutcomeTracker
from tapps_mcp.adaptive.scoring_engine import (
    AdaptiveScoringEngine,
    _get_default_weights,
    _pearson_correlation,
)
from tapps_mcp.adaptive.scoring_wrapper import AdaptiveScorerWrapper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(
    wid: str,
    scores: dict[str, float],
    *,
    success: bool = False,
) -> CodeOutcome:
    return CodeOutcome(
        workflow_id=wid,
        file_path="test.py",
        initial_scores=scores,
        first_pass_success=success,
    )


def _make_outcomes_for_correlation(n: int = 20) -> list[CodeOutcome]:
    """Create outcomes where high security score correlates with success."""
    outcomes: list[CodeOutcome] = []
    for i in range(n):
        high_sec = i >= n // 2
        outcomes.append(
            _make_outcome(
                f"wf-{i}",
                {
                    "complexity": 5.0,
                    "security": 9.0 if high_sec else 3.0,
                    "maintainability": 5.0,
                    "test_coverage": 5.0,
                    "performance": 5.0,
                    "structure": 5.0,
                    "devex": 5.0,
                },
                success=high_sec,
            )
        )
    return outcomes


# ---------------------------------------------------------------------------
# Pearson correlation
# ---------------------------------------------------------------------------


class TestPearsonCorrelation:
    def test_perfect_positive(self):
        corr = _pearson_correlation([0.0, 1.0], [False, True])
        assert corr == pytest.approx(1.0)

    def test_perfect_negative(self):
        corr = _pearson_correlation([0.0, 1.0], [True, False])
        assert corr == pytest.approx(-1.0)

    def test_zero_variance_x(self):
        corr = _pearson_correlation([5.0, 5.0, 5.0], [True, False, True])
        assert corr == 0.0

    def test_zero_variance_y(self):
        corr = _pearson_correlation([1.0, 2.0, 3.0], [True, True, True])
        assert corr == 0.0

    def test_insufficient_data(self):
        corr = _pearson_correlation([1.0], [True])
        assert corr == 0.0


# ---------------------------------------------------------------------------
# AdaptiveScoringEngine
# ---------------------------------------------------------------------------


class TestAdaptiveScoringEngine:
    @pytest.fixture()
    def tracker(self, tmp_path: Path) -> FileOutcomeTracker:
        return FileOutcomeTracker(tmp_path)

    @pytest.fixture()
    def engine(self, tracker: FileOutcomeTracker) -> AdaptiveScoringEngine:
        return AdaptiveScoringEngine(tracker, learning_rate=0.1)

    async def test_insufficient_outcomes_returns_defaults(self, engine: AdaptiveScoringEngine):
        outcomes = [_make_outcome("wf-1", {"security": 8.0})]
        result = await engine.adjust_weights(outcomes=outcomes)
        assert result == _get_default_weights()

    async def test_adjust_weights_changes_weights(self, engine: AdaptiveScoringEngine):
        outcomes = _make_outcomes_for_correlation(20)
        defaults = _get_default_weights()
        result = await engine.adjust_weights(outcomes=outcomes, current_weights=defaults)
        # Security should be boosted (positively correlated with success).
        assert result["security"] >= defaults["security"]

    async def test_weights_sum_to_one(self, engine: AdaptiveScoringEngine):
        outcomes = _make_outcomes_for_correlation(20)
        result = await engine.adjust_weights(outcomes=outcomes)
        assert abs(sum(result.values()) - 1.0) < 0.01

    async def test_learning_rate_applied(self, engine: AdaptiveScoringEngine):
        outcomes = _make_outcomes_for_correlation(20)
        defaults = _get_default_weights()
        result = await engine.adjust_weights(outcomes=outcomes, current_weights=defaults)
        # With lr=0.1, weights should be close to defaults (90% current + 10% optimal).
        for key in defaults:
            assert abs(result[key] - defaults[key]) < 0.15

    def test_get_recommendation(self, engine: AdaptiveScoringEngine):
        outcomes = _make_outcomes_for_correlation(20)
        rec = engine.get_recommendation(outcomes)
        assert rec["outcomes_analyzed"] == 20
        assert rec["sufficient_data"] is True
        assert "correlations" in rec
        assert "current_weights" in rec
        assert "optimal_weights" in rec

    def test_get_recommendation_insufficient(self, engine: AdaptiveScoringEngine):
        rec = engine.get_recommendation(outcomes=[])
        assert rec["sufficient_data"] is False


# ---------------------------------------------------------------------------
# AdaptiveScorerWrapper
# ---------------------------------------------------------------------------


class TestAdaptiveScorerWrapper:
    def test_disabled_returns_none(self):
        wrapper = AdaptiveScorerWrapper(enabled=False)
        import asyncio

        result = asyncio.run(wrapper.get_adaptive_weights())
        assert result is None

    async def test_cache_hit(self, tmp_path: Path):
        tracker = FileOutcomeTracker(tmp_path)
        engine = AdaptiveScoringEngine(tracker)
        wrapper = AdaptiveScorerWrapper(
            outcome_tracker=tracker,
            adaptive_engine=engine,
            enabled=True,
        )
        # First call computes (returns defaults since no outcomes).
        w1 = await wrapper.get_adaptive_weights()
        assert w1 is not None
        # Second call returns cached.
        w2 = await wrapper.get_adaptive_weights()
        assert w1 == w2

    def test_hash_prompt_deterministic(self):
        h1 = AdaptiveScorerWrapper.hash_prompt("test prompt")
        h2 = AdaptiveScorerWrapper.hash_prompt("test prompt")
        assert h1 == h2
        assert len(h1) == 16

    def test_hash_prompt_different_inputs(self):
        h1 = AdaptiveScorerWrapper.hash_prompt("prompt A")
        h2 = AdaptiveScorerWrapper.hash_prompt("prompt B")
        assert h1 != h2

    def test_get_weights_as_settings_no_cache(self):
        wrapper = AdaptiveScorerWrapper(enabled=False)
        sw = wrapper.get_weights_as_settings()
        # Should return default ScoringWeights.
        assert sw.complexity == pytest.approx(0.18)
        assert sw.security == pytest.approx(0.27)

    async def test_track_outcome(self, tmp_path: Path):
        tracker = FileOutcomeTracker(tmp_path)
        wrapper = AdaptiveScorerWrapper(outcome_tracker=tracker, enabled=True)
        await wrapper.track_outcome(
            workflow_id="wf-1",
            file_path=Path("main.py"),
            scores={"security": 8.0},
        )
        loaded = tracker.load_outcomes()
        assert len(loaded) == 1
        assert loaded[0].workflow_id == "wf-1"
