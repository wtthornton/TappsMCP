"""Tests for memory profile seeding (Epic 25, Story 25.3)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from tapps_mcp.memory.models import (
    MemoryEntry,
    MemoryScope,
    MemorySource,
    MemoryTier,
)
from tapps_mcp.memory.seeding import (
    _SEEDED_FROM,
    _SEEDED_TAG,
    _SOURCE_AGENT,
    reseed_from_profile,
    seed_from_profile,
)
from tapps_mcp.project.models import ProjectProfile, TechStack


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_profile(**overrides: object) -> ProjectProfile:
    defaults = {
        "tech_stack": TechStack(
            languages=["python"],
            frameworks=["fastapi"],
            libraries=["pydantic"],
        ),
        "project_type": "api-service",
        "project_type_confidence": 0.85,
        "has_docker": True,
        "has_ci": True,
        "ci_systems": ["github-actions"],
        "test_frameworks": ["pytest"],
        "package_managers": ["uv"],
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    return ProjectProfile(**defaults)  # type: ignore[arg-type]


def _make_store(count: int = 0, entries: list[MemoryEntry] | None = None) -> MagicMock:
    store = MagicMock()
    store.project_root = Path("/test/project")
    store.count.return_value = count
    store.list_all.return_value = entries or []
    store.get.return_value = None
    return store


# ---------------------------------------------------------------------------
# seed_from_profile tests
# ---------------------------------------------------------------------------


class TestSeedFromProfile:
    def test_empty_store_gets_seeded(self) -> None:
        store = _make_store(count=0)
        profile = _make_profile()

        result = seed_from_profile(store, profile)

        assert result["seeded_count"] > 0
        assert result["skipped"] is False
        assert store.save.call_count > 0

    def test_nonempty_store_is_not_seeded(self) -> None:
        store = _make_store(count=5)
        profile = _make_profile()

        result = seed_from_profile(store, profile)

        assert result["seeded_count"] == 0
        assert result["skipped"] is True
        store.save.assert_not_called()

    def test_seeded_memories_have_correct_source(self) -> None:
        store = _make_store(count=0)
        profile = _make_profile()

        seed_from_profile(store, profile)

        for c in store.save.call_args_list:
            kwargs = c.kwargs
            assert kwargs["source"] == MemorySource.system.value
            assert kwargs["source_agent"] == _SOURCE_AGENT

    def test_seeded_memories_have_auto_seeded_tag(self) -> None:
        store = _make_store(count=0)
        profile = _make_profile()

        seed_from_profile(store, profile)

        for c in store.save.call_args_list:
            kwargs = c.kwargs
            assert _SEEDED_TAG in kwargs["tags"]

    def test_seeded_from_field_set(self) -> None:
        store = _make_store(count=0)
        profile = _make_profile()

        seed_from_profile(store, profile)

        # update_fields should be called for each seeded entry
        assert store.update_fields.call_count > 0
        for c in store.update_fields.call_args_list:
            assert c.kwargs.get("seeded_from") == _SEEDED_FROM

    def test_project_type_seeded(self) -> None:
        store = _make_store(count=0)
        profile = _make_profile(project_type="cli-tool")

        seed_from_profile(store, profile)

        keys = [c.kwargs["key"] for c in store.save.call_args_list]
        assert "project-type" in keys

    def test_languages_seeded(self) -> None:
        store = _make_store(count=0)
        profile = _make_profile(
            tech_stack=TechStack(languages=["python", "typescript"])
        )

        seed_from_profile(store, profile)

        keys = [c.kwargs["key"] for c in store.save.call_args_list]
        assert "language-python" in keys
        assert "language-typescript" in keys

    def test_docker_seeded_when_present(self) -> None:
        store = _make_store(count=0)
        profile = _make_profile(has_docker=True)

        seed_from_profile(store, profile)

        keys = [c.kwargs["key"] for c in store.save.call_args_list]
        assert "has-docker" in keys

    def test_docker_not_seeded_when_absent(self) -> None:
        store = _make_store(count=0)
        profile = _make_profile(has_docker=False)

        seed_from_profile(store, profile)

        keys = [c.kwargs["key"] for c in store.save.call_args_list]
        assert "has-docker" not in keys

    def test_confidence_from_profile(self) -> None:
        store = _make_store(count=0)
        profile = _make_profile(project_type="api-service", project_type_confidence=0.95)

        seed_from_profile(store, profile)

        # Find the project-type save call
        for c in store.save.call_args_list:
            if c.kwargs["key"] == "project-type":
                assert c.kwargs["confidence"] >= 0.9
                break


# ---------------------------------------------------------------------------
# reseed_from_profile tests
# ---------------------------------------------------------------------------


class TestReseedFromProfile:
    def test_reseed_deletes_old_auto_seeded(self) -> None:
        old_entry = MemoryEntry(
            key="language-python",
            value="Project uses python",
            tier=MemoryTier.architectural,
            source=MemorySource.system,
            source_agent=_SOURCE_AGENT,
            scope=MemoryScope.project,
            tags=[_SEEDED_TAG, "language"],
        )
        store = _make_store(count=1, entries=[old_entry])

        profile = _make_profile()
        result = reseed_from_profile(store, profile)

        assert result["deleted_old"] == 1
        store.delete.assert_called_with("language-python")

    def test_reseed_does_not_touch_non_seeded(self) -> None:
        human_entry = MemoryEntry(
            key="custom-decision",
            value="We chose REST over GraphQL",
            tier=MemoryTier.architectural,
            source=MemorySource.human,
            source_agent="developer",
            scope=MemoryScope.project,
            tags=["architecture"],
        )
        store = _make_store(count=1, entries=[human_entry])

        profile = _make_profile()
        result = reseed_from_profile(store, profile)

        # Should not delete non-seeded memory
        store.delete.assert_not_called()
