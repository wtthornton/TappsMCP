"""InsightClient — cross-server client library for reading/writing InsightEntry records.

Both tapps-mcp and docs-mcp import this module to interact with tapps-brain
in a typed, insight-aware way. The client wraps :class:`tapps_brain.store.MemoryStore`
and handles:

- Writing ``InsightEntry`` records with proper tagging/grouping
- Searching the ``insights`` memory_group and promoting results to ``InsightEntry``
- Path-scoped search for per-file insight lookup
- Bulk promotion of existing ``MemoryEntry`` records to ``InsightEntry``

tapps-brain availability
------------------------
All methods return safe defaults when tapps-brain is not installed.
Callers should check :attr:`InsightClient.available` before trusting results.

Quick start::

    from tapps_core.insights.client import InsightClient
    from tapps_core.insights import InsightEntry, InsightType, InsightOrigin
    from pathlib import Path

    client = InsightClient(Path.cwd())
    if client.available:
        client.write(
            InsightEntry(
                key="arch.myproject.structure",
                value="3 packages, 12 modules",
                insight_type=InsightType.architecture,
                server_origin=InsightOrigin.docs_mcp,
            )
        )
        results = client.search("memory shim pattern")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from tapps_core.insights.migration import (
    InsightMigrationResult,
    bulk_migrate,
)
from tapps_core.insights.models import (
    InsightEntry,
    InsightOrigin,
    InsightType,
)
from tapps_core.insights.scope import ScopeViolation, enforce_scope

logger = structlog.get_logger(__name__)

_INSIGHT_MEMORY_GROUP = "insights"
_DEFAULT_SEARCH_LIMIT = 10
_INSIGHT_BASE_TAGS = ["architecture", "docs-mcp", "insight-type:architecture", "schema-v1"]


class InsightClient:
    """Typed interface to tapps-brain scoped to the ``insights`` memory_group.

    Args:
        project_root: Project root used to locate the ``.tapps-brain`` store.
        allow_shared_scope: When ``True``, ``InsightEntry`` records with
            ``scope=shared`` are written as-is. When ``False`` (default),
            scope is downgraded to ``project`` to prevent accidental leakage.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        allow_shared_scope: bool = False,
    ) -> None:
        self._root = project_root
        self._allow_shared = allow_shared_scope
        self._store: Any = None  # tapps_brain.store.MemoryStore | None
        self._available: bool | None = None  # lazy init sentinel

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return True when tapps-brain is installed and store opens cleanly."""
        if self._available is None:
            self._get_store()  # triggers lazy init
        return self._available or False

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, entry: InsightEntry, *, source_agent: str = "tapps-core") -> bool:
        """Write a single ``InsightEntry`` to the store.

        The entry's scope is enforced before writing (see :func:`enforce_scope`).
        Returns ``True`` on success, ``False`` on failure or unavailability.

        Args:
            entry: The insight to persist.
            source_agent: Agent identifier for provenance (default: 'tapps-core').
        """
        store = self._get_store()
        if store is None:
            return False
        try:
            guarded = enforce_scope(entry, allow_shared=self._allow_shared)
        except ScopeViolation as exc:
            logger.warning("insight_scope_violation", key=entry.key, reason=str(exc))
            return False

        tags = list(entry.tags)
        if "docs-mcp" not in tags:
            tags.append(str(entry.server_origin))
        if "schema-v1" not in tags:
            tags.append("schema-v1")
        if f"insight-type:{entry.insight_type}" not in tags:
            tags.append(f"insight-type:{entry.insight_type}")

        try:
            store.save(
                key=guarded.key,
                value=guarded.value,
                tier=str(guarded.tier),
                source=str(guarded.source),
                source_agent=source_agent,
                scope=str(guarded.scope),
                tags=tags[:10],  # tapps-brain limit
                memory_group=_INSIGHT_MEMORY_GROUP,
                skip_consolidation=True,
            )
            logger.debug("insight_written", key=guarded.key, type=str(guarded.insight_type))
            return True
        except Exception:
            logger.warning("insight_write_failed", key=entry.key, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        insight_type: InsightType | None = None,
        limit: int = _DEFAULT_SEARCH_LIMIT,
    ) -> list[InsightEntry]:
        """Search the insights memory_group and return promoted InsightEntry records.

        Args:
            query: BM25 search query.
            insight_type: Optional filter — only return entries of this type
                (matched via tag ``insight-type:{type}``).
            limit: Maximum number of results to return.

        Returns:
            List of :class:`InsightEntry` records, newest-first.
            Empty list on failure or unavailability.
        """
        store = self._get_store()
        if store is None:
            return []
        try:
            tags: list[str] | None = None
            if insight_type is not None:
                tags = [f"insight-type:{insight_type}"]
            raw = store.search(
                query,
                tags=tags,
                memory_group=_INSIGHT_MEMORY_GROUP,
            )
            entries = raw[:limit]
            result = bulk_migrate(entries)
            return result.succeeded
        except Exception:
            logger.warning("insight_search_failed", query=query, exc_info=True)
            return []

    def get_by_path(
        self, subject_path: str, *, limit: int = _DEFAULT_SEARCH_LIMIT
    ) -> list[InsightEntry]:
        """Return insights about a specific file or module path.

        Searches using the path as the query, restricted to the ``insights``
        group and filtered by path stem presence in the value.

        Args:
            subject_path: Relative file or module path to look up.
            limit: Maximum results to return.
        """
        if not subject_path:
            return []
        stem = Path(subject_path).stem
        return self.search(stem, limit=limit)

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    def promote_all(
        self,
        *,
        server_origin: InsightOrigin = InsightOrigin.unknown,
    ) -> InsightMigrationResult:
        """Promote all entries in the ``insights`` group to ``InsightEntry``.

        Reads the entire ``insights`` memory_group and runs
        :func:`tapps_core.insights.migration.bulk_migrate` on all entries.
        Does not re-write them — useful for in-memory classification.

        Args:
            server_origin: Applied to entries without an existing origin.
        """
        store = self._get_store()
        if store is None:
            return InsightMigrationResult(total=0)
        try:
            all_entries = store.search("", memory_group=_INSIGHT_MEMORY_GROUP)
            return bulk_migrate(all_entries, server_origin=server_origin)
        except Exception:
            logger.warning("promote_all_failed", exc_info=True)
            return InsightMigrationResult(total=0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_store(self) -> Any:
        """Lazily open and cache the MemoryStore; return None on failure."""
        if self._store is not None:
            return self._store
        if self._available is False:
            return None
        try:
            from tapps_brain.store import MemoryStore

            self._store = MemoryStore(self._root)
            self._available = True
            return self._store
        except ImportError:
            logger.debug("tapps_brain_unavailable", root=str(self._root))
            self._available = False
            return None
        except Exception:
            logger.warning("insight_store_open_failed", root=str(self._root), exc_info=True)
            self._available = False
            return None
