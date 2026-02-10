"""Adaptive scoring engine using Pearson correlation analysis.

Analyzes historical code-quality outcomes to identify which scoring
categories best predict first-pass success, then adjusts category
weights accordingly.
"""

from __future__ import annotations

import math
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any

import structlog

from tapps_mcp.adaptive.models import AdaptiveWeightsSnapshot, CodeOutcome
from tapps_mcp.adaptive.persistence import save_json_atomic

if TYPE_CHECKING:
    from tapps_mcp.adaptive.protocols import OutcomeTrackerProtocol

logger = structlog.get_logger(__name__)

# Default learning rate for weight adjustment.
DEFAULT_LEARNING_RATE = 0.1

# Minimum number of outcomes required before adjustment activates.
MIN_OUTCOMES_FOR_ADJUSTMENT = 10

# Metrics analyzed (keys in CodeOutcome.initial_scores).
_METRIC_KEYS = [
    "complexity",
    "security",
    "maintainability",
    "test_coverage",
    "performance",
    "structure",
    "devex",
]

# Mapping from score metric keys to weight keys.
_METRIC_TO_WEIGHT: dict[str, str] = {k: k for k in _METRIC_KEYS}


class AdaptiveScoringEngine:
    """Adjusts scoring category weights based on outcome correlations.

    The engine computes Pearson correlations between each scoring metric
    and first-pass success, then nudges weights toward metrics that
    positively predict success.
    """

    def __init__(
        self,
        outcome_tracker: OutcomeTrackerProtocol,
        learning_rate: float = DEFAULT_LEARNING_RATE,
    ) -> None:
        self._tracker = outcome_tracker
        self._learning_rate = learning_rate

    async def adjust_weights(
        self,
        outcomes: list[CodeOutcome] | None = None,
        current_weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Compute adjusted scoring weights from outcome history.

        Returns *current_weights* unchanged if fewer than
        :data:`MIN_OUTCOMES_FOR_ADJUSTMENT` outcomes are available.
        """
        if current_weights is None:
            current_weights = _get_default_weights()

        outcomes = self._load_outcomes(outcomes)

        if len(outcomes) < MIN_OUTCOMES_FOR_ADJUSTMENT:
            logger.debug(
                "adaptive_skip_insufficient_outcomes",
                count=len(outcomes),
                minimum=MIN_OUTCOMES_FOR_ADJUSTMENT,
            )
            return dict(current_weights)

        correlations = self._calculate_correlations(outcomes)
        optimal = self._calculate_optimal_weights(correlations, current_weights)
        adjusted = self._apply_learning_rate(current_weights, optimal)
        return self._normalize_weights(adjusted)

    def get_recommendation(
        self,
        outcomes: list[CodeOutcome] | None = None,
    ) -> dict[str, Any]:
        """Produce a diagnostic report without applying changes."""
        outcomes = self._load_outcomes(outcomes)

        current = _get_default_weights()
        correlations = self._calculate_correlations(outcomes) if outcomes else {}
        optimal = (
            self._calculate_optimal_weights(correlations, current) if correlations else current
        )

        return {
            "outcomes_analyzed": len(outcomes),
            "sufficient_data": len(outcomes) >= MIN_OUTCOMES_FOR_ADJUSTMENT,
            "correlations": correlations,
            "current_weights": current,
            "optimal_weights": optimal,
            "adjustments": {k: round(optimal.get(k, 0) - current.get(k, 0), 6) for k in current},
        }

    def save_snapshot(self, weights: dict[str, float], snapshot_path: Path) -> None:
        """Persist a :class:`AdaptiveWeightsSnapshot` to *snapshot_path*."""
        outcomes = self._load_outcomes()
        correlations = self._calculate_correlations(outcomes) if outcomes else {}
        snapshot = AdaptiveWeightsSnapshot(
            weights=weights,
            correlations=correlations,
            outcomes_analyzed=len(outcomes),
            learning_rate=self._learning_rate,
        )
        save_json_atomic(snapshot.model_dump(), snapshot_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_outcomes(self, outcomes: list[CodeOutcome] | None = None) -> list[CodeOutcome]:
        """Return *outcomes* if provided, otherwise load from tracker."""
        if outcomes is not None:
            return outcomes
        return self._tracker.load_outcomes(limit=1000)

    def _calculate_correlations(
        self,
        outcomes: list[CodeOutcome],
    ) -> dict[str, float]:
        """Compute Pearson correlation between each metric and first-pass success."""
        correlations: dict[str, float] = {}

        for metric in _METRIC_KEYS:
            values: list[float] = []
            successes: list[bool] = []
            for o in outcomes:
                score = o.initial_scores.get(metric)
                if score is not None:
                    values.append(score)
                    successes.append(o.first_pass_success)

            if len(values) >= 5:  # noqa: PLR2004
                corr = _pearson_correlation(values, successes)
                correlations[metric] = round(corr, 6)

        return correlations

    def _calculate_optimal_weights(
        self,
        correlations: dict[str, float],
        current_weights: dict[str, float],
    ) -> dict[str, float]:
        """Derive optimal weights from correlations."""
        raw: dict[str, float] = {}
        for metric, corr in correlations.items():
            weight_key = _METRIC_TO_WEIGHT.get(metric, metric)
            # Only positively-correlated metrics get weight.
            raw[weight_key] = max(corr, 0.0)

        # Fill in any weight keys not in correlations.
        for wk in current_weights:  # noqa: PLC0206
            if wk not in raw:
                raw[wk] = current_weights[wk]

        return self._normalize_weights(raw)

    def _apply_learning_rate(
        self,
        current: dict[str, float],
        optimal: dict[str, float],
    ) -> dict[str, float]:
        """Blend *current* toward *optimal* using the learning rate."""
        lr = self._learning_rate
        result: dict[str, float] = {}
        all_keys = set(current) | set(optimal)
        for k in all_keys:
            c = current.get(k, 0.0)
            o = optimal.get(k, 0.0)
            result[k] = c * (1.0 - lr) + o * lr
        return result

    @staticmethod
    def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
        """Normalize *weights* so they sum to 1.0."""
        total = sum(weights.values())
        if total <= 0:
            return dict(_get_default_weights())
        return {k: round(v / total, 6) for k, v in weights.items()}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _get_default_weights() -> dict[str, float]:
    """Return default scoring weights (matching ``ScoringWeights`` defaults)."""
    return {
        "complexity": 0.18,
        "security": 0.27,
        "maintainability": 0.24,
        "test_coverage": 0.13,
        "performance": 0.08,
        "structure": 0.05,
        "devex": 0.05,
    }


def _mean(values: list[float]) -> float:
    """Arithmetic mean of *values*."""
    return sum(values) / len(values)


def _variance(values: list[float], mu: float) -> float:
    """Population variance of *values* around *mu*."""
    return sum((v - mu) ** 2 for v in values) / len(values)


def _pearson_correlation(x: list[float], y: list[bool]) -> float:
    """Compute Pearson correlation between *x* (floats) and *y* (bools).

    Returns 0.0 when the correlation is undefined (zero variance).
    """
    n = len(x)
    if n < 2:  # noqa: PLR2004
        return 0.0

    y_float = [1.0 if v else 0.0 for v in y]

    mu_x = _mean(x)
    mu_y = _mean(y_float)

    cov = sum((xi - mu_x) * (yi - mu_y) for xi, yi in zip(x, y_float, strict=True)) / n
    var_x = _variance(x, mu_x)
    var_y = _variance(y_float, mu_y)

    # Guard against negative variance from floating-point rounding
    if var_x <= 0.0 or var_y <= 0.0:
        return 0.0

    corr = cov / (math.sqrt(var_x) * math.sqrt(var_y))
    return max(-1.0, min(1.0, corr))
