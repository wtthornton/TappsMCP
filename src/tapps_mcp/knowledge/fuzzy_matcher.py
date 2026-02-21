"""Fuzzy matcher v2 — multi-signal library name resolution.

Combines LCS similarity, edit distance, and token overlap for more
accurate library name matching.  Includes confidence bands and "did you
mean" suggestions for ambiguous matches.

No external fuzzy-matching library required.
"""

from __future__ import annotations

import structlog

from tapps_mcp.knowledge.models import FuzzyMatch

logger = structlog.get_logger(__name__)

# Confidence bands for match quality.
CONFIDENCE_HIGH = 0.85
CONFIDENCE_MEDIUM = 0.6
CONFIDENCE_LOW = 0.4

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


def edit_distance(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between *a* and *b*."""
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m

    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev, curr = curr, [0] * (n + 1)
    return prev[n]


def edit_distance_similarity(a: str, b: str) -> float:
    """Return a similarity score in [0.0, 1.0] based on edit distance.

    ``score = 1 - (edit_distance / max(len(a), len(b)))``
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    a_low = a.lower()
    b_low = b.lower()
    max_len = max(len(a_low), len(b_low))
    return 1.0 - edit_distance(a_low, b_low) / max_len


def token_overlap_score(a: str, b: str) -> float:
    """Score overlap of tokens (split on hyphens, underscores, spaces).

    Returns fraction of tokens in *a* that appear in *b*.
    """
    import re

    tokens_a = set(re.split(r"[-_ ]+", a.lower()))
    tokens_b = set(re.split(r"[-_ ]+", b.lower()))
    tokens_a.discard("")
    tokens_b.discard("")
    if not tokens_a:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a)


def multi_signal_score(query: str, candidate: str) -> float:
    """Combine LCS, edit distance, and token overlap into a single score.

    Weights: LCS 0.4, edit distance 0.35, token overlap 0.25.
    """
    lcs = lcs_similarity(query, candidate)
    ed = edit_distance_similarity(query, candidate)
    tok = token_overlap_score(query, candidate)
    return 0.4 * lcs + 0.35 * ed + 0.25 * tok


def confidence_band(score: float) -> str:
    """Classify a match score into a confidence band.

    Returns ``"high"``, ``"medium"``, or ``"low"``.
    """
    if score >= CONFIDENCE_HIGH:
        return "high"
    if score >= CONFIDENCE_MEDIUM:
        return "medium"
    return "low"


def resolve_alias(name: str) -> str:
    """Resolve a library alias to its canonical name."""
    return LIBRARY_ALIASES.get(name.lower().strip(), name.strip())


def fuzzy_match_library(
    query: str,
    known_libraries: list[str],
    *,
    threshold: float = 0.4,
    max_results: int = 5,
    project_libraries: list[str] | None = None,
) -> list[FuzzyMatch]:
    """Match *query* against *known_libraries* using multi-signal similarity.

    Uses a combination of LCS, edit distance, and token overlap for scoring.
    Libraries present in the project manifest get a priority boost.

    Args:
        query: Library name query string.
        known_libraries: List of known library names to match against.
        threshold: Minimum similarity score to include.
        max_results: Maximum number of results.
        project_libraries: Libraries from project manifest for priority boost.

    Returns:
        Sorted list of FuzzyMatch results (best first).
    """
    resolved = resolve_alias(query)
    query_lower = resolved.lower()
    matches: list[FuzzyMatch] = []
    project_set = {lib.lower() for lib in (project_libraries or [])}

    for lib in known_libraries:
        lib_lower = lib.lower()

        # Exact match
        if query_lower == lib_lower:
            matches.append(FuzzyMatch(library=lib, score=1.0, match_type="exact"))
            continue

        # Multi-signal scoring (v2)
        score = multi_signal_score(query_lower, lib_lower)

        # Prefix match bonus
        if lib_lower.startswith(query_lower) or query_lower.startswith(lib_lower):
            score = min(1.0, score + 0.15)

        # Project manifest prior: boost libraries found in the project.
        if project_set and lib_lower in project_set:
            score = min(1.0, score + 0.10)

        if score >= threshold:
            band = confidence_band(score)
            matches.append(
                FuzzyMatch(library=lib, score=round(score, 4), match_type=f"fuzzy_{band}")
            )

    # Sort by score descending
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:max_results]


def did_you_mean(
    query: str,
    known_libraries: list[str],
    *,
    threshold: float = 0.3,
    max_suggestions: int = 3,
) -> list[str]:
    """Return "did you mean?" suggestions for a low-confidence or failed match.

    Uses a lower threshold than normal matching to catch plausible typos.

    Args:
        query: The user's library name query.
        known_libraries: All known library names.
        threshold: Minimum score for a suggestion.
        max_suggestions: Maximum number of suggestions to return.

    Returns:
        List of library name suggestions, best first.
    """
    matches = fuzzy_match_library(
        query,
        known_libraries,
        threshold=threshold,
        max_results=max_suggestions,
    )
    return [m.library for m in matches if confidence_band(m.score) != "high"]


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
