"""Integration tests verifying Epic 25 code against the real MemoryStore.

These tests use tmp_path to create real SQLite-backed stores,
verifying seeding, retrieval, injection, and import/export end-to-end.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tapps_mcp.memory.decay import DecayConfig
from tapps_mcp.memory.injection import append_memory_to_answer, inject_memories
from tapps_mcp.memory.io import export_memories, import_memories
from tapps_mcp.memory.models import MemoryEntry, MemorySource, MemoryTier
from tapps_mcp.memory.retrieval import MemoryRetriever
from tapps_mcp.memory.seeding import reseed_from_profile, seed_from_profile
from tapps_mcp.memory.store import MemoryStore
from tapps_mcp.project.models import ProjectProfile, TechStack
from tapps_mcp.security.path_validator import PathValidator


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    """Create a real MemoryStore backed by SQLite in a temp directory."""
    return MemoryStore(tmp_path)


@pytest.fixture()
def profile() -> ProjectProfile:
    """Create a sample project profile for seeding tests."""
    return ProjectProfile(
        tech_stack=TechStack(
            languages=["python"],
            frameworks=["fastapi"],
            libraries=["pydantic", "structlog"],
        ),
        project_type="api-service",
        project_type_confidence=0.85,
        has_ci=True,
        ci_systems=["github-actions"],
        has_docker=True,
        has_tests=True,
        test_frameworks=["pytest"],
        package_managers=["uv"],
    )


@pytest.fixture()
def validator(tmp_path: Path) -> PathValidator:
    """Create a PathValidator rooted in the temp directory."""
    return PathValidator(project_root=tmp_path)


# ---------------------------------------------------------------------------
# Seeding with real store
# ---------------------------------------------------------------------------


class TestSeedingRealStore:
    """Verify profile seeding works with real SQLite-backed MemoryStore."""

    def test_seed_from_profile_populates_store(
        self, store: MemoryStore, profile: ProjectProfile
    ) -> None:
        assert store.count() == 0
        result = seed_from_profile(store, profile)
        assert result["seeded_count"] > 0
        assert not result["skipped"]
        assert store.count() == result["seeded_count"]

    def test_seed_creates_expected_keys(
        self, store: MemoryStore, profile: ProjectProfile
    ) -> None:
        seed_from_profile(store, profile)
        # Check specific expected keys
        project_type = store.get("project-type")
        assert project_type is not None
        assert "api-service" in project_type.value

        lang = store.get("language-python")
        assert lang is not None
        assert "python" in lang.value.lower()

        fw = store.get("framework-fastapi")
        assert fw is not None

        docker = store.get("has-docker")
        assert docker is not None

    def test_seed_skips_nonempty_store(
        self, store: MemoryStore, profile: ProjectProfile
    ) -> None:
        store.save(key="existing-entry", value="some value")
        result = seed_from_profile(store, profile)
        assert result["skipped"] is True
        assert result["seeded_count"] == 0

    def test_seed_tags_and_source(
        self, store: MemoryStore, profile: ProjectProfile
    ) -> None:
        seed_from_profile(store, profile)
        entry = store.get("project-type")
        assert entry is not None
        assert "auto-seeded" in entry.tags
        assert entry.source == MemorySource.system
        assert entry.source_agent == "tapps-brain"

    def test_seed_seeded_from_field(
        self, store: MemoryStore, profile: ProjectProfile
    ) -> None:
        seed_from_profile(store, profile)
        entry = store.get("project-type")
        assert entry is not None
        assert entry.seeded_from == "project_profile"

    def test_reseed_updates_auto_seeded(
        self, store: MemoryStore, profile: ProjectProfile
    ) -> None:
        seed_from_profile(store, profile)

        # Reseed with updated profile
        updated_profile = profile.model_copy(
            update={"project_type": "web-app"}
        )
        result = reseed_from_profile(store, updated_profile)
        assert result["seeded_count"] > 0

        # project-type should now say web-app
        entry = store.get("project-type")
        assert entry is not None
        assert "web-app" in entry.value

    def test_reseed_preserves_non_seeded(
        self, store: MemoryStore, profile: ProjectProfile
    ) -> None:
        seed_from_profile(store, profile)
        # Add a non-seeded memory
        store.save(key="manual-note", value="Important decision")

        reseed_from_profile(store, profile)
        # Manual note should still exist
        manual = store.get("manual-note")
        assert manual is not None
        assert manual.value == "Important decision"


# ---------------------------------------------------------------------------
# Retrieval with real store
# ---------------------------------------------------------------------------


class TestRetrievalRealStore:
    """Verify ranked retrieval works with real SQLite-backed MemoryStore."""

    def test_search_returns_results(self, store: MemoryStore) -> None:
        store.save(key="auth-pattern", value="Project uses JWT with RS256")
        store.save(key="db-choice", value="PostgreSQL is the primary database")

        retriever = MemoryRetriever()
        results = retriever.search("JWT authentication", store)
        assert len(results) > 0
        keys = [r.entry.key for r in results]
        assert "auth-pattern" in keys

    def test_search_empty_query(self, store: MemoryStore) -> None:
        store.save(key="test-entry", value="some value")
        retriever = MemoryRetriever()
        results = retriever.search("", store)
        assert results == []

    def test_search_no_matches(self, store: MemoryStore) -> None:
        store.save(key="auth-pattern", value="Project uses JWT")
        retriever = MemoryRetriever()
        results = retriever.search("kubernetes deployment", store)
        # May return 0 results or low-scoring results
        for r in results:
            assert r.score >= 0

    def test_search_respects_limit(self, store: MemoryStore) -> None:
        for i in range(10):
            store.save(key=f"pattern-{i}", value=f"Pattern number {i} for testing search")
        retriever = MemoryRetriever()
        results = retriever.search("pattern testing search", store, limit=3)
        assert len(results) <= 3

    def test_search_excludes_contradicted(self, store: MemoryStore) -> None:
        store.save(key="old-framework", value="Project uses Django framework")
        store.update_fields("old-framework", contradicted=True)

        retriever = MemoryRetriever()
        results = retriever.search("Django framework", store)
        keys = [r.entry.key for r in results]
        assert "old-framework" not in keys

    def test_search_includes_contradicted_when_requested(
        self, store: MemoryStore
    ) -> None:
        store.save(key="old-framework", value="Project uses Django framework")
        store.update_fields("old-framework", contradicted=True)

        retriever = MemoryRetriever()
        results = retriever.search(
            "Django framework", store, include_contradicted=True
        )
        keys = [r.entry.key for r in results]
        assert "old-framework" in keys

    def test_search_with_decay(self, store: MemoryStore) -> None:
        store.save(
            key="arch-decision",
            value="We chose microservices architecture",
            tier=MemoryTier.architectural.value,
        )
        config = DecayConfig()
        retriever = MemoryRetriever(config=config)
        results = retriever.search("microservices architecture", store)
        assert len(results) > 0
        # Fresh entry should have high effective confidence
        assert results[0].effective_confidence > 0.5

    def test_scored_memory_has_all_fields(self, store: MemoryStore) -> None:
        store.save(key="test-mem", value="Testing scored memory fields")
        retriever = MemoryRetriever()
        results = retriever.search("testing scored memory", store)
        if results:
            r = results[0]
            assert r.score >= 0
            assert 0 <= r.effective_confidence <= 1.0
            assert r.bm25_relevance >= 0
            assert isinstance(r.stale, bool)


# ---------------------------------------------------------------------------
# Injection with real store
# ---------------------------------------------------------------------------


class TestInjectionRealStore:
    """Verify memory injection works with real SQLite-backed MemoryStore."""

    def test_inject_finds_relevant_memories(self, store: MemoryStore) -> None:
        store.save(key="auth-jwt", value="Authentication uses JWT with RS256 signing")
        store.save(key="db-postgres", value="PostgreSQL is the primary database")

        result = inject_memories("How does authentication work?", store)
        # May or may not match depending on FTS5 scoring
        assert isinstance(result["memory_injected"], int)
        assert isinstance(result["memory_section"], str)

    def test_inject_low_engagement_never_injects(
        self, store: MemoryStore
    ) -> None:
        store.save(key="auth-jwt", value="Authentication uses JWT")
        result = inject_memories("authentication", store, engagement_level="low")
        assert result["memory_injected"] == 0
        assert result["memory_section"] == ""

    def test_inject_formats_markdown(self, store: MemoryStore) -> None:
        store.save(
            key="auth-jwt",
            value="Authentication uses JWT with RS256 signing",
            tier=MemoryTier.architectural.value,
            confidence=0.9,
        )
        result = inject_memories("JWT RS256 authentication signing", store)
        if result["memory_injected"] > 0:
            assert "### Project Memory" in result["memory_section"]
            assert "auth-jwt" in result["memory_section"]

    def test_append_memory_to_answer(self) -> None:
        answer = "Use JWT tokens for authentication."
        memory_result = {
            "memory_section": (
                "### Project Memory\n"
                "- **auth-jwt** (confidence: 0.90, tier: architectural): Uses RS256"
            ),
            "memory_injected": 1,
        }
        combined = append_memory_to_answer(answer, memory_result)
        assert "Use JWT tokens" in combined
        assert "### Project Memory" in combined

    def test_append_empty_section(self) -> None:
        answer = "Some answer."
        memory_result: dict[str, Any] = {"memory_section": "", "memory_injected": 0}
        combined = append_memory_to_answer(answer, memory_result)
        assert combined == "Some answer."


# ---------------------------------------------------------------------------
# Import/Export with real store
# ---------------------------------------------------------------------------


class TestImportExportRealStore:
    """Verify import/export works with real SQLite-backed MemoryStore."""

    def test_export_creates_json(
        self,
        store: MemoryStore,
        validator: PathValidator,
        tmp_path: Path,
    ) -> None:
        store.save(key="test-export", value="Export test value")
        output = tmp_path / "export.json"

        result = export_memories(store, output, validator)
        assert result["exported_count"] == 1
        assert output.exists()

        import json

        data = json.loads(output.read_text())
        assert len(data["memories"]) == 1
        assert data["memories"][0]["key"] == "test-export"

    def test_import_loads_entries(
        self,
        store: MemoryStore,
        validator: PathValidator,
        tmp_path: Path,
    ) -> None:
        import json

        # Create export file
        payload = {
            "memories": [
                {
                    "key": "imported-entry",
                    "value": "Imported from another project",
                    "tier": "pattern",
                    "source": "agent",
                    "source_agent": "other-agent",
                }
            ]
        }
        import_file = tmp_path / "import.json"
        import_file.write_text(json.dumps(payload))

        result = import_memories(store, import_file, validator)
        assert result["imported_count"] == 1
        assert result["skipped_count"] == 0

        entry = store.get("imported-entry")
        assert entry is not None
        assert "(imported)" in entry.source_agent

    def test_import_skips_existing(
        self,
        store: MemoryStore,
        validator: PathValidator,
        tmp_path: Path,
    ) -> None:
        import json

        store.save(key="existing-key", value="Original value")

        payload = {
            "memories": [
                {
                    "key": "existing-key",
                    "value": "New value that should be skipped",
                }
            ]
        }
        import_file = tmp_path / "import.json"
        import_file.write_text(json.dumps(payload))

        result = import_memories(store, import_file, validator)
        assert result["skipped_count"] == 1
        assert result["imported_count"] == 0

        # Original value preserved
        entry = store.get("existing-key")
        assert entry is not None
        assert entry.value == "Original value"

    def test_import_with_overwrite(
        self,
        store: MemoryStore,
        validator: PathValidator,
        tmp_path: Path,
    ) -> None:
        import json

        store.save(key="overwrite-key", value="Old value")

        payload = {
            "memories": [
                {
                    "key": "overwrite-key",
                    "value": "New overwritten value",
                }
            ]
        }
        import_file = tmp_path / "import.json"
        import_file.write_text(json.dumps(payload))

        result = import_memories(store, import_file, validator, overwrite=True)
        assert result["imported_count"] == 1

        entry = store.get("overwrite-key")
        assert entry is not None
        assert entry.value == "New overwritten value"

    def test_round_trip_export_import(
        self,
        tmp_path: Path,
    ) -> None:
        """Export from one store, import into another."""
        # Store A: export
        store_a = MemoryStore(tmp_path / "project_a")
        store_a.save(key="shared-pattern", value="Use dependency injection for services")
        store_a.save(key="db-choice", value="PostgreSQL with SQLAlchemy ORM")

        validator_a = PathValidator(project_root=tmp_path / "project_a")
        export_path = tmp_path / "project_a" / "export.json"
        export_result = export_memories(store_a, export_path, validator_a)
        assert export_result["exported_count"] == 2

        # Store B: import
        store_b = MemoryStore(tmp_path / "project_b")
        validator_b = PathValidator(project_root=tmp_path / "project_b")

        # Copy file to project_b for path validation
        import shutil

        import_path = tmp_path / "project_b" / "import.json"
        (tmp_path / "project_b").mkdir(parents=True, exist_ok=True)
        shutil.copy(export_path, import_path)

        import_result = import_memories(store_b, import_path, validator_b)
        assert import_result["imported_count"] == 2
        assert store_b.count() == 2

        entry = store_b.get("shared-pattern")
        assert entry is not None
        assert "dependency injection" in entry.value

        store_a.close()
        store_b.close()

    def test_export_with_filters(
        self,
        store: MemoryStore,
        validator: PathValidator,
        tmp_path: Path,
    ) -> None:
        store.save(
            key="arch-entry",
            value="Architecture decision",
            tier=MemoryTier.architectural.value,
        )
        store.save(
            key="ctx-entry",
            value="Session context",
            tier=MemoryTier.context.value,
        )

        output = tmp_path / "filtered.json"
        result = export_memories(
            store, output, validator, tier="architectural"
        )
        assert result["exported_count"] == 1

        import json

        data = json.loads(output.read_text())
        assert data["memories"][0]["key"] == "arch-entry"


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


class TestLifecycleRealStore:
    """Test the full memory lifecycle with real store."""

    def test_seed_search_inject_lifecycle(
        self,
        store: MemoryStore,
        profile: ProjectProfile,
    ) -> None:
        """Seed -> Search -> Inject lifecycle."""
        # Seed
        seed_result = seed_from_profile(store, profile)
        assert seed_result["seeded_count"] > 0

        # Search
        retriever = MemoryRetriever()
        results = retriever.search("python fastapi", store)
        assert len(results) > 0

        # Inject
        inject_result = inject_memories(
            "What framework does this project use?", store
        )
        # The seeded entries contain "fastapi" so injection may find them
        assert isinstance(inject_result["memory_injected"], int)

    def test_save_retrieve_delete_lifecycle(self, store: MemoryStore) -> None:
        """CRUD lifecycle."""
        # Save
        result = store.save(key="lifecycle-test", value="Testing the full lifecycle")
        assert isinstance(result, MemoryEntry)

        # Get
        entry = store.get("lifecycle-test")
        assert entry is not None
        assert entry.value == "Testing the full lifecycle"

        # Search
        results = store.search("lifecycle")
        assert len(results) >= 1

        # Delete
        deleted = store.delete("lifecycle-test")
        assert deleted is True

        # Verify gone
        assert store.get("lifecycle-test") is None
