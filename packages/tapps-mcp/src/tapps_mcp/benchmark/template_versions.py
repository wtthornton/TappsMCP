"""Template version tracking with SQLite persistence.

Records template versions, their benchmark scores, redundancy metrics,
and promotion status. Enables comparing template iterations and
selecting the best-performing version for each engagement level.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import structlog
from pydantic import BaseModel, ConfigDict, Field

from tapps_mcp.benchmark.models import BenchmarkSummary

__all__ = [
    "TemplateVersion",
    "TemplateVersionStore",
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS template_versions (
    version          INTEGER PRIMARY KEY,
    content_hash     TEXT    NOT NULL,
    engagement_level TEXT    NOT NULL,
    benchmark_scores TEXT,
    redundancy_score REAL,
    section_scores   TEXT,
    created_at       TEXT    NOT NULL,
    promoted         INTEGER NOT NULL DEFAULT 0,
    promotion_reason TEXT,
    metadata         TEXT    NOT NULL DEFAULT '{}'
)
"""

_INSERT_SQL = """\
INSERT INTO template_versions
    (content_hash, engagement_level, created_at, metadata)
VALUES
    (?, ?, datetime('now'), ?)
"""

_UPDATE_SCORES_SQL = """\
UPDATE template_versions
SET benchmark_scores = ?,
    redundancy_score = ?,
    section_scores   = ?
WHERE version = ?
"""

_SELECT_LATEST_SQL = """\
SELECT * FROM template_versions
WHERE engagement_level = ?
ORDER BY version DESC
LIMIT 1
"""

_SELECT_HISTORY_SQL = """\
SELECT * FROM template_versions
WHERE engagement_level = ?
ORDER BY version DESC
LIMIT ?
"""

_SELECT_VERSION_SQL = """\
SELECT * FROM template_versions
WHERE version = ?
"""

_PROMOTE_SQL = """\
UPDATE template_versions
SET promoted = 1, promotion_reason = ?
WHERE version = ?
"""


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class TemplateVersion(BaseModel):
    """A versioned snapshot of a template with optional benchmark scores."""

    model_config = ConfigDict(frozen=True)

    version: int = Field(description="Auto-incremented version number.")
    content_hash: str = Field(description="SHA-256 hash of the template content.")
    engagement_level: str = Field(description="Engagement level (high/medium/low).")
    benchmark_scores: BenchmarkSummary | None = Field(
        default=None, description="Benchmark results for this version."
    )
    redundancy_score: float | None = Field(
        default=None, description="Overall redundancy score (0.0-1.0)."
    )
    section_scores: dict[str, float] | None = Field(
        default=None, description="Per-section redundancy scores."
    )
    created_at: str = Field(description="ISO-8601 creation timestamp.")
    promoted: bool = Field(default=False, description="Whether this version is promoted.")
    promotion_reason: str | None = Field(default=None, description="Reason for promotion.")
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Arbitrary key-value metadata."
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class TemplateVersionStore:
    """SQLite-backed store for template version tracking."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()
        logger.debug("template_version_store_init", db_path=str(db_path))

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def record_version(
        self,
        content: str,
        engagement_level: str,
        metadata: dict[str, str] | None = None,
    ) -> TemplateVersion:
        """Record a new template version.

        Args:
            content: Full template content.
            engagement_level: Engagement level for this template.
            metadata: Optional key-value metadata.

        Returns:
            The newly created ``TemplateVersion``.
        """
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        meta_json = json.dumps(metadata or {})

        cursor = self._conn.execute(_INSERT_SQL, (content_hash, engagement_level, meta_json))
        self._conn.commit()
        version_id = cursor.lastrowid

        logger.info(
            "template_version_recorded",
            version=version_id,
            engagement_level=engagement_level,
            content_hash=content_hash[:12],
        )

        row = self._conn.execute(_SELECT_VERSION_SQL, (version_id,)).fetchone()
        return self._row_to_model(row)

    def record_scores(
        self,
        version: int,
        benchmark_scores: BenchmarkSummary | None = None,
        redundancy_score: float | None = None,
        section_scores: dict[str, float] | None = None,
    ) -> None:
        """Record benchmark and redundancy scores for a version.

        Args:
            version: Version number to update.
            benchmark_scores: Benchmark summary results.
            redundancy_score: Overall redundancy score.
            section_scores: Per-section redundancy scores.
        """
        scores_json = benchmark_scores.model_dump_json() if benchmark_scores else None
        sections_json = json.dumps(section_scores) if section_scores else None

        self._conn.execute(
            _UPDATE_SCORES_SQL,
            (scores_json, redundancy_score, sections_json, version),
        )
        self._conn.commit()
        logger.debug("template_scores_recorded", version=version)

    def get_latest(self, engagement_level: str) -> TemplateVersion | None:
        """Get the latest version for an engagement level.

        Args:
            engagement_level: Engagement level to query.

        Returns:
            Latest version or ``None`` if none exist.
        """
        row = self._conn.execute(_SELECT_LATEST_SQL, (engagement_level,)).fetchone()
        if row is None:
            return None
        return self._row_to_model(row)

    def get_history(self, engagement_level: str, limit: int = 10) -> list[TemplateVersion]:
        """Get version history for an engagement level.

        Args:
            engagement_level: Engagement level to query.
            limit: Maximum number of versions to return.

        Returns:
            List of versions, newest first.
        """
        rows = self._conn.execute(_SELECT_HISTORY_SQL, (engagement_level, limit)).fetchall()
        return [self._row_to_model(row) for row in rows]

    def get_best(self, engagement_level: str) -> TemplateVersion | None:
        """Get the version with the highest resolution rate.

        Args:
            engagement_level: Engagement level to query.

        Returns:
            Best version or ``None`` if none have benchmark scores.
        """
        rows = self._conn.execute(
            "SELECT * FROM template_versions "
            "WHERE engagement_level = ? AND benchmark_scores IS NOT NULL "
            "ORDER BY version DESC",
            (engagement_level,),
        ).fetchall()

        if not rows:
            return None

        best: TemplateVersion | None = None
        best_rate = -1.0

        for row in rows:
            model = self._row_to_model(row)
            if model.benchmark_scores is not None:
                rate = model.benchmark_scores.resolution_rate
                if rate > best_rate:
                    best_rate = rate
                    best = model

        return best

    def promote(self, version: int, reason: str) -> bool:
        """Mark a version as promoted.

        Args:
            version: Version number to promote.
            reason: Reason for promotion.

        Returns:
            ``True`` if the version was found and promoted.
        """
        row = self._conn.execute(_SELECT_VERSION_SQL, (version,)).fetchone()
        if row is None:
            return False

        self._conn.execute(_PROMOTE_SQL, (reason, version))
        self._conn.commit()
        logger.info("template_version_promoted", version=version, reason=reason)
        return True

    def compare(self, version_a: int, version_b: int) -> dict[str, Any]:
        """Compare two template versions.

        Args:
            version_a: First version number.
            version_b: Second version number.

        Returns:
            Dictionary with comparison metrics.
        """
        row_a = self._conn.execute(_SELECT_VERSION_SQL, (version_a,)).fetchone()
        row_b = self._conn.execute(_SELECT_VERSION_SQL, (version_b,)).fetchone()

        if row_a is None or row_b is None:
            return {
                "error": "One or both versions not found",
                "version_a_exists": row_a is not None,
                "version_b_exists": row_b is not None,
            }

        model_a = self._row_to_model(row_a)
        model_b = self._row_to_model(row_b)

        result: dict[str, Any] = {
            "version_a": version_a,
            "version_b": version_b,
            "same_content": model_a.content_hash == model_b.content_hash,
            "engagement_level_a": model_a.engagement_level,
            "engagement_level_b": model_b.engagement_level,
        }

        # Compare resolution rates if both have benchmark scores
        rate_a = model_a.benchmark_scores.resolution_rate if model_a.benchmark_scores else None
        rate_b = model_b.benchmark_scores.resolution_rate if model_b.benchmark_scores else None

        result["resolution_rate_a"] = rate_a
        result["resolution_rate_b"] = rate_b
        if rate_a is not None and rate_b is not None:
            result["resolution_delta"] = rate_b - rate_a

        # Compare redundancy scores
        result["redundancy_score_a"] = model_a.redundancy_score
        result["redundancy_score_b"] = model_b.redundancy_score
        if model_a.redundancy_score is not None and model_b.redundancy_score is not None:
            result["redundancy_delta"] = model_b.redundancy_score - model_a.redundancy_score

        return result

    # -- private helpers --------------------------------------------------

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> TemplateVersion:
        """Convert a SQLite row to a ``TemplateVersion`` model."""
        benchmark_scores: BenchmarkSummary | None = None
        if row["benchmark_scores"]:
            benchmark_scores = BenchmarkSummary.model_validate_json(row["benchmark_scores"])

        section_scores: dict[str, float] | None = None
        if row["section_scores"]:
            section_scores = json.loads(row["section_scores"])

        metadata: dict[str, str] = {}
        if row["metadata"]:
            metadata = json.loads(row["metadata"])

        return TemplateVersion(
            version=row["version"],
            content_hash=row["content_hash"],
            engagement_level=row["engagement_level"],
            benchmark_scores=benchmark_scores,
            redundancy_score=row["redundancy_score"],
            section_scores=section_scores,
            created_at=row["created_at"],
            promoted=bool(row["promoted"]),
            promotion_reason=row["promotion_reason"],
            metadata=metadata,
        )
