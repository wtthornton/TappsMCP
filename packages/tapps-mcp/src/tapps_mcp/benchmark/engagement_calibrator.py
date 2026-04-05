"""Engagement level optimization and calibration.

Evaluates TappsMCP templates at each engagement level (high, medium, low)
plus a no-context baseline, then recommends the level with the best
resolution-per-token efficiency ratio.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import structlog
from pydantic import BaseModel, ConfigDict, Field

from tapps_mcp.benchmark.models import ContextMode

if TYPE_CHECKING:
    from tapps_mcp.benchmark.models import BenchmarkConfig, BenchmarkResult

__all__ = [
    "EngagementCalibration",
    "EngagementCalibrationReport",
    "EngagementCalibrator",
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Engagement levels to test
# ---------------------------------------------------------------------------

_ENGAGEMENT_LEVELS = ("high", "medium", "low")


# ---------------------------------------------------------------------------
# Evaluator protocol
# ---------------------------------------------------------------------------


class _EvaluatorProtocol(Protocol):
    """Protocol matching MockEvaluator and Evaluator interfaces."""

    async def evaluate_batch(
        self,
        instances: Any,
        context_mode: Any,
        engagement_level: str,
    ) -> list[BenchmarkResult]: ...


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EngagementCalibration(BaseModel):
    """Calibration metrics for a single engagement level."""

    model_config = ConfigDict(frozen=True)

    level: str = Field(description="Engagement level (high/medium/low/none).")
    resolution_rate: float = Field(ge=0.0, le=1.0, description="Resolution rate achieved.")
    avg_token_cost: float = Field(ge=0.0, description="Average token usage per instance.")
    resolution_per_token: float = Field(
        ge=0.0,
        description="Resolution rate divided by avg token cost (efficiency).",
    )
    delta_vs_none: float = Field(
        description="Resolution rate improvement over no-context baseline."
    )
    delta_vs_medium: float = Field(
        description="Resolution rate improvement over medium engagement."
    )


class EngagementCalibrationReport(BaseModel):
    """Complete calibration report across all engagement levels."""

    model_config = ConfigDict(frozen=True)

    calibrations: list[EngagementCalibration] = Field(description="Per-level calibration results.")
    recommended_level: str = Field(description="Recommended engagement level.")
    recommendation_reason: str = Field(description="Explanation for the recommendation.")
    warning: str | None = Field(
        default=None,
        description="Warning message if any level performs worse than no-context.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_resolution_rate(results: list[BenchmarkResult]) -> float:
    """Compute resolution rate from a list of results."""
    if not results:
        return 0.0
    resolved = sum(1 for r in results if r.resolved)
    return resolved / len(results)


def _compute_avg_tokens(results: list[BenchmarkResult]) -> float:
    """Compute average token usage from results."""
    if not results:
        return 0.0
    return sum(r.token_usage for r in results) / len(results)


def _compute_efficiency(rate: float, tokens: float) -> float:
    """Compute resolution-per-token efficiency.

    When tokens are zero, uses rate multiplied by a large factor
    so free+effective outcomes rank highest.
    """
    if tokens > 0:
        return rate / tokens
    return rate * 1e6


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------


class EngagementCalibrator:
    """Calibrate engagement levels by evaluating each against benchmarks."""

    async def calibrate(
        self,
        config: BenchmarkConfig,
        evaluator: _EvaluatorProtocol,
    ) -> EngagementCalibrationReport:
        """Evaluate all engagement levels and recommend the best.

        Runs the evaluator for each engagement level (high, medium, low)
        plus a no-context baseline, computes efficiency ratios, and
        recommends the level with the best resolution-per-token ratio.

        Warns if any level performs worse than the no-context baseline.

        Args:
            config: Benchmark configuration.
            evaluator: Evaluator (mock or real) for running benchmarks.

        Returns:
            Calibration report with per-level metrics and recommendation.
        """
        from tapps_mcp.benchmark.dataset import DatasetLoader

        loader = DatasetLoader(config)
        instances = await loader.load()

        # Run no-context baseline
        none_results = await evaluator.evaluate_batch(instances, ContextMode.NONE, "medium")
        none_rate = _compute_resolution_rate(none_results)
        none_tokens = _compute_avg_tokens(none_results)

        logger.info(
            "calibration_baseline",
            none_rate=round(none_rate, 4),
            none_tokens=round(none_tokens, 1),
        )

        # Run each engagement level
        level_results: dict[str, list[BenchmarkResult]] = {}
        for level in _ENGAGEMENT_LEVELS:
            results = await evaluator.evaluate_batch(instances, config.context_mode, level)
            level_results[level] = results

        # Compute medium rate for delta_vs_medium
        medium_rate = _compute_resolution_rate(level_results.get("medium", []))

        # Build calibrations
        calibrations: list[EngagementCalibration] = []
        worse_than_none: list[str] = []

        for level in _ENGAGEMENT_LEVELS:
            results = level_results[level]
            rate = _compute_resolution_rate(results)
            tokens = _compute_avg_tokens(results)
            efficiency = _compute_efficiency(rate, tokens)

            delta_vs_none = rate - none_rate
            delta_vs_medium = rate - medium_rate

            if rate < none_rate:
                worse_than_none.append(level)

            cal = EngagementCalibration(
                level=level,
                resolution_rate=round(rate, 4),
                avg_token_cost=round(tokens, 1),
                resolution_per_token=round(efficiency, 8),
                delta_vs_none=round(delta_vs_none, 4),
                delta_vs_medium=round(delta_vs_medium, 4),
            )
            calibrations.append(cal)

        # Find best level by efficiency
        best_cal = max(calibrations, key=lambda c: c.resolution_per_token)
        recommended = best_cal.level

        reason = (
            f"Best efficiency: {best_cal.resolution_rate:.1%} resolution rate "
            f"at {best_cal.avg_token_cost:.0f} avg tokens per instance "
            f"({best_cal.resolution_per_token:.8f} resolution/token)."
        )

        warning: str | None = None
        if worse_than_none:
            warning = (
                f"Warning: engagement level(s) {', '.join(worse_than_none)} "
                f"performed worse than no-context baseline "
                f"(none={none_rate:.1%})."
            )

        logger.info(
            "calibration_complete",
            recommended=recommended,
            levels_tested=len(calibrations),
            worse_than_none=worse_than_none,
        )

        return EngagementCalibrationReport(
            calibrations=calibrations,
            recommended_level=recommended,
            recommendation_reason=reason,
            warning=warning,
        )
