"""Tests for blue/green MCP deploy (dev-monorepo zero-downtime flip)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

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
    manifest = {"version": name.split("-", 1)[0], "short_sha": name.split("-", 1)[1]}
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

    def test_resolve_blue_green_binary(
        self, bg_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bg, "blue_green_enabled", lambda: True)
        release = _make_release(bg_home / "releases", "3.12.35-deadbeef")
        ref = bg.ReleaseRef(version="3.12.35", short_sha="deadbeef", path=release)
        bg.flip_current(ref)
        resolved = bg.resolve_blue_green_binary("tapps-mcp")
        assert resolved == str((release / "bin" / "tapps-mcp").resolve())

    def test_resolve_blue_green_binary_disabled_by_env(
        self,
        bg_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TAPPS_MCP_USE_BLUE_GREEN", "0")
        release = _make_release(bg_home / "releases", "3.12.35-deadbeef")
        ref = bg.ReleaseRef(version="3.12.35", short_sha="deadbeef", path=release)
        bg.flip_current(ref)
        assert bg.resolve_blue_green_binary("tapps-mcp") is None

    def test_resolve_blue_green_binary_auto_when_current_present(
        self,
        bg_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TAPPS_MCP_USE_BLUE_GREEN", raising=False)
        release = _make_release(bg_home / "releases", "3.12.35-deadbeef")
        ref = bg.ReleaseRef(version="3.12.35", short_sha="deadbeef", path=release)
        bg.flip_current(ref)
        resolved = bg.resolve_blue_green_binary("tapps-mcp")
        assert resolved == str((release / "bin" / "tapps-mcp").resolve())


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
    def test_dry_run_does_not_flip(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checkout = tmp_path / "checkout"
        (checkout / "packages" / "tapps-mcp").mkdir(parents=True)
        pyproject = checkout / "packages" / "tapps-mcp" / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "3.12.35"\n', encoding="utf-8")

        monkeypatch.setattr(bg, "_read_short_sha", lambda _c: "abc1234")
        result = bg.deploy_blue_green(checkout, dry_run=True, skip_gate=True)
        assert result["ok"] is True
        assert not bg.CURRENT_LINK.exists()


class TestBuildRelease:
    def test_installs_packages_with_treesitter_extra(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TAP-4537: the release env needs the treesitter extra, otherwise its
        call-graph fingerprint (which folds in the grammar version) never
        matches the dev venv's and the index reports permanently stale."""
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        commands: list[list[str]] = []

        def _fake_run(cmd: list[str], **_kwargs: object) -> object:
            commands.append(cmd)
            if cmd[:2] == ["uv", "venv"]:
                (bg.RELEASES_DIR / "3.12.35-abc1234").mkdir(parents=True, exist_ok=True)
            return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(bg, "_run", _fake_run)
        ref = bg.ReleaseRef("3.12.35", "abc1234", bg.RELEASES_DIR / "3.12.35-abc1234")
        result = bg.build_release(checkout, ref)
        assert result["ok"] is True

        install_cmd = next(c for c in commands if c[:3] == ["uv", "pip", "install"])
        specs = [
            arg
            for arg in install_cmd[install_cmd.index("--python") + 2 :]
            if not arg.startswith("-")
        ]
        assert specs == [
            str(checkout / "packages" / "tapps-core"),
            f"{checkout / 'packages' / 'docs-mcp'}[treesitter]",
            f"{checkout / 'packages' / 'tapps-mcp'}[treesitter]",
        ]

    def test_installs_cpu_torch_wheels(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tapps-brain depends on sentence-transformers unconditionally, which
        pulls torch and ~4.5 GB of CUDA wheels the release env cannot use on a
        CPU host. The build must pin the PyTorch ecosystem to the CPU index."""
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        commands: list[list[str]] = []

        def _fake_run(cmd: list[str], **_kwargs: object) -> object:
            commands.append(cmd)
            if cmd[:2] == ["uv", "venv"]:
                (bg.RELEASES_DIR / "3.12.35-abc1234").mkdir(parents=True, exist_ok=True)
            return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(bg, "_run", _fake_run)
        ref = bg.ReleaseRef("3.12.35", "abc1234", bg.RELEASES_DIR / "3.12.35-abc1234")
        assert bg.build_release(checkout, ref)["ok"] is True

        install_cmd = next(c for c in commands if c[:3] == ["uv", "pip", "install"])
        assert "--torch-backend=cpu" in install_cmd


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


def _run_deploy(
    bg_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    keep_releases: int,
    reap_fn: Any,
) -> dict[str, Any]:
    """Drive deploy_blue_green end-to-end with build/smoke/fleet stubbed out.

    Only build_release, smoke_test_release, mcp_zombie_reap, fleet_control,
    and setup_generator are stubbed -- flip_current and gc_releases run for
    real against bg_home so GC-gating (TAP-6894) and protection (TAP-6895)
    are exercised, not mocked away.
    """
    releases_dir = bg_home / "releases"
    checkout = tmp_path / "checkout"
    (checkout / "packages" / "tapps-mcp").mkdir(parents=True, exist_ok=True)
    (checkout / "packages" / "tapps-mcp" / "pyproject.toml").write_text(
        '[project]\nversion = "3.12.36"\n', encoding="utf-8"
    )
    monkeypatch.setattr(bg, "_read_short_sha", lambda _c: "3333333")

    def _fake_build(
        _checkout: Path, release: bg.ReleaseRef, *, force: bool = False
    ) -> dict[str, Any]:
        _make_release(releases_dir, release.name)
        return {"ok": True, "skipped": False, "release": release.name, "path": str(release.path)}

    monkeypatch.setattr(bg, "build_release", _fake_build)
    monkeypatch.setattr(bg, "smoke_test_release", lambda *a, **k: {"ok": True, "versions": {}})
    monkeypatch.setattr(
        "tapps_mcp.distribution.mcp_zombie_reap.reap_orphan_mcp_serves",
        lambda: {"ok": True, "reaped": []},
    )
    monkeypatch.setattr("tapps_mcp.distribution.fleet_control.fleet_any_running", lambda: False)
    monkeypatch.setattr("tapps_mcp.distribution.fleet_control.reap_superseded_fleet", reap_fn)
    monkeypatch.setattr(
        "tapps_mcp.distribution.setup_generator.is_tapps_mcp_dev_monorepo",
        lambda _checkout: False,
    )
    return bg.deploy_blue_green(checkout, skip_gate=True, keep_releases=keep_releases)


class TestSupersededReapGatesGC:
    """TAP-6894: a failed superseded-fleet reap must block GC, not be swallowed."""

    def test_raising_reap_blocks_gc(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gc_spy = MagicMock(wraps=bg.gc_releases)
        monkeypatch.setattr(bg, "gc_releases", gc_spy)

        def _raising_reap() -> dict[str, Any]:
            raise RuntimeError("pidfile corrupt")

        result = _run_deploy(bg_home, tmp_path, monkeypatch, keep_releases=0, reap_fn=_raising_reap)

        # A good deploy (build/smoke/flip all succeeded) is still reported ok.
        assert result["ok"] is True
        assert result["superseded_reap"]["ok"] is False
        assert result["gc"] == {
            "ok": False,
            "skipped": True,
            "reason": "superseded_reap raised; GC blocked until reap succeeds",
        }
        # Known-negative: GC genuinely never ran -- not just "ran and kept
        # everything by coincidence."
        gc_spy.assert_not_called()

    def test_reap_with_recorded_error_blocks_gc_without_raising(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TAP-6894 follow-up: a reap that fails without raising must still gate GC."""
        gc_spy = MagicMock(wraps=bg.gc_releases)
        monkeypatch.setattr(bg, "gc_releases", gc_spy)

        result = _run_deploy(
            bg_home,
            tmp_path,
            monkeypatch,
            keep_releases=0,
            reap_fn=lambda: {
                "errors": ["1234: EPERM"],
                "superseded_pids": [1234],
                "reaped": [],
            },
        )

        assert result["ok"] is True
        assert result["superseded_reap"]["ok"] is False
        assert result["gc"] == {
            "ok": False,
            "skipped": True,
            "reason": "superseded_reap reported failure; GC blocked until reap succeeds",
        }
        # Known-negative: assert on the call itself, not a report field -- a
        # report field can read "skipped" while GC still ran underneath it.
        gc_spy.assert_not_called()

    def test_reap_with_pid_missing_from_reaped_blocks_gc(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pid absent from ``reaped`` with no recorded error is still a failure."""
        gc_spy = MagicMock(wraps=bg.gc_releases)
        monkeypatch.setattr(bg, "gc_releases", gc_spy)

        result = _run_deploy(
            bg_home,
            tmp_path,
            monkeypatch,
            keep_releases=0,
            reap_fn=lambda: {
                "superseded_pids": [1234],
                "reaped": [],
                "errors": [],
            },
        )

        assert result["ok"] is True
        assert result["superseded_reap"]["ok"] is False
        assert result["gc"]["skipped"] is True
        gc_spy.assert_not_called()

    def test_succeeding_reap_still_reaches_gc(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gc_spy = MagicMock(wraps=bg.gc_releases)
        monkeypatch.setattr(bg, "gc_releases", gc_spy)

        result = _run_deploy(
            bg_home,
            tmp_path,
            monkeypatch,
            keep_releases=3,
            reap_fn=lambda: {"superseded_pids": [], "reaped": [], "errors": []},
        )

        assert result["ok"] is True
        assert result["superseded_reap"]["ok"] is True
        # Known-positive: a succeeding reap still reaches GC, with the same
        # arguments as today -- not just "called."
        gc_spy.assert_called_once()
        assert gc_spy.call_args.kwargs["keep"] == 3
        assert gc_spy.call_args.kwargs["protect"].name == "3.12.36-3333333"
        assert gc_spy.call_args.kwargs["protect_extra"] is None
        assert result["gc"]["ok"] is True


class TestGcProtectsPreviousRelease:
    """TAP-6895: gc_releases must protect the outgoing (pre-flip) release too."""

    def test_outgoing_release_survives_index_eviction(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        releases_dir = bg_home / "releases"
        now = time.time()
        delete_target = _make_release(releases_dir, "3.12.30-0000001")
        os.utime(delete_target, (now - 400, now - 400))
        outgoing = _make_release(releases_dir, "3.12.34-1111111")
        os.utime(outgoing, (now - 300, now - 300))
        filler = _make_release(releases_dir, "3.12.35-2222222")
        os.utime(filler, (now - 200, now - 200))
        bg.flip_current(bg.ReleaseRef("3.12.34", "1111111", outgoing))

        result = _run_deploy(
            bg_home,
            tmp_path,
            monkeypatch,
            keep_releases=2,
            reap_fn=lambda: {"ok": True, "reaped": [], "errors": []},
        )

        assert result["ok"] is True
        gc = result["gc"]
        # Known-positive: outgoing (what `current` resolved to pre-flip)
        # survives even though keep=2 fills both index-kept slots with the
        # new incoming release and filler, which would otherwise evict it.
        assert outgoing.name in gc["kept"]
        assert gc["protected"][outgoing.name] == "previous"
        assert outgoing.exists()
        # Known-negative: an unprotected, un-kept, unreferenced release is
        # still deleted -- proves the fix protects specific paths, not
        # everything.
        assert delete_target.name in gc["deleted"]
        assert not delete_target.exists()
        # keep semantics unchanged for filler: kept by index, not by name.
        assert filler.name in gc["kept"]
        assert filler.name not in gc["protected"]
