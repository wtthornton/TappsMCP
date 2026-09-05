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

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tapps_mcp.distribution import blue_green as bg
from tapps_mcp.distribution import doctor_runner
from tapps_mcp.distribution.doctor_result import CheckResult
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


def _resolve_check_fn(fn: Callable[[], CheckResult]) -> Callable[..., CheckResult]:
    """Unwrap a ``_check_specs`` entry down to the real ``check_*`` function.

    Most entries are ``lambda: check_x(root)`` (or ``_cb.check_x(root)`` for
    the two submodules imported locally into ``_check_specs``) so the marker
    lives on the callable *inside* the closure, not on the lambda itself.
    ``inspect.getclosurevars`` resolves both plain globals (``check_x``) and
    attribute lookups off a closed-over module (``_cb.check_x``) via
    ``co_names``.
    """
    if getattr(fn, "__name__", "") != "<lambda>":
        return fn

    closure = inspect.getclosurevars(fn)
    candidates: list[Callable[..., CheckResult]] = []
    for used_name in fn.__code__.co_names:
        if not used_name.startswith("check_"):
            continue
        if used_name in closure.globals:
            candidates.append(closure.globals[used_name])
        for nonlocal_value in closure.nonlocals.values():
            attr = getattr(nonlocal_value, used_name, None)
            if callable(attr):
                candidates.append(attr)

    if len(candidates) != 1:
        msg = (
            f"could not uniquely resolve the check function backing spec lambda "
            f"(co_names={fn.__code__.co_names!r}, candidates={candidates!r})"
        )
        raise AssertionError(msg)
    return candidates[0]


def _assert_categories_match_decorator_markers(root: Path, *, quick: bool = True) -> None:
    """Derived guard (TAP-6965 round 2): category follows the decorator, not a list.

    Walks every ``(display name, check fn)`` pair ``doctor_runner._check_specs``
    registers, resolves each to its real ``check_*`` function, and partitions
    by whether ``consumer_staleness`` stamped it with ``__tapps_category__``.
    Then runs the real doctor on *root* and asserts: every marker-carrying
    check produced a ``consumer-staleness`` row, every non-marked check did
    not, and the two counts line up -- all derived from the decorator at call
    time, never a hand-typed name or count.
    """
    specs = doctor_runner._check_specs(root, quick=quick)
    checks = doctor_runner._collect_checks(root, quick=quick)
    # `_collect_checks` runs `specs` in order, then appends extra rows (the
    # quick-mode "Quality tools" stub, or the full quality-tools set) that
    # have no corresponding spec -- so only the first len(specs) results
    # align positionally.
    aligned = list(zip(specs, checks[: len(specs)], strict=True))

    mismatches: list[str] = []
    marked_count = 0
    for (display_name, fn), result in aligned:
        underlying = _resolve_check_fn(fn)
        is_marked = getattr(underlying, "__tapps_category__", None) == "consumer-staleness"
        if is_marked:
            marked_count += 1
            if result.category != "consumer-staleness":
                mismatches.append(
                    f"{display_name}: marked @consumer_staleness but produced "
                    f"category={result.category!r}"
                )
        elif result.category == "consumer-staleness":
            mismatches.append(
                f"{display_name}: produced category='consumer-staleness' but has no "
                f"@consumer_staleness marker"
            )

    if mismatches:
        raise AssertionError("; ".join(mismatches))

    actual_staleness_count = sum(1 for r in checks if r.category == "consumer-staleness")
    assert actual_staleness_count == marked_count, (
        f"consumer-staleness row count ({actual_staleness_count}) != "
        f"marker-carrying check count ({marked_count})"
    )


class TestDerivedConsumerStalenessGuard:
    """Replaces the PROBE-C tautology.

    ``staleness_names <= real_names`` was vacuously true by construction
    (both sides came from the same list) and could never fail. This derives
    the expected category from the decorator itself and asserts it against
    what the real doctor actually produced.
    """

    def test_categories_match_decorator_markers(self) -> None:
        _assert_categories_match_decorator_markers(Path.cwd(), quick=True)

    def test_negative_control_missing_marker_is_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proves the guard can fail: strip one check's marker, expect a named failure.

        Simulates the round-1 verifier's exact scenario -- a merge silently
        dropping ``@consumer_staleness`` from ``check_upgrade_skip_token_drift``
        -- by removing just the marker attribute the guard reads. The
        decorator's runtime behavior (setting ``result.category``) is
        untouched, so this creates the same "unmarked but still produces
        consumer-staleness" mismatch a real dropped decorator would, and the
        guard must name the offending check rather than pass silently the way
        the old tautology would have.
        """
        target = doctor_runner.check_upgrade_skip_token_drift
        monkeypatch.delattr(target, "__tapps_category__")

        with pytest.raises(AssertionError, match="upgrade_skip_files drift"):
            _assert_categories_match_decorator_markers(Path.cwd(), quick=True)


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
