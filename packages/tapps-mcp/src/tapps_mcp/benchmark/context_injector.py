"""Context injection engine for the benchmark subsystem.

Generates TappsMCP AGENTS.md files and injects them into benchmark
repository checkouts. Also provides redundancy analysis to measure
overlap between injected context and existing repository documentation.
"""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.common.logging import get_logger
from tapps_mcp.prompts.prompt_loader import load_agents_template

log = get_logger(__name__)

__all__ = [
    "ContextInjector",
    "RedundancyAnalyzer",
    "SectionRedundancy",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")

# Redundancy thresholds for section recommendations.
_REDUNDANCY_REMOVE_THRESHOLD = 0.6
_REDUNDANCY_REDUCE_THRESHOLD = 0.3

# Backup file suffix used when preserving existing files.
_BACKUP_SUFFIX = ".bak"


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokenization.

    Splits *text* into a set of lowercase alphanumeric tokens using a
    simple regex. Non-word characters are discarded.
    """
    return set(_WORD_RE.findall(text.lower()))


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute the Jaccard similarity index between two sets.

    Returns 1.0 when both sets are empty (identical empty documents).
    """
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SectionRedundancy(BaseModel):
    """Per-section redundancy score for an AGENTS.md section."""

    model_config = ConfigDict(frozen=True)

    section_name: str = Field(description="Name of the AGENTS.md section.")
    redundancy_score: float = Field(ge=0.0, le=1.0, description="Redundancy score (0.0-1.0).")
    recommendation: str = Field(description="Action recommendation: 'keep', 'reduce', or 'remove'.")


# ---------------------------------------------------------------------------
# ContextInjector
# ---------------------------------------------------------------------------


class ContextInjector:
    """Generate and inject TappsMCP context files into repositories."""

    def __init__(self, engagement_level: str = "medium") -> None:
        self._engagement_level = engagement_level

    def generate_tapps_context(self, repo_path: Path) -> str:
        """Generate TappsMCP AGENTS.md content for a repository.

        Args:
            repo_path: Path to the repository checkout (unused today but
                reserved for future project-type-aware generation).

        Returns:
            The AGENTS.md template content for the configured engagement
            level.
        """
        content = load_agents_template(self._engagement_level)
        log.info(
            "generated_tapps_context",
            repo_path=str(repo_path),
            engagement_level=self._engagement_level,
            content_length=len(content),
        )
        return content

    def inject_context(
        self,
        repo_path: Path,
        content: str,
        filename: str = "AGENTS.md",
    ) -> Path:
        """Write context content into a repository checkout.

        If a file with *filename* already exists at *repo_path*, it is
        backed up as ``{filename}.bak`` so that it can be restored later
        (e.g. for the HUMAN baseline condition).

        Args:
            repo_path: Root of the repository checkout.
            content: Content to write.
            filename: Target filename (default ``AGENTS.md``).

        Returns:
            Absolute path to the written file.
        """
        target = repo_path / filename
        self._backup_if_exists(repo_path, filename)
        target.write_text(content, encoding="utf-8")
        log.info("injected_context", path=str(target), size=len(content))
        return target

    def remove_context(
        self,
        repo_path: Path,
        filename: str = "AGENTS.md",
    ) -> None:
        """Remove an injected context file and restore any backup.

        Args:
            repo_path: Root of the repository checkout.
            filename: Target filename (default ``AGENTS.md``).
        """
        target = repo_path / filename
        backup = repo_path / f"{filename}{_BACKUP_SUFFIX}"

        if target.exists():
            target.unlink()
            log.info("removed_context", path=str(target))

        if backup.exists():
            backup.rename(target)
            log.info(
                "restored_backup",
                backup=str(backup),
                restored=str(target),
            )

    # -- private helpers --------------------------------------------------

    def _backup_if_exists(self, repo_path: Path, filename: str) -> None:
        """Back up an existing file before overwriting it."""
        target = repo_path / filename
        if target.exists():
            backup = repo_path / f"{filename}{_BACKUP_SUFFIX}"
            target.rename(backup)
            log.info(
                "backed_up_existing_file",
                original=str(target),
                backup=str(backup),
            )


# ---------------------------------------------------------------------------
# RedundancyAnalyzer
# ---------------------------------------------------------------------------

# Files to consider as existing repository documentation.
_REPO_DOC_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "CLAUDE.md",
    "AGENTS.md",
)


class RedundancyAnalyzer:
    """Measure token-level redundancy between injected context and docs."""

    def score_redundancy(self, agents_md: str, repo_docs: list[str]) -> float:
        """Compute average Jaccard similarity across *repo_docs*.

        Args:
            agents_md: The AGENTS.md content to compare.
            repo_docs: Existing repository documentation contents.

        Returns:
            Average overlap score from 0.0 (fully unique) to 1.0 (fully
            redundant). Returns 0.0 when *repo_docs* is empty.
        """
        if not repo_docs:
            return 0.0
        agents_tokens = _tokenize(agents_md)
        scores = [_jaccard_similarity(agents_tokens, _tokenize(doc)) for doc in repo_docs]
        return sum(scores) / len(scores)

    def collect_repo_docs(self, repo_path: Path) -> list[str]:
        """Read standard documentation files from a repository.

        Reads ``README.md``, ``CONTRIBUTING.md``, ``CLAUDE.md``, and
        ``AGENTS.md`` when present. Also reads the ``[project.description]``
        field from ``pyproject.toml`` if available.

        Missing files are silently skipped.
        """
        docs: list[str] = []
        for name in _REPO_DOC_FILES:
            path = repo_path / name
            if path.is_file():
                with contextlib.suppress(OSError):
                    docs.append(path.read_text(encoding="utf-8"))

        pyproject = repo_path / "pyproject.toml"
        if pyproject.is_file():
            with contextlib.suppress(OSError):
                text = pyproject.read_text(encoding="utf-8")
                desc = _extract_pyproject_description(text)
                if desc:
                    docs.append(desc)

        return docs

    def analyze_sections(
        self,
        agents_md: str,
        repo_docs: list[str],
    ) -> list[SectionRedundancy]:
        """Score each ``## `` section in *agents_md* against *repo_docs*.

        Sections are identified by splitting on lines starting with
        ``## ``. Each section is scored individually and given a
        recommendation:

        * ``"remove"`` when redundancy > 0.6
        * ``"reduce"`` when redundancy is between 0.3 and 0.6
        * ``"keep"`` when redundancy < 0.3
        """
        sections = _split_sections(agents_md)
        combined_tokens = set[str]()
        for doc in repo_docs:
            combined_tokens |= _tokenize(doc)

        return [_score_section(name, body, combined_tokens) for name, body in sections]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _recommend(score: float) -> str:
    """Map a redundancy score to an action recommendation.

    Returns ``"remove"`` when *score* exceeds the remove threshold,
    ``"reduce"`` when between reduce and remove thresholds, and
    ``"keep"`` otherwise.
    """
    if score > _REDUNDANCY_REMOVE_THRESHOLD:
        return "remove"
    if score >= _REDUNDANCY_REDUCE_THRESHOLD:
        return "reduce"
    return "keep"


def _score_section(name: str, body: str, combined_tokens: set[str]) -> SectionRedundancy:
    """Score a single section against combined repository tokens."""
    section_tokens = _tokenize(body)
    score = _jaccard_similarity(section_tokens, combined_tokens)
    return SectionRedundancy(
        section_name=name,
        redundancy_score=round(score, 4),
        recommendation=_recommend(score),
    )


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown text on ``## `` headers.

    Returns a list of ``(section_name, body)`` tuples. Content before the
    first ``## `` header is assigned the section name ``"_preamble"``.
    """
    parts = re.split(r"(?m)^## ", text)
    sections: list[tuple[str, str]] = []
    for i, part in enumerate(parts):
        if i == 0:
            # Content before the first ## header
            stripped = part.strip()
            if stripped:
                sections.append(("_preamble", stripped))
            continue
        # First line is the header text, rest is the body
        lines = part.split("\n", 1)
        name = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections.append((name, body))
    return sections


def _extract_pyproject_description(text: str) -> str | None:
    """Extract the ``description`` field from a pyproject.toml string.

    Uses a simple regex rather than a TOML parser to avoid adding a
    dependency.
    """
    match = re.search(r'(?m)^description\s*=\s*"([^"]*)"', text)
    if match:
        return match.group(1)
    return None
