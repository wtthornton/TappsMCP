"""Embedding-based deduplication gate for agent proposals.

Checks whether a proposed new agent overlaps with existing agents
in the catalog using embedding cosine similarity. When overlap is
detected, returns the overlapping agents instead of allowing creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from docs_mcp.agents.embeddings import EmbeddingBackend, cosine_similarity
from docs_mcp.agents.models import AgentConfig

logger: Any = structlog.get_logger(__name__)

# Default similarity threshold for dedup (0.85 balances precision vs recall)
DEDUP_THRESHOLD: float = 0.85


@dataclass(frozen=True)
class DedupResult:
    """Result of a deduplication check."""

    is_duplicate: bool
    overlapping_agents: list[DedupMatch]
    threshold: float


@dataclass(frozen=True)
class DedupMatch:
    """A single overlap match from dedup checking."""

    agent: AgentConfig
    similarity: float


def check_dedup(
    proposal_text: str,
    catalog_agents: list[AgentConfig],
    backend: EmbeddingBackend,
    threshold: float = DEDUP_THRESHOLD,
    precomputed_embeddings: list[list[float]] | None = None,
) -> DedupResult:
    """Check if a proposed agent overlaps with existing catalog agents.

    Args:
        proposal_text: Description/keywords of the proposed new agent,
            typically the embedding_text() of a candidate AgentConfig.
        catalog_agents: Existing agents to check against.
        backend: Embedding backend for computing similarity.
        threshold: Cosine similarity threshold (default 0.85).
        precomputed_embeddings: Pre-computed embeddings for catalog_agents
            (from HybridMatcher._agent_embeddings). If None, computes fresh.

    Returns:
        DedupResult indicating whether the proposal is a duplicate.
    """
    if not catalog_agents:
        return DedupResult(
            is_duplicate=False,
            overlapping_agents=[],
            threshold=threshold,
        )

    # Compute proposal embedding
    proposal_embedding = backend.embed([proposal_text])[0]

    # Use precomputed or compute catalog embeddings
    if precomputed_embeddings is not None:
        agent_embeddings = precomputed_embeddings
    else:
        texts = [a.embedding_text() for a in catalog_agents]
        agent_embeddings = backend.embed(texts)

    # Score against all active agents
    matches: list[DedupMatch] = []
    for i, agent in enumerate(catalog_agents):
        if agent.deprecated:
            continue
        if i >= len(agent_embeddings):
            continue

        sim = cosine_similarity(proposal_embedding, agent_embeddings[i])
        if sim >= threshold:
            matches.append(DedupMatch(agent=agent, similarity=sim))
            logger.info(
                "dedup_overlap_detected",
                proposal=proposal_text[:80],
                existing_agent=agent.name,
                similarity=round(sim, 4),
            )

    matches.sort(key=lambda m: m.similarity, reverse=True)

    return DedupResult(
        is_duplicate=len(matches) > 0,
        overlapping_agents=matches,
        threshold=threshold,
    )
