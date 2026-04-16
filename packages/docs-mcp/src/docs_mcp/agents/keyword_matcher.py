"""Keyword-based agent matching for DocsMCP.

Provides a simple TF-IDF-inspired overlap scorer as the baseline
matching strategy and fallback when embeddings are unavailable.
"""

from __future__ import annotations

import re
from collections import Counter

# Common English stopwords for filtering
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "it",
        "in",
        "on",
        "at",
        "to",
        "of",
        "for",
        "and",
        "or",
        "but",
        "not",
        "with",
        "by",
        "from",
        "as",
        "be",
        "was",
        "are",
        "were",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "my",
        "your",
        "his",
        "her",
        "its",
        "our",
        "their",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words, removing stopwords.

    Handles hyphenated and underscore-joined tokens as single units
    (e.g., ``machine-learning``, ``api_key``).
    """
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def keyword_score(query_tokens: list[str], agent_tokens: list[str]) -> float:
    """Compute keyword overlap score between query and agent tokens.

    Uses a normalized overlap metric: the count of shared token types
    divided by the geometric mean of both token-set sizes. This balances
    precision (how much of the query matches) with recall (how much of
    the agent's keywords are covered).

    Returns a score in [0.0, 1.0].
    """
    if not query_tokens or not agent_tokens:
        return 0.0

    query_counts = Counter(query_tokens)
    agent_counts = Counter(agent_tokens)

    # Count shared token types (not instances)
    shared = set(query_counts) & set(agent_counts)
    if not shared:
        return 0.0

    # Geometric mean normalization
    query_size = len(set(query_counts))
    agent_size = len(set(agent_counts))
    denominator = (query_size * agent_size) ** 0.5

    return len(shared) / denominator if denominator > 0 else 0.0
