"""Hybrid agent matcher combining keyword and embedding scores.

Routes prompts to the best-matching agent using a weighted combination
of keyword overlap and embedding cosine similarity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from docs_mcp.agents.embeddings import (
    EmbeddingBackend,
    EmbeddingCache,
    StubEmbeddingBackend,
    cosine_similarity,
)
from docs_mcp.agents.keyword_matcher import keyword_score, tokenize
from docs_mcp.agents.models import AgentConfig

logger: Any = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MatchResult:
    """Result of matching a prompt against an agent."""

    agent: AgentConfig
    score: float
    keyword_score: float = 0.0
    embedding_score: float = 0.0


@dataclass
class HybridMatcher:
    """Combines keyword and embedding matching for agent routing.

    On initialization, pre-computes keyword tokens and embedding vectors
    for all active agents. At match time, scores the prompt against all
    agents and returns results above the threshold.

    Args:
        agents: List of agent configurations to match against.
        backend: Embedding backend to use. Falls back to StubEmbeddingBackend
            if None (keyword-only mode with degraded embedding scores).
        keyword_weight: Weight for keyword score in combined ranking.
        embedding_weight: Weight for embedding score in combined ranking.
        cache_dir: Directory for embedding vector cache. If None, caching
            is disabled.
    """

    agents: list[AgentConfig] = field(default_factory=list)
    backend: EmbeddingBackend | None = None
    keyword_weight: float = 0.3
    embedding_weight: float = 0.7
    cache_dir: Path | None = None

    # Computed at post_init
    _agent_tokens: list[list[str]] = field(default_factory=list, repr=False)
    _agent_embeddings: list[list[float]] = field(default_factory=list, repr=False)
    _cache: EmbeddingCache | None = field(default=None, repr=False)
    _degraded: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """Pre-compute keyword tokens and embeddings for all agents."""
        if self.backend is None:
            self._degraded = True
            self.backend = StubEmbeddingBackend()
            logger.warning(
                "hybrid_matcher_degraded",
                reason="No embedding backend provided, using stub (keyword-heavy mode)",
            )
            # In degraded mode, shift weights to keyword-only
            object.__setattr__(self, "keyword_weight", 1.0)
            object.__setattr__(self, "embedding_weight", 0.0)

        # Set up cache
        if self.cache_dir is not None:
            self._cache = EmbeddingCache(self.cache_dir)

        # Pre-compute tokens
        self._agent_tokens = [tokenize(agent.embedding_text()) for agent in self.agents]

        # Pre-compute embeddings
        texts = [agent.embedding_text() for agent in self.agents]
        if texts:
            if self._cache is not None:
                self._agent_embeddings = self._cache.get_or_compute(
                    texts,
                    self.backend,
                )
            else:
                self._agent_embeddings = self.backend.embed(texts)
        else:
            self._agent_embeddings = []

    @property
    def is_degraded(self) -> bool:
        """True if running without a real embedding backend."""
        return self._degraded

    def match(
        self,
        prompt: str,
        threshold: float = 0.7,
        max_results: int = 5,
    ) -> list[MatchResult]:
        """Match a prompt against all active (non-deprecated) agents.

        Args:
            prompt: User prompt to match.
            threshold: Minimum combined score to include in results.
            max_results: Maximum number of results to return.

        Returns:
            Sorted list of MatchResult (highest score first).
        """
        if not self.agents:
            return []

        assert self.backend is not None  # set in __post_init__

        query_tokens = tokenize(prompt)

        # Compute query embedding
        if self._cache is not None:
            query_embeddings = self._cache.get_or_compute(
                [prompt],
                self.backend,
            )
        else:
            query_embeddings = self.backend.embed([prompt])
        query_embedding = query_embeddings[0] if query_embeddings else []

        results: list[MatchResult] = []
        for i, agent in enumerate(self.agents):
            if agent.deprecated:
                continue

            # Keyword score
            kw_score = keyword_score(query_tokens, self._agent_tokens[i])

            # Embedding score
            emb_score = 0.0
            if query_embedding and i < len(self._agent_embeddings):
                emb_score = cosine_similarity(
                    query_embedding,
                    self._agent_embeddings[i],
                )
                # Map from [-1, 1] to [0, 1]
                emb_score = (emb_score + 1) / 2

            # Combined score
            combined = self.keyword_weight * kw_score + self.embedding_weight * emb_score

            if combined >= threshold:
                results.append(
                    MatchResult(
                        agent=agent,
                        score=combined,
                        keyword_score=kw_score,
                        embedding_score=emb_score,
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]

    def pairwise_similarity(self) -> dict[tuple[str, str], float]:
        """Compute cosine similarity between all agent pairs.

        Returns a dict mapping ``(agent_a_name, agent_b_name)`` to their
        cosine similarity score. Only includes pairs where a < b
        (alphabetically) to avoid duplicates.

        Used by EPIC-12 catalog governance for deduplication scoring.
        """
        pairs: dict[tuple[str, str], float] = {}
        n = len(self.agents)

        for i in range(n):
            for j in range(i + 1, n):
                if i < len(self._agent_embeddings) and j < len(self._agent_embeddings):
                    sim = cosine_similarity(
                        self._agent_embeddings[i],
                        self._agent_embeddings[j],
                    )
                    name_a = self.agents[i].name
                    name_b = self.agents[j].name
                    # Alphabetical ordering for consistency
                    if name_a > name_b:
                        name_a, name_b = name_b, name_a
                    pairs[(name_a, name_b)] = sim

        return pairs
