"""One-shot migration: flat ``arch.{project}.*`` brain entries → KG triples (TAP-1953).

Before TAP-1948 the architecture writer stored flat memory entries keyed
``arch.{project}.structure`` / ``arch.{project}.pkg.{name}`` /
``arch.{project}.entry_points`` (tier ``architectural``). TAP-1948 replaced that
flat write path with Knowledge-Graph triples, but any **pre-TAP-1948 leftover**
flat entries still sit in the brain. This module reads those, re-emits each as a
KG entity (with the original prose preserved as ``summary`` metadata plus a
provenance evidence row), and tags the flat entry ``migrated_to_kg=true`` plus a
dated ``migrated_to_kg_at=<iso>`` companion — it never deletes. The terminal GC
(:meth:`ArchMigrator.gc_migrated`, TAP-1954) drops migrated entries once that
dated tag is older than a retention window (default 14 days), reading the date
from the tag because ``memory_list`` exposes no per-entry timestamp.

Brain profiles, one bridge per phase
------------------------------------
No single tapps-brain profile (3.22.0) spans the whole flow, so this module
opens one bridge per phase and pins the profile via the ``X-Brain-Profile``
header:

  - ``reviewer`` — enumerate flat entries (``memory_list`` / ``memory_get``)
  - ``agent_brain`` — emit KG triples (``brain_record_event`` via the TAP-1947
    ``upsert_entity`` / ``add_evidence`` shims)
  - ``seeder`` — re-tag flat entries (``memory_save`` upsert)
  - ``full`` — delete migrated flat entries during GC (``memory_delete``)

Fidelity
--------
Flat values are prose summaries, not structured data, so the migration emits
**entities only** (one ``project`` / ``package`` entity per flat entry) — it does
not attempt to reconstruct ``exports`` / ``depends_on`` edges from prose. The full
edge graph is rebuilt by the live writer on the next ``docs_generate_architecture``
run. The canonical name is parsed from the prose where possible so a migrated
entity collapses onto the live writer's entity (same deterministic UUID).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Tag written onto a flat entry once its KG triples are emitted. TAP-1954's GC
# keys off this exact string.
MIGRATED_TAG = "migrated_to_kg=true"

# Companion tag carrying the ISO date the entry was migrated, e.g.
# ``migrated_to_kg_at=2026-06-02``. tapps-brain's ``memory_list`` exposes no
# per-entry timestamp, so the GC (TAP-1954) reads the migration date from this
# self-describing tag to enforce its retention window without a brain change.
MIGRATED_AT_PREFIX = "migrated_to_kg_at="

# Stored as the evidence ``commit_sha`` so migrated entities are distinguishable
# from code-grounded ones in the KG.
_PROVENANCE_SHA = "arch-to-kg-migration"

# tapps-brain caps metadata values at 4096 chars.
_MAX_VALUE_LEN = 4096

# Brain profiles per phase (see module docstring).
_READ_PROFILE = "reviewer"
_KG_PROFILE = "agent_brain"
_TAG_PROFILE = "seeder"
# Profile exposing ``memory_delete`` for the TAP-1954 GC.
_DELETE_PROFILE = "full"

# Prose shapes produced by the pre-TAP-1948 writer (used to recover the real
# canonical name so migrated entities dedupe with live-writer entities).
_STRUCTURE_RE = re.compile(r"^Architecture summary for (?P<name>.+?):")
_PKG_RE = re.compile(r"^Package (?P<name>.+?) in ")
_ENTRY_RE = re.compile(r"^Entry points for (?P<name>.+?):")


def _truncate(value: str) -> str:
    return value[:_MAX_VALUE_LEN]


@dataclass
class PlannedEntry:
    """A flat entry resolved to its target KG entity."""

    key: str
    entity_type: str
    canonical_name: str
    metadata: dict[str, Any]
    value: str
    tier: str
    scope: str
    tags: list[str]
    status: str = "planned"  # planned | already_migrated | migrated | failed


@dataclass
class MigrationResult:
    """Aggregate outcome of a migration run."""

    dry_run: bool
    available: bool = True
    flat_total: int = 0
    unparseable: int = 0
    planned: list[PlannedEntry] = field(default_factory=list)
    migrated: int = 0
    already_migrated: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when the run completed without per-entry failures."""
        return self.available and self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "available": self.available,
            "flat_total": self.flat_total,
            "to_migrate": len([p for p in self.planned if p.status == "planned"]),
            "already_migrated": self.already_migrated,
            "migrated": self.migrated,
            "unparseable": self.unparseable,
            "failed": self.failed,
            "errors": self.errors,
        }


@dataclass
class GcResult:
    """Aggregate outcome of a GC run (TAP-1954)."""

    dry_run: bool
    available: bool = True
    older_than_days: int = 14
    scanned: int = 0
    eligible: list[str] = field(default_factory=list)
    skipped_undated: int = 0
    skipped_recent: int = 0
    deleted: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.available and self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "available": self.available,
            "older_than_days": self.older_than_days,
            "scanned": self.scanned,
            "eligible": len(self.eligible),
            "skipped_undated": self.skipped_undated,
            "skipped_recent": self.skipped_recent,
            "deleted": self.deleted,
            "failed": self.failed,
            "errors": self.errors,
        }


def _parse_migrated_at(tags: list[str]) -> date | None:
    """Extract the migration date from a ``migrated_to_kg_at=<iso>`` tag."""
    for tag in tags:
        if tag.startswith(MIGRATED_AT_PREFIX):
            try:
                return date.fromisoformat(tag[len(MIGRATED_AT_PREFIX) :])
            except ValueError:
                return None
    return None


def _derive(key: str, value: str) -> tuple[str, str, dict[str, Any]] | None:
    """Resolve a flat ``arch.*`` entry to ``(entity_type, canonical_name, metadata)``.

    Returns ``None`` when *key* is not an ``arch.{project}.*`` entry or its shape
    is unrecognised (caller counts it as unparseable).
    """
    parts = key.split(".")
    if len(parts) < 3 or parts[0] != "arch":
        return None
    project_slug = parts[1]
    rest = parts[2:]
    summary = {"summary": _truncate(value)} if value else {}

    if rest == ["structure"]:
        match = _STRUCTURE_RE.match(value)
        name = match.group("name") if match else project_slug
        return "project", name, summary
    if rest == ["entry_points"]:
        match = _ENTRY_RE.match(value)
        name = match.group("name") if match else project_slug
        return "project", name, summary
    if rest[0] == "pkg" and len(rest) >= 2:
        match = _PKG_RE.match(value)
        name = match.group("name") if match else ".".join(rest[1:])
        return "package", name, summary
    return None


class ArchMigrator:
    """Migrates flat ``arch.*`` brain entries to KG entities.

    Bridges are resolved lazily per phase and may be injected (set the private
    attributes) in tests. The read bridge is always needed; the KG and tag
    bridges are only opened for an ``execute`` run.
    """

    def __init__(self, project_root: Path, settings: Any = None) -> None:
        self._root = project_root
        # tapps-core settings object (TAP-1955). When provided, the brain
        # transport + auth headers resolve from ``.tapps-mcp.yaml`` instead of
        # env vars only — so a CLI operator who configured the brain in their
        # project file does not also have to export
        # ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` / ``_AUTH_TOKEN``. ``None``
        # preserves the env-only behaviour (and test bridge injection).
        self._settings = settings
        self._reader: Any = None
        self._kg: Any = None
        self._tagger: Any = None
        self._deleter: Any = None
        self._reader_resolved = False
        self._kg_resolved = False
        self._tagger_resolved = False
        self._deleter_resolved = False

    # ------------------------------------------------------------------
    # Bridge resolution
    # ------------------------------------------------------------------

    def _make_bridge(self, profile: str) -> Any:
        """Open a BrainBridge pinned to *profile* (None if no transport)."""
        try:
            from tapps_core.brain_bridge import create_brain_bridge

            bridge = create_brain_bridge(settings=self._settings, default_profile=profile)
        except ImportError:
            logger.debug("tapps_core_not_available", root=str(self._root))
            return None
        except Exception:
            logger.warning("arch_migration_bridge_failed", profile=profile, exc_info=True)
            return None
        # Force the profile header so the phase's tool surface is guaranteed
        # regardless of any TAPPS_BRAIN_PROFILE env override (HTTP bridges only).
        headers = getattr(bridge, "_http_headers", None)
        if isinstance(headers, dict):
            headers["X-Brain-Profile"] = profile
        return bridge

    def _reader_bridge(self) -> Any:
        if not self._reader_resolved:
            self._reader = self._make_bridge(_READ_PROFILE)
            self._reader_resolved = True
        return self._reader

    def _kg_bridge(self) -> Any:
        if not self._kg_resolved:
            self._kg = self._make_bridge(_KG_PROFILE)
            self._kg_resolved = True
        return self._kg

    def _tagger_bridge(self) -> Any:
        if not self._tagger_resolved:
            self._tagger = self._make_bridge(_TAG_PROFILE)
            self._tagger_resolved = True
        return self._tagger

    def _deleter_bridge(self) -> Any:
        if not self._deleter_resolved:
            self._deleter = self._make_bridge(_DELETE_PROFILE)
            self._deleter_resolved = True
        return self._deleter

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------

    async def _collect(self) -> list[dict[str, Any]]:
        """List flat ``arch.*`` entries from the architectural tier."""
        reader = self._reader_bridge()
        if reader is None:
            return []
        entries = await reader.list_memories(limit=1000, tier="architectural")
        return [e for e in entries if str(e.get("key", "")).startswith("arch.")]

    async def migrate(self, *, execute: bool, today: date | None = None) -> MigrationResult:
        """Run the migration. ``execute=False`` plans only (writes nothing)."""
        result = MigrationResult(dry_run=not execute)
        stamp = (today or date.today()).isoformat()
        reader = self._reader_bridge()
        if reader is None:
            result.available = False
            result.errors.append("brain bridge unavailable (no transport configured)")
            return result

        raw = await self._collect()
        result.flat_total = len(raw)

        for entry in raw:
            key = str(entry.get("key", ""))
            value = str(entry.get("value", ""))
            derived = _derive(key, value)
            if derived is None:
                result.unparseable += 1
                logger.info("arch_migration_unparseable", key=key)
                continue
            entity_type, canonical_name, metadata = derived
            tags = [str(t) for t in (entry.get("tags") or [])]
            planned = PlannedEntry(
                key=key,
                entity_type=entity_type,
                canonical_name=canonical_name,
                metadata=metadata,
                value=value,
                tier=str(entry.get("tier") or "architectural"),
                scope=str(entry.get("scope") or "project"),
                tags=tags,
            )
            if MIGRATED_TAG in tags:
                planned.status = "already_migrated"
                result.already_migrated += 1
                result.planned.append(planned)
                continue
            if execute:
                await self._migrate_one(planned, result, stamp)
            result.planned.append(planned)

        return result

    async def _migrate_one(
        self, planned: PlannedEntry, result: MigrationResult, stamp: str
    ) -> None:
        """Emit KG triples for one entry and tag the flat entry migrated."""
        kg = self._kg_bridge()
        tagger = self._tagger_bridge()
        if kg is None or tagger is None:
            planned.status = "failed"
            result.failed += 1
            result.errors.append(f"{planned.key}: KG or tagger bridge unavailable")
            return
        try:
            upsert = await kg.upsert_entity(
                planned.canonical_name, planned.entity_type, metadata=planned.metadata
            )
            entity_id = str(upsert.get("entity_id", "")) if isinstance(upsert, dict) else ""
            if entity_id:
                await kg.add_evidence(
                    file_path=f"brain-migration:{planned.key}",
                    line_range="",
                    commit_sha=_PROVENANCE_SHA,
                    entity_id=entity_id,
                )
            await tagger.save(
                planned.key,
                planned.value,
                tier=planned.tier,
                scope=planned.scope,
                tags=sorted({*planned.tags, MIGRATED_TAG, f"{MIGRATED_AT_PREFIX}{stamp}"}),
            )
        except Exception as exc:  # record + continue; CLI exits non-zero on failures
            planned.status = "failed"
            result.failed += 1
            result.errors.append(f"{planned.key}: {type(exc).__name__}: {exc}")
            logger.warning("arch_migration_entry_failed", key=planned.key, exc_info=True)
            return
        planned.status = "migrated"
        result.migrated += 1

    # ------------------------------------------------------------------
    # GC (TAP-1954)
    # ------------------------------------------------------------------

    async def gc_migrated(
        self, *, older_than_days: int = 14, execute: bool, today: date | None = None
    ) -> GcResult:
        """Delete flat entries migrated more than *older_than_days* ago.

        Reads the migration date from the ``migrated_to_kg_at`` tag (no brain
        timestamp exists), so undated entries are skipped as a safety guard.
        ``execute=False`` reports the eligible keys without deleting.
        """
        result = GcResult(dry_run=not execute, older_than_days=older_than_days)
        reader = self._reader_bridge()
        if reader is None:
            result.available = False
            result.errors.append("brain bridge unavailable (no transport configured)")
            return result

        now = today or date.today()
        for entry in await self._collect():
            tags = [str(t) for t in (entry.get("tags") or [])]
            if MIGRATED_TAG not in tags:
                continue
            result.scanned += 1
            migrated_at = _parse_migrated_at(tags)
            if migrated_at is None:
                result.skipped_undated += 1
                logger.info("arch_gc_skipped_undated", key=entry.get("key"))
                continue
            if (now - migrated_at).days <= older_than_days:
                result.skipped_recent += 1
                continue
            key = str(entry.get("key", ""))
            result.eligible.append(key)
            if execute:
                await self._delete_one(key, result)
        return result

    async def _delete_one(self, key: str, result: GcResult) -> None:
        """Delete one flat entry by key, recording success/failure."""
        deleter = self._deleter_bridge()
        if deleter is None:
            result.failed += 1
            result.errors.append(f"{key}: deleter bridge unavailable")
            return
        try:
            await deleter.delete(key)
        except Exception as exc:  # record + continue; CLI exits non-zero on failures
            result.failed += 1
            result.errors.append(f"{key}: {type(exc).__name__}: {exc}")
            logger.warning("arch_gc_delete_failed", key=key, exc_info=True)
            return
        result.deleted += 1
