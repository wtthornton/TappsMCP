"""Context7 code-reference quality normalization.

Processes raw Context7 documentation content to:
1. Rank code snippets by completeness + query relevance.
2. Deduplicate similar snippets.
3. Format as compact "reference cards".
4. Enforce per-section token budgets to avoid context overflow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Default token budget per section.
_DEFAULT_SECTION_TOKEN_BUDGET = 800
# Approximate chars per token.
_CHARS_PER_TOKEN = 4
# Minimum snippet length (chars) to be considered useful.
_MIN_SNIPPET_LENGTH = 30
# Jaccard similarity threshold for deduplication.
_DEDUP_THRESHOLD = 0.7
# Minimum lines for a snippet to not be penalised.
_MIN_SNIPPET_LINES = 3
# Maximum lines for a snippet to not be penalised.
_MAX_SNIPPET_LINES = 50


@dataclass
class CodeSnippet:
    """A code snippet extracted from documentation content."""

    code: str
    language: str = ""
    context: str = ""  # Surrounding text/header.
    score: float = 0.0
    token_count: int = 0


@dataclass
class ReferenceCard:
    """Compact reference card for a documentation section."""

    title: str
    snippets: list[CodeSnippet] = field(default_factory=list)
    summary: str = ""
    token_count: int = 0

    def to_markdown(self) -> str:
        parts = [f"### {self.title}"]
        if self.summary:
            parts.append(self.summary)
        for s in self.snippets:
            lang_hint = s.language or ""
            parts.append(f"```{lang_hint}\n{s.code}\n```")
            if s.context:
                parts.append(f"_{s.context}_")
        return "\n\n".join(parts)


@dataclass
class NormalizationResult:
    """Result of normalizing Context7 content."""

    cards: list[ReferenceCard] = field(default_factory=list)
    total_snippets: int = 0
    deduped_snippets: int = 0
    total_tokens: int = 0
    budget_applied: bool = False

    def to_markdown(self) -> str:
        return "\n\n---\n\n".join(card.to_markdown() for card in self.cards)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_snippets": self.total_snippets,
            "deduped_snippets": self.deduped_snippets,
            "total_tokens": self.total_tokens,
            "budget_applied": self.budget_applied,
            "card_count": len(self.cards),
        }


# ---------------------------------------------------------------------------
# Snippet extraction
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(
    r"```(\w*)\n(.*?)```",
    re.DOTALL,
)


def extract_snippets(content: str) -> list[CodeSnippet]:
    """Extract code snippets from markdown content."""
    snippets: list[CodeSnippet] = []
    lines = content.split("\n")
    prev_header = ""

    for match in _CODE_BLOCK_RE.finditer(content):
        language = match.group(1) or ""
        code = match.group(2).strip()
        if len(code) < _MIN_SNIPPET_LENGTH:
            continue

        # Find the nearest header before this snippet.
        start_pos = match.start()
        line_num = content[:start_pos].count("\n")
        for i in range(min(line_num, len(lines) - 1), -1, -1):
            if lines[i].strip().startswith("#"):
                prev_header = lines[i].strip().lstrip("#").strip()
                break

        token_count = len(code) // _CHARS_PER_TOKEN

        snippets.append(
            CodeSnippet(
                code=code,
                language=language,
                context=prev_header,
                token_count=token_count,
            )
        )

    return snippets


# ---------------------------------------------------------------------------
# Snippet ranking
# ---------------------------------------------------------------------------


def rank_snippets(
    snippets: list[CodeSnippet],
    query: str = "",
) -> list[CodeSnippet]:
    """Rank snippets by code completeness + query overlap + language fit.

    Scoring:
    - Completeness: Has imports, function defs, or class defs → higher.
    - Query relevance: Keywords from query appear in snippet → higher.
    - Language fit: Python/JS/TS snippets preferred for TappsMCP context.
    """
    query_lower = query.lower()
    query_words = set(re.split(r"\W+", query_lower)) - {"", "how", "to", "the", "a", "in"}

    for snippet in snippets:
        code_lower = snippet.code.lower()
        score = 0.0

        # Completeness signals.
        if "import " in code_lower or "from " in code_lower:
            score += 0.2
        if "def " in code_lower or "function " in code_lower:
            score += 0.25
        if "class " in code_lower:
            score += 0.15
        if "return " in code_lower:
            score += 0.1

        # Query relevance.
        if query_words:
            hits = sum(1 for w in query_words if w in code_lower)
            score += 0.3 * (hits / len(query_words))

        # Language preference.
        if snippet.language in ("python", "py", "javascript", "js", "typescript", "ts"):
            score += 0.1

        # Penalise very short or very long snippets.
        lines = snippet.code.count("\n") + 1
        if lines < _MIN_SNIPPET_LINES or lines > _MAX_SNIPPET_LINES:
            score -= 0.1

        snippet.score = round(min(1.0, max(0.0, score)), 4)

    snippets.sort(key=lambda s: s.score, reverse=True)
    return snippets


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def deduplicate_snippets(
    snippets: list[CodeSnippet],
    threshold: float = _DEDUP_THRESHOLD,
) -> list[CodeSnippet]:
    """Remove near-duplicate snippets using Jaccard similarity."""
    if len(snippets) <= 1:
        return snippets

    unique: list[CodeSnippet] = [snippets[0]]

    for snippet in snippets[1:]:
        s_words = set(snippet.code.lower().split())
        is_dup = False
        for existing in unique:
            e_words = set(existing.code.lower().split())
            if not s_words or not e_words:
                continue
            # Substring containment.
            s_stripped = snippet.code.strip()
            e_stripped = existing.code.strip()
            if s_stripped in e_stripped or e_stripped in s_stripped:
                is_dup = True
                break
            # Jaccard similarity.
            jaccard = len(s_words & e_words) / len(s_words | e_words)
            if jaccard > threshold:
                is_dup = True
                break
        if not is_dup:
            unique.append(snippet)

    return unique


# ---------------------------------------------------------------------------
# Token budget enforcement
# ---------------------------------------------------------------------------


def apply_token_budget(
    snippets: list[CodeSnippet],
    budget: int = _DEFAULT_SECTION_TOKEN_BUDGET,
) -> list[CodeSnippet]:
    """Keep only snippets that fit within the token budget."""
    result: list[CodeSnippet] = []
    used = 0
    for snippet in snippets:
        if used + snippet.token_count > budget:
            break
        result.append(snippet)
        used += snippet.token_count
    return result


# ---------------------------------------------------------------------------
# Main normalisation pipeline
# ---------------------------------------------------------------------------


def normalize_content(
    content: str,
    query: str = "",
    section_token_budget: int = _DEFAULT_SECTION_TOKEN_BUDGET,
) -> NormalizationResult:
    """Normalise Context7 content into ranked, deduplicated reference cards.

    Args:
        content: Raw documentation content (markdown).
        query: The user's query for relevance ranking.
        section_token_budget: Max tokens per reference card section.

    Returns:
        NormalizationResult with compact reference cards.
    """
    # 1. Extract snippets.
    snippets = extract_snippets(content)
    total_snippets = len(snippets)

    if not snippets:
        return NormalizationResult(total_snippets=0)

    # 2. Rank by quality + relevance.
    ranked = rank_snippets(snippets, query)

    # 3. Deduplicate.
    deduped = deduplicate_snippets(ranked)
    deduped_count = total_snippets - len(deduped)

    # 4. Apply token budget.
    budgeted = apply_token_budget(deduped, section_token_budget)
    budget_applied = len(budgeted) < len(deduped)

    # 5. Group into reference cards by context header.
    card_map: dict[str, list[CodeSnippet]] = {}
    for s in budgeted:
        key = s.context or "General"
        card_map.setdefault(key, []).append(s)

    cards: list[ReferenceCard] = []
    total_tokens = 0
    for title, card_snippets in card_map.items():
        card_tokens = sum(s.token_count for s in card_snippets)
        total_tokens += card_tokens
        cards.append(
            ReferenceCard(
                title=title,
                snippets=card_snippets,
                token_count=card_tokens,
            )
        )

    return NormalizationResult(
        cards=cards,
        total_snippets=total_snippets,
        deduped_snippets=deduped_count,
        total_tokens=total_tokens,
        budget_applied=budget_applied,
    )
