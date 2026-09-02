"""Tests for the `tapps-mcp memory` CLI command group (Epic 53, Story 53.1).

``--json`` assertions parse ``result.stdout``, never ``result.output``: since
Click 8.2 the latter interleaves stderr, so any log record emitted during the
command corrupts the parse. That surfaced as an order-dependent failure —
a settings cache miss logged ``memory.project_id_auto_derived`` to stderr and
broke ``json.loads``. The CLI itself is correct (JSON on stdout, logs on
stderr), which is exactly what reading stdout asserts.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner
from tapps_brain.models import MemoryEntry, MemoryScope, MemorySource, MemoryTier

from tapps_mcp.cli import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_entry(
    key: str = "test-key",
    value: str = "test value",
    tier: str = "pattern",
    scope: str = "project",
    confidence: float = 0.8,
) -> MemoryEntry:
    return MemoryEntry(
        key=key,
        value=value,
        tier=MemoryTier(tier),
        scope=MemoryScope(scope),
        confidence=confidence,
        source=MemorySource.agent,
    )


def _mock_store(entries: list[MemoryEntry] | None = None) -> MagicMock:
    """Create a mock MemoryStore with sensible defaults."""
    store = MagicMock()
    store.list_all.return_value = entries or []
    store.search.return_value = entries or []
    store.get.return_value = entries[0] if entries else None
    store.save.return_value = entries[0] if entries else _make_entry()
    store.delete.return_value = True
    store.close.return_value = None
    return store


_ROOT_PATCH = "tapps_mcp.cli._get_project_root"
_STORE_PATCH = "tapps_brain.store.MemoryStore"
_BRIDGE_PATCH = "tapps_mcp.cli._create_cli_brain_bridge"


def _mock_bridge(
    *,
    save_result: dict[str, object] | None = None,
    get_result: dict[str, object] | None = None,
    search_result: list[dict[str, object]] | None = None,
) -> MagicMock:
    bridge = MagicMock()
    bridge.save = AsyncMock(
        return_value=save_result or {"key": "test-key", "value": "test value", "success": True}
    )
    bridge.get = AsyncMock(return_value=get_result)
    bridge.search = AsyncMock(
        return_value=search_result
        if search_result is not None
        else [{"key": "found-it", "tier": "pattern", "confidence": 0.8, "value": "hit"}]
    )
    bridge.close = MagicMock()
    return bridge


def _mock_list_bridge(entries: list[dict[str, object]] | None = None) -> MagicMock:
    """Bridge mock for the list/delete commands (migrated off local MemoryStore)."""
    bridge = MagicMock()
    bridge.list_memories = AsyncMock(return_value=entries or [])
    bridge.delete = AsyncMock(return_value=True)
    bridge.close = MagicMock()
    return bridge


class TestMemoryList:
    def test_list_empty(self, runner: CliRunner) -> None:
        bridge = _mock_list_bridge()
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(main, ["memory", "list"])
        assert result.exit_code == 0
        assert "No memories found" in result.output

    def test_list_with_entries(self, runner: CliRunner) -> None:
        entries = [{"key": "arch-decision", "tier": "architectural", "confidence": 0.8}]
        bridge = _mock_list_bridge(entries)
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(main, ["memory", "list"])
        assert result.exit_code == 0
        assert "arch-decision" in result.output
        assert "architectural" in result.output

    def test_list_json_output(self, runner: CliRunner) -> None:
        entries = [{"key": "test-key", "tier": "pattern", "confidence": 0.8}]
        bridge = _mock_list_bridge(entries)
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(main, ["memory", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["key"] == "test-key"

    def test_list_with_tier_filter(self, runner: CliRunner) -> None:
        bridge = _mock_list_bridge()
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(main, ["memory", "list", "--tier", "architectural"])
        assert result.exit_code == 0
        bridge.list_memories.assert_awaited_once_with(limit=500, tier="architectural")

    def test_list_with_scope_filter(self, runner: CliRunner) -> None:
        entries = [
            {"key": "keep", "scope": "branch", "tier": "pattern", "confidence": 0.8},
            {"key": "drop", "scope": "project", "tier": "pattern", "confidence": 0.8},
        ]
        bridge = _mock_list_bridge(entries)
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(main, ["memory", "list", "--scope", "branch"])
        assert result.exit_code == 0
        assert "keep" in result.output
        assert "drop" not in result.output


class TestMemorySave:
    def test_save_success(self, runner: CliRunner) -> None:
        bridge = _mock_bridge()
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(
                main, ["memory", "save", "--key", "test-key", "--value", "test value"]
            )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["key"] == "test-key"
        assert "memory_group_note" in data
        bridge.save.assert_awaited_once()
        bridge.close.assert_called_once()

    def test_save_with_memory_group(self, runner: CliRunner) -> None:
        bridge = _mock_bridge(
            save_result={"key": "insight-1", "success": True, "memory_group": "insights"}
        )
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(
                main,
                [
                    "memory",
                    "save",
                    "--key",
                    "insight-1",
                    "--value",
                    "pattern",
                    "--memory-group",
                    "insights",
                ],
            )
        assert result.exit_code == 0
        bridge.save.assert_awaited_once_with(
            key="insight-1",
            value="pattern",
            tier="pattern",
            tags=[],
            memory_group="insights",
        )
        data = json.loads(result.stdout)
        assert "memory_group_note" not in data

    def test_save_with_tags(self, runner: CliRunner) -> None:
        bridge = _mock_bridge()
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(
                main,
                [
                    "memory",
                    "save",
                    "--key",
                    "test-key",
                    "--value",
                    "test value",
                    "--tags",
                    "python,testing",
                ],
            )
        assert result.exit_code == 0
        bridge.save.assert_awaited_once_with(
            key="test-key",
            value="test value",
            tier="pattern",
            tags=["python", "testing"],
        )

    def test_save_blocked_by_safety(self, runner: CliRunner) -> None:
        bridge = _mock_bridge(
            save_result={"error": "content_blocked", "message": "Blocked by safety."}
        )
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(
                main, ["memory", "save", "--key", "bad-key", "--value", "bad content"]
            )
        assert result.exit_code == 1
        assert "Blocked by safety" in result.output

    def test_save_bridge_unavailable(self, runner: CliRunner) -> None:
        with patch(_BRIDGE_PATCH, return_value=None):
            result = runner.invoke(
                main, ["memory", "save", "--key", "test-key", "--value", "test value"]
            )
        assert result.exit_code == 2
        assert "brain_http_url" in result.output
        assert "TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN" in result.output


class TestMemorySaveHandoffOverCap:
    """A handoff over the brain's 4096-char value cap must land durably on
    disk via the manual `memory save` fallback, not be handed to a brain
    write that rejects or truncates it with no local copy anywhere (TAP-6853).
    Slot routing / non-handoff-key exemption are unit-tested against
    ``try_persist_oversized_handoff`` in test_handoff_write.py; this class
    covers only the CLI wiring.
    """

    _OVER_CAP_VALUE = "x" * 4200

    def test_over_cap_writes_file_not_brain(self, runner: CliRunner, tmp_path: Path) -> None:
        """Before this fix the CLI had no durable fallback for an over-cap
        handoff: it went straight to `bridge.save()`, which the brain would
        reject or truncate, leaving no copy anywhere."""
        bridge = _mock_bridge()
        with patch(_ROOT_PATCH, return_value=tmp_path), patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(
                main,
                ["memory", "save", "--key", "session-handoff", "--value", self._OVER_CAP_VALUE],
            )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["brain_mirror"] == "skipped_value_over_cap"
        target = tmp_path / ".tapps-mcp" / "session-handoff.md"
        assert data["persisted_to"] == str(target)
        assert target.read_text(encoding="utf-8") == self._OVER_CAP_VALUE
        bridge.save.assert_not_awaited()

    def test_under_cap_handoff_key_still_uses_brain(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """The file fallback is over-cap-only — an ordinary handoff still
        mirrors to the brain exactly as it did before this fix."""
        bridge = _mock_bridge()
        with patch(_ROOT_PATCH, return_value=tmp_path), patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(
                main, ["memory", "save", "--key", "session-handoff", "--value", "short body"]
            )
        assert result.exit_code == 0
        bridge.save.assert_awaited_once()
        assert not (tmp_path / ".tapps-mcp" / "session-handoff.md").exists()


class TestMemoryGet:
    def test_get_found(self, runner: CliRunner) -> None:
        bridge = _mock_bridge(get_result={"key": "test-key", "value": "test value"})
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(main, ["memory", "get", "--key", "test-key"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["key"] == "test-key"
        bridge.get.assert_awaited_once_with("test-key")

    def test_get_not_found(self, runner: CliRunner) -> None:
        bridge = _mock_bridge(get_result=None)
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(main, ["memory", "get", "--key", "missing"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_get_bridge_unavailable(self, runner: CliRunner) -> None:
        with patch(_BRIDGE_PATCH, return_value=None):
            result = runner.invoke(main, ["memory", "get", "--key", "test-key"])
        assert result.exit_code == 2
        assert "BrainBridge unavailable" in result.output


class TestMemorySearch:
    def test_search_uses_bridge_when_available(self, runner: CliRunner) -> None:
        bridge = _mock_bridge()
        with (
            patch("tapps_core.brain_bridge.create_brain_bridge", return_value=bridge),
            patch(_STORE_PATCH) as store_ctor,
        ):
            result = runner.invoke(main, ["memory", "search", "--query", "test"])
        assert result.exit_code == 0
        assert "found-it" in result.output
        bridge.search.assert_awaited_once_with("test", limit=10)
        store_ctor.assert_not_called()

    def test_search_falls_back_to_store_when_bridge_unavailable(self, runner: CliRunner) -> None:
        entries = [_make_entry(key="local-hit")]
        store = _mock_store(entries)
        with (
            patch("tapps_core.brain_bridge.create_brain_bridge", return_value=None),
            patch(_ROOT_PATCH, return_value=Path("/fake")),
            patch(_STORE_PATCH, return_value=store),
        ):
            result = runner.invoke(main, ["memory", "search", "--query", "test"])
        assert result.exit_code == 0
        assert "local-hit" in result.output
        store.search.assert_called_once_with("test")

    def test_search_no_results(self, runner: CliRunner) -> None:
        bridge = _mock_bridge(search_result=[])
        with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=bridge):
            result = runner.invoke(main, ["memory", "search", "--query", "nothing"])
        assert result.exit_code == 0
        assert "No results found" in result.output

    def test_search_json_output(self, runner: CliRunner) -> None:
        bridge = _mock_bridge(
            search_result=[{"key": "test-key", "tier": "pattern", "confidence": 0.8, "value": "x"}]
        )
        with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=bridge):
            result = runner.invoke(main, ["memory", "search", "--query", "test", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert data[0]["key"] == "test-key"

    def test_search_with_limit(self, runner: CliRunner) -> None:
        bridge = _mock_bridge()
        with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=bridge):
            result = runner.invoke(main, ["memory", "search", "--query", "test", "--limit", "2"])
        assert result.exit_code == 0
        bridge.search.assert_awaited_once_with("test", limit=2)


class TestMemoryDelete:
    def test_delete_success(self, runner: CliRunner) -> None:
        bridge = _mock_list_bridge()
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(main, ["memory", "delete", "--key", "test-key"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_delete_not_found(self, runner: CliRunner) -> None:
        bridge = _mock_list_bridge()
        bridge.delete = AsyncMock(return_value=False)
        with patch(_BRIDGE_PATCH, return_value=bridge):
            result = runner.invoke(main, ["memory", "delete", "--key", "missing"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestMemoryPromoteInstincts:
    """CLI-level tests for `tapps-mcp memory promote-instincts` (TAP-6701, VAL-23).

    Selector/dry-run/apply logic itself is covered in test_instinct_promotion.py;
    these tests only exercise the click wiring (report path, --operator gate,
    bridge plumbing). ``Path.home()`` is monkeypatched so this never touches the
    real ``~/.claude/homunculus/`` tree.
    """

    def _seed_homunculus(self, home: Path, repo_root: Path, *, instinct_id: str = "seed") -> None:
        homunculus = home / ".claude" / "homunculus"
        homunculus.mkdir(parents=True)
        (homunculus / "projects.json").write_text(
            json.dumps({"p1": {"id": "p1", "name": "tapps-mcp", "root": str(repo_root)}}),
            encoding="utf-8",
        )
        instincts_dir = homunculus / "projects" / "p1" / "instincts" / "personal"
        instincts_dir.mkdir(parents=True)
        (instincts_dir / f"{instinct_id}.md").write_text(
            "---\n"
            f"id: {instinct_id}\n"
            "trigger: when doing the thing\n"
            "confidence: 0.9\n"
            "domain: workflow\n"
            "source: session-observation\n"
            "scope: project\n"
            "project_id: p1\n"
            "project_name: tapps-mcp\n"
            "---\n"
            "\n## Action\nDo the thing.\n\n"
            "## Evidence\n- Observed 5 times in session x\n- Last observed: 2026-08-20\n",
            encoding="utf-8",
        )

    def test_dry_run_writes_report(self, runner: CliRunner, tmp_path: Path) -> None:
        home = tmp_path / "home"
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        self._seed_homunculus(home, repo_root)
        report_path = tmp_path / "out.md"

        with (
            patch(_ROOT_PATCH, return_value=repo_root),
            patch("pathlib.Path.home", return_value=home),
        ):
            result = runner.invoke(
                main,
                ["memory", "promote-instincts", "--report", str(report_path)],
            )
        assert result.exit_code == 0
        assert "1 instinct promotion candidate" in result.output
        assert report_path.exists()
        assert "key: seed" in report_path.read_text(encoding="utf-8")

    def test_apply_requires_operator(self, runner: CliRunner, tmp_path: Path) -> None:
        home = tmp_path / "home"
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        report_path = tmp_path / "out.md"
        with (
            patch(_ROOT_PATCH, return_value=repo_root),
            patch("pathlib.Path.home", return_value=home),
        ):
            result = runner.invoke(
                main,
                ["memory", "promote-instincts", "--apply", "--report", str(report_path)],
            )
        assert result.exit_code == 2
        assert "--operator is required" in result.output

    def test_apply_calls_bridge_promote_instinct(self, runner: CliRunner, tmp_path: Path) -> None:
        home = tmp_path / "home"
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        self._seed_homunculus(home, repo_root)
        report_path = tmp_path / "out.md"

        bridge = MagicMock()
        bridge.promote_instinct = AsyncMock(return_value={"key": "seed", "success": True})
        bridge.close = MagicMock()

        with (
            patch(_ROOT_PATCH, return_value=repo_root),
            patch("pathlib.Path.home", return_value=home),
            patch(_BRIDGE_PATCH, return_value=bridge),
        ):
            result = runner.invoke(
                main,
                [
                    "memory",
                    "promote-instincts",
                    "--apply",
                    "--operator",
                    "bill",
                    "--report",
                    str(report_path),
                ],
            )
        assert result.exit_code == 0
        assert "Promoted 1 instinct(s)" in result.output
        bridge.promote_instinct.assert_awaited_once()
        _, kwargs = bridge.promote_instinct.call_args
        assert kwargs["actor"] == "operator:bill"
        assert kwargs["evidence"] == "instinct:seed"
        assert kwargs["signal"] == "human"
        instinct_file = (
            home
            / ".claude"
            / "homunculus"
            / "projects"
            / "p1"
            / "instincts"
            / "personal"
            / "seed.md"
        )
        assert "promoted_key: seed" in instinct_file.read_text(encoding="utf-8")

    def test_apply_bridge_unavailable(self, runner: CliRunner, tmp_path: Path) -> None:
        home = tmp_path / "home"
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        self._seed_homunculus(home, repo_root)
        report_path = tmp_path / "out.md"

        with (
            patch(_ROOT_PATCH, return_value=repo_root),
            patch("pathlib.Path.home", return_value=home),
            patch(_BRIDGE_PATCH, return_value=None),
        ):
            result = runner.invoke(
                main,
                [
                    "memory",
                    "promote-instincts",
                    "--apply",
                    "--operator",
                    "bill",
                    "--report",
                    str(report_path),
                ],
            )
        assert result.exit_code == 2
        assert "BrainBridge unavailable" in result.output

    def test_apply_not_implemented_bridge_exits_cleanly(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """The in-process BrainBridge's ``promote_instinct`` raises
        ``NotImplementedError`` until the brain ships the capability — this must
        surface as a clean CLI error, not an uncaught traceback. Regression for
        the fact that ``NotImplementedError`` subclasses ``RuntimeError``, so a
        bare ``except RuntimeError`` would swallow-and-reraise it unhelpfully."""
        home = tmp_path / "home"
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        self._seed_homunculus(home, repo_root)
        report_path = tmp_path / "out.md"

        bridge = MagicMock()
        bridge.promote_instinct = AsyncMock(
            side_effect=NotImplementedError("promote_instinct requires the HTTP brain path")
        )
        bridge.close = MagicMock()

        with (
            patch(_ROOT_PATCH, return_value=repo_root),
            patch("pathlib.Path.home", return_value=home),
            patch(_BRIDGE_PATCH, return_value=bridge),
        ):
            result = runner.invoke(
                main,
                [
                    "memory",
                    "promote-instincts",
                    "--apply",
                    "--operator",
                    "bill",
                    "--report",
                    str(report_path),
                ],
            )
        assert result.exit_code == 2
        assert "requires the HTTP brain path" in result.output


class TestMemoryImportExport:
    def test_import_success(self, runner: CliRunner, tmp_path: Path) -> None:
        import_file = tmp_path / "memories.json"
        import_file.write_text('{"memories": []}')

        mock_store = _mock_store()
        with (
            patch(_ROOT_PATCH, return_value=tmp_path),
            patch(_STORE_PATCH, return_value=mock_store),
            patch("tapps_brain.io.import_memories") as mock_import,
        ):
            mock_import.return_value = {
                "imported_count": 3,
                "skipped_count": 1,
                "error_count": 0,
            }
            result = runner.invoke(main, ["memory", "import-file", "--file", str(import_file)])
        assert result.exit_code == 0 or "Imported" in result.output or result.exit_code == 0

    def test_export_success(self, runner: CliRunner, tmp_path: Path) -> None:
        export_file = tmp_path / "export.json"
        mock_store = _mock_store()
        with (
            patch(_ROOT_PATCH, return_value=tmp_path),
            patch(_STORE_PATCH, return_value=mock_store),
            patch("tapps_brain.io.export_memories") as mock_export,
        ):
            mock_export.return_value = {
                "exported_count": 5,
                "file_path": str(export_file),
            }
            result = runner.invoke(main, ["memory", "export-file", "--file", str(export_file)])
        assert result.exit_code == 0 or "Exported" in result.output or result.exit_code == 0

    def test_export_with_tier_and_format(self, runner: CliRunner, tmp_path: Path) -> None:
        export_file = tmp_path / "export.md"
        mock_store = _mock_store()
        with (
            patch(_ROOT_PATCH, return_value=tmp_path),
            patch(_STORE_PATCH, return_value=mock_store),
            patch("tapps_brain.io.export_memories") as mock_export,
        ):
            mock_export.return_value = {
                "exported_count": 2,
                "file_path": str(export_file),
            }
            result = runner.invoke(
                main,
                [
                    "memory",
                    "export-file",
                    "--file",
                    str(export_file),
                    "--format",
                    "markdown",
                    "--tier",
                    "architectural",
                    "--scope",
                    "project",
                ],
            )
        assert result.exit_code == 0
        mock_export.assert_called_once()
        _, kwargs = mock_export.call_args
        assert kwargs["export_format"] == "markdown"
        assert kwargs["tier"] == "architectural"
        assert kwargs["scope"] == "project"

    def test_export_bad_format_rejected(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            main,
            [
                "memory",
                "export-file",
                "--file",
                str(tmp_path / "out.json"),
                "--format",
                "yaml",
            ],
        )
        assert result.exit_code != 0


class TestMemoryReseed:
    def test_reseed_requires_confirm(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["memory", "reseed"])
        assert result.exit_code != 0

    def test_reseed_success(self, runner: CliRunner, tmp_path: Path) -> None:
        mock_store = _mock_store()
        mock_profile = MagicMock()
        mock_profile.project_type = "python"
        with (
            patch(_ROOT_PATCH, return_value=tmp_path),
            patch(_STORE_PATCH, return_value=mock_store),
            patch("tapps_mcp.project.profiler.detect_project_profile", return_value=mock_profile),
            patch("tapps_brain.seeding.reseed_from_profile") as mock_reseed,
            patch("tapps_core.config.settings.load_settings") as mock_settings,
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_reseed.return_value = {"seeded_count": 4}
            result = runner.invoke(main, ["memory", "reseed", "--confirm"])
        assert result.exit_code == 0
        assert "Re-seeded" in result.output
        mock_reseed.assert_called_once()
