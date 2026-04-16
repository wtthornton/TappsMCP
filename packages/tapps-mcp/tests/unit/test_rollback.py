"""Tests for distribution/rollback.py — backup and rollback manager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tapps_mcp.distribution.rollback import BackupManager


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a minimal project with some config files."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE", encoding="utf-8")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{}", encoding="utf-8")
    return tmp_path


class TestBackupCreation:
    def test_creates_backup_directory(self, project: Path) -> None:
        mgr = BackupManager(project)
        files = [project / "AGENTS.md", project / "CLAUDE.md"]
        backup_dir = mgr.create_backup(files, version="0.5.0")

        assert backup_dir.exists()
        assert (backup_dir / "manifest.json").exists()
        assert (backup_dir / "AGENTS.md").exists()
        assert (backup_dir / "CLAUDE.md").exists()

    def test_manifest_contains_metadata(self, project: Path) -> None:
        mgr = BackupManager(project)
        files = [project / "AGENTS.md"]
        backup_dir = mgr.create_backup(files, version="0.5.0", reason="test")

        manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["version"] == "0.5.0"
        assert manifest["reason"] == "test"
        assert "AGENTS.md" in manifest["files"]
        assert manifest["timestamp"]  # non-empty

    def test_preserves_relative_path_structure(self, project: Path) -> None:
        mgr = BackupManager(project)
        settings = project / ".claude" / "settings.json"
        backup_dir = mgr.create_backup([settings], version="0.5.0")

        restored_file = backup_dir / ".claude" / "settings.json"
        assert restored_file.exists()
        assert restored_file.read_text(encoding="utf-8") == "{}"

    def test_skips_nonexistent_files(self, project: Path) -> None:
        mgr = BackupManager(project)
        files = [project / "AGENTS.md", project / "nonexistent.md"]
        backup_dir = mgr.create_backup(files, version="0.5.0")

        manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["files"] == ["AGENTS.md"]

    def test_skips_files_outside_root(self, tmp_path: Path) -> None:
        # Use a subdirectory as project root so the outside file is truly outside
        proj = tmp_path / "myproject"
        proj.mkdir()
        (proj / "AGENTS.md").write_text("# AGENTS", encoding="utf-8")

        outside = tmp_path / "other" / "secret.txt"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("secret", encoding="utf-8")

        mgr = BackupManager(proj)
        backup_dir = mgr.create_backup([outside], version="0.5.0")

        manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["files"] == []


class TestBackupList:
    def test_lists_backups_newest_first(self, project: Path) -> None:
        mgr = BackupManager(project)
        files = [project / "AGENTS.md"]
        mgr.create_backup(files, version="0.4.0")
        mgr.create_backup(files, version="0.5.0")

        backups = mgr.list_backups()
        assert len(backups) == 2

    def test_empty_when_no_backups(self, project: Path) -> None:
        mgr = BackupManager(project)
        assert mgr.list_backups() == []


class TestBackupRestore:
    def test_restores_from_latest(self, project: Path) -> None:
        mgr = BackupManager(project)
        original_content = (project / "AGENTS.md").read_text(encoding="utf-8")

        mgr.create_backup([project / "AGENTS.md"], version="0.5.0")

        # Modify the file
        (project / "AGENTS.md").write_text("MODIFIED", encoding="utf-8")
        assert (project / "AGENTS.md").read_text(encoding="utf-8") == "MODIFIED"

        # Restore
        restored = mgr.restore_backup()
        assert "AGENTS.md" in restored
        assert (project / "AGENTS.md").read_text(encoding="utf-8") == original_content

    def test_restores_from_specific_backup(self, project: Path) -> None:
        mgr = BackupManager(project)
        backup_dir = mgr.create_backup([project / "AGENTS.md"], version="0.5.0")

        (project / "AGENTS.md").write_text("MODIFIED", encoding="utf-8")

        restored = mgr.restore_backup(backup_dir)
        assert "AGENTS.md" in restored
        assert (project / "AGENTS.md").read_text(encoding="utf-8") == "# AGENTS"

    def test_dry_run_does_not_modify(self, project: Path) -> None:
        mgr = BackupManager(project)
        mgr.create_backup([project / "AGENTS.md"], version="0.5.0")
        (project / "AGENTS.md").write_text("MODIFIED", encoding="utf-8")

        restored = mgr.restore_backup(dry_run=True)
        assert "AGENTS.md" in restored
        # File should NOT be restored in dry-run
        assert (project / "AGENTS.md").read_text(encoding="utf-8") == "MODIFIED"

    def test_returns_empty_when_no_backups(self, project: Path) -> None:
        mgr = BackupManager(project)
        assert mgr.restore_backup() == []


class TestBackupCleanup:
    def test_keeps_n_most_recent(self, project: Path) -> None:
        mgr = BackupManager(project)
        files = [project / "AGENTS.md"]
        for i in range(7):
            mgr.create_backup(files, version=f"0.{i}.0")

        removed = mgr.cleanup_old_backups(keep=3)
        remaining = mgr.list_backups()
        assert len(remaining) == 3
        assert removed == 4

    def test_no_op_when_under_limit(self, project: Path) -> None:
        mgr = BackupManager(project)
        mgr.create_backup([project / "AGENTS.md"], version="0.5.0")
        removed = mgr.cleanup_old_backups(keep=5)
        assert removed == 0
