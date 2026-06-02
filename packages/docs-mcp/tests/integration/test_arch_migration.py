"""End-to-end tests for the arch.* -> KG migration (TAP-1953).

A FakeBridge stands in for each of the three brain profiles (read / KG / tag)
so the migration runs without a live tapps-brain. asyncio auto-mode means the
async tests need no marker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from click.testing import CliRunner

from docs_mcp.cli import cli
from docs_mcp.integrations.arch_migration import (
    MIGRATED_TAG,
    ArchMigrator,
    _derive,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeBridge:
    """Records list/upsert/evidence/save calls for one migration phase."""

    def __init__(self, entries: list[dict[str, Any]] | None = None) -> None:
        self._entries = entries or []
        self.upserts: list[tuple[str, str, dict[str, Any] | None]] = []
        self.evidence: list[dict[str, Any]] = []
        self.saves: list[dict[str, Any]] = []

    async def list_memories(self, limit: int = 20, tier: str | None = None) -> list[dict[str, Any]]:
        return list(self._entries)

    async def upsert_entity(
        self,
        canonical_name: str,
        entity_type: str,
        *,
        metadata: dict[str, Any] | None = None,
        project_id: str = "",
    ) -> dict[str, Any]:
        self.upserts.append((canonical_name, entity_type, metadata))
        return {"entity_id": f"e:{entity_type}:{canonical_name}"}

    async def add_evidence(
        self,
        *,
        file_path: str,
        line_range: str,
        commit_sha: str,
        entity_id: str = "",
        edge_id: str = "",
    ) -> dict[str, Any]:
        self.evidence.append(
            {"file_path": file_path, "commit_sha": commit_sha, "entity_id": entity_id}
        )
        return {"recorded": True}

    async def save(
        self,
        key: str,
        value: str,
        *,
        tier: str = "pattern",
        scope: str = "project",
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.saves.append({"key": key, "value": value, "tier": tier, "tags": tags or []})
        return {"key": key, "success": True}


def _structure_entry(project: str = "myproj") -> dict[str, Any]:
    return {
        "key": f"arch.{project}.structure",
        "value": f"Architecture summary for {project}: 3 packages, 12 modules, 20 import edges, 8 classes.",
        "tier": "architectural",
        "scope": "project",
        "tags": ["architecture", "docs-mcp"],
    }


def _pkg_entry(name: str = "tapps_core", project: str = "myproj") -> dict[str, Any]:
    return {
        "key": f"arch.{project}.pkg.{name}",
        "value": f"Package {name} in {project}: Contains 5 public API symbols, 2 classes.",
        "tier": "architectural",
        "scope": "project",
        "tags": ["architecture"],
    }


def _migrator(tmp_path: Path, read: FakeBridge, kg: FakeBridge, tag: FakeBridge) -> ArchMigrator:
    m = ArchMigrator(tmp_path)
    m._reader, m._reader_resolved = read, True
    m._kg, m._kg_resolved = kg, True
    m._tagger, m._tagger_resolved = tag, True
    return m


# ---------------------------------------------------------------------------
# _derive
# ---------------------------------------------------------------------------


class TestDerive:
    def test_structure_parses_project_name_from_prose(self) -> None:
        out = _derive("arch.myproj.structure", "Architecture summary for real-name: 1 packages.")
        assert out is not None
        etype, name, meta = out
        assert (etype, name) == ("project", "real-name")
        assert meta["summary"].startswith("Architecture summary")

    def test_pkg_parses_package_name(self) -> None:
        out = _derive("arch.myproj.pkg.tapps_core", "Package tapps_core in myproj: Contains 5.")
        assert out is not None
        assert out[0] == "package" and out[1] == "tapps_core"

    def test_entry_points_maps_to_project(self) -> None:
        out = _derive("arch.myproj.entry_points", "Entry points for myproj: a, b")
        assert out is not None and out[0] == "project"

    def test_falls_back_to_key_slug_when_prose_unrecognised(self) -> None:
        out = _derive("arch.myproj.structure", "garbage value")
        assert out is not None and out[1] == "myproj"

    def test_non_arch_key_returns_none(self) -> None:
        assert _derive("pattern.foo.bar", "x") is None

    def test_unknown_arch_shape_returns_none(self) -> None:
        assert _derive("arch.myproj.weird.thing", "x") is None


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


class TestDryRun:
    async def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        kg, tag = FakeBridge(), FakeBridge()
        m = _migrator(tmp_path, FakeBridge([_structure_entry(), _pkg_entry()]), kg, tag)

        result = await m.migrate(execute=False)

        assert result.dry_run is True
        assert result.flat_total == 2
        assert len([p for p in result.planned if p.status == "planned"]) == 2
        assert kg.upserts == [] and tag.saves == []
        assert result.migrated == 0

    async def test_unparseable_entry_counted_not_migrated(self, tmp_path: Path) -> None:
        bad = {"key": "arch.myproj.weird.thing", "value": "x", "tier": "architectural", "tags": []}
        m = _migrator(tmp_path, FakeBridge([bad]), FakeBridge(), FakeBridge())

        result = await m.migrate(execute=False)

        assert result.unparseable == 1
        assert result.planned == []


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


class TestExecute:
    async def test_execute_emits_entity_evidence_and_tags(self, tmp_path: Path) -> None:
        kg, tag = FakeBridge(), FakeBridge()
        m = _migrator(tmp_path, FakeBridge([_structure_entry(), _pkg_entry()]), kg, tag)

        result = await m.migrate(execute=True)

        assert result.migrated == 2 and result.failed == 0 and result.ok
        # one entity + one evidence row per entry
        assert {e[1] for e in kg.upserts} == {"project", "package"}
        assert len(kg.evidence) == 2
        assert all(ev["commit_sha"] == "arch-to-kg-migration" for ev in kg.evidence)
        assert all(ev["file_path"].startswith("brain-migration:") for ev in kg.evidence)
        # flat entries re-tagged migrated, never deleted
        assert len(tag.saves) == 2
        assert all(MIGRATED_TAG in s["tags"] for s in tag.saves)

    async def test_idempotent_second_run_is_noop(self, tmp_path: Path) -> None:
        already = _structure_entry()
        already["tags"] = ["architecture", MIGRATED_TAG]
        kg, tag = FakeBridge(), FakeBridge()
        m = _migrator(tmp_path, FakeBridge([already]), kg, tag)

        result = await m.migrate(execute=True)

        assert result.already_migrated == 1 and result.migrated == 0
        assert kg.upserts == [] and tag.saves == []

    async def test_partial_failure_recorded_and_not_ok(self, tmp_path: Path) -> None:
        class BoomKG(FakeBridge):
            async def upsert_entity(self, *a: Any, **k: Any) -> dict[str, Any]:
                raise RuntimeError("brain down")

        m = _migrator(tmp_path, FakeBridge([_structure_entry()]), BoomKG(), FakeBridge())

        result = await m.migrate(execute=True)

        assert result.failed == 1 and not result.ok
        assert result.errors and "brain down" in result.errors[0]

    async def test_unavailable_reader_marks_result(self, tmp_path: Path) -> None:
        m = ArchMigrator(tmp_path)
        m._reader, m._reader_resolved = None, True

        result = await m.migrate(execute=False)

        assert result.available is False and not result.ok


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


class TestCli:
    def test_cli_dry_run_reports_without_writing(self, tmp_path: Path, monkeypatch: Any) -> None:
        kg, tag = FakeBridge(), FakeBridge()
        read = FakeBridge([_structure_entry()])

        def _fake_migrator(_root: Path) -> ArchMigrator:
            return _migrator(tmp_path, read, kg, tag)

        # ArchMigrator is imported inside the command; patch the source symbol.
        monkeypatch.setattr("docs_mcp.integrations.arch_migration.ArchMigrator", _fake_migrator)

        result = CliRunner().invoke(cli, ["migrate-arch-to-kg", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "DRY-RUN" in result.output
        assert "flat arch.* entries found: 1" in result.output
        assert kg.upserts == [] and tag.saves == []

    def test_cli_execute_exits_nonzero_on_failure(self, tmp_path: Path, monkeypatch: Any) -> None:
        class BoomKG(FakeBridge):
            async def upsert_entity(self, *a: Any, **k: Any) -> dict[str, Any]:
                raise RuntimeError("brain down")

        def _fake_migrator(_root: Path) -> ArchMigrator:
            return _migrator(tmp_path, FakeBridge([_structure_entry()]), BoomKG(), FakeBridge())

        monkeypatch.setattr("docs_mcp.integrations.arch_migration.ArchMigrator", _fake_migrator)

        result = CliRunner().invoke(cli, ["migrate-arch-to-kg", "--execute"])

        assert result.exit_code == 1
        assert "failed: 1" in result.output
