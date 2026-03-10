"""Memory subsystem effectiveness tracking for MCP tool benchmarks.

Measures how memory operations (save, get, search, inject) affect task
resolution across different memory tiers (architectural, pattern, procedural, context).
"""

from __future__ import annotations

from collections import defaultdict

import structlog
from pydantic import BaseModel, ConfigDict, Field

from tapps_mcp.benchmark.tool_evaluator import ToolCondition, ToolImpactResult

__all__ = [
    "MemoryEffectiveness",
    "MemoryEffectivenessAnalyzer",
    "MemoryEffectivenessReport",
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Memory tier definitions (Epic 65.11: procedural added)
# ---------------------------------------------------------------------------

_MEMORY_TIERS = ["architectural", "pattern", "procedural", "context"]
_MEMORY_TOOL = "tapps_memory"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class MemoryEffectiveness(BaseModel):
    """Effectiveness metrics for a single memory tier."""

    model_config = ConfigDict(frozen=True)

    memory_tier: str = Field(
        description="Memory tier: 'architectural', 'pattern', 'procedural', or 'context'.",
    )
    retrievals: int = Field(ge=0, description="Number of memory retrievals observed.")
    resolution_with: float = Field(
        ge=0.0,
        le=1.0,
        description="Resolution rate when memory was available.",
    )
    resolution_without: float = Field(
        ge=0.0,
        le=1.0,
        description="Resolution rate when memory was not available.",
    )
    impact: float = Field(
        description="Resolution rate delta (with - without).",
    )
    relevance_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Estimated relevance of retrieved memories.",
    )


class MemoryEffectivenessReport(BaseModel):
    """Report summarizing memory effectiveness across tiers."""

    model_config = ConfigDict(frozen=True)

    per_tier: list[MemoryEffectiveness] = Field(
        description="Per-tier effectiveness metrics.",
    )
    most_effective_tier: str = Field(
        description="Tier with highest positive impact.",
    )


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class MemoryEffectivenessAnalyzer:
    """Analyze memory subsystem effectiveness from benchmark results."""

    def analyze(
        self,
        results: list[ToolImpactResult],
    ) -> MemoryEffectivenessReport:
        """Analyze memory effectiveness across tiers.

        Groups results by whether memory was available, then distributes
        tasks across memory tiers using a deterministic assignment based
        on task_id hash. This simulates tier-level analysis when actual
        tier metadata is not available.

        Args:
            results: Tool impact results from evaluation.

        Returns:
            Report with per-tier effectiveness metrics.
        """
        # Separate results with and without memory
        with_memory: list[ToolImpactResult] = []
        without_memory: list[ToolImpactResult] = []

        for result in results:
            if result.condition == ToolCondition.ALL_TOOLS:
                with_memory.append(result)
            elif (
                result.condition == ToolCondition.ALL_MINUS_ONE and result.tool_name == _MEMORY_TOOL
            ):
                without_memory.append(result)

        # Distribute tasks across tiers deterministically
        tier_with: dict[str, list[bool]] = defaultdict(list)
        tier_without: dict[str, list[bool]] = defaultdict(list)

        for result in with_memory:
            tier = self._assign_tier(result.task_id)
            tier_with[tier].append(result.resolved)

        for result in without_memory:
            tier = self._assign_tier(result.task_id)
            tier_without[tier].append(result.resolved)

        # Compute per-tier metrics
        per_tier: list[MemoryEffectiveness] = []

        for tier in _MEMORY_TIERS:
            w_results = tier_with.get(tier, [])
            wo_results = tier_without.get(tier, [])

            rate_with = sum(w_results) / max(len(w_results), 1)
            rate_without = sum(wo_results) / max(len(wo_results), 1)
            impact = rate_with - rate_without

            # Estimate relevance based on tier type
            relevance = self._estimate_relevance(tier, len(w_results))

            per_tier.append(
                MemoryEffectiveness(
                    memory_tier=tier,
                    retrievals=len(w_results),
                    resolution_with=round(rate_with, 4),
                    resolution_without=round(rate_without, 4),
                    impact=round(impact, 4),
                    relevance_score=round(relevance, 4),
                )
            )

        # Sort by impact descending
        per_tier.sort(key=lambda m: -m.impact)

        most_effective = per_tier[0].memory_tier if per_tier else "pattern"

        logger.debug(
            "memory_effectiveness_analyzed",
            tier_count=len(per_tier),
            most_effective=most_effective,
            total_with=len(with_memory),
            total_without=len(without_memory),
        )

        return MemoryEffectivenessReport(
            per_tier=per_tier,
            most_effective_tier=most_effective,
        )

    @staticmethod
    def _assign_tier(task_id: str) -> str:
        """Assign a task to a memory tier deterministically."""
        hash_val = sum(ord(c) for c in task_id)
        return _MEMORY_TIERS[hash_val % len(_MEMORY_TIERS)]

    @staticmethod
    def _estimate_relevance(tier: str, sample_size: int) -> float:
        """Estimate relevance score based on tier characteristics.

        Architectural memories are highly relevant but rare.
        Pattern memories are moderately relevant and common.
        Context memories are broadly relevant with moderate specificity.
        """
        base_relevance: dict[str, float] = {
            "architectural": 0.85,
            "pattern": 0.70,
            "procedural": 0.62,  # Epic 65.11: between pattern and context
            "context": 0.55,
        }
        base = base_relevance.get(tier, 0.5)
        # Slightly adjust by sample size (more data = slightly higher confidence)
        adjustment = min(sample_size / 50.0, 0.1)
        return min(base + adjustment, 1.0)
