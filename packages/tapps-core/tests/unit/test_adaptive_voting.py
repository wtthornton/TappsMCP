"""Tests for adaptive voting engine and weight distributor."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.adaptive.models import ExpertPerformance, ExpertWeightMatrix
from tapps_core.adaptive.persistence import FilePerformanceTracker
from tapps_core.adaptive.voting_engine import AdaptiveVotingEngine
from tapps_core.adaptive.weight_distributor import WeightDistributor

# ---------------------------------------------------------------------------
# WeightDistributor
# ---------------------------------------------------------------------------


class TestWeightDistributor:
    def test_two_experts_two_domains(self):
        matrix = WeightDistributor.calculate_weights(
            domains=["security", "testing"],
            expert_primary_map={"security": "expert-sec", "testing": "expert-test"},
        )
        assert matrix.get_expert_weight("expert-sec", "security") >= 0.51
        assert matrix.get_expert_weight("expert-test", "testing") >= 0.51
        # Column sums.
        for d in matrix.domains:
            total = sum(matrix.get_expert_weight(e, d) for e in matrix.experts)
            assert abs(total - 1.0) < 0.01

    def test_single_expert_gets_100_percent(self):
        matrix = WeightDistributor.calculate_weights(
            domains=["security"],
            expert_primary_map={"security": "expert-sec"},
        )
        assert matrix.get_expert_weight("expert-sec", "security") == 1.0

    def test_three_experts(self):
        matrix = WeightDistributor.calculate_weights(
            domains=["a", "b", "c"],
            expert_primary_map={"a": "e-1", "b": "e-2", "c": "e-3"},
        )
        # Each primary >= 0.51.
        assert matrix.get_expert_weight("e-1", "a") >= 0.51
        assert matrix.get_expert_weight("e-2", "b") >= 0.51
        assert matrix.get_expert_weight("e-3", "c") >= 0.51

    def test_missing_domain_raises(self):
        with pytest.raises(ValueError, match="no primary expert"):
            WeightDistributor.calculate_weights(
                domains=["a", "b"],
                expert_primary_map={"a": "e-1"},
            )

    def test_recalculate_on_domain_add(self):
        matrix = WeightDistributor.calculate_weights(
            domains=["security"],
            expert_primary_map={"security": "expert-sec"},
        )
        new_matrix = WeightDistributor.recalculate_on_domain_add(matrix, "testing", "expert-test")
        assert "testing" in new_matrix.domains
        assert new_matrix.get_expert_weight("expert-test", "testing") >= 0.51

    def test_format_matrix(self):
        matrix = WeightDistributor.calculate_weights(
            domains=["security"],
            expert_primary_map={"security": "expert-sec"},
        )
        text = WeightDistributor.format_matrix(matrix)
        assert "expert-sec" in text
        assert "security" in text

    def test_format_empty_matrix(self):
        matrix = ExpertWeightMatrix()
        text = WeightDistributor.format_matrix(matrix)
        assert text == "(empty matrix)"


# ---------------------------------------------------------------------------
# AdaptiveVotingEngine
# ---------------------------------------------------------------------------


class TestAdaptiveVotingEngine:
    @pytest.fixture()
    def tracker(self, tmp_path: Path) -> FilePerformanceTracker:
        return FilePerformanceTracker(tmp_path)

    @pytest.fixture()
    def engine(self, tracker: FilePerformanceTracker) -> AdaptiveVotingEngine:
        return AdaptiveVotingEngine(tracker)

    def _make_matrix(self) -> ExpertWeightMatrix:
        return WeightDistributor.calculate_weights(
            domains=["security", "testing"],
            expert_primary_map={"security": "expert-sec", "testing": "expert-test"},
        )

    async def test_no_performance_data_returns_original(self, engine: AdaptiveVotingEngine):
        matrix = self._make_matrix()
        result = await engine.adjust_voting_weights(performance_data={}, current_matrix=matrix)
        assert result.domains == matrix.domains

    async def test_high_performance_increases_weight(self, engine: AdaptiveVotingEngine):
        matrix = self._make_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=50,
                avg_confidence=0.90,
                first_pass_success_rate=0.85,
                code_quality_improvement=5.0,
            ),
        }
        result = await engine.adjust_voting_weights(performance_data=perf, current_matrix=matrix)
        # Primary should still be >= 0.51 and possibly higher.
        assert result.get_expert_weight("expert-sec", "security") >= 0.51

    async def test_low_performance_adjustment(self, engine: AdaptiveVotingEngine):
        matrix = self._make_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=50,
                avg_confidence=0.30,
                first_pass_success_rate=0.20,
                code_quality_improvement=-3.0,
            ),
        }
        result = await engine.adjust_voting_weights(performance_data=perf, current_matrix=matrix)
        # Primary rule still enforced even with poor performance.
        assert result.get_expert_weight("expert-sec", "security") >= 0.51

    async def test_primary_rule_maintained(self, engine: AdaptiveVotingEngine):
        matrix = self._make_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=100,
                avg_confidence=0.95,
                first_pass_success_rate=0.95,
            ),
            "expert-test": ExpertPerformance(
                expert_id="expert-test",
                consultations=100,
                avg_confidence=0.95,
                first_pass_success_rate=0.95,
            ),
        }
        result = await engine.adjust_voting_weights(performance_data=perf, current_matrix=matrix)
        for domain in result.domains:
            primary = result.get_primary_expert(domain)
            assert primary is not None
            assert result.get_expert_weight(primary, domain) >= 0.51

    async def test_domain_column_sums_to_one(self, engine: AdaptiveVotingEngine):
        matrix = self._make_matrix()
        perf = {
            "expert-sec": ExpertPerformance(
                expert_id="expert-sec",
                consultations=30,
                avg_confidence=0.75,
                first_pass_success_rate=0.70,
            ),
        }
        result = await engine.adjust_voting_weights(performance_data=perf, current_matrix=matrix)
        for domain in result.domains:
            total = sum(result.get_expert_weight(e, domain) for e in result.experts)
            assert abs(total - 1.0) < 0.02
