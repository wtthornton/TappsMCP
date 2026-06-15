"""Tests for backup dedupe during upgrade."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.rollback import BackupManager


def test_find_recent_backup_within_window(tmp_path: Path) -> None:
    mgr = BackupManager(tmp_path)
    target = tmp_path / "AGENTS.md"
    target.write_text("# agents\n", encoding="utf-8")
    backup_dir = mgr.create_backup([target], version="1.0.0")

    found = mgr.find_recent_backup(max_age_seconds=60)

    assert found == backup_dir


def test_find_recent_backup_empty_when_none(tmp_path: Path) -> None:
    mgr = BackupManager(tmp_path)
    assert mgr.find_recent_backup(max_age_seconds=60) is None
