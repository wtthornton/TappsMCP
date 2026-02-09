"""Fuzzy matcher — library name resolution with LCS-based similarity.

Uses a built-in LCS (Longest Common Subsequence) algorithm for string
similarity.  No external fuzzy-matching library required.
"""

from __future__ import annotations

import structlog

from tapps_mcp.knowledge.models import FuzzyMatch

logger = structlog.get_logger(__name__)

# Common library aliases: alias → canonical name
LIBRARY_ALIASES: dict[str, str] = {
    "pg": "postgres",
    "postgres": "postgresql",
    "tf": "tensorflow",
    "np": "numpy",
    "pd": "pandas",
    "plt": "matplotlib",
    "sk": "scikit-learn",
    "sklearn": "scikit-learn",
    "fa": "fastapi",
    "dj": "django",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "opencv": "opencv-python",
    "jwt": "pyjwt",
    "aio": "aiohttp",
    "boto": "boto3",
    "rx": "rxpy",
    "tz": "pytz",
    "ws": "websockets",
}

# Language hints: library → primary language
LANGUAGE_HINTS: dict[str, str] = {
    "fastapi": "python",
    "django": "python",
    "flask": "python",
    "sqlalchemy": "python",
    "pydantic": "python",
    "pytest": "python",
    "numpy": "python",
    "pandas": "python",
    "tensorflow": "python",
    "pytorch": "python",
    "react": "javascript",
    "next": "javascript",
    "vue": "javascript",
    "svelte": "javascript",
    "express": "javascript",
    "nest": "typescript",
    "angular": "typescript",
}


def lcs_length(a: str, b: str) -> int:
    """Compute the length of the Longest Common Subsequence of *a* and *b*."""
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0

    # Space-optimised DP: two rows
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, [0] * (n + 1)
    return prev[n]


def lcs_similarity(a: str, b: str) -> float:
    """Return a similarity score in [0.0, 1.0] based on LCS ratio.

    ``score = 2 * lcs_len / (len(a) + len(b))``
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    a_low = a.lower()
    b_low = b.lower()
    length = lcs_length(a_low, b_low)
    return 2.0 * length / (len(a_low) + len(b_low))


def resolve_alias(name: str) -> str:
    """Resolve a library alias to its canonical name."""
    return LIBRARY_ALIASES.get(name.lower().strip(), name.strip())


def fuzzy_match_library(
    query: str,
    known_libraries: list[str],
    *,
    threshold: float = 0.4,
    max_results: int = 5,
) -> list[FuzzyMatch]:
    """Match *query* against *known_libraries* using LCS similarity.

    Args:
        query: Library name query string.
        known_libraries: List of known library names to match against.
        threshold: Minimum similarity score to include.
        max_results: Maximum number of results.

    Returns:
        Sorted list of FuzzyMatch results (best first).
    """
    resolved = resolve_alias(query)
    query_lower = resolved.lower()
    matches: list[FuzzyMatch] = []

    for lib in known_libraries:
        lib_lower = lib.lower()

        # Exact match
        if query_lower == lib_lower:
            matches.append(FuzzyMatch(library=lib, score=1.0, match_type="exact"))
            continue

        # Prefix match bonus
        score = lcs_similarity(query_lower, lib_lower)
        if lib_lower.startswith(query_lower) or query_lower.startswith(lib_lower):
            score = min(1.0, score + 0.15)

        if score >= threshold:
            matches.append(FuzzyMatch(library=lib, score=round(score, 4), match_type="fuzzy"))

    # Sort by score descending
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:max_results]


def fuzzy_match_topic(
    query: str,
    topics: list[str],
    *,
    threshold: float = 0.3,
) -> FuzzyMatch | None:
    """Match *query* against available *topics* for a library.

    Returns the best match above the threshold, or ``None``.
    """
    if not topics:
        return None
    best: FuzzyMatch | None = None
    for topic in topics:
        score = lcs_similarity(query.lower(), topic.lower())
        if score >= threshold and (best is None or score > best.score):
            best = FuzzyMatch(library="", topic=topic, score=round(score, 4), match_type="topic")
    return best


def combined_score(
    library_score: float,
    topic_score: float,
    *,
    library_weight: float = 0.6,
    topic_weight: float = 0.4,
) -> float:
    """Compute a weighted combined score for library + topic match."""
    return library_score * library_weight + topic_score * topic_weight
