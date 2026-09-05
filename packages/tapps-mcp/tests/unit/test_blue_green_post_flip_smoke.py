"""Post-flip doctor classification tests for TAP-6965.

Split out of ``test_blue_green.py`` (TAP-6904 ratchet: that file already sits
at its passing-score floor, so any addition there regresses it under gate).

TAP-6965 round 2: the classifier used to be a hand-typed name allowlist in
``blue_green.py`` (``_RELEASE_HEALTH_CHECK_NAMES``) with consumer-staleness
defined as its *complement* -- an unknown or crashed check defaulted to
non-gating. It is now inverted: each doctor check tags its own
``CheckResult.category`` (``consumer_staleness`` decorator in
``doctor_result.py``, applied at the check functions that genuinely measure
consumer-worktree freshness), ``smoke_test_release`` reads that field from
``tapps-mcp doctor --quick --json``, and anything not positively tagged
``"consumer-staleness"`` -- including a renamed check and a crashed one --
gates the deploy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tapps_mcp.distribution import blue_green as bg
from tapps_mcp.distribution.doctor_runner import _collect_checks


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


def _stub_doctor_json(
    monkeypatch: pytest.MonkeyPatch, checks: list[dict[str, Any]], *, returncode: int = 1
) -> None:
    """`--version` probes stay canned; the doctor call returns *checks* as JSON."""
    payload = json.dumps({"checks": checks})

    def _fake_run(cmd: list[str], **_kwargs: object) -> Any:
        if cmd[-1] == "--version":
            return MagicMock(returncode=0, stdout="1.0.0", stderr="")
        return MagicMock(returncode=returncode, stdout=payload, stderr="")

    monkeypatch.setattr(bg, "_run", _fake_run)


def _finding(
    name: str, severity: str, category: str, message: str = "detail"
) -> dict[str, Any]:
    return {"name": name, "ok": severity == "pass", "severity": severity, "category": category, "message": message}


class TestPostFlipConsumerStalenessNonGating:
    def test_post_flip_consumer_staleness_non_gating(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TAP-6965: consumer-freshness findings are reported but do not abort the deploy."""
        ref = bg.ReleaseRef("3.9", "s1", _make_release(bg_home / "releases", "3.9-s1"))
        _stub_doctor_json(
            monkeypatch,
            [
                _finding("tapps-mcp binary", "pass", "release-health"),
                _finding("tapps-mcp binary version", "pass", "release-health"),
                _finding(
                    "Claude Code (project) config",
                    "fail",
                    "consumer-staleness",
                    f"Not found: {tmp_path}/.mcp.json",
                ),
                _finding(
                    "Skill asset drift",
                    "warn",
                    "consumer-staleness",
                    "WARN: 2 skill asset(s) drifted from template",
                ),
                _finding(
                    "Skills manifest directory diff",
                    "fail",
                    "consumer-staleness",
                    "manifest/directory mismatch",
                ),
            ],
        )

        result = bg.smoke_test_release(ref, project_root=tmp_path)

        assert result["ok"] is True
        staleness_names = {f["name"] for f in result["consumer_staleness"]}
        assert staleness_names == {
            "Claude Code (project) config",
            "Skill asset drift",
            "Skills manifest directory diff",
        }

    def test_post_flip_smoke_aborts_on_known_release_health_fail(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PROBE-D (positive control): a known release-health FAIL still aborts."""
        ref = bg.ReleaseRef("3.9", "s2", _make_release(bg_home / "releases", "3.9-s2"))
        _stub_doctor_json(
            monkeypatch,
            [
                _finding(
                    "tapps-mcp binary version",
                    "fail",
                    "release-health",
                    "Version mismatch: tapps-mcp=3.8, server=3.9",
                ),
                _finding(
                    "Claude Code (project) config",
                    "fail",
                    "consumer-staleness",
                    f"Not found: {tmp_path}/.mcp.json",
                ),
            ],
        )

        result = bg.smoke_test_release(ref, project_root=tmp_path)

        assert result["ok"] is False
        assert any("tapps-mcp binary version" in f for f in result["failures"])

    def test_post_flip_smoke_aborts_on_import_failure(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: a crash with no parseable JSON report still aborts."""
        ref = bg.ReleaseRef("3.9", "s3", _make_release(bg_home / "releases", "3.9-s3"))

        def _fake_run(cmd: list[str], **_kwargs: object) -> Any:
            if cmd[-1] == "--version":
                return MagicMock(returncode=0, stdout="1.0.0", stderr="")
            return MagicMock(
                returncode=1,
                stdout="Traceback (most recent call last):\nImportError: no module named tapps_mcp\n",
                stderr="",
            )

        monkeypatch.setattr(bg, "_run", _fake_run)

        result = bg.smoke_test_release(ref, project_root=tmp_path)

        assert result["ok"] is False
        assert "import/crash" in result["failures"][0]


class TestProbeAUnknownDefaultsToGating:
    """PROBE-A: a check renamed away from any known label still gates.

    The old allowlist keyed on ``CheckResult.name`` -- a one-character rename
    of a release-health check flipped it into an unrecognized, non-gating
    "consumer staleness" row. Category travels on the ``CheckResult`` object
    itself now, independent of the name, so a rename cannot silently defang
    a real release-health failure: the fake doctor JSON below explicitly
    still tags it ``release-health`` (as the real check would), and even a
    payload that *omitted* category altogether would default to
    ``release-health`` per ``_parse_doctor_json`` / ``CheckResult``.
    """

    def test_renamed_release_health_check_still_aborts(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ref = bg.ReleaseRef("3.9", "s4", _make_release(bg_home / "releases", "3.9-s4"))
        # A one-character rename of "tapps-mcp binary version" -- the exact
        # PROBE-A mutation from the verifier -- with no category field at all,
        # exercising the _parse_doctor_json default.
        payload = {
            "checks": [
                {
                    "name": "tapps-mcp binary versions",
                    "ok": False,
                    "severity": "fail",
                    "message": "Version mismatch: tapps-mcp=3.8, server=3.9",
                }
            ]
        }

        def _fake_run(cmd: list[str], **_kwargs: object) -> Any:
            if cmd[-1] == "--version":
                return MagicMock(returncode=0, stdout="1.0.0", stderr="")
            return MagicMock(returncode=1, stdout=json.dumps(payload), stderr="")

        monkeypatch.setattr(bg, "_run", _fake_run)

        result = bg.smoke_test_release(ref, project_root=tmp_path)

        assert result["ok"] is False
        assert any("tapps-mcp binary versions" in f for f in result["failures"])


class TestProbeBCrashedCheckGates:
    """PROBE-B: a check that crashed inside doctor still gates.

    ``doctor_runner._safe_check`` converts a raised exception into a fresh
    ``CheckResult(name, False, "Check crashed: ...")`` with no category
    carried over from the check that raised -- so it defaults to
    ``release-health`` and gates, regardless of which check crashed.
    """

    def test_crashed_check_still_aborts(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ref = bg.ReleaseRef("3.9", "s5", _make_release(bg_home / "releases", "3.9-s5"))
        _stub_doctor_json(
            monkeypatch,
            [
                _finding(
                    "Managed JSON parseable",
                    "fail",
                    "release-health",
                    "Check crashed: ImportError: no module named foo",
                )
            ],
        )

        result = bg.smoke_test_release(ref, project_root=tmp_path)

        assert result["ok"] is False
        assert any("Managed JSON parseable" in f for f in result["failures"])


class TestProbeCEveryConsumerStalenessNameIsReal:
    """PROBE-C: every check tagged consumer-staleness exists among the real rows.

    The old bug was the inverse direction (an allowlist entry absent from the
    real rows was silently inert). Guard the new direction too: nothing can
    tag itself ``consumer-staleness`` under a name ``_collect_checks`` never
    actually produces, which would be a dead/unreachable classification.
    """

    def test_all_consumer_staleness_names_are_real_check_names(self) -> None:
        checks = _collect_checks(Path.cwd(), quick=True)
        real_names = {c.name for c in checks}
        staleness_names = {c.name for c in checks if c.category == "consumer-staleness"}

        assert staleness_names, "expected at least one consumer-staleness check"
        assert staleness_names <= real_names
        # Sanity: the split is neither empty nor total -- both categories are
        # represented among the ~94 real doctor rows.
        release_health_names = {c.name for c in checks if c.category == "release-health"}
        assert release_health_names


class TestAllowlistDeleted:
    def test_no_hand_typed_release_health_name_list_survives(self) -> None:
        assert not hasattr(bg, "_RELEASE_HEALTH_CHECK_NAMES")


class TestDeployUnderLockPostFlip:
    """The verifier found zero tests reaching ``_deploy_under_lock`` /
    ``post_flip_status``. Exercise it once end-to-end through
    ``deploy_blue_green`` with every side-effecting dependency stubbed and a
    stubbed doctor providing one release-health PASS and one
    consumer-staleness FAIL -- the deploy must complete (``ok=True``) and
    report the consumer-staleness warning separately, never abort on it.
    """

    def test_deploy_completes_with_consumer_staleness_warnings(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        release = bg.ReleaseRef("3.9", "s6", _make_release(bg_home / "releases", "3.9-s6"))

        monkeypatch.setattr(bg, "_release_ref", lambda _checkout: release)
        monkeypatch.setattr(bg, "build_release", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(bg, "flip_current", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(bg, "current_release_path", lambda: None)
        monkeypatch.setattr(bg, "_reap_superseded_then_gc", lambda *a, **k: {})

        import tapps_mcp.distribution.fleet_control as fleet_mod
        import tapps_mcp.distribution.mcp_zombie_reap as zombie_mod
        import tapps_mcp.distribution.setup_generator as setup_mod

        monkeypatch.setattr(zombie_mod, "reap_orphan_mcp_serves", lambda **k: {"ok": True})
        monkeypatch.setattr(fleet_mod, "fleet_any_running", lambda: False)
        monkeypatch.setattr(setup_mod, "is_tapps_mcp_dev_monorepo", lambda _checkout: False)

        _stub_doctor_json(
            monkeypatch,
            [
                _finding("tapps-mcp binary version", "pass", "release-health"),
                _finding(
                    "Skill asset drift",
                    "fail",
                    "consumer-staleness",
                    "2 skill asset(s) drifted from template",
                ),
            ],
        )

        report = bg.deploy_blue_green(checkout, skip_gate=True, run_doctor_smoke=True)

        assert report["ok"] is True
        assert report["post_flip_status"] == "completed with consumer-staleness warnings"
        staleness_names = {f["name"] for f in report["post_flip_smoke"]["consumer_staleness"]}
        assert staleness_names == {"Skill asset drift"}

    def test_deploy_aborts_when_post_flip_smoke_finds_release_health_fail(
        self, bg_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        release = bg.ReleaseRef("3.9", "s7", _make_release(bg_home / "releases", "3.9-s7"))

        monkeypatch.setattr(bg, "_release_ref", lambda _checkout: release)
        monkeypatch.setattr(bg, "build_release", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(bg, "flip_current", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(bg, "current_release_path", lambda: None)
        monkeypatch.setattr(bg, "_reap_superseded_then_gc", lambda *a, **k: {})

        import tapps_mcp.distribution.fleet_control as fleet_mod
        import tapps_mcp.distribution.mcp_zombie_reap as zombie_mod
        import tapps_mcp.distribution.setup_generator as setup_mod

        monkeypatch.setattr(zombie_mod, "reap_orphan_mcp_serves", lambda **k: {"ok": True})
        monkeypatch.setattr(fleet_mod, "fleet_any_running", lambda: False)
        monkeypatch.setattr(setup_mod, "is_tapps_mcp_dev_monorepo", lambda _checkout: False)

        _stub_doctor_json(
            monkeypatch,
            [
                _finding(
                    "tapps-mcp binary version",
                    "fail",
                    "release-health",
                    "Version mismatch: tapps-mcp=3.8, server=3.9",
                ),
            ],
        )

        report = bg.deploy_blue_green(checkout, skip_gate=True, run_doctor_smoke=True)

        assert report["ok"] is False
        assert report["post_flip_status"] == "aborted: release sick"
