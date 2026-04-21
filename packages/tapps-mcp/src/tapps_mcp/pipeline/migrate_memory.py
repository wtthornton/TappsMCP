"""TAP-415: SQLite → tapps-brain v3 memory migration.

Reads ``.tapps-mcp/memory/*.db`` (v2 SQLite schema) and writes each entry
to tapps-brain v3 via ``BrainBridge``. Each migrated entry is tagged with
a ``migration-run:{run_id}`` tag and a marker entry
``migration/run/{run_id}`` is created in brain so the run is idempotent
and reversible.

This is a one-shot tool — callers are expected to run it once per project
when upgrading from the in-process SQLite backend to the tapps-brain
HTTP adapter.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


MIGRATION_RUN_TAG_PREFIX = "migration-run:"
MIGRATION_MARKER_KEY_PREFIX = "migration/run/"
DEFAULT_MEMORY_DIR = ".tapps-mcp/memory"

# v2 scope → v3 scope. v3 dropped ``private``/``group``/``hive`` in favor of
# ``project``/``branch``/``shared``/``session``. ``private`` is the safest
# fallback target (stays within the project boundary).
_SCOPE_MAP: dict[str, str] = {
    "private": "project",
    "group": "project",
    "hive": "shared",
    "project": "project",
    "branch": "branch",
    "shared": "shared",
    "session": "session",
}


@dataclass
class MigrationEntry:
    """Single row from SQLite mapped to BrainBridge.save() kwargs."""

    key: str
    value: str
    tier: str
    scope: str
    source: str
    source_agent: str
    confidence: float
    tags: list[str] = field(default_factory=list)
    branch: str | None = None


@dataclass
class MigrationResult:
    """Outcome of a migrate/rollback run."""

    run_id: str
    dry_run: bool
    discovered_dbs: list[Path]
    migrated: int = 0
    skipped_duplicate: int = 0
    failed: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    tier_counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"migration run_id:       {self.run_id}",
            f"dry_run:                {self.dry_run}",
            f"sqlite dbs discovered:  {len(self.discovered_dbs)}",
            f"entries migrated:       {self.migrated}",
            f"entries skipped (dup):  {self.skipped_duplicate}",
            f"entries failed:         {self.failed}",
        ]
        if self.tier_counts:
            tiers = ", ".join(f"{t}={n}" for t, n in sorted(self.tier_counts.items()))
            lines.append(f"tier distribution:      {tiers}")
        return "\n".join(lines)


def discover_sqlite_dbs(project_root: Path) -> list[Path]:
    """Return all ``*.db`` files under ``<project_root>/.tapps-mcp/memory/``."""
    mem_dir = project_root / DEFAULT_MEMORY_DIR
    if not mem_dir.is_dir():
        return []
    return sorted(p for p in mem_dir.glob("*.db") if p.is_file())


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(loaded, list):
        return [str(t) for t in loaded if t]
    return []


def _row_to_entry(row: sqlite3.Row) -> MigrationEntry:
    raw_scope = (row["scope"] or "project").lower()
    keys = row.keys()
    tags = _parse_tags(row["tags"] if "tags" in keys else None)
    branch = row["branch"] if "branch" in keys else None
    return MigrationEntry(
        key=row["key"],
        value=row["value"],
        tier=row["tier"] or "pattern",
        scope=_SCOPE_MAP.get(raw_scope, "project"),
        source=row["source"] or "agent",
        source_agent=row["source_agent"] or "unknown",
        confidence=float(row["confidence"] or 0.6),
        tags=tags,
        branch=branch if isinstance(branch, str) and branch else None,
    )


def read_sqlite_entries(db_path: Path) -> list[MigrationEntry]:
    """Return all non-archived memory rows from ``db_path``."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT key, value, tier, scope, source, source_agent, "
            "confidence, tags, branch FROM memories"
        )
        return [_row_to_entry(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _tag_entry_with_run(entry: MigrationEntry, run_id: str) -> list[str]:
    """Return a tags list that includes the run_id marker, bounded at 10."""
    run_tag = f"{MIGRATION_RUN_TAG_PREFIX}{run_id}"
    tags = [*entry.tags, run_tag]
    seen: set[str] = set()
    deduped: list[str] = []
    for t in tags:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)
    return deduped[:10]


async def _save_marker(bridge: Any, run_id: str, entries_migrated: int) -> None:
    now = datetime.now(tz=UTC).isoformat()
    payload = json.dumps(
        {"run_id": run_id, "started_at": now, "entries_migrated": entries_migrated}
    )
    await bridge.save(
        f"{MIGRATION_MARKER_KEY_PREFIX}{run_id}",
        payload,
        tier="architectural",
        scope="project",
        tags=[f"{MIGRATION_RUN_TAG_PREFIX}{run_id}", "tapps-mcp-migration"],
    )


async def _migrate_one(bridge: Any, entry: MigrationEntry, run_id: str) -> str:
    """Save one entry via BrainBridge. Return 'ok' | 'duplicate' | 'error'."""
    existing = await bridge.get(entry.key)
    if existing is not None:
        return "duplicate"
    await bridge.save(
        entry.key,
        entry.value,
        tier=entry.tier,
        scope=entry.scope,
        tags=_tag_entry_with_run(entry, run_id),
    )
    return "ok"


async def run_migration(
    project_root: Path,
    bridge: Any,
    *,
    dry_run: bool = False,
    validate_only: bool = False,
) -> MigrationResult:
    """Discover SQLite dbs under ``project_root`` and migrate them via ``bridge``.

    ``dry_run=True`` performs discovery + mapping but no brain writes.
    ``validate_only=True`` is an alias for ``dry_run=True`` that also
    populates ``failures`` with mapping errors per entry.
    """
    run_id = uuid.uuid4().hex[:12]
    dbs = discover_sqlite_dbs(project_root)
    result = MigrationResult(
        run_id=run_id,
        dry_run=dry_run or validate_only,
        discovered_dbs=dbs,
    )
    if not dbs:
        return result

    all_entries: list[MigrationEntry] = []
    for db in dbs:
        try:
            all_entries.extend(read_sqlite_entries(db))
        except sqlite3.DatabaseError as exc:
            result.failed += 1
            result.failures.append({"db": str(db), "error": str(exc)})

    for entry in all_entries:
        result.tier_counts[entry.tier] = result.tier_counts.get(entry.tier, 0) + 1

    if dry_run or validate_only:
        result.migrated = len(all_entries)
        return result

    for entry in all_entries:
        try:
            status = await _migrate_one(bridge, entry, run_id)
        except Exception as exc:
            result.failed += 1
            result.failures.append({"key": entry.key, "error": str(exc)})
            continue
        if status == "duplicate":
            result.skipped_duplicate += 1
        else:
            result.migrated += 1

    if result.migrated > 0:
        try:
            await _save_marker(bridge, run_id, result.migrated)
        except Exception as exc:
            logger.warning("migration_marker_save_failed", run_id=run_id, error=str(exc))

    return result


async def rollback_migration(bridge: Any, run_id: str) -> dict[str, Any]:
    """Delete all entries tagged with ``migration-run:{run_id}`` via ``bridge``.

    Requires a BrainBridge with ``search`` and ``delete`` methods.
    """
    tag = f"{MIGRATION_RUN_TAG_PREFIX}{run_id}"
    try:
        hits = await bridge.search(tag, limit=10000)
    except Exception as exc:
        return {
            "run_id": run_id,
            "ok": False,
            "deleted": 0,
            "error": f"search_failed: {exc}",
        }

    deleted = 0
    errors: list[dict[str, str]] = []
    for hit in hits or []:
        key = hit.get("key") if isinstance(hit, dict) else None
        if not key:
            continue
        try:
            ok = await bridge.delete(key)
        except Exception as exc:
            errors.append({"key": key, "error": str(exc)})
            continue
        if ok:
            deleted += 1

    marker_key = f"{MIGRATION_MARKER_KEY_PREFIX}{run_id}"
    try:
        await bridge.delete(marker_key)
    except Exception:
        # Marker deletion is best-effort; the tagged entries are the
        # authoritative record.
        pass

    return {
        "run_id": run_id,
        "ok": not errors,
        "deleted": deleted,
        "errors": errors,
    }


def sqlite_present(project_root: Path) -> bool:
    """Return True if at least one ``.db`` is present under the memory dir."""
    return bool(discover_sqlite_dbs(project_root))


def run_migration_sync(
    project_root: Path,
    bridge: Any,
    *,
    dry_run: bool = False,
    validate_only: bool = False,
) -> MigrationResult:
    """Sync wrapper for :func:`run_migration`."""
    return asyncio.run(
        run_migration(
            project_root, bridge, dry_run=dry_run, validate_only=validate_only
        )
    )


def rollback_migration_sync(bridge: Any, run_id: str) -> dict[str, Any]:
    """Sync wrapper for :func:`rollback_migration`."""
    return asyncio.run(rollback_migration(bridge, run_id))
