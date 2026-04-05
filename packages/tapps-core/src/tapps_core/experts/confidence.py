"""Confidence scoring for expert consultations.

Computes a weighted confidence score from multiple factors:

- **RAG quality** (40%) — how many knowledge chunks matched and their scores.
- **Domain relevance** (30%) — whether the question maps to a technical domain.
- **Source coverage** (30%) — fraction of query keywords covered by sources.

This is a simplified version of the TappsCodingAgents ``ConfidenceCalculator``
with the ``ProjectProfile`` and agent-threshold dependencies removed.
"""

from __future__ import annotations

from tapps_core.experts.models import ConfidenceFactors
from tapps_core.experts.registry import ExpertRegistry

# Weights — must sum to 1.0.
_W_RAG_QUALITY = 0.40
_W_DOMAIN_RELEVANCE = 0.30
_W_SOURCE_COVERAGE = 0.30


def compute_confidence(factors: ConfidenceFactors, domain: str) -> float:
    """Compute a 0.0-1.0 confidence score from *factors* and *domain*.

    Args:
        factors: Pre-computed confidence factors.
        domain: The expert domain that handled the consultation.

    Returns:
        Confidence score clamped to ``[0.0, 1.0]``.
    """
    # Three-tier relevance: technical (1.0), business (0.9), unknown (0.7).
    if ExpertRegistry.is_technical_domain(domain):
        domain_relevance = 1.0
    elif ExpertRegistry.is_business_domain(domain):
        domain_relevance = 0.9  # Known business domain
    else:
        domain_relevance = 0.7  # Truly unknown domain
    factors.domain_relevance = domain_relevance

    score = (
        factors.rag_quality * _W_RAG_QUALITY
        + factors.domain_relevance * _W_DOMAIN_RELEVANCE
        + factors.chunk_coverage * _W_SOURCE_COVERAGE
    )
    return max(0.0, min(1.0, round(score, 4)))


def compute_rag_quality(chunk_scores: list[float]) -> float:
    """Derive a RAG-quality factor from individual chunk scores.

    Args:
        chunk_scores: List of ``KnowledgeChunk.score`` values (0.0-1.0).

    Returns:
        Quality score in ``[0.0, 1.0]``.
    """
    if not chunk_scores:
        return 0.0
    # Use the mean of the top-3 chunk scores.
    top = sorted(chunk_scores, reverse=True)[:3]
    return round(sum(top) / len(top), 4)


def compute_chunk_coverage(keywords: set[str], chunk_texts: list[str]) -> float:
    """Fraction of *keywords* that appear in at least one chunk.

    Args:
        keywords: The normalised query keywords.
        chunk_texts: Lowered content of each retrieved chunk.

    Returns:
        Coverage ratio in ``[0.0, 1.0]``.
    """
    if not keywords:
        return 0.0
    combined = " ".join(chunk_texts).lower()
    hits = sum(1 for kw in keywords if kw in combined)
    return round(hits / len(keywords), 4)
