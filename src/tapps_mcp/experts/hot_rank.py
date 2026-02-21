"""Hot-rank — adaptive ranking from usage + feedback signals.

Consumes metrics from the feedback tracker, expert performance tracker, and
RAG metrics tracker to compute a hot-rank score for domains.  This score can
be used as a tie-breaker in retrieval ranking to prioritise domains and sources
that historically produce helpful results.

Includes guardrails against popularity-only lock-in: new/under-served domains
get a minimum exploration bonus.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Recency half-life in days — consultations older than this contribute half weight.
_RECENCY_HALF_LIFE_DAYS = 14.0
# Minimum exploration score for domains with few consultations.
_EXPLORATION_BONUS = 0.15
# Consultation count below which exploration bonus applies.
_EXPLORATION_THRESHOLD = 5


@dataclass
class DomainHotRank:
    """Hot-rank score for a single domain."""

    domain: str
    score: float
    consultations: int = 0
    avg_confidence: float = 0.0
    helpful_rate: float = 0.0
    recency_weight: float = 0.0
    exploration_bonus: float = 0.0


def compute_hot_rank(
    domain: str,
    consultations: int,
    avg_confidence: float,
    helpful_rate: float,
    days_since_last: float = 0.0,
) -> DomainHotRank:
    """Compute hot-rank for a domain.

    Score combines:
    - Helpfulness signal (40%): How often the domain's results are marked helpful.
    - Confidence trend (30%): Average confidence of recent consultations.
    - Recency decay (20%): Exponential decay based on days since last use.
    - Exploration bonus (10%): Boost for under-served domains.

    Args:
        domain: Domain identifier.
        consultations: Total consultation count.
        avg_confidence: Average confidence score.
        helpful_rate: Fraction of consultations marked helpful.
        days_since_last: Days since the most recent consultation.

    Returns:
        DomainHotRank with computed score and component breakdown.
    """
    # Recency weight: exponential decay.
    recency = math.exp(-0.693 * days_since_last / _RECENCY_HALF_LIFE_DAYS) if days_since_last >= 0 else 1.0

    # Exploration bonus for under-served domains.
    exploration = _EXPLORATION_BONUS if consultations < _EXPLORATION_THRESHOLD else 0.0

    # Weighted combination.
    score = (
        0.4 * helpful_rate
        + 0.3 * avg_confidence
        + 0.2 * recency
        + 0.1 * (1.0 + exploration)  # base 0.1 + bonus
    )
    score = min(1.0, max(0.0, score))

    return DomainHotRank(
        domain=domain,
        score=round(score, 4),
        consultations=consultations,
        avg_confidence=round(avg_confidence, 4),
        helpful_rate=round(helpful_rate, 4),
        recency_weight=round(recency, 4),
        exploration_bonus=round(exploration, 4),
    )


def get_domain_hot_ranks(metrics_dir: Path) -> list[DomainHotRank]:
    """Compute hot-ranks for all domains using stored metrics.

    Args:
        metrics_dir: Directory containing metrics files.

    Returns:
        Sorted list of DomainHotRank (highest score first).
    """
    from tapps_mcp.common.utils import utc_now
    from tapps_mcp.metrics.expert_metrics import ExpertPerformanceTracker
    from tapps_mcp.metrics.feedback import FeedbackTracker

    tracker = ExpertPerformanceTracker(metrics_dir)
    feedback = FeedbackTracker(metrics_dir)

    performances = tracker.get_performance(days=30)
    domain_breakdown = tracker.get_domain_breakdown(days=30)
    feedback_stats = feedback.get_by_tool()

    # Build feedback rates per domain (approximation via tool name).
    expert_feedback = feedback_stats.get("tapps_consult_expert", {})
    overall_helpful_rate = expert_feedback.get("helpful_rate", 0.5) if expert_feedback else 0.5

    now = utc_now()
    ranks: list[DomainHotRank] = []

    for domain, stats in domain_breakdown.items():
        consultations = stats.get("consultations", 0)
        avg_confidence = stats.get("avg_confidence", 0.0)

        # Use per-domain helpful rate if available, else fall back to overall.
        helpful_rate = overall_helpful_rate

        # Estimate days since last consultation from the performance records.
        days_since = 30.0  # default
        for perf in performances:
            if perf.domain == domain:
                days_since = 0.0  # Has recent activity.
                break

        rank = compute_hot_rank(
            domain=domain,
            consultations=consultations,
            avg_confidence=avg_confidence,
            helpful_rate=helpful_rate,
            days_since_last=days_since,
        )
        ranks.append(rank)

    ranks.sort(key=lambda r: r.score, reverse=True)
    return ranks


def apply_hot_rank_boost(
    chunks: list[Any],
    domain: str,
    metrics_dir: Path | None = None,
    boost_factor: float = 0.05,
) -> list[Any]:
    """Apply a hot-rank tie-breaker boost to chunk scores.

    Only modifies scores within a narrow band to avoid popularity-only lock-in.

    Args:
        chunks: List of KnowledgeChunk objects (must have a ``score`` attribute).
        domain: The domain being queried.
        metrics_dir: Path to metrics directory (if None, no boost applied).
        boost_factor: Maximum score boost (default 0.05 = 5%).

    Returns:
        The same chunks list (scores modified in place).
    """
    if metrics_dir is None:
        return chunks

    try:
        ranks = get_domain_hot_ranks(metrics_dir)
    except Exception:
        logger.debug("hot_rank_boost_skip", reason="metrics unavailable")
        return chunks

    domain_rank = next((r for r in ranks if r.domain == domain), None)
    if domain_rank is None:
        return chunks

    boost = domain_rank.score * boost_factor
    for chunk in chunks:
        if hasattr(chunk, "score"):
            chunk.score = min(1.0, chunk.score + boost)  # type: ignore[attr-defined]

    return chunks
