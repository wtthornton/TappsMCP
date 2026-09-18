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
from unittest.mock import MagicMock

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
            # TAP-6896: the preview models post-flip state, so the incoming
            # (not-yet-built) release occupies the newest keep-slot too --
            # 2, not 1, is required for one existing release to still fit.
            "2",
        ],
    )

    after = sorted(p.name for p in releases_dir.iterdir())

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["ok"] is True
    assert report["dry_run"] is True

    preview = report["gc_preview"]
    # Known-positive: with --keep-releases 2, one incoming slot + one
    # existing slot -- the older of the two existing releases is evicted.
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

    # Known-positive: with the CLI's --keep-releases 2, the incoming release
    # occupies the newest keep-slot (post-flip modeling, TAP-6896) and
    # `newest` occupies the other.
    assert newest.name in preview["kept"]
    # Known-negative: `middle` is evicted at keep=2 once the incoming release
    # consumes a slot -- under the library default of 3 it would still be
    # kept, so this proves the CLI's 2, not the default 3, reached the
    # preview.
    assert middle.name in preview["to_delete"]
    assert oldest.name in preview["to_delete"]
    assert all(p.exists() for p in (oldest, middle, newest))


class TestAbortedDeployExitCode:
    """TAP-7848 acceptance: an aborted deploy must not exit like a completed
    one. ``deploy_local_cmd`` raises ``SystemExit(1)`` whenever
    ``report.get("ok")`` is falsy -- exercised here through a real abort
    (a genuinely sick release, non-skew) driven through the CLI entry point.
    """

    def test_aborted_deploy_exits_non_zero(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checkout = _make_checkout(tmp_path)
        release = bg.ReleaseRef(
            "3.12.90", "abc1234", _make_release(bg_home / "releases", "3.12.90-abc1234")
        )
        monkeypatch.setattr(bg, "_release_ref", lambda _c: release)
        monkeypatch.setattr(bg, "build_release", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(bg, "flip_current", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(bg, "current_release_path", lambda: None)
        monkeypatch.setattr(bg, "_reap_superseded_then_gc", lambda *a, **k: {})

        import tapps_mcp.distribution.fleet_control as fleet_mod
        import tapps_mcp.distribution.mcp_zombie_reap as zombie_mod
        import tapps_mcp.distribution.setup_generator as setup_mod

        monkeypatch.setattr(zombie_mod, "reap_orphan_mcp_serves", lambda **k: {"ok": True})
        monkeypatch.setattr(fleet_mod, "fleet_any_running", lambda: True)
        monkeypatch.setattr(setup_mod, "is_tapps_mcp_dev_monorepo", lambda _c: False)
        monkeypatch.setattr(
            "tapps_mcp.distribution.blue_green_profile_smoke.pre_flip_profile_smoke",
            lambda *a, **k: {"ok": True, "profiles": {}},
        )

        payload = json.dumps(
            {
                "checks": [
                    {
                        "name": "tapps-mcp binary version",
                        "ok": False,
                        "severity": "fail",
                        "category": "release-health",
                        "message": "Version mismatch: tapps-mcp=3.8, server=3.9",
                    }
                ]
            }
        )

        def _fake_run(cmd: list[str], **_kwargs: object) -> object:
            if cmd[-1] == "--version":
                return MagicMock(returncode=0, stdout="1.0.0", stderr="")
            return MagicMock(returncode=1, stdout=payload, stderr="")

        monkeypatch.setattr(bg, "_run", _fake_run)

        runner = CliRunner()
        result = runner.invoke(
            main, ["deploy-local", "--tapps-checkout", str(checkout), "--skip-gate"]
        )

        report = json.loads(result.output)
        assert report["ok"] is False
        assert report["post_flip_status"] == "aborted: release sick"
        assert result.exit_code != 0, (
            f"aborted deploy must not exit 0, got {result.exit_code}: {result.output}"
        )
