"""Call pattern analysis for MCP tool benchmarks.

Analyzes how tools are called relative to expectations, detecting
overcalls, undercalls, common call sequences, and computing efficiency
metrics. Generates actionable recommendations for tool usage.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field

from tapps_mcp.benchmark.tool_evaluator import ToolCondition, ToolImpactResult

if TYPE_CHECKING:
    from tapps_mcp.benchmark.tool_task_models import ToolTask

__all__ = [
    "CallPattern",
    "CallPatternAnalyzer",
    "CallPatternReport",
    "CallRecommendation",
]

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CallPattern(BaseModel):
    """Call pattern analysis for a single task."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(description="Task identifier.")
    tools_called: list[str] = Field(description="Tools that were actually called.")
    tools_expected: list[str] = Field(description="Tools that were expected to be called.")
    overcalls: list[str] = Field(
        description="Tools called but not expected.",
    )
    undercalls: list[str] = Field(
        description="Tools expected but not called.",
    )
    call_efficiency: float = Field(
        ge=0.0,
        le=1.0,
        description="Ratio of useful calls to total calls (0.0-1.0).",
    )


class CallPatternReport(BaseModel):
    """Aggregated call pattern analysis across all tasks."""

    model_config = ConfigDict(frozen=True)

    patterns: list[CallPattern] = Field(
        description="Per-task call patterns.",
    )
    avg_efficiency: float = Field(
        ge=0.0,
        le=1.0,
        description="Average call efficiency across all tasks.",
    )
    most_overcalled: list[tuple[str, int]] = Field(
        description="Tools most frequently called unnecessarily, as (name, count) pairs.",
    )
    most_undercalled: list[tuple[str, int]] = Field(
        description="Tools most frequently missing when expected, as (name, count) pairs.",
    )
    common_sequences: list[list[str]] = Field(
        description="Most common tool call sequences observed.",
    )


class CallRecommendation(BaseModel):
    """Recommendation for adjusting tool usage."""

    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(description="Tool this recommendation applies to.")
    recommendation: str = Field(
        description="Action: 'increase', 'decrease', or 'keep'.",
    )
    rationale: str = Field(description="Explanation for the recommendation.")


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_OVERCALL_THRESHOLD = 3
_UNDERCALL_THRESHOLD = 3
_SEQUENCE_MIN_COUNT = 2


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class CallPatternAnalyzer:
    """Analyze tool call patterns relative to expectations."""

    def analyze(
        self,
        results: list[ToolImpactResult],
        tasks: list[ToolTask],
    ) -> CallPatternReport:
        """Analyze call patterns across results and tasks.

        Compares actual tool calls against expected tools for each task,
        computing per-task efficiency and aggregate overcall/undercall
        statistics.

        Args:
            results: Tool impact results from evaluation.
            tasks: Task definitions with expected tool lists.

        Returns:
            Aggregated call pattern report.
        """
        task_map = {t.task_id: t for t in tasks}
        patterns: list[CallPattern] = []
        overcall_counter: Counter[str] = Counter()
        undercall_counter: Counter[str] = Counter()
        all_sequences: list[list[str]] = []

        # Only analyze ALL_TOOLS condition results
        all_tools_results = [r for r in results if r.condition == ToolCondition.ALL_TOOLS]

        for result in all_tools_results:
            task = task_map.get(result.task_id)
            if task is None:
                continue

            called = set(result.tools_called)
            expected = set(task.expected_tools)

            overcalls = sorted(called - expected)
            undercalls = sorted(expected - called)

            # Efficiency: useful calls / total calls
            useful = len(called & expected)
            total = len(called)
            efficiency = useful / max(total, 1)

            patterns.append(
                CallPattern(
                    task_id=result.task_id,
                    tools_called=result.tools_called,
                    tools_expected=task.expected_tools,
                    overcalls=overcalls,
                    undercalls=undercalls,
                    call_efficiency=round(efficiency, 4),
                )
            )

            for tool in overcalls:
                overcall_counter[tool] += 1
            for tool in undercalls:
                undercall_counter[tool] += 1

            if result.tools_called:
                all_sequences.append(result.tools_called)

        # Compute aggregate metrics
        avg_efficiency = 0.0
        if patterns:
            avg_efficiency = sum(p.call_efficiency for p in patterns) / len(patterns)

        most_overcalled = overcall_counter.most_common(10)
        most_undercalled = undercall_counter.most_common(10)
        common_sequences = self._find_common_sequences(all_sequences)

        logger.debug(
            "call_patterns_analyzed",
            task_count=len(patterns),
            avg_efficiency=round(avg_efficiency, 4),
            overcalled_tools=len(most_overcalled),
            undercalled_tools=len(most_undercalled),
        )

        return CallPatternReport(
            patterns=patterns,
            avg_efficiency=round(avg_efficiency, 4),
            most_overcalled=most_overcalled,
            most_undercalled=most_undercalled,
            common_sequences=common_sequences,
        )

    def generate_recommendations(
        self,
        report: CallPatternReport,
    ) -> list[CallRecommendation]:
        """Generate tool usage recommendations from a call pattern report.

        Tools that are frequently undercalled get an "increase" recommendation.
        Tools that are frequently overcalled get a "decrease" recommendation.
        All other tools get a "keep" recommendation.

        Args:
            report: Call pattern report to analyze.

        Returns:
            List of recommendations, one per tool mentioned in patterns.
        """
        recommendations: list[CallRecommendation] = []

        # Collect all tool names
        all_tools: set[str] = set()
        overcall_map: dict[str, int] = dict(report.most_overcalled)
        undercall_map: dict[str, int] = dict(report.most_undercalled)

        for pattern in report.patterns:
            all_tools.update(pattern.tools_called)
            all_tools.update(pattern.tools_expected)

        for tool in sorted(all_tools):
            over_count = overcall_map.get(tool, 0)
            under_count = undercall_map.get(tool, 0)

            if under_count >= _UNDERCALL_THRESHOLD:
                recommendations.append(
                    CallRecommendation(
                        tool_name=tool,
                        recommendation="increase",
                        rationale=(
                            f"Expected but not called in {under_count} tasks. "
                            "Consider prompting agents to use this tool more."
                        ),
                    )
                )
            elif over_count >= _OVERCALL_THRESHOLD:
                recommendations.append(
                    CallRecommendation(
                        tool_name=tool,
                        recommendation="decrease",
                        rationale=(
                            f"Called unnecessarily in {over_count} tasks. "
                            "Consider reducing tool prominence in prompts."
                        ),
                    )
                )
            else:
                recommendations.append(
                    CallRecommendation(
                        tool_name=tool,
                        recommendation="keep",
                        rationale="Tool usage frequency is appropriate.",
                    )
                )

        return recommendations

    @staticmethod
    def _find_common_sequences(
        sequences: list[list[str]],
    ) -> list[list[str]]:
        """Find the most common tool call sequences.

        Counts exact-match sequences and returns those appearing at
        least ``_SEQUENCE_MIN_COUNT`` times.
        """
        counter: Counter[tuple[str, ...]] = Counter()
        for seq in sequences:
            key = tuple(seq)
            counter[key] += 1

        common: list[list[str]] = []
        for seq_tuple, count in counter.most_common(10):
            if count >= _SEQUENCE_MIN_COUNT:
                common.append(list(seq_tuple))

        return common
