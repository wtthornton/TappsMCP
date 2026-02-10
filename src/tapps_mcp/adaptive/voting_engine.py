"""Adaptive voting engine for expert weight adjustment.

Adjusts expert voting weights based on performance data while enforcing
the 51% primary expert constraint.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any

import structlog

from tapps_mcp.adaptive.models import (
    ExpertPerformance,
    ExpertWeightMatrix,
    ExpertWeightsSnapshot,
)
from tapps_mcp.adaptive.persistence import save_json_atomic
from tapps_mcp.adaptive.weight_distributor import WeightDistributor

if TYPE_CHECKING:
    from tapps_mcp.adaptive.protocols import PerformanceTrackerProtocol

logger = structlog.get_logger(__name__)

# Performance thresholds.
_HIGH_PERFORMANCE_THRESHOLD = 0.75
_LOW_PERFORMANCE_THRESHOLD = 0.50

# Adjustment scaling factors.
_PRIMARY_ADJUSTMENT_SCALE = 0.1
_SECONDARY_ADJUSTMENT_SCALE = 0.05

# Primary expert weight floor (51% rule).
_PRIMARY_WEIGHT_FLOOR = 0.51


class AdaptiveVotingEngine:
    """Adjusts expert voting weights based on consultation performance.

    High-performing experts get increased weight; low-performing experts
    get decreased weight.  The 51% primary rule is always enforced.
    """

    def __init__(self, performance_tracker: PerformanceTrackerProtocol) -> None:
        self._tracker = performance_tracker

    async def adjust_voting_weights(
        self,
        performance_data: dict[str, ExpertPerformance] | None = None,
        current_matrix: ExpertWeightMatrix | None = None,
    ) -> ExpertWeightMatrix:
        """Compute adjusted voting weights.

        If *current_matrix* is ``None``, a default matrix is built from
        :class:`ExpertRegistry`.
        """
        if current_matrix is None:
            current_matrix = _build_default_matrix()

        if performance_data is None:
            performance_data = self._tracker.get_all_performance(days=30)

        if not performance_data:
            return current_matrix

        adjustments = self._calculate_weight_adjustments(performance_data, current_matrix)
        return self._apply_adjustments(current_matrix, adjustments)

    def save_snapshot(
        self,
        matrix: ExpertWeightMatrix,
        snapshot_path: Path,
        performance_data: dict[str, ExpertPerformance] | None = None,
    ) -> None:
        """Persist an :class:`ExpertWeightsSnapshot`."""
        summary: dict[str, Any] = {}
        if performance_data:
            summary = {eid: p.avg_confidence for eid, p in performance_data.items()}
        snapshot = ExpertWeightsSnapshot(
            matrix=matrix,
            performance_summary=summary,
        )
        save_json_atomic(snapshot.model_dump(), snapshot_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_weight_adjustments(
        self,
        performance_data: dict[str, ExpertPerformance],
        current_matrix: ExpertWeightMatrix,
    ) -> dict[str, dict[str, float]]:
        """Compute per-expert per-domain adjustment deltas."""
        adjustments: dict[str, dict[str, float]] = {}

        for eid in current_matrix.experts:
            perf = performance_data.get(eid)
            if perf is None:
                continue

            factor = self._calculate_adjustment_factor(perf)
            adj: dict[str, float] = {}

            for domain in current_matrix.domains:
                is_primary = current_matrix.get_primary_expert(domain) == eid
                scale = _PRIMARY_ADJUSTMENT_SCALE if is_primary else _SECONDARY_ADJUSTMENT_SCALE
                adj[domain] = round(factor * scale, 6)

            adjustments[eid] = adj

        return adjustments

    @staticmethod
    def _calculate_adjustment_factor(perf: ExpertPerformance) -> float:
        """Compute a signed adjustment factor from -1.0 to 1.0.

        Weighting: success_rate (50%), confidence (30%), improvement (20%).
        """
        # Normalize success rate around threshold.
        success_factor = (perf.first_pass_success_rate - _LOW_PERFORMANCE_THRESHOLD) * 2.0

        # Normalize confidence around mid-threshold.
        mid = (_HIGH_PERFORMANCE_THRESHOLD + _LOW_PERFORMANCE_THRESHOLD) / 2.0
        confidence_factor = (perf.avg_confidence - mid) * 2.0

        # Quality improvement already signed.
        improvement_factor = max(-1.0, min(1.0, perf.code_quality_improvement / 10.0))

        raw = success_factor * 0.5 + confidence_factor * 0.3 + improvement_factor * 0.2
        return max(-1.0, min(1.0, raw))

    def _apply_adjustments(
        self,
        current_matrix: ExpertWeightMatrix,
        adjustments: dict[str, dict[str, float]],
    ) -> ExpertWeightMatrix:
        """Apply adjustments and normalize to maintain the 51% primary rule."""
        new_weights: dict[str, dict[str, float]] = {}

        for eid in current_matrix.experts:
            new_weights[eid] = {}
            for domain in current_matrix.domains:
                base = current_matrix.get_expert_weight(eid, domain)
                delta = adjustments.get(eid, {}).get(domain, 0.0)
                new_weights[eid][domain] = max(0.0, base + delta)

        # Normalize per-domain and enforce primary rule.
        return self._normalize_matrix(new_weights, current_matrix)

    @staticmethod
    def _normalize_matrix(
        weights: dict[str, dict[str, float]],
        original_matrix: ExpertWeightMatrix,
    ) -> ExpertWeightMatrix:
        """Normalize weights per domain: sum to 1.0, primary >= 0.51."""
        for domain in original_matrix.domains:
            primary = original_matrix.get_primary_expert(domain)
            col_sum = sum(weights[eid].get(domain, 0.0) for eid in original_matrix.experts)

            if col_sum <= 0:
                # Reset to uniform.
                n = len(original_matrix.experts)
                for eid in original_matrix.experts:
                    weights[eid][domain] = 1.0 / n
                col_sum = 1.0

            # Normalize to sum=1.
            for eid in original_matrix.experts:
                weights[eid][domain] = weights[eid].get(domain, 0.0) / col_sum

            # Enforce primary >= 0.51 (for multi-expert domains).
            if primary and len(original_matrix.experts) > 1:
                primary_w = weights[primary][domain]
                if primary_w < _PRIMARY_WEIGHT_FLOOR:
                    deficit = _PRIMARY_WEIGHT_FLOOR - primary_w
                    weights[primary][domain] = _PRIMARY_WEIGHT_FLOOR
                    # Redistribute deficit from non-primary experts.
                    others = [e for e in original_matrix.experts if e != primary]
                    other_total = sum(weights[e][domain] for e in others)
                    if other_total > 0:
                        for eid in others:
                            share = weights[eid][domain] / other_total
                            weights[eid][domain] = max(0.0, weights[eid][domain] - deficit * share)

                    # Re-normalize.
                    col_sum = sum(weights[eid][domain] for eid in original_matrix.experts)
                    if col_sum > 0:
                        for eid in original_matrix.experts:
                            weights[eid][domain] = round(weights[eid][domain] / col_sum, 6)
                            # Final primary floor after re-normalization.
                        if weights[primary][domain] < _PRIMARY_WEIGHT_FLOOR:
                            weights[primary][domain] = _PRIMARY_WEIGHT_FLOOR
                            # Final fix-up.
                            remainder = 1.0 - _PRIMARY_WEIGHT_FLOOR
                            others_sum = sum(weights[e][domain] for e in others)
                            if others_sum > 0:
                                for eid in others:
                                    weights[eid][domain] = round(
                                        (weights[eid][domain] / others_sum) * remainder, 6
                                    )

        return ExpertWeightMatrix(
            weights=weights,
            domains=original_matrix.domains,
            experts=original_matrix.experts,
        )


def _build_default_matrix() -> ExpertWeightMatrix:
    """Build a default weight matrix from :class:`ExpertRegistry`."""
    from tapps_mcp.experts.registry import ExpertRegistry

    experts = ExpertRegistry.get_all_experts()
    if not experts:
        return ExpertWeightMatrix()

    domains = [e.primary_domain for e in experts]
    primary_map = {e.primary_domain: e.expert_id for e in experts}

    return WeightDistributor.calculate_weights(domains, primary_map)
