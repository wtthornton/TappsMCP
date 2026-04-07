"""Proposer overlap guard for agent catalog governance.

Before creating a new agent, the overlap guard identifies the top-N
most similar existing agents. This context can be injected into a
proposer prompt or presented to a human reviewer to reduce
redundant agent creation.
"""

from __future__ import annotations

from dataclasses import dataclass

from docs_mcp.agents.matcher import HybridMatcher, MatchResult


@dataclass(frozen=True)
class OverlapContext:
    """Context about existing agents that overlap with a proposal."""

    proposal_text: str
    similar_agents: list[MatchResult]
    warning: str | None = None

    def to_prompt_injection(self) -> str:
        """Format as text suitable for injection into a proposer prompt."""
        if not self.similar_agents:
            return "No existing agents overlap with this proposal."

        lines = [
            "The following existing agents have similar capabilities. "
            "Consider extending one of them instead of creating a new agent:",
            "",
        ]
        for result in self.similar_agents:
            lines.append(
                f"- **{result.agent.name}** (similarity: {result.score:.0%}): "
                f"{result.agent.description}"
            )
            if result.agent.keywords:
                lines.append(f"  Keywords: {', '.join(result.agent.keywords)}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Serialize for MCP tool responses."""
        return {
            "proposal_text": self.proposal_text[:200],
            "similar_count": len(self.similar_agents),
            "warning": self.warning,
            "similar_agents": [
                {
                    "name": r.agent.name,
                    "description": r.agent.description,
                    "score": round(r.score, 4),
                    "keyword_score": round(r.keyword_score, 4),
                    "embedding_score": round(r.embedding_score, 4),
                }
                for r in self.similar_agents
            ],
        }


def get_overlap_context(
    proposal_text: str,
    matcher: HybridMatcher,
    top_n: int = 3,
    threshold: float = 0.3,
) -> OverlapContext:
    """Get overlap context for a proposed agent.

    Returns the top-N most similar existing agents above the threshold.
    Use a lower threshold than the dedup gate (0.3 vs 0.85) to surface
    agents that are somewhat related even if not duplicates.

    Args:
        proposal_text: Description/keywords of the proposed agent.
        matcher: HybridMatcher with the existing catalog.
        top_n: Maximum number of similar agents to return.
        threshold: Minimum score to include (default 0.3 for broad coverage).

    Returns:
        OverlapContext with similar agents and optional warning.
    """
    results = matcher.match(
        prompt=proposal_text,
        threshold=threshold,
        max_results=top_n,
    )

    warning = None
    if results and results[0].score >= 0.85:
        warning = (
            f"High overlap detected with '{results[0].agent.name}' "
            f"({results[0].score:.0%} similarity). This proposal may be "
            f"a duplicate."
        )

    return OverlapContext(
        proposal_text=proposal_text,
        similar_agents=results,
        warning=warning,
    )
