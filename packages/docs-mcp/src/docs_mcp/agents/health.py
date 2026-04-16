"""Catalog health analysis for agent governance.

Computes pairwise similarity between all agents and identifies
potential overlaps that may indicate redundant agents needing
merge or cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from docs_mcp.agents.matcher import HybridMatcher

logger: Any = structlog.get_logger(__name__)

# Threshold above which agent pairs are flagged as potential overlaps
OVERLAP_THRESHOLD: float = 0.7


@dataclass(frozen=True)
class OverlapPair:
    """A pair of agents with high embedding similarity."""

    agent_a: str
    agent_b: str
    similarity: float
    recommendation: str


@dataclass
class CatalogHealthReport:
    """Health report for the agent catalog."""

    total_agents: int = 0
    active_agents: int = 0
    deprecated_agents: int = 0
    overlap_pairs: list[OverlapPair] = field(default_factory=list)
    overlap_threshold: float = OVERLAP_THRESHOLD

    @property
    def health_score(self) -> float:
        """Catalog health score (0-100).

        Penalized by number of overlapping pairs relative to total agents.
        A catalog with no overlaps scores 100.
        """
        if self.active_agents == 0:
            return 100.0

        max_pairs = self.active_agents * (self.active_agents - 1) / 2
        if max_pairs == 0:
            return 100.0

        overlap_ratio = len(self.overlap_pairs) / max_pairs
        return round(max(0.0, (1.0 - overlap_ratio) * 100), 1)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a dict for MCP tool responses."""
        return {
            "total_agents": self.total_agents,
            "active_agents": self.active_agents,
            "deprecated_agents": self.deprecated_agents,
            "overlap_count": len(self.overlap_pairs),
            "overlap_threshold": self.overlap_threshold,
            "health_score": self.health_score,
            "overlaps": [
                {
                    "agent_a": p.agent_a,
                    "agent_b": p.agent_b,
                    "similarity": round(p.similarity, 4),
                    "recommendation": p.recommendation,
                }
                for p in self.overlap_pairs
            ],
        }


def analyze_catalog_health(
    matcher: HybridMatcher,
    threshold: float = OVERLAP_THRESHOLD,
) -> CatalogHealthReport:
    """Analyze catalog health by computing pairwise agent similarity.

    Args:
        matcher: HybridMatcher with pre-computed embeddings.
        threshold: Similarity threshold for flagging overlaps (default 0.7).

    Returns:
        CatalogHealthReport with overlap pairs and health score.
    """
    active = [a for a in matcher.agents if not a.deprecated]
    deprecated = [a for a in matcher.agents if a.deprecated]

    pairs = matcher.pairwise_similarity()

    overlap_pairs: list[OverlapPair] = []
    for (name_a, name_b), sim in sorted(
        pairs.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        if sim >= threshold:
            if sim >= 0.85:
                recommendation = (
                    f"High overlap ({sim:.0%}). Consider merging "
                    f"'{name_b}' into '{name_a}' or vice versa."
                )
            else:
                recommendation = (
                    f"Moderate overlap ({sim:.0%}). Review whether both "
                    f"agents are needed or if capabilities can be consolidated."
                )

            overlap_pairs.append(
                OverlapPair(
                    agent_a=name_a,
                    agent_b=name_b,
                    similarity=sim,
                    recommendation=recommendation,
                )
            )

    report = CatalogHealthReport(
        total_agents=len(matcher.agents),
        active_agents=len(active),
        deprecated_agents=len(deprecated),
        overlap_pairs=overlap_pairs,
        overlap_threshold=threshold,
    )

    logger.info(
        "catalog_health_analyzed",
        total=report.total_agents,
        active=report.active_agents,
        overlaps=len(report.overlap_pairs),
        health_score=report.health_score,
    )

    return report
