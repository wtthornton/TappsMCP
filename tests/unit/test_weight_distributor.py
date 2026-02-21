"""Tests for tapps_mcp.adaptive.weight_distributor."""

from __future__ import annotations

import pytest

from tapps_mcp.adaptive.weight_distributor import WeightDistributor


class TestCalculateWeights:
    """Core weight distribution logic."""

    def test_single_expert_single_domain(self) -> None:
        matrix = WeightDistributor.calculate_weights(
            domains=["security"],
            expert_primary_map={"security": "expert_a"},
        )
        assert matrix.get_expert_weight("expert_a", "security") == 1.0

    def test_two_experts_two_domains(self) -> None:
        matrix = WeightDistributor.calculate_weights(
            domains=["security", "testing"],
            expert_primary_map={"security": "expert_a", "testing": "expert_b"},
        )
        # Primary gets ~0.51, other gets ~0.49
        assert matrix.get_expert_weight("expert_a", "security") == pytest.approx(0.51, abs=0.01)
        assert matrix.get_expert_weight("expert_b", "security") == pytest.approx(0.49, abs=0.01)

    def test_columns_sum_to_one(self) -> None:
        domains = ["security", "testing", "architecture"]
        matrix = WeightDistributor.calculate_weights(
            domains=domains,
            expert_primary_map={
                "security": "expert_a",
                "testing": "expert_b",
                "architecture": "expert_c",
            },
        )
        for d in domains:
            col_sum = sum(matrix.get_expert_weight(e, d) for e in matrix.experts)
            assert col_sum == pytest.approx(1.0, abs=0.001), f"Column {d} sums to {col_sum}"

    def test_missing_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="no primary expert"):
            WeightDistributor.calculate_weights(
                domains=["security", "testing"],
                expert_primary_map={"security": "expert_a"},
            )

    def test_three_experts_three_domains(self) -> None:
        matrix = WeightDistributor.calculate_weights(
            domains=["a", "b", "c"],
            expert_primary_map={"a": "e1", "b": "e2", "c": "e3"},
        )
        assert len(matrix.experts) == 3
        assert len(matrix.domains) == 3
        # Primary should always be highest
        assert matrix.get_expert_weight("e1", "a") > matrix.get_expert_weight("e2", "a")


class TestRecalculateOnDomainAdd:
    """Adding a new domain recalculates the matrix."""

    def test_add_domain(self) -> None:
        matrix = WeightDistributor.calculate_weights(
            domains=["security"],
            expert_primary_map={"security": "expert_a"},
        )
        updated = WeightDistributor.recalculate_on_domain_add(matrix, "testing", "expert_b")
        assert "testing" in updated.domains
        assert "expert_b" in updated.experts
        # All columns still sum to 1.0
        for d in updated.domains:
            col_sum = sum(updated.get_expert_weight(e, d) for e in updated.experts)
            assert col_sum == pytest.approx(1.0, abs=0.001)


class TestFormatMatrix:
    """Matrix formatting for display."""

    def test_empty_matrix(self) -> None:
        from tapps_mcp.adaptive.models import ExpertWeightMatrix

        matrix = ExpertWeightMatrix(weights={}, domains=[], experts=[])
        assert WeightDistributor.format_matrix(matrix) == "(empty matrix)"

    def test_non_empty_matrix(self) -> None:
        matrix = WeightDistributor.calculate_weights(
            domains=["security", "testing"],
            expert_primary_map={"security": "expert_a", "testing": "expert_b"},
        )
        text = WeightDistributor.format_matrix(matrix)
        assert "expert_a" in text
        assert "expert_b" in text
        assert "security" in text
