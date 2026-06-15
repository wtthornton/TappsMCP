"""Tests for legacy hook sidecar cleanup."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.platform_hooks import cleanup_legacy_hook_sidecars


def test_cleanup_removes_co_located_sidecars(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "tapps-stop.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (hooks_dir / "tapps-stop.sh.pre-upgrade.111").write_text("old\n", encoding="utf-8")
    (hooks_dir / "tapps-stop.sh.pre-upgrade.222").write_text("older\n", encoding="utf-8")

    report = cleanup_legacy_hook_sidecars(tmp_path, dry_run=False)

    assert report["removed_sidecar_count"] == 2
    assert list(hooks_dir.glob("*.pre-upgrade.*")) == []
    assert (hooks_dir / "tapps-stop.sh").exists()


def test_cleanup_dry_run_does_not_delete(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".cursor" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "tapps-before-mcp.sh.pre-upgrade.999").write_text("x\n", encoding="utf-8")

    report = cleanup_legacy_hook_sidecars(tmp_path, dry_run=True)

    assert report["action"] == "dry-run"
    assert report["removed_sidecar_count"] == 1
    assert list(hooks_dir.glob("*.pre-upgrade.*"))


def test_cleanup_prunes_excess_storage_copies(tmp_path: Path) -> None:
    storage = tmp_path / ".tapps-mcp" / "hook-backups" / ".claude" / "hooks"
    storage.mkdir(parents=True)
    for i in range(4):
        (storage / f"tapps-stop.sh.pre-upgrade.{1000 + i}").write_text(f"v{i}\n", encoding="utf-8")

    report = cleanup_legacy_hook_sidecars(tmp_path, dry_run=False, prune_storage_keep=2)

    assert report["pruned_storage_count"] == 2
    assert len(list(storage.glob("tapps-stop.sh.pre-upgrade.*"))) == 2
