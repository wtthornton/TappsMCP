"""Capability merge suggestion generator for agent catalog governance.

When the dedup gate detects overlap between a proposed agent and an
existing one, this module generates structured merge suggestions:
which keywords/capabilities to add to the existing agent to cover
the proposed functionality.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from docs_mcp.agents.models import AgentConfig


@dataclass(frozen=True)
class MergeSuggestion:
    """Structured suggestion for merging capabilities into an existing agent."""

    target_agent: str
    similarity: float
    new_keywords: list[str]
    new_capabilities: list[str]
    description_addition: str
    rationale: str


def generate_merge_suggestion(
    proposal: AgentConfig,
    existing: AgentConfig,
    similarity: float,
) -> MergeSuggestion:
    """Generate a merge suggestion for combining a proposal into an existing agent.

    Computes the diff between the proposal's keywords/capabilities and the
    existing agent's, then suggests additions that would cover the new
    functionality without creating a redundant agent.

    Args:
        proposal: The proposed new agent.
        existing: The existing agent that overlaps.
        similarity: Cosine similarity score between the two.

    Returns:
        A MergeSuggestion with specific additions to make.
    """
    existing_keywords = set(existing.keywords)
    existing_capabilities = set(existing.capabilities)

    new_keywords = [k for k in proposal.keywords if k not in existing_keywords]
    new_capabilities = [c for c in proposal.capabilities if c not in existing_capabilities]

    # Build description addition from the proposal's unique aspects
    description_addition = ""
    if proposal.description and proposal.description != existing.description:
        description_addition = proposal.description

    rationale = (
        f"Agent '{proposal.name}' has {similarity:.0%} similarity to "
        f"'{existing.name}'. Instead of creating a new agent, consider "
        f"extending '{existing.name}' with the suggested keywords and "
        f"capabilities."
    )

    return MergeSuggestion(
        target_agent=existing.name,
        similarity=similarity,
        new_keywords=new_keywords,
        new_capabilities=new_capabilities,
        description_addition=description_addition,
        rationale=rationale,
    )


@dataclass
class MergeReport:
    """Collection of merge suggestions for a single proposal."""

    proposal_name: str
    is_duplicate: bool
    suggestions: list[MergeSuggestion] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a dict for MCP tool responses."""
        return {
            "proposal_name": self.proposal_name,
            "is_duplicate": self.is_duplicate,
            "suggestion_count": len(self.suggestions),
            "suggestions": [
                {
                    "target_agent": s.target_agent,
                    "similarity": round(s.similarity, 4),
                    "new_keywords": s.new_keywords,
                    "new_capabilities": s.new_capabilities,
                    "description_addition": s.description_addition,
                    "rationale": s.rationale,
                }
                for s in self.suggestions
            ],
        }
