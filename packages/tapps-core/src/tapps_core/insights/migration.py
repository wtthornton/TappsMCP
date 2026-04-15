"""Migration utilities: promote bare MemoryEntry records to InsightEntry.

Migration design:
- Non-destructive: the original MemoryEntry is never modified in the store.
  The caller is responsible for writing the returned InsightEntry.
- Idempotent: migrating an already-promoted InsightEntry returns an equivalent
  InsightEntry with the same schema_version.
- Conservative defaults: missing insight_type is inferred from tags where
  possible; falls back to InsightType.quality. Origin defaults to unknown.
- Bulk helper: :func:`bulk_migrate` processes a list and returns a
  :class:`InsightMigrationResult` with both successes and failures.

Typical usage::

    from tapps_core.insights.migration import migrate_memory_entry_to_insight
    from tapps_core.insights.models import InsightOrigin

    insight = migrate_memory_entry_to_insight(
        entry,
        server_origin=InsightOrigin.docs_mcp,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from tapps_core.insights.models import (
    INSIGHT_SCHEMA_VERSION,
    InsightEntry,
    InsightOrigin,
    InsightType,
    SubjectKind,
)

if TYPE_CHECKING:
    from tapps_brain.models import MemoryEntry

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Tag → InsightType heuristics
# ---------------------------------------------------------------------------

_TAG_TYPE_MAP: dict[str, InsightType] = {
    "architecture": InsightType.architecture,
    "arch": InsightType.architecture,
    "design": InsightType.architecture,
    "docs": InsightType.documentation,
    "documentation": InsightType.documentation,
    "readme": InsightType.documentation,
    "security": InsightType.security,
    "vuln": InsightType.security,
    "cve": InsightType.security,
    "pattern": InsightType.pattern,
    "anti-pattern": InsightType.pattern,
    "convention": InsightType.pattern,
    "dependency": InsightType.dependency,
    "dep": InsightType.dependency,
    "import": InsightType.dependency,
    "quality": InsightType.quality,
    "score": InsightType.quality,
    "lint": InsightType.quality,
}


def _infer_insight_type(entry: MemoryEntry) -> InsightType:
    """Infer InsightType from tag names; default to quality."""
    for tag in entry.tags:
        normalized = tag.lower().strip()
        if normalized in _TAG_TYPE_MAP:
            return _TAG_TYPE_MAP[normalized]
    return InsightType.quality


def _infer_subject_kind(subject_path: str) -> SubjectKind:
    """Infer SubjectKind from a path string."""
    if not subject_path:
        return SubjectKind.system
    p = subject_path.lower()
    if p.endswith(".py"):
        return SubjectKind.file
    if "/" in p or "." in p:
        return SubjectKind.module
    return SubjectKind.system


# ---------------------------------------------------------------------------
# Single-entry migration
# ---------------------------------------------------------------------------


def migrate_memory_entry_to_insight(
    entry: MemoryEntry,
    *,
    insight_type: InsightType | None = None,
    server_origin: InsightOrigin = InsightOrigin.unknown,
    subject_path: str = "",
    subject_kind: SubjectKind | None = None,
) -> InsightEntry:
    """Promote a :class:`tapps_brain.models.MemoryEntry` to an :class:`InsightEntry`.

    All MemoryEntry fields are preserved verbatim. The caller may override
    any insight-specific field; omitting them triggers inference from tags.

    Args:
        entry: Source MemoryEntry (or existing InsightEntry — idempotent).
        insight_type: Explicit classification. Inferred from tags if omitted.
        server_origin: Which server produced this insight.
        subject_path: File/module path the insight is about.
        subject_kind: Granularity override. Inferred from subject_path if omitted.

    Returns:
        A new :class:`InsightEntry` with ``schema_version=INSIGHT_SCHEMA_VERSION``.
    """
    resolved_type = insight_type if insight_type is not None else _infer_insight_type(entry)
    resolved_kind = subject_kind if subject_kind is not None else _infer_subject_kind(subject_path)

    # If already an InsightEntry, preserve origin and subject unless caller overrides.
    if isinstance(entry, InsightEntry):
        resolved_type = insight_type if insight_type is not None else entry.insight_type
        if server_origin is InsightOrigin.unknown:
            server_origin = entry.server_origin
        if not subject_path:
            subject_path = entry.subject_path
        if subject_kind is None:
            resolved_kind = entry.subject_kind

    data = entry.model_dump()
    data.update({
        "insight_type": resolved_type,
        "server_origin": server_origin,
        "schema_version": INSIGHT_SCHEMA_VERSION,
        "subject_path": subject_path,
        "subject_kind": resolved_kind,
    })

    insight = InsightEntry.model_validate(data)
    logger.debug(
        "migrated_to_insight",
        key=entry.key,
        insight_type=str(resolved_type),
        server_origin=str(server_origin),
    )
    return insight


# ---------------------------------------------------------------------------
# Bulk migration
# ---------------------------------------------------------------------------


class InsightMigrationResult(BaseModel):
    """Result of a bulk migration operation."""

    succeeded: list[InsightEntry] = Field(
        default_factory=list,
        description="Successfully migrated InsightEntry records.",
    )
    failed_keys: list[str] = Field(
        default_factory=list,
        description="Keys of entries that could not be migrated (validation error).",
    )
    total: int = Field(default=0, ge=0, description="Total entries processed.")
    success_count: int = Field(default=0, ge=0, description="Count of successful migrations.")
    failure_count: int = Field(default=0, ge=0, description="Count of failed migrations.")


def bulk_migrate(
    entries: list[MemoryEntry],
    *,
    server_origin: InsightOrigin = InsightOrigin.unknown,
    subject_path: str = "",
) -> InsightMigrationResult:
    """Migrate a list of MemoryEntry records to InsightEntry in bulk.

    Failures (validation errors) are captured per-key and do not abort the
    entire batch. The caller should inspect ``failed_keys`` and handle or
    log them as appropriate.

    Args:
        entries: Source entries to promote.
        server_origin: Applied to all entries (can be overridden per-entry by
                       using :func:`migrate_memory_entry_to_insight` directly).
        subject_path: Applied to all entries that lack a subject_path.

    Returns:
        :class:`InsightMigrationResult` with successes, failures, and counts.
    """
    succeeded: list[InsightEntry] = []
    failed_keys: list[str] = []

    for entry in entries:
        try:
            insight = migrate_memory_entry_to_insight(
                entry,
                server_origin=server_origin,
                subject_path=subject_path if not isinstance(entry, InsightEntry) else "",
            )
            succeeded.append(insight)
        except Exception:
            logger.warning("insight_migration_failed", key=entry.key, exc_info=True)
            failed_keys.append(entry.key)

    result = InsightMigrationResult(
        succeeded=succeeded,
        failed_keys=failed_keys,
        total=len(entries),
        success_count=len(succeeded),
        failure_count=len(failed_keys),
    )
    logger.info(
        "bulk_migrate_complete",
        total=result.total,
        succeeded=result.success_count,
        failed=result.failure_count,
    )
    return result
