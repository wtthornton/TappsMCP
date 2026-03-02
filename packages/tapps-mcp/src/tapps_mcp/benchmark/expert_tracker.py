"""Expert domain effectiveness tracking for MCP tool benchmarks.

Measures how expert consultations affect task resolution by analyzing
which domains are most effective and computing per-domain impact metrics.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field

from tapps_mcp.benchmark.tool_evaluator import ToolCondition, ToolImpactResult

if TYPE_CHECKING:
    from tapps_mcp.benchmark.tool_task_models import ToolTask

__all__ = [
    "ExpertEffectiveness",
    "ExpertEffectivenessAnalyzer",
    "ExpertEffectivenessReport",
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Expert domain mapping
# ---------------------------------------------------------------------------

# Maps task categories to the expert domains most likely consulted.
_CATEGORY_DOMAIN_MAP: dict[str, str] = {
    "quality": "code-quality-analysis",
    "security": "security",
    "architecture": "software-architecture",
    "debugging": "testing-strategies",
    "refactoring": "code-quality-analysis",
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ExpertEffectiveness(BaseModel):
    """Effectiveness metrics for a single expert domain."""

    model_config = ConfigDict(frozen=True)

    domain: str = Field(description="Expert domain name.")
    consultations: int = Field(ge=0, description="Number of tasks where experts were consulted.")
    resolution_with: float = Field(
        ge=0.0,
        le=1.0,
        description="Resolution rate when expert tools were available.",
    )
    resolution_without: float = Field(
        ge=0.0,
        le=1.0,
        description="Resolution rate when expert tools were removed.",
    )
    impact: float = Field(
        description="Resolution rate delta (with - without).",
    )
    avg_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Average consultation confidence score.",
    )


class ExpertEffectivenessReport(BaseModel):
    """Report summarizing expert effectiveness across domains."""

    model_config = ConfigDict(frozen=True)

    per_domain: list[ExpertEffectiveness] = Field(
        description="Per-domain effectiveness metrics.",
    )
    most_effective_domain: str = Field(
        description="Domain with highest positive impact.",
    )
    least_effective_domain: str = Field(
        description="Domain with lowest (or most negative) impact.",
    )


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class ExpertEffectivenessAnalyzer:
    """Analyze expert consultation effectiveness from benchmark results."""

    def analyze(
        self,
        results: list[ToolImpactResult],
        tasks: list[ToolTask],
    ) -> ExpertEffectivenessReport:
        """Analyze expert effectiveness across task categories.

        Groups tasks by their associated expert domain, then compares
        resolution rates with and without expert tools available.

        Args:
            results: Tool impact results (must include tapps_consult_expert
                and tapps_research entries).
            tasks: Task definitions for category mapping.

        Returns:
            Report with per-domain effectiveness metrics.
        """
        task_map = {t.task_id: t for t in tasks}
        expert_tools = {"tapps_consult_expert", "tapps_research"}

        # Group results by domain
        domain_with: dict[str, list[bool]] = defaultdict(list)
        domain_without: dict[str, list[bool]] = defaultdict(list)

        for result in results:
            task = task_map.get(result.task_id)
            if task is None:
                continue

            domain = _CATEGORY_DOMAIN_MAP.get(task.category, "code-quality-analysis")

            # Check if expert tools are in the context
            has_expert = bool(expert_tools & set(result.tools_called))

            if result.condition == ToolCondition.ALL_TOOLS:
                domain_with[domain].append(result.resolved)
            elif result.condition == ToolCondition.ALL_MINUS_ONE:
                # If the removed tool is an expert tool, this is "without"
                if result.tool_name in expert_tools:
                    domain_without[domain].append(result.resolved)
                elif has_expert:
                    # Still has expert tools, treat as "with"
                    domain_with[domain].append(result.resolved)
                else:
                    domain_without[domain].append(result.resolved)

        # Compute per-domain metrics
        all_domains = sorted(set(domain_with.keys()) | set(domain_without.keys()))
        per_domain: list[ExpertEffectiveness] = []

        for domain in all_domains:
            with_results = domain_with.get(domain, [])
            without_results = domain_without.get(domain, [])

            rate_with = sum(with_results) / max(len(with_results), 1)
            rate_without = sum(without_results) / max(len(without_results), 1)
            impact = rate_with - rate_without

            # Simulated confidence (based on sample size and resolution)
            sample_size = len(with_results) + len(without_results)
            confidence = min(sample_size / 20.0, 1.0) * 0.8 + 0.1

            per_domain.append(
                ExpertEffectiveness(
                    domain=domain,
                    consultations=len(with_results),
                    resolution_with=round(rate_with, 4),
                    resolution_without=round(rate_without, 4),
                    impact=round(impact, 4),
                    avg_confidence=round(confidence, 4),
                )
            )

        # Sort by impact descending
        per_domain.sort(key=lambda e: -e.impact)

        most_effective = per_domain[0].domain if per_domain else "none"
        least_effective = per_domain[-1].domain if per_domain else "none"

        logger.debug(
            "expert_effectiveness_analyzed",
            domain_count=len(per_domain),
            most_effective=most_effective,
            least_effective=least_effective,
        )

        return ExpertEffectivenessReport(
            per_domain=per_domain,
            most_effective_domain=most_effective,
            least_effective_domain=least_effective,
        )
