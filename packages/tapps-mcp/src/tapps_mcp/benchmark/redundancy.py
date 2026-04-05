"""Enhanced redundancy analysis with per-section scoring and TF-IDF.

Provides ``RedundancyAnalyzerV2`` which computes TF-IDF cosine similarity
combined with token-level Jaccard overlap to score template sections
against existing repository documentation. Generates reduced templates
by removing or trimming redundant sections.
"""

from __future__ import annotations

import contextlib
import math
import re
from collections import Counter
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RedundancyAnalyzerV2",
    "SectionRedundancyReport",
    "TemplateRedundancyReport",
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")

# Thresholds for section recommendations.
_REMOVE_THRESHOLD = 0.6
_REDUCE_THRESHOLD = 0.3

# TF-IDF weight in the combined similarity score.
_TFIDF_WEIGHT = 0.6
_JACCARD_WEIGHT = 0.4

# Files to collect as existing repository documentation.
_REPO_DOC_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "CLAUDE.md",
    "AGENTS.md",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SectionRedundancyReport(BaseModel):
    """Per-section redundancy analysis result."""

    model_config = ConfigDict(frozen=True)

    section_name: str = Field(description="Name of the template section.")
    section_content: str = Field(description="Full content of the section.")
    redundancy_score: float = Field(
        ge=0.0, le=1.0, description="Combined redundancy score (0.0-1.0)."
    )
    overlapping_sources: list[str] = Field(
        default_factory=list, description="Source documents with overlap."
    )
    recommendation: str = Field(description="Action: 'keep', 'reduce', or 'remove'.")
    unique_content: str = Field(default="", description="Content unique to this section.")


class TemplateRedundancyReport(BaseModel):
    """Full template redundancy analysis result."""

    model_config = ConfigDict(frozen=True)

    overall_score: float = Field(ge=0.0, le=1.0, description="Average redundancy across sections.")
    sections: list[SectionRedundancyReport] = Field(
        default_factory=list, description="Per-section reports."
    )
    total_sections: int = Field(ge=0, description="Total sections analyzed.")
    sections_to_remove: int = Field(ge=0, description="Sections recommended for removal.")
    sections_to_reduce: int = Field(ge=0, description="Sections recommended for reduction.")


# ---------------------------------------------------------------------------
# TF-IDF helpers (no scikit-learn dependency)
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokenization returning a list (preserves frequency)."""
    return _WORD_RE.findall(text.lower())


def _tokenize_set(text: str) -> set[str]:
    """Lowercase word tokenization returning a set (unique tokens)."""
    return set(_WORD_RE.findall(text.lower()))


def _build_tf(tokens: list[str]) -> dict[str, float]:
    """Compute term frequency (normalized by document length).

    Returns a mapping of term to its relative frequency in the document.
    """
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = len(tokens)
    return {term: count / total for term, count in counts.items()}


def _build_idf(documents: list[list[str]]) -> dict[str, float]:
    """Compute inverse document frequency across a document collection.

    Uses the standard IDF formula: log(N / df(t)) where N is the total
    number of documents and df(t) is the number of documents containing
    term t.
    """
    n_docs = len(documents)
    if n_docs == 0:
        return {}

    df: Counter[str] = Counter()
    for doc_tokens in documents:
        unique_tokens = set(doc_tokens)
        for token in unique_tokens:
            df[token] += 1

    return {
        term: math.log((n_docs + 1) / (count + 1)) + 1.0 for term, count in df.items()
    }


def _tfidf_vector(tf: dict[str, float], idf: dict[str, float]) -> dict[str, float]:
    """Compute TF-IDF vector for a single document."""
    return {term: freq * idf.get(term, 0.0) for term, freq in tf.items()}


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors.

    Returns 0.0 when either vector is zero.
    """
    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    if not common_keys:
        return 0.0

    dot_product = sum(vec_a[k] * vec_b[k] for k in common_keys)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown text on ``## `` headers.

    Returns a list of ``(section_name, body)`` tuples.
    Content before the first ``## `` header is assigned ``"_preamble"``.
    """
    parts = re.split(r"(?m)^## ", text)
    sections: list[tuple[str, str]] = []
    for i, part in enumerate(parts):
        if i == 0:
            stripped = part.strip()
            if stripped:
                sections.append(("_preamble", stripped))
            continue
        lines = part.split("\n", 1)
        name = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections.append((name, body))
    return sections


def _extract_unique_content(section_tokens: set[str], doc_tokens: set[str]) -> str:
    """Extract tokens unique to the section (not found in docs)."""
    unique = section_tokens - doc_tokens
    return " ".join(sorted(unique))


def _recommend(score: float) -> str:
    """Map a redundancy score to an action recommendation."""
    if score > _REMOVE_THRESHOLD:
        return "remove"
    if score >= _REDUCE_THRESHOLD:
        return "reduce"
    return "keep"


# ---------------------------------------------------------------------------
# Repository documentation collection
# ---------------------------------------------------------------------------


def _collect_repo_docs(repo_path: Path) -> dict[str, str]:
    """Read standard documentation files from a repository.

    Returns a mapping of filename to content. Also extracts the
    ``[project.description]`` from ``pyproject.toml`` if available.
    """
    docs: dict[str, str] = {}
    for name in _REPO_DOC_FILES:
        path = repo_path / name
        if path.is_file():
            with contextlib.suppress(OSError):
                docs[name] = path.read_text(encoding="utf-8")

    pyproject = repo_path / "pyproject.toml"
    if pyproject.is_file():
        with contextlib.suppress(OSError):
            text = pyproject.read_text(encoding="utf-8")
            match = re.search(r'(?m)^description\s*=\s*"([^"]*)"', text)
            if match:
                docs["pyproject.toml:description"] = match.group(1)

    return docs


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class RedundancyAnalyzerV2:
    """Enhanced redundancy analyzer with TF-IDF and Jaccard scoring."""

    def analyze_template_redundancy(
        self, template: str, repo_path: Path
    ) -> TemplateRedundancyReport:
        """Analyze template redundancy against repository documentation.

        For each section in the template, computes a combined score
        using TF-IDF cosine similarity (60%) and token-level Jaccard
        (40%) against the collected repo docs.

        Args:
            template: Full template content.
            repo_path: Path to the repository root.

        Returns:
            Comprehensive redundancy report with per-section analysis.
        """
        repo_docs = _collect_repo_docs(repo_path)
        sections = _split_sections(template)

        if not sections:
            return TemplateRedundancyReport(
                overall_score=0.0,
                sections=[],
                total_sections=0,
                sections_to_remove=0,
                sections_to_reduce=0,
            )

        # Build document collection for TF-IDF (repo docs + template sections)
        doc_names = list(repo_docs.keys())
        doc_texts = list(repo_docs.values())

        # Tokenize all documents
        all_doc_tokens: list[list[str]] = [_tokenize(text) for text in doc_texts]
        section_token_lists = [_tokenize(body) for _, body in sections]

        # Build IDF from the full collection (repo docs + sections)
        full_collection = all_doc_tokens + section_token_lists
        idf = _build_idf(full_collection)

        # Compute TF-IDF vectors for repo docs
        repo_tfidf_vectors = [_tfidf_vector(_build_tf(tokens), idf) for tokens in all_doc_tokens]

        # Combined tokens from all repo docs (for Jaccard)
        combined_doc_tokens: set[str] = set()
        for tokens in all_doc_tokens:
            combined_doc_tokens.update(tokens)

        # Analyze each section
        section_reports: list[SectionRedundancyReport] = []
        for (name, body), section_tokens_list in zip(sections, section_token_lists, strict=True):
            section_tf = _build_tf(section_tokens_list)
            section_tfidf = _tfidf_vector(section_tf, idf)
            section_token_set = set(section_tokens_list)

            # Find overlapping sources and compute max cosine similarity
            overlapping: list[str] = []
            max_cosine = 0.0
            for doc_name, doc_vec in zip(doc_names, repo_tfidf_vectors, strict=True):
                sim = _cosine_similarity(section_tfidf, doc_vec)
                if sim > 0.1:
                    overlapping.append(doc_name)
                max_cosine = max(max_cosine, sim)

            # Compute Jaccard with combined docs
            jaccard = _jaccard_similarity(section_token_set, combined_doc_tokens)

            # Combined score
            combined_score = min(1.0, _TFIDF_WEIGHT * max_cosine + _JACCARD_WEIGHT * jaccard)

            unique = _extract_unique_content(section_token_set, combined_doc_tokens)

            report = SectionRedundancyReport(
                section_name=name,
                section_content=body,
                redundancy_score=round(combined_score, 4),
                overlapping_sources=overlapping,
                recommendation=_recommend(combined_score),
                unique_content=unique,
            )
            section_reports.append(report)

        # Compute overall score
        overall = (
            sum(s.redundancy_score for s in section_reports) / len(section_reports)
            if section_reports
            else 0.0
        )

        to_remove = sum(1 for s in section_reports if s.recommendation == "remove")
        to_reduce = sum(1 for s in section_reports if s.recommendation == "reduce")

        logger.info(
            "redundancy_analysis_complete",
            total_sections=len(section_reports),
            overall_score=round(overall, 4),
            to_remove=to_remove,
            to_reduce=to_reduce,
        )

        return TemplateRedundancyReport(
            overall_score=round(overall, 4),
            sections=section_reports,
            total_sections=len(section_reports),
            sections_to_remove=to_remove,
            sections_to_reduce=to_reduce,
        )

    def generate_reduced_template(self, report: TemplateRedundancyReport) -> str:
        """Generate a reduced template based on redundancy analysis.

        Removes sections marked ``"remove"`` and strips overlapping
        content from sections marked ``"reduce"``. Preserves ``"keep"``
        sections verbatim and maintains markdown structure.

        Args:
            report: Redundancy analysis report.

        Returns:
            Reduced template string.
        """
        lines: list[str] = []
        for section in report.sections:
            if section.recommendation == "remove":
                continue

            if section.section_name == "_preamble":
                if section.recommendation == "reduce" and section.unique_content:
                    lines.append(section.unique_content)
                else:
                    lines.append(section.section_content)
                lines.append("")
                continue

            lines.append(f"## {section.section_name}")
            if section.recommendation == "reduce" and section.unique_content:
                lines.append(section.unique_content)
            else:
                lines.append(section.section_content)
            lines.append("")

        return "\n".join(lines).strip() + "\n"
