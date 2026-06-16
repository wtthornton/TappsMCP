"""Tests for blue/green MCP deploy (dev-monorepo zero-downtime flip)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.distribution import blue_green as bg


@pytest.fixture
def bg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect blue/green paths to a temp home."""
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
    manifest = {"version": name.split("-")[0], "short_sha": name.split("-", 1)[1]}
    (release_dir / "release.json").write_text(json.dumps(manifest), encoding="utf-8")
    return release_dir


class TestFlipCurrent:
    def test_atomic_flip(self, bg_home: Path) -> None:
        release = _make_release(bg_home / "releases", "3.12.35-abc1234")
        ref = bg.ReleaseRef(version="3.12.35", short_sha="abc1234", path=release)
        result = bg.flip_current(ref)
        assert result["ok"] is True
        assert bg.current_release_path() == release.resolve()
        assert bg.CURRENT_LINK.is_symlink()

    def test_resolve_blue_green_binary(self, bg_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(bg, "blue_green_enabled", lambda: True)
        release = _make_release(bg_home / "releases", "3.12.35-deadbeef")
        ref = bg.ReleaseRef(version="3.12.35", short_sha="deadbeef", path=release)
        bg.flip_current(ref)
        resolved = bg.resolve_blue_green_binary("tapps-mcp")
        assert resolved == str((release / "bin" / "tapps-mcp").resolve())

    def test_resolve_blue_green_binary_disabled_by_default(self, bg_home: Path) -> None:
        release = _make_release(bg_home / "releases", "3.12.35-deadbeef")
        ref = bg.ReleaseRef(version="3.12.35", short_sha="deadbeef", path=release)
        bg.flip_current(ref)
        assert bg.resolve_blue_green_binary("tapps-mcp") is None


class TestGcReleases:
    def test_keeps_current_and_recent(self, bg_home: Path) -> None:
        releases = bg_home / "releases"
        old = _make_release(releases, "3.12.34-1111111")
        mid = _make_release(releases, "3.12.35-2222222")
        current = _make_release(releases, "3.12.35-3333333")
        bg.flip_current(bg.ReleaseRef("3.12.35", "3333333", current))
        result = bg.gc_releases(keep=2, protect=current)
        assert old.name in result["deleted"]
        assert current.name in result["kept"]
        assert not old.exists()
        assert mid.exists() or mid.name in result["kept"]

    def test_skips_in_use_release(self, bg_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        releases = bg_home / "releases"
        in_use = _make_release(releases, "3.12.35-inuse00")
        current = _make_release(releases, "3.12.35-current0")
        bg.flip_current(bg.ReleaseRef("3.12.35", "current0", current))

        def _fake_pids(path: Path) -> set[int]:
            if path.resolve() == in_use.resolve():
                return {99999}
            return set()

        monkeypatch.setattr("tapps_mcp.distribution.blue_green.pids_referencing", _fake_pids)
        result = bg.gc_releases(keep=0, protect=current)
        assert in_use.name in result["skipped_in_use"]
        assert in_use.exists()


class TestDeployLock:
    def test_serializes_deploys(self, bg_home: Path) -> None:
        with bg.deploy_lock():
            assert bg.is_deploy_lock_held() is True
        assert bg.is_deploy_lock_held() is False


class TestDeployBlueGreenDryRun:
    def test_dry_run_does_not_flip(self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        checkout = tmp_path / "checkout"
        (checkout / "packages" / "tapps-mcp").mkdir(parents=True)
        pyproject = checkout / "packages" / "tapps-mcp" / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "3.12.35"\n', encoding="utf-8")

        monkeypatch.setattr(bg, "_read_short_sha", lambda _c: "abc1234")
        result = bg.deploy_blue_green(checkout, dry_run=True, skip_gate=True)
        assert result["ok"] is True
        assert not bg.CURRENT_LINK.exists()


class TestSmokeTestRelease:
    def test_smoke_passes_for_stub_binaries(self, bg_home: Path) -> None:
        release_dir = _make_release(bg_home / "releases", "3.12.35-smoke01")
        ref = bg.ReleaseRef("3.12.35", "smoke01", release_dir)
        result = bg.smoke_test_release(ref, project_root=None)
        assert result["ok"] is True
        assert "tapps-mcp" in result["versions"]


class TestQuiescenceGate:
    def test_ok_when_no_pytest(self, tmp_path: Path) -> None:
        checkout = tmp_path / "repo"
        checkout.mkdir()
        with patch.object(bg.Path, "is_dir", return_value=False):
            gate = bg.quiescence_gate(checkout)
        assert gate["ok"] is True
