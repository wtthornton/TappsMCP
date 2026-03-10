"""Memory injection into expert and research responses.

Provides a helper that retrieves relevant memories and formats them
for injection into tool responses. RAG safety is applied as a
defense-in-depth measure before injection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from tapps_core.security.content_safety import check_content_safety
from tapps_core.memory.retrieval import MemoryRetriever

if TYPE_CHECKING:
    from tapps_core.memory.decay import DecayConfig
    from tapps_core.memory.store import MemoryStore

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_INJECT_HIGH = 5
_MAX_INJECT_MEDIUM = 3
_MIN_SCORE = 0.3
_MIN_CONFIDENCE_MEDIUM = 0.5


def estimate_tokens(text: str) -> int:
    """Estimate token count. Approximation: 1 token ~ 4 characters."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Injection logic
# ---------------------------------------------------------------------------


def inject_memories(
    question: str,
    store: MemoryStore,
    engagement_level: str = "high",
    *,
    decay_config: DecayConfig | None = None,
) -> dict[str, Any]:
    """Search for and format relevant memories for injection.

    Args:
        question: The user's query to match against memories.
        store: The memory store to search.
        engagement_level: "high", "medium", or "low".
        decay_config: Optional decay configuration.

    Returns:
        Dict with:
        - ``memory_section``: Formatted markdown section (or empty string).
        - ``memory_injected``: Number of memories injected.
        - ``memories``: List of injected memory summaries.
    """
    # Low engagement: never inject
    if engagement_level == "low":
        return {"memory_section": "", "memory_injected": 0, "memories": []}

    from tapps_core.config.settings import load_settings
    from tapps_core.memory.reranker import get_reranker

    settings = load_settings()
    rr = settings.memory.reranker
    reranker = (
        get_reranker(
            enabled=rr.enabled,
            provider=rr.provider,
            top_k=rr.top_k,
            api_key=rr.api_key,
        )
        if rr.enabled
        else None
    )
    retriever = MemoryRetriever(
        config=decay_config,
        reranker=reranker,
        reranker_enabled=rr.enabled,
    )

    # Determine limits based on engagement level
    if engagement_level == "medium":
        max_inject = _MAX_INJECT_MEDIUM
        min_confidence = _MIN_CONFIDENCE_MEDIUM
    else:
        max_inject = _MAX_INJECT_HIGH
        min_confidence = _MIN_SCORE

    try:
        results = retriever.search(
            question,
            store,
            limit=max_inject,
            min_confidence=min_confidence,
        )
    except Exception:
        logger.debug("memory_injection_search_failed", question=question[:80])
        return {"memory_section": "", "memory_injected": 0, "memories": []}

    # Filter by minimum score
    results = [r for r in results if r.score >= _MIN_SCORE]

    if not results:
        return {"memory_section": "", "memory_injected": 0, "memories": []}

    # RAG safety check on values before injection (defense-in-depth)
    safe_results = []
    for scored in results:
        safety = check_content_safety(scored.entry.value)
        if safety.safe:
            safe_results.append(scored)
        else:
            logger.warning(
                "memory_injection_blocked",
                key=scored.entry.key,
                patterns=safety.flagged_patterns,
            )

    if not safe_results:
        return {"memory_section": "", "memory_injected": 0, "memories": []}

    # Context budget enforcement (Epic 65.16)
    max_tokens = settings.memory.injection_max_tokens
    budgeted_results: list[Any] = []
    used_tokens = 0
    for scored in safe_results[:max_inject]:
        entry = scored.entry
        tier = entry.tier.value if hasattr(entry.tier, "value") else str(entry.tier)
        entry_text = (
            f"- **{entry.key}** (confidence: {scored.effective_confidence:.2f}, "
            f"tier: {tier}): {entry.value}"
        )
        entry_tokens = estimate_tokens(entry_text)
        if used_tokens + entry_tokens > max_tokens and budgeted_results:
            break
        budgeted_results.append(scored)
        used_tokens += entry_tokens

    truncated = len(budgeted_results) < len(safe_results[:max_inject])

    # Format the injection section
    lines = ["### Project Memory"]
    summaries = []
    for scored in budgeted_results:
        entry = scored.entry
        tier = entry.tier.value if hasattr(entry.tier, "value") else str(entry.tier)
        lines.append(
            f"- **{entry.key}** (confidence: {scored.effective_confidence:.2f}, "
            f"tier: {tier}): {entry.value}"
        )
        summaries.append({
            "key": entry.key,
            "confidence": scored.effective_confidence,
            "tier": tier,
            "score": scored.score,
            "stale": scored.stale,
        })

    return {
        "memory_section": "\n".join(lines),
        "memory_injected": len(budgeted_results),
        "memories": summaries,
        "truncated": truncated,
        "injected_tokens": used_tokens,
    }


def append_memory_to_answer(answer: str, memory_result: dict[str, Any]) -> str:
    """Append memory section to an expert/research answer if available."""
    section = memory_result.get("memory_section", "")
    if not section:
        return answer
    return f"{answer}\n\n---\n\n{section}"
