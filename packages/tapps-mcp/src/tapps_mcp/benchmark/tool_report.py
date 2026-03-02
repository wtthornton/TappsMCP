"""Dashboard integration and reporting for tool effectiveness benchmarks.

Generates human-readable reports from tool effectiveness, call pattern,
and calibration data. Provides a ToolEffectivenessSection model for
integration with the main TappsMCP dashboard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field

from tapps_mcp.benchmark.tool_evaluator import ToolRanking  # noqa: TC001

if TYPE_CHECKING:
    from tapps_mcp.benchmark.call_patterns import CallPatternReport
    from tapps_mcp.benchmark.tool_evaluator import ToolEffectivenessReport

__all__ = [
    "ToolEffectivenessSection",
    "generate_tool_effectiveness_report",
]

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Dashboard model
# ---------------------------------------------------------------------------


class ToolEffectivenessSection(BaseModel):
    """Tool effectiveness section for the main dashboard."""

    model_config = ConfigDict(frozen=True)

    tool_rankings: list[ToolRanking] = Field(
        description="Tools ranked by effectiveness.",
    )
    call_efficiency: float = Field(
        ge=0.0,
        le=1.0,
        description="Average call efficiency across tasks.",
    )
    calibration_pending: bool = Field(
        default=False,
        description="Whether checklist calibration needs attention.",
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_tool_effectiveness_report(
    tool_report: ToolEffectivenessReport,
    call_report: CallPatternReport,
    output_format: str = "markdown",
) -> str:
    """Generate a tool effectiveness report in the specified format.

    Args:
        tool_report: Tool effectiveness report from benchmark.
        call_report: Call pattern analysis from benchmark.
        output_format: Output format - 'markdown' or 'json'.

    Returns:
        Formatted report string.
    """
    if output_format == "json":
        return _generate_json_report(tool_report, call_report)
    return _generate_markdown_report(tool_report, call_report)


def _generate_markdown_report(
    tool_report: ToolEffectivenessReport,
    call_report: CallPatternReport,
) -> str:
    """Generate a Markdown tool effectiveness report."""
    lines: list[str] = [
        "# Tool Effectiveness Report",
        "",
        "## Summary",
        "",
        f"- **Tasks evaluated**: {tool_report.task_count}",
        f"- **Conditions tested**: {tool_report.condition_count}",
        f"- **Tools ranked**: {len(tool_report.tool_rankings)}",
        f"- **Average call efficiency**: {call_report.avg_efficiency:.1%}",
        "",
        "## Tool Rankings",
        "",
        "| Rank | Tool | Impact | Helped | Hurt | Neutral | Avg Token Cost |",
        "|------|------|--------|--------|------|---------|----------------|",
    ]

    for i, ranking in enumerate(tool_report.tool_rankings, 1):
        lines.append(
            f"| {i} | {ranking.tool_name} "
            f"| {ranking.impact_score:+.1%} "
            f"| {ranking.tasks_helped} "
            f"| {ranking.tasks_hurt} "
            f"| {ranking.tasks_neutral} "
            f"| {ranking.avg_token_cost:,} |"
        )

    lines.append("")

    # Call pattern section
    lines.extend(
        [
            "## Call Patterns",
            "",
            f"- **Average efficiency**: {call_report.avg_efficiency:.1%}",
        ]
    )

    if call_report.most_overcalled:
        lines.append("")
        lines.append("### Most Overcalled Tools")
        lines.append("")
        for tool, count in call_report.most_overcalled[:5]:
            lines.append(f"- {tool}: {count} unnecessary calls")

    if call_report.most_undercalled:
        lines.append("")
        lines.append("### Most Undercalled Tools")
        lines.append("")
        for tool, count in call_report.most_undercalled[:5]:
            lines.append(f"- {tool}: missed in {count} tasks")

    lines.append("")

    # Top performers and underperformers
    if tool_report.tool_rankings:
        top = [r for r in tool_report.tool_rankings if r.impact_score > 0]
        bottom = [r for r in tool_report.tool_rankings if r.impact_score <= 0]

        if top:
            lines.extend(
                [
                    "## High-Impact Tools",
                    "",
                ]
            )
            for r in top[:5]:
                lines.append(
                    f"- **{r.tool_name}**: {r.impact_score:+.1%} impact, "
                    f"helped {r.tasks_helped} tasks"
                )
            lines.append("")

        if bottom:
            lines.extend(
                [
                    "## Low-Impact Tools",
                    "",
                ]
            )
            for r in bottom[:5]:
                lines.append(
                    f"- **{r.tool_name}**: {r.impact_score:+.1%} impact, hurt {r.tasks_hurt} tasks"
                )
            lines.append("")

    return "\n".join(lines)


def _generate_json_report(
    tool_report: ToolEffectivenessReport,
    call_report: CallPatternReport,
) -> str:
    """Generate a JSON tool effectiveness report."""
    import json

    data = {
        "summary": {
            "task_count": tool_report.task_count,
            "condition_count": tool_report.condition_count,
            "tool_count": len(tool_report.tool_rankings),
            "avg_call_efficiency": call_report.avg_efficiency,
        },
        "tool_rankings": [
            {
                "tool_name": r.tool_name,
                "impact_score": r.impact_score,
                "tasks_helped": r.tasks_helped,
                "tasks_hurt": r.tasks_hurt,
                "tasks_neutral": r.tasks_neutral,
                "avg_token_cost": r.avg_token_cost,
                "pass_at_k": r.pass_at_k,
            }
            for r in tool_report.tool_rankings
        ],
        "call_patterns": {
            "avg_efficiency": call_report.avg_efficiency,
            "most_overcalled": [{"tool": t, "count": c} for t, c in call_report.most_overcalled],
            "most_undercalled": [{"tool": t, "count": c} for t, c in call_report.most_undercalled],
        },
    }

    return json.dumps(data, indent=2)
