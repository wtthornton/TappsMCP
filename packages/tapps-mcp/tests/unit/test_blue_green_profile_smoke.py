"""Pre-flip profile smoke tests for TAP-7234.

``smoke_test_release`` only ever checked that the release's binaries exist and
run ``--version`` -- it never imported ``server.py``, so a broken tool
registration (release 3.12.84's missing ``TOOL_DESCRIPTIONS`` entry) was
invisible until the *post-flip* fleet restart, by which point ``current``
already pointed at the broken release. ``pre_flip_profile_smoke`` starts every
``_NLT_TAPPS_TOOL_PRESETS`` profile from the release's own binary on a scratch
port and runs the same MCP handshake the shared HTTP fleet uses, so a broken
registration is caught before ``flip_current`` runs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tapps_mcp.distribution import blue_green as bg
from tapps_mcp.distribution import blue_green_profile_smoke as bgps
from tapps_mcp.server import _NLT_TAPPS_TOOL_PRESETS


def _write_release(tmp_path: Path, *, drop_tool: str | None) -> bg.ReleaseRef:
    """A release whose ``bin/tapps-mcp`` runs the real CLI from this venv.

    *drop_tool* pops a real entry out of the live ``TOOL_DESCRIPTIONS`` dict
    before ``tapps_mcp.cli`` (and therefore ``server.py``) is ever imported in
    the child process -- the exact 3.12.84 failure shape: ``register_tool``
    raises ``KeyError`` for real, at real module-import time, in a real
    subprocess. Nothing here fakes the ``ok: false`` verdict itself.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    script = bin_dir / "tapps-mcp"
    corruption = ""
    if drop_tool is not None:
        corruption = (
            "import tapps_mcp.tool_descriptions as _td\n"
            f"_td.TOOL_DESCRIPTIONS.pop({drop_tool!r}, None)\n"
        )
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"{corruption}"
        "from tapps_mcp.cli import main\n"
        "sys.exit(main())\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return bg.ReleaseRef(version="0.0.0", short_sha="test", path=tmp_path)


class TestPreFlipProfileSmokeIntactRelease:
    @pytest.mark.live_network
    def test_every_preset_reports_ok_with_tools(self, tmp_path: Path) -> None:
        release = _write_release(tmp_path, drop_tool=None)
        result = bgps.pre_flip_profile_smoke(release, project_root=tmp_path, timeout=60.0)

        assert result["ok"] is True, result
        assert set(result["profiles"]) == set(_NLT_TAPPS_TOOL_PRESETS)
        for profile, row in result["profiles"].items():
            assert row["ok"] is True, (profile, row)
            assert row["tool_count"] > 0, (profile, row)
            assert row["profile"] == profile
            assert isinstance(row["elapsed_s"], float)


class TestPreFlipProfileSmokeBrokenRegistration:
    @pytest.mark.live_network
    def test_missing_tool_descriptions_entry_reports_ok_false_naming_the_profile(
        self, tmp_path: Path
    ) -> None:
        # tapps_session_start is eagerly registered outside the frozenset-based
        # filter for the three canonical presets (nlt-build/-memory/-setup);
        # their nlt-code-quality/nlt-platform-admin aliases don't register it
        # and are unaffected -- this asserts the real, profile-specific shape
        # rather than assuming every preset shares one tool.
        release = _write_release(tmp_path, drop_tool="tapps_session_start")
        result = bgps.pre_flip_profile_smoke(release, project_root=tmp_path, timeout=60.0)

        assert result["ok"] is False, result
        assert set(result["profiles"]) == set(_NLT_TAPPS_TOOL_PRESETS)
        expected_broken = {"nlt-build", "nlt-memory", "nlt-setup"}
        for profile in expected_broken:
            row = result["profiles"][profile]
            assert row["ok"] is False, (profile, row)
            assert row["profile"] == profile
            assert "KeyError" in row["error"] or "tapps_session_start" in row["error"], row


class TestDeployUnderLockNeverFlipsOnProfileSmokeFailure:
    """``flip_current`` must never run once the profile smoke reports ok: false."""

    def test_flip_current_not_called_when_profile_smoke_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        release = bg.ReleaseRef(version="1.2.3", short_sha="abc1234", path=tmp_path / "release")
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        monkeypatch.setattr(bg, "build_release", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(
            bg, "smoke_test_release", lambda *a, **k: {"ok": True, "versions": {}}
        )
        monkeypatch.setattr(
            "tapps_mcp.distribution.mcp_zombie_reap.reap_orphan_mcp_serves",
            lambda *a, **k: {"ok": True, "reaped": []},
        )
        failing_smoke = {
            "ok": False,
            "profiles": {
                "nlt-build": {
                    "ok": False,
                    "profile": "nlt-build",
                    "error": "process exited with code 1: KeyError",
                    "tool_count": 0,
                    "elapsed_s": 0.5,
                }
            },
        }
        monkeypatch.setattr(bgps, "pre_flip_profile_smoke", lambda *a, **k: failing_smoke)
        flip_mock = MagicMock(side_effect=AssertionError("flip_current must not be called"))
        monkeypatch.setattr(bg, "flip_current", flip_mock)

        report = bg._deploy_under_lock(
            checkout,
            release,
            {},
            force_build=False,
            keep_releases=3,
            run_doctor_smoke=False,
        )

        assert flip_mock.call_count == 0
        assert report["ok"] is False
        assert report["pre_flip_profile_smoke"] == failing_smoke
        assert "flip" not in report
