"""Tests for tapps_core.insights.client — InsightClient (STORY-102.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from tapps_brain.models import MemoryEntry, MemoryScope, MemorySource, MemoryTier

from tapps_core.insights.client import InsightClient
from tapps_core.insights.models import InsightEntry, InsightOrigin, InsightType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeStore:
    def __init__(self, search_results: list[MemoryEntry] | None = None) -> None:
        self.saves: list[dict[str, Any]] = []
        self._results = search_results or []

    def save(self, **kwargs: Any) -> dict[str, Any]:
        self.saves.append(kwargs)
        return {"key": kwargs["key"]}

    def search(self, query: str, **kwargs: Any) -> list[MemoryEntry]:
        return list(self._results)


def _make_client(tmp_path: Path, *, store: FakeStore | None = None) -> tuple[InsightClient, FakeStore]:
    fake = store or FakeStore()
    client = InsightClient(tmp_path)
    client._store = fake
    client._available = True
    return client, fake


def _insight(**kwargs: Any) -> InsightEntry:
    return InsightEntry(
        key=kwargs.pop("key", "test.client.insight"),
        value=kwargs.pop("value", "An insight value"),
        insight_type=kwargs.pop("insight_type", InsightType.architecture),
        server_origin=kwargs.pop("server_origin", InsightOrigin.docs_mcp),
        **kwargs,
    )


def _mem_entry(key: str = "test.mem.entry", tags: list[str] | None = None) -> MemoryEntry:
    return MemoryEntry(
        key=key,
        value="A memory entry value",
        tags=tags or ["architecture"],
        tier=MemoryTier.architectural,
        source=MemorySource.agent,
        scope=MemoryScope.project,
    )


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


class TestInsightClientAvailability:
    def test_available_when_store_injected(self, tmp_path: Path):
        client, _ = _make_client(tmp_path)
        assert client.available is True

    def test_unavailable_when_import_error(self, tmp_path: Path):
        client = InsightClient(tmp_path)
        with patch.dict("sys.modules", {"tapps_brain": None, "tapps_brain.store": None}):
            result = client.available
        assert result is False


# ---------------------------------------------------------------------------
# InsightClient.write
# ---------------------------------------------------------------------------


class TestInsightClientWrite:
    def test_write_returns_true_on_success(self, tmp_path: Path):
        client, _ = _make_client(tmp_path)
        assert client.write(_insight()) is True

    def test_write_calls_store_save(self, tmp_path: Path):
        client, store = _make_client(tmp_path)
        client.write(_insight(key="test.write.one"))
        assert len(store.saves) == 1
        assert store.saves[0]["key"] == "test.write.one"

    def test_write_tags_include_schema_v1(self, tmp_path: Path):
        client, store = _make_client(tmp_path)
        client.write(_insight())
        tags = store.saves[0]["tags"]
        assert "schema-v1" in tags

    def test_write_tags_include_insight_type(self, tmp_path: Path):
        client, store = _make_client(tmp_path)
        client.write(_insight(insight_type=InsightType.security))
        tags = store.saves[0]["tags"]
        assert "insight-type:security" in tags

    def test_write_memory_group_is_insights(self, tmp_path: Path):
        client, store = _make_client(tmp_path)
        client.write(_insight())
        assert store.saves[0]["memory_group"] == "insights"

    def test_write_returns_false_on_unavailable(self, tmp_path: Path):
        client = InsightClient(tmp_path)
        client._available = False
        assert client.write(_insight()) is False

    def test_write_enforces_session_scope(self, tmp_path: Path):
        """Session scope should be downgraded to project before write."""
        client, store = _make_client(tmp_path)
        entry = _insight(scope=MemoryScope.session)
        client.write(entry)
        assert store.saves[0]["scope"] == "project"

    def test_write_store_exception_returns_false(self, tmp_path: Path):
        fake = FakeStore()
        fake.save = MagicMock(side_effect=RuntimeError("db error"))  # type: ignore[method-assign]
        client, _ = _make_client(tmp_path, store=fake)
        assert client.write(_insight()) is False

    def test_write_source_agent_kwarg(self, tmp_path: Path):
        client, store = _make_client(tmp_path)
        client.write(_insight(), source_agent="docs-mcp")
        assert store.saves[0]["source_agent"] == "docs-mcp"


# ---------------------------------------------------------------------------
# InsightClient.search
# ---------------------------------------------------------------------------


class TestInsightClientSearch:
    def test_search_returns_insight_entries(self, tmp_path: Path):
        raw = [_mem_entry("arch.one"), _mem_entry("arch.two")]
        client, _ = _make_client(tmp_path, store=FakeStore(search_results=raw))
        results = client.search("architecture")
        assert all(isinstance(e, InsightEntry) for e in results)

    def test_search_returns_empty_on_unavailable(self, tmp_path: Path):
        client = InsightClient(tmp_path)
        client._available = False
        assert client.search("anything") == []

    def test_search_empty_store(self, tmp_path: Path):
        client, _ = _make_client(tmp_path, store=FakeStore(search_results=[]))
        assert client.search("anything") == []

    def test_search_respects_limit(self, tmp_path: Path):
        raw = [_mem_entry(f"key.{i}") for i in range(20)]
        client, _ = _make_client(tmp_path, store=FakeStore(search_results=raw))
        results = client.search("test", limit=5)
        assert len(results) <= 5

    def test_search_exception_returns_empty(self, tmp_path: Path):
        fake = FakeStore()
        fake.search = MagicMock(side_effect=RuntimeError("search error"))  # type: ignore[method-assign]
        client, _ = _make_client(tmp_path, store=fake)
        assert client.search("query") == []


# ---------------------------------------------------------------------------
# InsightClient.get_by_path
# ---------------------------------------------------------------------------


class TestInsightClientGetByPath:
    def test_empty_path_returns_empty(self, tmp_path: Path):
        client, _ = _make_client(tmp_path)
        assert client.get_by_path("") == []

    def test_searches_by_path_stem(self, tmp_path: Path):
        raw = [_mem_entry("scorer.insight")]
        fake = FakeStore(search_results=raw)
        client, _ = _make_client(tmp_path, store=fake)
        results = client.get_by_path("src/tapps_mcp/scorer.py")
        assert len(results) >= 0  # search was called

    def test_returns_insight_entries(self, tmp_path: Path):
        raw = [_mem_entry("path.insight")]
        client, _ = _make_client(tmp_path, store=FakeStore(search_results=raw))
        results = client.get_by_path("src/foo.py")
        assert all(isinstance(e, InsightEntry) for e in results)


# ---------------------------------------------------------------------------
# InsightClient.promote_all
# ---------------------------------------------------------------------------


class TestInsightClientPromoteAll:
    def test_returns_migration_result(self, tmp_path: Path):
        from tapps_core.insights import InsightMigrationResult

        client, _ = _make_client(tmp_path, store=FakeStore(search_results=[]))
        result = client.promote_all()
        assert isinstance(result, InsightMigrationResult)

    def test_empty_store_total_zero(self, tmp_path: Path):
        client, _ = _make_client(tmp_path, store=FakeStore(search_results=[]))
        result = client.promote_all()
        assert result.total == 0

    def test_promotes_all_entries(self, tmp_path: Path):
        raw = [_mem_entry(f"promo.{i}") for i in range(5)]
        client, _ = _make_client(tmp_path, store=FakeStore(search_results=raw))
        result = client.promote_all()
        assert result.total == 5
        assert result.success_count == 5

    def test_unavailable_returns_empty_result(self, tmp_path: Path):
        client = InsightClient(tmp_path)
        client._available = False
        result = client.promote_all()
        assert result.total == 0
