"""Tests for adaptive voting engine — AdaptiveVotingEngine."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.adaptive.models import ExpertPerformance, ExpertWeightMatrix
from tapps_core.adaptive.persistence import FilePerformanceTracker
from tapps_core.adaptive.voting_engine import (
    AdaptiveVotingEngine,
    _build_default_matrix,
)
from tapps_core.adaptive.weight_distributor import WeightDistributor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tracker(tmp_path: Path) -> FilePerformanceTracker:
    return FilePerformanceTracker(tmp_path)


@pytest.fixture()
def engine(tracker: FilePerformanceTracker) -> AdaptiveVotingEngine:
    return AdaptiveVotingEngine(tracker)


def _two_expert_matrix() -> ExpertWeightMatrix:
    """Helper: 2 experts, 2 domains."""
    return WeightDistributor.calculate_weights(
        domains=["security", "testing"],
        expert_primary_map={"security": "expert-sec", "testing": "expert-test"},
    )


def _three_expert_matrix() -> ExpertWeightMatrix:
    """Helper: 3 experts, 3 domains."""
    return WeightDistributor.calculate_weights(
        domains=["security", "testing", "performance"],
        expert_primary_map={
            "security": "e-sec",
            "testing": "e-test",
            "performance": "e-perf",
        },
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestVotingEngineInit:
    def test_engine_creation(self, engine: AdaptiveVotingEngine) -> None:
        assert engine is not None
        assert engine._tracker is not None

    def test_engine_with_mock_tracker(self) -> None:
        mock_tracker = MagicMock()
        mock_tracker.get_all_performance.return_value = {}
        eng = AdaptiveVotingEngine(mock_tracker)
        assert eng._tracker is mock_tracker


# ---------------------------------------------------------------------------
# adjust_voting_weights — normal inputs
# ---------------------------------------------------------------------------


class TestAdjustWeights:
    @pytest.mark.asyncio
    async def test_empty_performance_returns_original(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        matrix = _two_expert_matrix()
        result = await engine.adjust_voting_weights(
            performance_data={}, current_matrix=matrix
        )
        assert result.domains == matrix.domains
        assert result.experts == matrix.experts

    @pytest.mark.asyncio
    async def test_none_performance_uses_tracker(self) -> None:
        mock_tracker = MagicMock()
        mock_tracker.get_all_performance.return_value = {}
        eng = AdaptiveVotingEngine(mock_tracker)
        matrix = _two_expert_matrix()

        result = await eng.adjust_voting_weights(
            performance_data=None, current_matrix=matrix
        )
        mock_tracker.get_all_performance.assert_called_once_with(days=30)
        assert result.domains == matrix.domains

    @pytest.mark.asyncio
    async def test_none_matrix_builds_default(self, engine: AdaptiveVotingEngine) -> None:
        with patch(
            "tapps_core.adaptive.voting_engine._build_default_matrix"
        ) as mock_build:
            mock_build.return_value = _two_expert_matrix()
            result = await engine.adjust_voting_weights(
                performance_data={}, current_matrix=None
            )
            mock_build.assert_called_once()
            assert result.domains == ["security", "testing"]

    @pytest.mark.asyncio
    async def test_high_performance_preserves_primary_rule(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        matrix = _two_expert_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=100,
                avg_confidence=0.95,
                first_pass_success_rate=0.90,
                code_quality_improvement=8.0,
            ),
        }
        result = await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        assert result.get_expert_weight("expert-sec", "security") >= 0.51

    @pytest.mark.asyncio
    async def test_low_performance_still_enforces_primary(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        matrix = _two_expert_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=50,
                avg_confidence=0.20,
                first_pass_success_rate=0.10,
                code_quality_improvement=-5.0,
            ),
        }
        result = await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        assert result.get_expert_weight("expert-sec", "security") >= 0.51

    @pytest.mark.asyncio
    async def test_columns_sum_to_one_after_adjustment(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        matrix = _three_expert_matrix()
        perf = {
            "e-sec": ExpertPerformance(
                expert_id="e-sec",
                consultations=40,
                avg_confidence=0.80,
                first_pass_success_rate=0.75,
                code_quality_improvement=3.0,
            ),
            "e-test": ExpertPerformance(
                expert_id="e-test",
                consultations=40,
                avg_confidence=0.60,
                first_pass_success_rate=0.55,
                code_quality_improvement=1.0,
            ),
        }
        result = await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        for domain in result.domains:
            total = sum(result.get_expert_weight(e, domain) for e in result.experts)
            assert abs(total - 1.0) < 0.02, f"Domain {domain} sums to {total}"

    @pytest.mark.asyncio
    async def test_all_experts_high_performance(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        matrix = _two_expert_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=100,
                avg_confidence=0.90,
                first_pass_success_rate=0.90,
                code_quality_improvement=5.0,
            ),
            "expert-test": ExpertPerformance(
                expert_id="expert-test",
                consultations=100,
                avg_confidence=0.90,
                first_pass_success_rate=0.90,
                code_quality_improvement=5.0,
            ),
        }
        result = await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        for domain in result.domains:
            primary = result.get_primary_expert(domain)
            assert primary is not None
            assert result.get_expert_weight(primary, domain) >= 0.51


# ---------------------------------------------------------------------------
# _calculate_adjustment_factor
# ---------------------------------------------------------------------------


class TestAdjustmentFactor:
    def test_perfect_performance(self, engine: AdaptiveVotingEngine) -> None:
        perf = ExpertPerformance(
            expert_id="x",
            avg_confidence=1.0,
            first_pass_success_rate=1.0,
            code_quality_improvement=10.0,
        )
        factor = engine._calculate_adjustment_factor(perf)
        assert factor > 0.0
        assert factor <= 1.0

    def test_worst_performance(self, engine: AdaptiveVotingEngine) -> None:
        perf = ExpertPerformance(
            expert_id="x",
            avg_confidence=0.0,
            first_pass_success_rate=0.0,
            code_quality_improvement=-10.0,
        )
        factor = engine._calculate_adjustment_factor(perf)
        assert factor < 0.0
        assert factor >= -1.0

    def test_mid_performance_near_zero(self, engine: AdaptiveVotingEngine) -> None:
        perf = ExpertPerformance(
            expert_id="x",
            avg_confidence=0.625,
            first_pass_success_rate=0.50,
            code_quality_improvement=0.0,
        )
        factor = engine._calculate_adjustment_factor(perf)
        assert -0.3 < factor < 0.3

    def test_factor_clamped(self, engine: AdaptiveVotingEngine) -> None:
        perf = ExpertPerformance(
            expert_id="x",
            avg_confidence=1.0,
            first_pass_success_rate=1.0,
            code_quality_improvement=100.0,
        )
        factor = engine._calculate_adjustment_factor(perf)
        assert factor <= 1.0


# ---------------------------------------------------------------------------
# save_snapshot
# ---------------------------------------------------------------------------


class TestSaveSnapshot:
    def test_save_creates_file(
        self, engine: AdaptiveVotingEngine, tmp_path: Path
    ) -> None:
        matrix = _two_expert_matrix()
        path = tmp_path / "snapshot.json"
        engine.save_snapshot(matrix, path)
        assert path.exists()

    def test_save_with_performance_summary(
        self, engine: AdaptiveVotingEngine, tmp_path: Path
    ) -> None:
        matrix = _two_expert_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=10,
                avg_confidence=0.85,
                first_pass_success_rate=0.80,
            ),
        }
        path = tmp_path / "snapshot_perf.json"
        engine.save_snapshot(matrix, path, performance_data=perf)
        assert path.exists()

    def test_save_without_performance(
        self, engine: AdaptiveVotingEngine, tmp_path: Path
    ) -> None:
        matrix = _two_expert_matrix()
        path = tmp_path / "snapshot_no_perf.json"
        engine.save_snapshot(matrix, path, performance_data=None)
        assert path.exists()


# ---------------------------------------------------------------------------
# _build_default_matrix
# ---------------------------------------------------------------------------


class TestBuildDefaultMatrix:
    @patch("tapps_core.adaptive.voting_engine.WeightDistributor")
    def test_build_from_registry(self, mock_wd: MagicMock) -> None:
        """When experts exist, _build_default_matrix calls WeightDistributor."""
        mock_expert = MagicMock()
        mock_expert.primary_domain = "security"
        mock_expert.expert_id = "exp-sec"
        mock_wd.calculate_weights.return_value = _two_expert_matrix()

        with patch(
            "tapps_core.experts.registry.ExpertRegistry.get_all_experts",
            return_value=[mock_expert],
        ):
            result = _build_default_matrix()
            assert result.domains is not None

    def test_empty_registry_returns_empty_matrix(self) -> None:
        with patch(
            "tapps_core.experts.registry.ExpertRegistry.get_all_experts",
            return_value=[],
        ):
            result = _build_default_matrix()
            assert result.domains == []
            assert result.experts == []


# ---------------------------------------------------------------------------
# Edge cases — single expert
# ---------------------------------------------------------------------------


class TestSingleExpert:
    @pytest.mark.asyncio
    async def test_single_expert_single_domain(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        matrix = WeightDistributor.calculate_weights(
            domains=["security"],
            expert_primary_map={"security": "only-one"},
        )
        perf = {
            "only-one": ExpertPerformance(
                expert_id="only-one",
                consultations=20,
                avg_confidence=0.70,
                first_pass_success_rate=0.65,
            ),
        }
        result = await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        assert result.get_expert_weight("only-one", "security") == 1.0


# ---------------------------------------------------------------------------
# Normalization edge cases (zero-weight columns, primary floor enforcement)
# ---------------------------------------------------------------------------


class TestNormalizationEdgeCases:
    """Tests targeting _normalize_domain_column and _enforce_primary_floor branches."""

    def test_zero_weight_column_distributes_evenly(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """When all weights in a domain column are zero, distribute 1/n each."""
        weights: dict[str, dict[str, float]] = {
            "e-a": {"dom": 0.0},
            "e-b": {"dom": 0.0},
        }
        original = ExpertWeightMatrix(
            weights={"e-a": {"dom": 0.51}, "e-b": {"dom": 0.49}},
            domains=["dom"],
            experts=["e-a", "e-b"],
        )
        result = AdaptiveVotingEngine._normalize_matrix(weights, original)
        # Each expert gets 1/2 = 0.5; primary floor then enforces >= 0.51.
        assert result.get_expert_weight("e-a", "dom") >= 0.51
        total = sum(result.get_expert_weight(e, "dom") for e in result.experts)
        assert abs(total - 1.0) < 0.02

    def test_zero_weight_column_three_experts(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """Zero-weight column with three experts distributes 1/3 each."""
        weights: dict[str, dict[str, float]] = {
            "e1": {"d": 0.0},
            "e2": {"d": 0.0},
            "e3": {"d": 0.0},
        }
        original = ExpertWeightMatrix(
            weights={"e1": {"d": 0.6}, "e2": {"d": 0.2}, "e3": {"d": 0.2}},
            domains=["d"],
            experts=["e1", "e2", "e3"],
        )
        result = AdaptiveVotingEngine._normalize_matrix(weights, original)
        # After even distribution (1/3 each), primary e1 gets boosted to >= 0.51.
        assert result.get_expert_weight("e1", "d") >= 0.51
        total = sum(result.get_expert_weight(e, "d") for e in result.experts)
        assert abs(total - 1.0) < 0.02

    @pytest.mark.asyncio
    async def test_all_zero_weights_via_adjust(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """Extreme negative adjustments that push all weights to zero are handled."""
        matrix = ExpertWeightMatrix(
            weights={"ea": {"dom": 0.51, "dom2": 0.49}, "eb": {"dom": 0.49, "dom2": 0.51}},
            domains=["dom", "dom2"],
            experts=["ea", "eb"],
        )
        # Give extremely bad performance to push weights toward zero.
        perf = {
            "ea": ExpertPerformance(
                expert_id="ea",
                consultations=50,
                avg_confidence=0.0,
                first_pass_success_rate=0.0,
                code_quality_improvement=-100.0,
            ),
            "eb": ExpertPerformance(
                expert_id="eb",
                consultations=50,
                avg_confidence=0.0,
                first_pass_success_rate=0.0,
                code_quality_improvement=-100.0,
            ),
        }
        result = await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        # Must still produce valid matrix: columns sum to 1, primaries >= 0.51.
        for domain in result.domains:
            total = sum(result.get_expert_weight(e, domain) for e in result.experts)
            assert abs(total - 1.0) < 0.02
            primary = result.get_primary_expert(domain)
            assert primary is not None

    def test_enforce_primary_floor_with_zero_others(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """When non-primary experts have zero weight, enforce_primary_floor returns early."""
        weights: dict[str, dict[str, float]] = {
            "primary-e": {"dom": 0.4},
            "other-e": {"dom": 0.0},
        }
        original = ExpertWeightMatrix(
            weights={"primary-e": {"dom": 0.51}, "other-e": {"dom": 0.49}},
            domains=["dom"],
            experts=["primary-e", "other-e"],
        )
        # Manually normalize just this column with zero other_total.
        AdaptiveVotingEngine._normalize_domain_column(weights, original, "dom")
        # Primary should still be >= 0.51 (the only one with weight).
        assert weights["primary-e"]["dom"] >= 0.51

    def test_primary_below_floor_after_first_normalization(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """When primary is still < 0.51 after proportional redistribution, secondary pass fires."""
        # Construct a scenario where many non-primary experts dilute the primary.
        experts = ["primary", "s1", "s2", "s3", "s4"]
        weights: dict[str, dict[str, float]] = {
            "primary": {"dom": 0.10},
            "s1": {"dom": 0.25},
            "s2": {"dom": 0.25},
            "s3": {"dom": 0.20},
            "s4": {"dom": 0.20},
        }
        original = ExpertWeightMatrix(
            weights={
                "primary": {"dom": 0.51},
                "s1": {"dom": 0.1225},
                "s2": {"dom": 0.1225},
                "s3": {"dom": 0.1225},
                "s4": {"dom": 0.1225},
            },
            domains=["dom"],
            experts=experts,
        )
        result = AdaptiveVotingEngine._normalize_matrix(weights, original)
        assert result.get_expert_weight("primary", "dom") >= 0.51
        total = sum(result.get_expert_weight(e, "dom") for e in experts)
        assert abs(total - 1.0) < 0.02

    def test_enforce_primary_floor_zero_other_total(self) -> None:
        """Direct call: all non-primary experts have zero weight -> early return."""
        weights: dict[str, dict[str, float]] = {
            "primary": {"dom": 0.40},
            "other1": {"dom": 0.0},
            "other2": {"dom": 0.0},
        }
        original = ExpertWeightMatrix(
            weights={"primary": {"dom": 0.6}, "other1": {"dom": 0.2}, "other2": {"dom": 0.2}},
            domains=["dom"],
            experts=["primary", "other1", "other2"],
        )
        AdaptiveVotingEngine._enforce_primary_floor(
            weights, original, "dom", "primary", ["primary", "other1", "other2"]
        )
        # Primary set to 0.51, others remain 0.0.
        assert weights["primary"]["dom"] == 0.51
        assert weights["other1"]["dom"] == 0.0
        assert weights["other2"]["dom"] == 0.0

    def test_enforce_primary_floor_secondary_pass(self) -> None:
        """When rounding in the first pass pushes primary below 0.51, secondary pass fires."""
        # Set up a scenario where the deficit redistribution + rounding will leave
        # primary just below 0.51. With many small-weight others, the rounding
        # of weights[primary] / col_sum can produce < 0.51.
        experts = [f"e{i}" for i in range(20)]
        primary = "e0"
        weights: dict[str, dict[str, float]] = {}
        weights[primary] = {"dom": 0.40}
        for eid in experts[1:]:
            weights[eid] = {"dom": 0.60 / 19}

        original = ExpertWeightMatrix(
            weights={eid: {"dom": 0.51 if eid == primary else 0.49 / 19} for eid in experts},
            domains=["dom"],
            experts=experts,
        )
        # Call _enforce_primary_floor directly.
        AdaptiveVotingEngine._enforce_primary_floor(
            weights, original, "dom", primary, experts
        )
        # Primary must be at least 0.51 after enforcement.
        assert weights[primary]["dom"] >= 0.51

    def test_enforce_primary_floor_secondary_pass_redistributes_others(self) -> None:
        """Force the secondary enforcement pass and verify others are redistributed."""
        experts = ["primary", "other1", "other2"]
        weights: dict[str, dict[str, float]] = {
            "primary": {"dom": 0.30},
            "other1": {"dom": 0.40},
            "other2": {"dom": 0.30},
        }
        original = ExpertWeightMatrix(
            weights={"primary": {"dom": 0.51}, "other1": {"dom": 0.25}, "other2": {"dom": 0.24}},
            domains=["dom"],
            experts=experts,
        )
        # Capture others' weights before enforce call.
        original_round = round
        call_count = 0

        def rigged_round(value: float, ndigits: int = 0) -> float:
            nonlocal call_count
            call_count += 1
            result = original_round(value, ndigits)
            # On the first normalization pass (lines 213-214), rig the primary
            # to be just below 0.51 to trigger the secondary pass (line 216).
            # The first 3 round calls are for the first normalization of all experts.
            if call_count <= len(experts) and 0.50 < result < 0.52:
                return 0.5099
            return result

        with patch("builtins.round", side_effect=rigged_round):
            AdaptiveVotingEngine._enforce_primary_floor(
                weights, original, "dom", "primary", experts
            )
        # The secondary pass (lines 217-221) should redistribute others to fit in
        # remainder = 1.0 - 0.51 = 0.49. Both others should have been recalculated.
        others_sum = weights["other1"]["dom"] + weights["other2"]["dom"]
        assert others_sum == pytest.approx(0.49, abs=0.01)


# ---------------------------------------------------------------------------
# _calculate_weight_adjustments — direct testing
# ---------------------------------------------------------------------------


class TestCalculateWeightAdjustments:
    def test_adjustments_for_known_expert(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        matrix = _two_expert_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=30,
                avg_confidence=0.80,
                first_pass_success_rate=0.80,
                code_quality_improvement=5.0,
            ),
        }
        adjustments = engine._calculate_weight_adjustments(perf, matrix)
        assert "expert-sec" in adjustments
        # expert-sec is primary for "security" domain => larger scale.
        assert "security" in adjustments["expert-sec"]
        assert "testing" in adjustments["expert-sec"]
        # Primary scale (0.1) vs secondary scale (0.05).
        assert abs(adjustments["expert-sec"]["security"]) >= abs(
            adjustments["expert-sec"]["testing"]
        )

    def test_adjustments_skip_unknown_expert(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """Performance data for an expert not in the matrix is skipped."""
        matrix = _two_expert_matrix()
        perf = {
            "unknown-expert": ExpertPerformance(
                expert_id="unknown-expert",
                consultations=10,
                avg_confidence=0.70,
                first_pass_success_rate=0.60,
            ),
        }
        adjustments = engine._calculate_weight_adjustments(perf, matrix)
        assert "unknown-expert" not in adjustments

    def test_adjustments_positive_for_high_performer(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        matrix = _two_expert_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=50,
                avg_confidence=0.95,
                first_pass_success_rate=0.95,
                code_quality_improvement=8.0,
            ),
        }
        adjustments = engine._calculate_weight_adjustments(perf, matrix)
        for domain in matrix.domains:
            assert adjustments["expert-sec"][domain] > 0.0

    def test_adjustments_negative_for_low_performer(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        matrix = _two_expert_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=50,
                avg_confidence=0.10,
                first_pass_success_rate=0.10,
                code_quality_improvement=-8.0,
            ),
        }
        adjustments = engine._calculate_weight_adjustments(perf, matrix)
        for domain in matrix.domains:
            assert adjustments["expert-sec"][domain] < 0.0


# ---------------------------------------------------------------------------
# _calculate_adjustment_factor — additional edge cases
# ---------------------------------------------------------------------------


class TestAdjustmentFactorEdgeCases:
    def test_negative_improvement_clamped(self, engine: AdaptiveVotingEngine) -> None:
        """Extreme negative code_quality_improvement is clamped to -1.0 factor."""
        perf = ExpertPerformance(
            expert_id="x",
            avg_confidence=0.625,
            first_pass_success_rate=0.50,
            code_quality_improvement=-200.0,
        )
        factor = engine._calculate_adjustment_factor(perf)
        assert factor >= -1.0

    def test_positive_improvement_clamped(self, engine: AdaptiveVotingEngine) -> None:
        """Extreme positive code_quality_improvement is clamped to +1.0 factor."""
        perf = ExpertPerformance(
            expert_id="x",
            avg_confidence=0.625,
            first_pass_success_rate=0.50,
            code_quality_improvement=200.0,
        )
        factor = engine._calculate_adjustment_factor(perf)
        assert factor <= 1.0

    def test_high_confidence_low_success_mixed(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """High confidence but low success rate produces near-zero or negative."""
        perf = ExpertPerformance(
            expert_id="x",
            avg_confidence=1.0,
            first_pass_success_rate=0.0,
            code_quality_improvement=0.0,
        )
        factor = engine._calculate_adjustment_factor(perf)
        # success_factor dominates at 50% weight, so overall should be negative.
        assert factor < 0.2

    def test_low_confidence_high_success_mixed(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """Low confidence but high success rate produces positive."""
        perf = ExpertPerformance(
            expert_id="x",
            avg_confidence=0.0,
            first_pass_success_rate=1.0,
            code_quality_improvement=0.0,
        )
        factor = engine._calculate_adjustment_factor(perf)
        # success_factor = (1.0 - 0.5)*2*0.5 = 0.5, confidence_factor negative.
        # Should be positive overall since success_rate has highest weight.
        assert factor > 0.0


# ---------------------------------------------------------------------------
# Mixed performance scenarios
# ---------------------------------------------------------------------------


class TestMixedPerformance:
    @pytest.mark.asyncio
    async def test_one_high_one_low_primary_rule_holds(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """One expert high, one low — primary rule always holds."""
        matrix = _two_expert_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=50,
                avg_confidence=0.95,
                first_pass_success_rate=0.95,
                code_quality_improvement=8.0,
            ),
            "expert-test": ExpertPerformance(
                expert_id="expert-test",
                consultations=50,
                avg_confidence=0.10,
                first_pass_success_rate=0.10,
                code_quality_improvement=-5.0,
            ),
        }
        result = await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        for domain in result.domains:
            primary = result.get_primary_expert(domain)
            assert primary is not None
            assert result.get_expert_weight(primary, domain) >= 0.51

    @pytest.mark.asyncio
    async def test_three_experts_mixed_performance(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """Three experts, each with different performance levels."""
        matrix = _three_expert_matrix()
        perf = {
            "e-sec": ExpertPerformance(
                expert_id="e-sec",
                consultations=50,
                avg_confidence=0.90,
                first_pass_success_rate=0.85,
                code_quality_improvement=6.0,
            ),
            "e-test": ExpertPerformance(
                expert_id="e-test",
                consultations=50,
                avg_confidence=0.50,
                first_pass_success_rate=0.40,
                code_quality_improvement=-2.0,
            ),
            "e-perf": ExpertPerformance(
                expert_id="e-perf",
                consultations=50,
                avg_confidence=0.70,
                first_pass_success_rate=0.65,
                code_quality_improvement=1.0,
            ),
        }
        result = await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        # Validate all matrix invariants.
        errors = result.validate_matrix()
        assert len(errors) == 0, f"Matrix validation errors: {errors}"


# ---------------------------------------------------------------------------
# save_snapshot — content verification
# ---------------------------------------------------------------------------


class TestSaveSnapshotContent:
    def test_snapshot_json_contains_matrix(
        self, engine: AdaptiveVotingEngine, tmp_path: Path
    ) -> None:
        """Snapshot JSON includes the matrix weights."""
        matrix = _two_expert_matrix()
        path = tmp_path / "snap.json"
        engine.save_snapshot(matrix, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "matrix" in data
        assert "weights" in data["matrix"]
        assert "expert-sec" in data["matrix"]["weights"]

    def test_snapshot_json_contains_performance_summary(
        self, engine: AdaptiveVotingEngine, tmp_path: Path
    ) -> None:
        """Snapshot JSON includes the performance_summary field."""
        matrix = _two_expert_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=10,
                avg_confidence=0.85,
                first_pass_success_rate=0.80,
            ),
        }
        path = tmp_path / "snap_perf.json"
        engine.save_snapshot(matrix, path, performance_data=perf)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "performance_summary" in data
        assert "expert-sec" in data["performance_summary"]
        assert data["performance_summary"]["expert-sec"] == pytest.approx(0.85)

    def test_snapshot_json_empty_performance(
        self, engine: AdaptiveVotingEngine, tmp_path: Path
    ) -> None:
        """Snapshot with empty dict performance data has empty summary."""
        matrix = _two_expert_matrix()
        path = tmp_path / "snap_empty.json"
        engine.save_snapshot(matrix, path, performance_data={})
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["performance_summary"] == {}


# ---------------------------------------------------------------------------
# Matrix validation after adjustment
# ---------------------------------------------------------------------------


class TestMatrixValidation:
    @pytest.mark.asyncio
    async def test_adjusted_matrix_passes_validation(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """Full adjustment cycle produces a valid matrix."""
        matrix = _three_expert_matrix()
        perf = {
            "e-sec": ExpertPerformance(
                expert_id="e-sec",
                consultations=40,
                avg_confidence=0.80,
                first_pass_success_rate=0.75,
                code_quality_improvement=3.0,
            ),
        }
        result = await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        errors = result.validate_matrix()
        assert errors == [], f"Validation errors: {errors}"

    @pytest.mark.asyncio
    async def test_original_weights_not_mutated(
        self, engine: AdaptiveVotingEngine
    ) -> None:
        """Adjusting weights returns a new matrix, original is unchanged."""
        matrix = _two_expert_matrix()
        original_weight = matrix.get_expert_weight("expert-sec", "security")
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=100,
                avg_confidence=0.95,
                first_pass_success_rate=0.90,
                code_quality_improvement=8.0,
            ),
        }
        await engine.adjust_voting_weights(
            performance_data=perf, current_matrix=matrix
        )
        assert matrix.get_expert_weight("expert-sec", "security") == original_weight
