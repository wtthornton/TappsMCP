"""Documentation freshness scoring based on file modification times."""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# Documentation file extensions to scan.
_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})

# Directories to skip.
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", "__pycache__", "node_modules",
    ".venv", "venv", ".env", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build",
    ".eggs",
})

# Freshness thresholds in days.
_FRESH_THRESHOLD = 30
_AGING_THRESHOLD = 90
_STALE_THRESHOLD = 365


class FreshnessItem(BaseModel):
    """Freshness info for a single documentation file."""

    file_path: str
    last_modified: str  # ISO date
    age_days: int
    freshness: str  # "fresh", "aging", "stale", "ancient"


class FreshnessReport(BaseModel):
    """Aggregated freshness scoring results."""

    items: list[FreshnessItem] = []
    average_age_days: float = 0.0
    freshness_score: float = 0.0  # 0-100, higher is better
    category_counts: dict[str, int] = Field(
        default_factory=lambda: {"fresh": 0, "aging": 0, "stale": 0, "ancient": 0},
    )


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped during scanning."""
    if dirname in _SKIP_DIRS:
        return True
    return dirname.endswith(".egg-info")


def _classify_freshness(age_days: int) -> str:
    """Classify a file's freshness based on its age in days."""
    if age_days < _FRESH_THRESHOLD:
        return "fresh"
    if age_days < _AGING_THRESHOLD:
        return "aging"
    if age_days < _STALE_THRESHOLD:
        return "stale"
    return "ancient"


def _freshness_weight(age_days: int) -> float:
    """Calculate a freshness weight for scoring.

    Uses exponential decay: newer files contribute more to the score.
    Returns a value between 0.0 and 1.0.
    """
    # Half-life of 90 days: files lose half their "freshness" every 90 days
    half_life = 90.0
    return math.exp(-0.693 * age_days / half_life)


def _find_doc_files(project_root: Path) -> list[Path]:
    """Find all documentation files under the project root."""
    doc_files: list[Path] = []
    if not project_root.is_dir():
        return doc_files

    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        current = Path(dirpath)
        for fname in filenames:
            fpath = current / fname
            if fpath.suffix.lower() in _DOC_EXTENSIONS:
                doc_files.append(fpath)

    return doc_files


class FreshnessChecker:
    """Score documentation freshness based on file modification times."""

    def check(
        self,
        project_root: Path,
        *,
        relative_to: Path | None = None,
    ) -> FreshnessReport:
        """Run freshness check.

        Args:
            project_root: Root directory to scan for doc files.
            relative_to: Base path for computing relative file paths.
                When scanning a subdirectory, pass the true project root
                here so paths remain project-relative. Defaults to
                *project_root* when not provided.

        Returns:
            A FreshnessReport with per-file freshness and overall score.
        """
        if not project_root.is_dir():
            return FreshnessReport()

        rel_base = relative_to if relative_to is not None else project_root

        doc_files = _find_doc_files(project_root)

        if not doc_files:
            return FreshnessReport()

        now = time.time()
        items: list[FreshnessItem] = []
        total_weight = 0.0
        weight_sum = 0.0
        counts: dict[str, int] = {"fresh": 0, "aging": 0, "stale": 0, "ancient": 0}

        for doc_file in doc_files:
            try:
                mtime = doc_file.stat().st_mtime
            except OSError:
                continue

            age_seconds = now - mtime
            age_days = max(0, int(age_seconds / 86400))

            iso_date = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime),
            )
            freshness_label = _classify_freshness(age_days)
            counts[freshness_label] += 1

            rel_path = str(doc_file.relative_to(rel_base)).replace("\\", "/")

            items.append(FreshnessItem(
                file_path=rel_path,
                last_modified=iso_date,
                age_days=age_days,
                freshness=freshness_label,
            ))

            weight = _freshness_weight(age_days)
            weight_sum += weight
            total_weight += 1.0

        # Sort by age descending (stalest first) for actionable truncation
        items.sort(key=lambda it: it.age_days, reverse=True)

        # Calculate average age
        if items:
            average_age = sum(item.age_days for item in items) / len(items)
        else:
            average_age = 0.0

        # Calculate freshness score (0-100)
        if total_weight > 0:
            freshness_score = (weight_sum / total_weight) * 100
        else:
            freshness_score = 0.0

        return FreshnessReport(
            items=items,
            average_age_days=round(average_age, 1),
            freshness_score=round(freshness_score, 1),
            category_counts=counts,
        )
