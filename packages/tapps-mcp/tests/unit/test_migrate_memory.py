"""TAP-415: tests for SQLite → tapps-brain memory migration."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tapps_mcp.pipeline.migrate_memory import (
    _SCOPE_MAP,
    MIGRATION_MARKER_KEY_PREFIX,
    MIGRATION_RUN_TAG_PREFIX,
    _tag_entry_with_run,
    discover_sqlite_dbs,
    read_sqlite_entries,
    rollback_migration,
    run_migration,
    sqlite_present,
)


def _make_fake_sqlite(path: Path, rows: list[dict[str, Any]]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE memories ("
            "key TEXT PRIMARY KEY, value TEXT, tier TEXT, scope TEXT, "
            "source TEXT, source_agent TEXT, confidence REAL, tags TEXT, "
            "branch TEXT)"
        )
        for row in rows:
            conn.execute(
                "INSERT INTO memories VALUES (:key, :value, :tier, :scope, "
                ":source, :source_agent, :confidence, :tags, :branch)",
                row,
            )
        conn.commit()
    finally:
        conn.close()


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "key": "test.key",
        "value": "test value",
        "tier": "pattern",
        "scope": "private",
        "source": "agent",
        "source_agent": "tapps-mcp",
        "confidence": 0.7,
        "tags": "[]",
        "branch": None,
    }
    base.update(overrides)
    return base


class TestDiscovery:
    def test_discover_returns_empty_when_no_memory_dir(self, tmp_path: Path) -> None:
        assert discover_sqlite_dbs(tmp_path) == []

    def test_discover_finds_db_files(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / ".tapps-mcp" / "memory"
        mem_dir.mkdir(parents=True)
        (mem_dir / "memory.db").write_bytes(b"SQLite format 3")
        (mem_dir / "extra.db").write_bytes(b"SQLite format 3")
        (mem_dir / "readme.txt").write_text("not a db")
        found = discover_sqlite_dbs(tmp_path)
        assert len(found) == 2
        assert all(p.suffix == ".db" for p in found)

    def test_sqlite_present_reflects_discovery(self, tmp_path: Path) -> None:
        assert sqlite_present(tmp_path) is False
        mem_dir = tmp_path / ".tapps-mcp" / "memory"
        mem_dir.mkdir(parents=True)
        (mem_dir / "memory.db").write_bytes(b"SQLite format 3")
        assert sqlite_present(tmp_path) is True


class TestRowMapping:
    def test_scope_map_covers_v2_values(self) -> None:
        assert _SCOPE_MAP["private"] == "project"
        assert _SCOPE_MAP["group"] == "project"
        assert _SCOPE_MAP["hive"] == "shared"

    def test_row_to_entry_parses_json_tags(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        _make_fake_sqlite(db, [_row(tags=json.dumps(["a", "b"]))])
        entries = read_sqlite_entries(db)
        assert len(entries) == 1
        assert entries[0].tags == ["a", "b"]

    def test_row_to_entry_falls_back_on_bad_tags(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        _make_fake_sqlite(db, [_row(tags="not-json")])
        entries = read_sqlite_entries(db)
        assert entries[0].tags == []

    def test_row_to_entry_remaps_private_scope(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        _make_fake_sqlite(db, [_row(scope="private")])
        assert read_sqlite_entries(db)[0].scope == "project"

    def test_row_to_entry_remaps_hive_scope(self, tmp_path: Path) -> None:
        db = tmp_path / "m.db"
        _make_fake_sqlite(db, [_row(scope="hive")])
        assert read_sqlite_entries(db)[0].scope == "shared"


class TestTagging:
    def test_run_tag_is_appended(self) -> None:
        from tapps_mcp.pipeline.migrate_memory import MigrationEntry

        entry = MigrationEntry(
            key="k",
            value="v",
            tier="pattern",
            scope="project",
            source="agent",
            source_agent="tapps",
            confidence=0.5,
            tags=["existing"],
        )
        tags = _tag_entry_with_run(entry, "abc123")
        assert "existing" in tags
        assert f"{MIGRATION_RUN_TAG_PREFIX}abc123" in tags

    def test_tags_are_deduped_and_capped_at_ten(self) -> None:
        from tapps_mcp.pipeline.migrate_memory import MigrationEntry

        entry = MigrationEntry(
            key="k",
            value="v",
            tier="pattern",
            scope="project",
            source="agent",
            source_agent="tapps",
            confidence=0.5,
            tags=[f"t{i}" for i in range(15)],
        )
        tags = _tag_entry_with_run(entry, "run")
        assert len(tags) == 10
        assert len(set(tags)) == 10


class TestRunMigration:
    def _fake_bridge(self) -> Any:
        bridge = AsyncMock()
        bridge.get = AsyncMock(return_value=None)
        bridge.save = AsyncMock(return_value={"key": "k", "success": True})
        bridge.delete = AsyncMock(return_value=True)
        return bridge

    def test_no_dbs_returns_empty_result(self, tmp_path: Path) -> None:
        bridge = self._fake_bridge()
        result = asyncio.run(run_migration(tmp_path, bridge))
        assert result.discovered_dbs == []
        assert result.migrated == 0
        bridge.save.assert_not_awaited()

    def test_dry_run_counts_entries_but_does_not_write(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / ".tapps-mcp" / "memory"
        mem_dir.mkdir(parents=True)
        _make_fake_sqlite(mem_dir / "memory.db", [_row(key=f"k{i}") for i in range(3)])

        bridge = self._fake_bridge()
        result = asyncio.run(run_migration(tmp_path, bridge, dry_run=True))

        assert result.dry_run is True
        assert result.migrated == 3
        assert result.tier_counts == {"pattern": 3}
        bridge.save.assert_not_awaited()

    def test_real_migration_writes_and_tags(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / ".tapps-mcp" / "memory"
        mem_dir.mkdir(parents=True)
        _make_fake_sqlite(mem_dir / "memory.db", [_row(key=f"k{i}") for i in range(2)])

        bridge = self._fake_bridge()
        result = asyncio.run(run_migration(tmp_path, bridge))

        assert result.migrated == 2
        assert result.failed == 0
        # One save per entry + one marker save.
        assert bridge.save.await_count == 3
        first_call_kwargs = bridge.save.await_args_list[0].kwargs
        assert any(
            t.startswith(MIGRATION_RUN_TAG_PREFIX)
            for t in first_call_kwargs.get("tags", [])
        )
        # Marker entry uses the migration key prefix.
        marker_call_args = bridge.save.await_args_list[-1].args
        assert marker_call_args[0].startswith(MIGRATION_MARKER_KEY_PREFIX)

    def test_duplicate_key_skipped_not_failed(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / ".tapps-mcp" / "memory"
        mem_dir.mkdir(parents=True)
        _make_fake_sqlite(mem_dir / "memory.db", [_row(key="dup")])

        bridge = self._fake_bridge()
        bridge.get = AsyncMock(return_value={"key": "dup", "value": "already-there"})
        result = asyncio.run(run_migration(tmp_path, bridge))

        assert result.migrated == 0
        assert result.skipped_duplicate == 1
        bridge.save.assert_not_awaited()


class TestRollback:
    def test_rollback_deletes_tagged_entries(self) -> None:
        bridge = AsyncMock()
        bridge.search = AsyncMock(
            return_value=[{"key": "a"}, {"key": "b"}, {"key": "c"}]
        )
        bridge.delete = AsyncMock(return_value=True)

        result = asyncio.run(rollback_migration(bridge, "run123"))

        assert result["ok"] is True
        assert result["deleted"] == 3
        # 3 tagged entries + marker key
        assert bridge.delete.await_count == 4

    def test_rollback_reports_errors_per_key(self) -> None:
        bridge = AsyncMock()
        bridge.search = AsyncMock(return_value=[{"key": "a"}])
        bridge.delete = AsyncMock(side_effect=RuntimeError("boom"))

        result = asyncio.run(rollback_migration(bridge, "run-err"))

        assert result["ok"] is False
        assert result["deleted"] == 0
        assert result["errors"] and result["errors"][0]["key"] == "a"

    def test_rollback_survives_search_failure(self) -> None:
        bridge = AsyncMock()
        bridge.search = AsyncMock(side_effect=RuntimeError("brain down"))

        result = asyncio.run(rollback_migration(bridge, "nope"))

        assert result["ok"] is False
        assert "search_failed" in result["error"]


@pytest.mark.parametrize("scope", ["private", "group", "project"])
def test_private_group_project_all_map_to_project(tmp_path: Path, scope: str) -> None:
    db = tmp_path / "m.db"
    _make_fake_sqlite(db, [_row(scope=scope)])
    entries = read_sqlite_entries(db)
    assert entries[0].scope == "project"
