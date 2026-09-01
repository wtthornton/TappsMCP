"""Tests for the ``deploy-local`` CLI (TAP-6896).

``--dry-run`` used to return before build/flip/GC, so the preview could not
say what the one irreversible part of a real run -- the GC -- would delete.
The fix computes the preview from the same ``_plan_gc`` helper the real GC
uses (blue_green.py), so these tests exercise it through the actual CLI
entry point rather than the underlying library function directly.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution import blue_green as bg


@pytest.fixture
def bg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect blue/green paths to a temp home (mirrors test_blue_green.py)."""
    home = tmp_path / "tapps-mcp-home"
    releases = home / "releases"
    current = home / "current"
    lock_path = home / ".deploy.lock"
    monkeypatch.setattr(bg, "TAPPS_MCP_HOME", home)
    monkeypatch.setattr(bg, "RELEASES_DIR", releases)
    monkeypatch.setattr(bg, "CURRENT_LINK", current)
    monkeypatch.setattr(bg, "DEPLOY_LOCK", lock_path)
    releases.mkdir(parents=True, exist_ok=True)
    return home


def _make_release(releases: Path, name: str) -> Path:
    release_dir = releases / name
    bin_dir = release_dir / "bin"
    bin_dir.mkdir(parents=True)
    for tool in bg._REQUIRED_BINARIES:
        exe = bin_dir / tool
        exe.write_text("#!/bin/sh\necho tool, version 1.0.0\n", encoding="utf-8")
        exe.chmod(0o755)
    manifest = {"version": name.split("-", 1)[0], "short_sha": name.split("-", 1)[1]}
    (release_dir / "release.json").write_text(json.dumps(manifest), encoding="utf-8")
    return release_dir


def _make_checkout(tmp_path: Path, version: str = "3.12.40") -> Path:
    checkout = tmp_path / "checkout"
    (checkout / "packages" / "tapps-mcp").mkdir(parents=True)
    (checkout / "packages" / "tapps-mcp" / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )
    return checkout


def test_dry_run_previews_evictions_and_deletes_nothing(
    bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releases_dir = bg_home / "releases"
    evictable = _make_release(releases_dir, "3.12.30-0000001")
    kept_by_index = _make_release(releases_dir, "3.12.35-1111111")

    checkout = _make_checkout(tmp_path)
    monkeypatch.setattr(bg, "_read_short_sha", lambda _c: "abc1234")

    before = sorted(p.name for p in releases_dir.iterdir())

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "deploy-local",
            "--tapps-checkout",
            str(checkout),
            "--dry-run",
            "--skip-gate",
            "--keep-releases",
            "1",
        ],
    )

    after = sorted(p.name for p in releases_dir.iterdir())

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["ok"] is True
    assert report["dry_run"] is True

    preview = report["gc_preview"]
    # Known-positive: with --keep-releases 1, the older of the two existing
    # releases would be evicted by index -- the preview must say so.
    assert evictable.name in preview["to_delete"]
    # Known-negative: the release within keep is not slated for deletion.
    assert kept_by_index.name in preview["kept"]
    assert evictable.name not in preview["kept"]

    # The one irreversible part of a deploy: --dry-run must delete nothing.
    # Before/after directory listing proves it -- not just an "ok" flag.
    assert before == after
    assert evictable.exists()
    assert kept_by_index.exists()


def test_dry_run_honours_keep_releases_from_command_line(
    bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--keep-releases 2 (not the library default of 3) must reach the preview."""
    releases_dir = bg_home / "releases"
    now = time.time()
    oldest = _make_release(releases_dir, "3.12.20-aaaaaaa")
    os.utime(oldest, (now - 300, now - 300))
    middle = _make_release(releases_dir, "3.12.25-bbbbbbb")
    os.utime(middle, (now - 200, now - 200))
    newest = _make_release(releases_dir, "3.12.30-ccccccc")
    os.utime(newest, (now - 100, now - 100))

    checkout = _make_checkout(tmp_path)
    monkeypatch.setattr(bg, "_read_short_sha", lambda _c: "abc1234")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "deploy-local",
            "--tapps-checkout",
            str(checkout),
            "--dry-run",
            "--skip-gate",
            "--keep-releases",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    preview = report["gc_preview"]

    # Known-positive: with the CLI's --keep-releases 2 (below the library
    # default of 3), the two most-recent releases are kept by index.
    assert newest.name in preview["kept"]
    assert middle.name in preview["kept"]
    # Known-negative: the third-oldest is evicted -- proves the CLI value
    # of 2, not the library default of 3, reached the preview.
    assert oldest.name in preview["to_delete"]
    assert all(p.exists() for p in (oldest, middle, newest))
