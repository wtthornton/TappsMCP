"""Data-driven checklist tier calibration.

Uses benchmark measurements (tool impact, call frequency, cost) to
recommend whether each tool should be 'required', 'recommended', or
'optional' in TappsMCP's task-completion checklist. Thresholds adjust
by engagement level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from tapps_mcp.benchmark.call_patterns import CallPatternReport
    from tapps_mcp.benchmark.tool_evaluator import ToolRanking

__all__ = [
    "ChecklistCalibration",
    "ChecklistCalibrator",
    "ToolTierClassification",
]

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ToolTierClassification(BaseModel):
    """Classification of a tool into a checklist tier."""

    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(description="Name of the tool.")
    measured_impact: float = Field(description="Measured impact score from benchmark.")
    measured_cost: float = Field(description="Measured cost ratio (token overhead).")
    call_frequency: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of tasks where the tool was called.",
    )
    recommended_tier: str = Field(
        description="Recommended tier: 'required', 'recommended', or 'optional'.",
    )
    current_tier: str = Field(
        description="Current tier in the checklist.",
    )
    tier_change: str | None = Field(
        default=None,
        description="Change direction: 'promoted', 'demoted', or 'unchanged'.",
    )
    justification: str = Field(
        description="Explanation for the tier recommendation.",
    )


class ChecklistCalibration(BaseModel):
    """Complete calibration result for all tools."""

    model_config = ConfigDict(frozen=True)

    classifications: list[ToolTierClassification] = Field(
        description="Per-tool tier classifications.",
    )
    engagement_level: str = Field(
        description="Engagement level used for threshold calculation.",
    )


# ---------------------------------------------------------------------------
# Tier ordering
# ---------------------------------------------------------------------------

_TIER_ORDER = {"required": 2, "recommended": 1, "optional": 0}


def _tier_change(current: str, recommended: str) -> str | None:
    """Determine the change direction between tiers."""
    cur_val = _TIER_ORDER.get(current, 0)
    rec_val = _TIER_ORDER.get(recommended, 0)
    if rec_val > cur_val:
        return "promoted"
    if rec_val < cur_val:
        return "demoted"
    return "unchanged"


# ---------------------------------------------------------------------------
# Impact thresholds by engagement level
# ---------------------------------------------------------------------------

_IMPACT_THRESHOLDS: dict[str, float] = {
    "high": 0.01,
    "medium": 0.03,
    "low": 0.05,
}

_COST_THRESHOLD = 0.15

# Frequency threshold: tools called in more than 30% of tasks are "frequent".
_FREQUENCY_THRESHOLD = 0.3


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------


class ChecklistCalibrator:
    """Calibrate checklist tool tiers based on benchmark measurements."""

    def calibrate_tiers(
        self,
        tool_rankings: list[ToolRanking],
        call_report: CallPatternReport,
        engagement_level: str = "medium",
    ) -> ChecklistCalibration:
        """Classify tools into checklist tiers using measured data.

        Tier rules (before engagement-level adjustment):
        - Impact > threshold AND cost < 15%: "required"
        - Impact > 0% OR frequently called: "recommended"
        - Impact <= 0% or rarely called: "optional"

        Impact threshold varies by engagement level:
        - high: 1%
        - medium: 3%
        - low: 5%

        Args:
            tool_rankings: Per-tool impact rankings from benchmark.
            call_report: Call pattern analysis for frequency data.
            engagement_level: Engagement level for threshold tuning.

        Returns:
            Complete calibration with per-tool classifications.
        """
        impact_threshold = _IMPACT_THRESHOLDS.get(engagement_level, 0.03)

        # Build call frequency map from patterns
        call_freq_map = self._compute_call_frequencies(call_report)

        classifications: list[ToolTierClassification] = []

        for ranking in tool_rankings:
            frequency = call_freq_map.get(ranking.tool_name, 0.0)
            cost_ratio = ranking.avg_token_cost / max(ranking.avg_token_cost + 1000, 1)

            # Determine recommended tier
            recommended = self._classify_tier(
                impact=ranking.impact_score,
                cost=cost_ratio,
                frequency=frequency,
                impact_threshold=impact_threshold,
            )

            # Use "recommended" as fallback current tier
            current = "recommended"
            change = _tier_change(current, recommended)

            justification = self._build_justification(
                ranking,
                recommended,
                frequency,
                cost_ratio,
                impact_threshold,
            )

            classifications.append(
                ToolTierClassification(
                    tool_name=ranking.tool_name,
                    measured_impact=ranking.impact_score,
                    measured_cost=round(cost_ratio, 4),
                    call_frequency=round(frequency, 4),
                    recommended_tier=recommended,
                    current_tier=current,
                    tier_change=change,
                    justification=justification,
                )
            )

        logger.debug(
            "checklist_calibrated",
            engagement=engagement_level,
            tool_count=len(classifications),
            required=sum(1 for c in classifications if c.recommended_tier == "required"),
            recommended=sum(1 for c in classifications if c.recommended_tier == "recommended"),
            optional=sum(1 for c in classifications if c.recommended_tier == "optional"),
        )

        return ChecklistCalibration(
            classifications=classifications,
            engagement_level=engagement_level,
        )

    @staticmethod
    def _classify_tier(
        impact: float,
        cost: float,
        frequency: float,
        impact_threshold: float,
    ) -> str:
        """Classify a tool into a tier based on metrics."""
        if impact > impact_threshold and cost < _COST_THRESHOLD:
            return "required"
        if impact > 0 or frequency > _FREQUENCY_THRESHOLD:
            return "recommended"
        return "optional"

    @staticmethod
    def _build_justification(
        ranking: ToolRanking,
        tier: str,
        frequency: float,
        cost_ratio: float,
        impact_threshold: float,
    ) -> str:
        """Build a human-readable justification for a tier classification."""
        parts: list[str] = []

        if tier == "required":
            parts.append(
                f"Impact {ranking.impact_score:.1%} exceeds threshold "
                f"{impact_threshold:.1%} with acceptable cost ratio "
                f"{cost_ratio:.1%}."
            )
        elif tier == "recommended":
            if ranking.impact_score > 0:
                parts.append(f"Positive impact ({ranking.impact_score:.1%}).")
            if frequency > _FREQUENCY_THRESHOLD:
                parts.append(f"Frequently called ({frequency:.0%} of tasks).")
        else:
            parts.append(f"Low or negative impact ({ranking.impact_score:.1%}).")
            if frequency <= _FREQUENCY_THRESHOLD:
                parts.append(f"Rarely called ({frequency:.0%} of tasks).")

        parts.append(
            f"Helped {ranking.tasks_helped} tasks, "
            f"hurt {ranking.tasks_hurt}, "
            f"neutral {ranking.tasks_neutral}."
        )

        return " ".join(parts)

    @staticmethod
    def _compute_call_frequencies(
        call_report: CallPatternReport,
    ) -> dict[str, float]:
        """Compute per-tool call frequency from patterns.

        Returns the fraction of tasks where each tool was called.
        """
        total = len(call_report.patterns)
        if total == 0:
            return {}

        freq: dict[str, int] = {}
        for pattern in call_report.patterns:
            for tool in pattern.tools_called:
                freq[tool] = freq.get(tool, 0) + 1

        return {tool: count / total for tool, count in freq.items()}
