"""Post-flip doctor classification tests for TAP-6965.

Split out of ``test_blue_green.py`` (TAP-6904 ratchet: that file already sits
at its passing-score floor, so any addition there regresses it under gate).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tapps_mcp.distribution import blue_green as bg


@pytest.fixture
def bg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect blue/green paths to a temp home."""
    home = tmp_path / "tapps-mcp-home"
    releases = home / "releases"
    monkeypatch.setattr(bg, "TAPPS_MCP_HOME", home)
    monkeypatch.setattr(bg, "RELEASES_DIR", releases)
    monkeypatch.setattr(bg, "CURRENT_LINK", home / "current")
    monkeypatch.setattr(bg, "DEPLOY_LOCK", home / ".deploy.lock")
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


def _stub_doctor_report(monkeypatch: pytest.MonkeyPatch, stdout: str) -> None:
    """`--version` probes stay canned; the doctor call returns *stdout* at exit 1."""

    def _fake_run(cmd: list[str], **_kwargs: object) -> Any:
        if cmd[-1] == "--version":
            return MagicMock(returncode=0, stdout="1.0.0", stderr="")
        return MagicMock(returncode=1, stdout=stdout, stderr="")

    monkeypatch.setattr(bg, "_run", _fake_run)


class TestPostFlipConsumerStalenessNonGating:
    def test_post_flip_consumer_staleness_non_gating(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TAP-6965: consumer-freshness findings are reported but do not abort the deploy.

        Real doctor check rows (the names doctor_mcp.py / doctor_skills.py
        register), fed through the classifier as the actual ``doctor --quick``
        stdout a worktree lacking ``.mcp.json`` would produce -- this is not a
        mocked ``ok=False`` shortcut.
        """
        ref = bg.ReleaseRef("3.9", "s1", _make_release(bg_home / "releases", "3.9-s1"))
        _stub_doctor_report(
            monkeypatch,
            "  PASS  tapps-mcp binary: tapps-mcp is on PATH\n"
            "  PASS  tapps-mcp binary version: tapps-mcp binary and server versions match\n"
            f"  FAIL  Claude Code (project): Not found: {tmp_path}/.mcp.json\n"
            "  WARN  Skill asset drift: WARN: 2 skill asset(s) drifted from template\n"
            "  FAIL  Skills manifest directory diff: manifest/directory mismatch\n",
        )

        result = bg.smoke_test_release(ref, project_root=tmp_path)

        assert result["ok"] is True
        staleness_names = {f["name"] for f in result["consumer_staleness"]}
        assert staleness_names == {
            "Claude Code (project)",
            "Skill asset drift",
            "Skills manifest directory diff",
        }

    def test_post_flip_smoke_aborts_on_version_skew(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: a genuinely sick release (version skew) still aborts."""
        ref = bg.ReleaseRef("3.9", "s2", _make_release(bg_home / "releases", "3.9-s2"))
        _stub_doctor_report(
            monkeypatch,
            "  FAIL  tapps-mcp binary version: Version mismatch: "
            "tapps-mcp=3.8, server=3.9\n"
            f"  FAIL  Claude Code (project): Not found: {tmp_path}/.mcp.json\n",
        )

        result = bg.smoke_test_release(ref, project_root=tmp_path)

        assert result["ok"] is False
        assert any("tapps-mcp binary version" in f for f in result["failures"])

    def test_post_flip_smoke_aborts_on_import_failure(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: a crash with no parseable report still aborts."""
        ref = bg.ReleaseRef("3.9", "s3", _make_release(bg_home / "releases", "3.9-s3"))
        _stub_doctor_report(
            monkeypatch,
            "Traceback (most recent call last):\nImportError: no module named tapps_mcp\n",
        )

        result = bg.smoke_test_release(ref, project_root=tmp_path)

        assert result["ok"] is False
        assert "import/crash" in result["failures"][0]
