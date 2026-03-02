"""Adaptive weight feedback loop from benchmark measurements.

Translates tool effectiveness measurements into scoring category weight
adjustments, closing the loop between benchmarking and the adaptive
scoring engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from tapps_mcp.benchmark.tool_evaluator import ToolEffectivenessReport, ToolRanking

__all__ = [
    "AdaptiveFeedbackGenerator",
    "BenchmarkFeedback",
]

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class BenchmarkFeedback(BaseModel):
    """Feedback from benchmark measurements for the adaptive engine."""

    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(description="Tool this feedback applies to.")
    impact_score: float = Field(description="Measured impact score.")
    cost_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Cost ratio (token overhead relative to total).",
    )
    category_impacts: dict[str, float] = Field(
        description="Impact scores broken down by task category.",
    )
    source: str = Field(
        default="benchmark",
        description="Source of this feedback.",
    )
    sample_size: int = Field(ge=0, description="Number of tasks measured.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the measurement.",
    )


# ---------------------------------------------------------------------------
# Tool-to-category mapping
# ---------------------------------------------------------------------------

# Maps tool names to the scoring categories they most influence.
_TOOL_CATEGORY_MAP: dict[str, list[str]] = {
    "tapps_score_file": ["complexity", "maintainability", "structure"],
    "tapps_quality_gate": ["complexity", "maintainability"],
    "tapps_quick_check": ["complexity", "maintainability", "structure"],
    "tapps_security_scan": ["security"],
    "tapps_validate_changed": ["complexity", "maintainability", "security"],
    "tapps_consult_expert": ["maintainability", "structure"],
    "tapps_lookup_docs": ["maintainability"],
    "tapps_checklist": ["structure", "devex"],
    "tapps_project_profile": ["structure"],
    "tapps_impact_analysis": ["maintainability", "structure"],
    "tapps_dead_code": ["maintainability", "structure"],
    "tapps_dependency_scan": ["security"],
    "tapps_dependency_graph": ["structure", "maintainability"],
    "tapps_memory": ["maintainability", "devex"],
    "tapps_research": ["maintainability"],
    "tapps_session_start": ["devex"],
}

# Scoring category weights used in the quality gate.
_CATEGORY_WEIGHTS: dict[str, float] = {
    "security": 0.27,
    "maintainability": 0.24,
    "complexity": 0.18,
    "test_coverage": 0.13,
    "performance": 0.08,
    "structure": 0.05,
    "devex": 0.05,
}

# Minimum confidence to generate feedback.
_MIN_CONFIDENCE = 0.3

# Maximum weight adjustment per category per feedback cycle.
_MAX_ADJUSTMENT = 0.05

# Epsilon for floating-point zero comparison.
_ZERO_EPSILON = 1e-10


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class AdaptiveFeedbackGenerator:
    """Generate adaptive scoring feedback from benchmark results."""

    def generate_feedback(
        self,
        tool_report: ToolEffectivenessReport,
    ) -> list[BenchmarkFeedback]:
        """Generate per-tool feedback from effectiveness measurements.

        Each tool gets a BenchmarkFeedback entry with its measured impact
        broken down by scoring category, plus a confidence score based
        on sample size.

        Args:
            tool_report: Tool effectiveness report from benchmark.

        Returns:
            List of feedback entries, one per tool.
        """
        feedback_list: list[BenchmarkFeedback] = []

        for ranking in tool_report.tool_rankings:
            total_tasks = ranking.tasks_helped + ranking.tasks_hurt + ranking.tasks_neutral
            confidence = self._compute_confidence(total_tasks)

            if confidence < _MIN_CONFIDENCE:
                logger.debug(
                    "feedback_skipped_low_confidence",
                    tool=ranking.tool_name,
                    confidence=confidence,
                )
                continue

            category_impacts = self._compute_category_impacts(ranking)
            cost_ratio = ranking.avg_token_cost / max(ranking.avg_token_cost + 1000, 1)

            feedback_list.append(
                BenchmarkFeedback(
                    tool_name=ranking.tool_name,
                    impact_score=ranking.impact_score,
                    cost_ratio=round(cost_ratio, 4),
                    category_impacts=category_impacts,
                    source="benchmark",
                    sample_size=total_tasks,
                    confidence=round(confidence, 4),
                )
            )

        logger.info(
            "benchmark_feedback_generated",
            total=len(feedback_list),
            skipped=len(tool_report.tool_rankings) - len(feedback_list),
        )

        return feedback_list

    def generate_weight_adjustments(
        self,
        feedback: list[BenchmarkFeedback],
    ) -> dict[str, float]:
        """Generate scoring category weight adjustments from feedback.

        Aggregates per-tool category impacts into overall weight deltas.
        Adjustments are capped at ``_MAX_ADJUSTMENT`` per category and
        normalized to sum to zero (so overall weight sum is preserved).

        Args:
            feedback: Benchmark feedback entries.

        Returns:
            Mapping of category name to weight adjustment delta.
        """
        # Accumulate weighted impacts per category
        category_deltas: dict[str, float] = dict.fromkeys(_CATEGORY_WEIGHTS, 0.0)
        total_weight = 0.0

        for entry in feedback:
            weight = entry.confidence * abs(entry.impact_score)
            total_weight += weight

            for category, impact in entry.category_impacts.items():
                if category in category_deltas:
                    category_deltas[category] += impact * entry.confidence

        # Normalize and cap adjustments
        if total_weight > 0:
            for category, delta in category_deltas.items():
                raw = delta / total_weight
                category_deltas[category] = max(-_MAX_ADJUSTMENT, min(raw, _MAX_ADJUSTMENT))

        # Ensure adjustments sum to zero (zero-sum normalization)
        total_delta = sum(category_deltas.values())
        if abs(total_delta) > _ZERO_EPSILON and len(category_deltas) > 0:
            correction = total_delta / len(category_deltas)
            for category, val in category_deltas.items():
                category_deltas[category] = round(val - correction, 6)

        logger.debug(
            "weight_adjustments_generated",
            adjustments=category_deltas,
            feedback_count=len(feedback),
        )

        return category_deltas

    @staticmethod
    def _compute_confidence(sample_size: int) -> float:
        """Compute confidence score based on sample size.

        Uses a simple logistic-style curve that approaches 1.0 as
        sample size increases.
        """
        if sample_size <= 0:
            return 0.0
        # Confidence ramps up quickly with sample size
        # 5 tasks -> ~0.5, 10 -> ~0.67, 20 -> ~0.80, 50 -> ~0.91
        return round(sample_size / (sample_size + 5.0), 4)

    @staticmethod
    def _compute_category_impacts(ranking: ToolRanking) -> dict[str, float]:
        """Distribute a tool's impact across its associated categories.

        The tool's impact_score is divided evenly among the categories
        it influences (as defined in ``_TOOL_CATEGORY_MAP``).
        """
        categories = _TOOL_CATEGORY_MAP.get(ranking.tool_name, [])
        if not categories:
            return {}

        per_category = ranking.impact_score / len(categories)
        return {cat: round(per_category, 6) for cat in categories}
