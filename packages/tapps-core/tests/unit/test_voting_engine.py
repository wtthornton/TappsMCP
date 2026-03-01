"""Tests for adaptive voting engine — AdaptiveVotingEngine."""

from __future__ import annotations

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
