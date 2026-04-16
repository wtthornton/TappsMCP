"""Integration tests for Epic 25 memory retrieval and integration.

Tests the full lifecycle: seed -> use -> retrieve -> inject -> export/import.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from tapps_mcp.memory.injection import inject_memories
from tapps_mcp.memory.io import export_memories, import_memories
from tapps_mcp.memory.models import (
    MemoryEntry,
    MemoryScope,
    MemorySnapshot,
    MemorySource,
    MemoryTier,
)
from tapps_mcp.memory.retrieval import MemoryRetriever, ScoredMemory
from tapps_mcp.memory.seeding import seed_from_profile
from tapps_mcp.project.models import ProjectProfile, TechStack

_RECENT = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    key: str,
    value: str,
    *,
    tier: MemoryTier = MemoryTier.pattern,
    confidence: float = 0.8,
    tags: list[str] | None = None,
) -> MemoryEntry:
    return MemoryEntry(
        key=key,
        value=value,
        tier=tier,
        confidence=confidence,
        source=MemorySource.agent,
        source_agent="test",
        scope=MemoryScope.project,
        tags=tags or [],
        updated_at=_RECENT,
        created_at=_RECENT,
        last_accessed=_RECENT,
        access_count=3,
    )


def _make_mock_store(entries: list[MemoryEntry] | None = None) -> MagicMock:
    """Create a full mock MemoryStore."""
    store = MagicMock()
    entries = entries or []
    store.project_root = Path("/test/project")
    store.count.return_value = len(entries)
    store.list_all.return_value = entries
    store.search.return_value = entries

    entry_map = {e.key: e for e in entries}
    store.get.side_effect = lambda k, **kw: entry_map.get(k)

    # v2.0.4: MemoryRetriever validates scoring weights from store.profile
    store.profile = None

    store.snapshot.return_value = MemorySnapshot(
        project_root="/test/project",
        entries=entries,
        total_count=len(entries),
    )
    return store


def _make_profile() -> ProjectProfile:
    return ProjectProfile(
        tech_stack=TechStack(
            languages=["python", "typescript"],
            frameworks=["fastapi"],
        ),
        project_type="api-service",
        project_type_confidence=0.85,
        has_docker=True,
        test_frameworks=["pytest"],
        package_managers=["uv"],
        ci_systems=["github-actions"],
    )


def _make_validator(tmp_path: Path) -> MagicMock:
    validator = MagicMock()
    validator.validate_path.side_effect = lambda p, **kw: Path(p).resolve()
    return validator


# ---------------------------------------------------------------------------
# Lifecycle: seed -> search -> inject
# ---------------------------------------------------------------------------


class TestSeedSearchInjectLifecycle:
    """Test the full seed -> search -> inject pipeline."""

    def test_seed_then_search_finds_seeded_entries(self) -> None:
        """Seeded entries should be findable via retrieval."""
        store = _make_mock_store()
        profile = _make_profile()

        # Seed
        seed_result = seed_from_profile(store, profile)
        assert seed_result["seeded_count"] > 0

        # The store was called with save() for each seeded entry
        seeded_keys = [c.kwargs["key"] for c in store.save.call_args_list]
        assert "language-python" in seeded_keys
        assert "framework-fastapi" in seeded_keys

    def test_seeded_entries_are_searchable(self) -> None:
        """Mock seeded entries and verify search finds them."""
        entries = [
            _make_entry("language-python", "Project uses python", tags=["auto-seeded"]),
            _make_entry(
                "framework-fastapi", "Project uses fastapi framework", tags=["auto-seeded"]
            ),
        ]
        store = _make_mock_store(entries)
        retriever = MemoryRetriever()

        results = retriever.search("python", store)
        assert len(results) >= 1
        keys = [r.entry.key for r in results]
        assert "language-python" in keys

    def test_inject_uses_seeded_entries(self) -> None:
        """Memory injection should find and include seeded entries."""
        entries = [
            _make_entry("framework-fastapi", "Project uses fastapi framework"),
        ]
        store = _make_mock_store(entries)

        result = inject_memories("fastapi framework", store, "high")
        assert result["memory_injected"] >= 1
        assert "fastapi" in result["memory_section"]


# ---------------------------------------------------------------------------
# Export -> Import round-trip
# ---------------------------------------------------------------------------


class TestExportImportRoundTrip:
    def test_export_import_round_trip(self, tmp_path: Path) -> None:
        """Exported memories can be re-imported into a fresh store."""
        entries = [
            _make_entry("key-1", "value one"),
            _make_entry("key-2", "value two"),
        ]

        # Export
        export_store = _make_mock_store(entries)
        validator = _make_validator(tmp_path)
        export_path = tmp_path / "memories.json"

        export_result = export_memories(export_store, export_path, validator)
        assert export_result["exported_count"] == 2
        assert export_path.exists()

        # Import into fresh store
        import_store = _make_mock_store([])
        import_result = import_memories(import_store, export_path, validator)

        assert import_result["imported_count"] == 2
        assert import_result["skipped_count"] == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_search_with_no_results(self) -> None:
        store = _make_mock_store([])
        store.search.return_value = []
        retriever = MemoryRetriever()

        results = retriever.search("nonexistent", store)
        assert results == []

    def test_inject_with_empty_store(self) -> None:
        store = _make_mock_store([])
        result = inject_memories("any query", store, "high")
        assert result["memory_injected"] == 0
        assert result["memory_section"] == ""

    def test_seeding_minimal_profile(self) -> None:
        """Seeding with only language detected should still work."""
        store = _make_mock_store()
        profile = ProjectProfile(
            tech_stack=TechStack(languages=["python"]),
        )
        result = seed_from_profile(store, profile)
        assert result["seeded_count"] >= 1

    def test_retriever_stale_flag(self) -> None:
        """Very old entries should be flagged as stale."""
        old_time = (datetime.now(tz=UTC) - timedelta(days=200)).isoformat()
        entries = [
            _make_entry("old-key", "old value"),
        ]
        # Manually set the updated_at to be very old
        entries[0] = entries[0].model_copy(update={"updated_at": old_time})
        store = _make_mock_store(entries)

        retriever = MemoryRetriever()
        results = retriever.search("old value", store)

        if results:
            # Pattern tier has 60-day half-life, 200 days is very stale
            assert results[0].stale is True

    def test_scored_memory_serialization(self) -> None:
        """ScoredMemory should be serializable."""
        entry = _make_entry("test-key", "test value")
        scored = ScoredMemory(
            entry=entry,
            score=0.75,
            effective_confidence=0.8,
            bm25_relevance=0.5,
            stale=False,
        )
        data = scored.model_dump()
        assert data["score"] == 0.75
        assert data["entry"]["key"] == "test-key"
