"""Adaptive scoring engine using Pearson correlation analysis.

Analyzes historical code-quality outcomes to identify which scoring
categories best predict first-pass success, then adjusts category
weights accordingly.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from tapps_core.adaptive.models import AdaptiveWeightsSnapshot, CodeOutcome
from tapps_core.adaptive.persistence import save_json_atomic

if TYPE_CHECKING:
    from tapps_core.adaptive.protocols import OutcomeTrackerProtocol

logger = structlog.get_logger(__name__)

# Default learning rate for weight adjustment.
DEFAULT_LEARNING_RATE = 0.1

# Minimum number of outcomes required before adjustment activates.
# Lowered from 10 to 5 to allow adaptive weights to activate sooner.
MIN_OUTCOMES_FOR_ADJUSTMENT = 5

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
    positively predict success. When *metrics_dir* is provided, feedback
    records from tapps_feedback are merged in so negative feedback
    influences weight recalibration.
    """

    def __init__(
        self,
        outcome_tracker: OutcomeTrackerProtocol,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        *,
        metrics_dir: Path | None = None,
    ) -> None:
        self._tracker = outcome_tracker
        self._learning_rate = learning_rate
        self._metrics_dir = metrics_dir

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
        """Return *outcomes* if provided, otherwise load from tracker and feedback."""
        if outcomes is not None:
            return outcomes
        base = self._tracker.load_outcomes(limit=1000)
        if self._metrics_dir is not None:
            merged = self._merge_feedback_outcomes(base, self._metrics_dir)
            return merged
        return base

    def _merge_feedback_outcomes(
        self, base_outcomes: list[CodeOutcome], metrics_dir: Path
    ) -> list[CodeOutcome]:
        """Merge feedback-derived outcomes so negative feedback influences weights."""
        try:
            from tapps_core.metrics.feedback import FeedbackTracker

            tracker = FeedbackTracker(metrics_dir)
            raw = tracker.to_adaptive_outcomes()
        except (ImportError, OSError) as e:
            logger.debug("feedback_merge_skipped", error=str(e))
            return base_outcomes

        if not raw:
            return base_outcomes

        # Convert feedback dicts to CodeOutcome with neutral initial_scores so they
        # contribute to correlation (helpful=False pulls correlations down).
        neutral_scores = dict.fromkeys(_METRIC_KEYS, 5.0)
        for i, fb in enumerate(raw):
            base_outcomes.append(
                CodeOutcome(
                    workflow_id=f"feedback-{i}",
                    file_path="(feedback)",
                    initial_scores=neutral_scores,
                    first_pass_success=bool(fb.get("first_pass_success", False)),
                    timestamp=fb.get("timestamp", ""),
                )
            )
        return base_outcomes

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

            if len(values) >= 5:
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
        for wk in current_weights:
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
    if n < 2:
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
