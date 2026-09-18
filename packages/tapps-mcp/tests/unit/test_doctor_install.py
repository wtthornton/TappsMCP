"""Smoke tests for tapps_mcp.distribution.doctor_install (TAP-5606 split)."""

from __future__ import annotations

from unittest.mock import patch

from tapps_mcp.common.models import InstallDriftDiagnostic, InstallDriftEntry
from tapps_mcp.distribution.doctor_install import (
    check_binary_on_path,
    check_blue_green_deploy,
    check_global_local_install,
)


class TestCheckBinaryOnPath:
    def test_found_on_path(self) -> None:
        with patch(
            "tapps_mcp.distribution.doctor_install.shutil.which",
            return_value="/usr/bin/tapps-mcp",
        ):
            result = check_binary_on_path()
        assert result.ok is True
        assert "PATH" in result.message

    def test_missing_from_path(self) -> None:
        with patch("tapps_mcp.distribution.doctor_install.shutil.which", return_value=None):
            result = check_binary_on_path()
        assert result.ok is False
        assert "not found" in result.message


class TestCheckBlueGreenDeploy:
    def test_not_configured_passes(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        with (
            patch(
                "tapps_mcp.distribution.blue_green.current_release_path",
                return_value=None,
            ),
            patch("tapps_mcp.distribution.blue_green.RELEASES_DIR", tmp_path / "no-such-dir"),
        ):
            result = check_blue_green_deploy()
        assert result.ok is True
        assert "Not configured" in result.message


def _no_drift_diagnostic() -> InstallDriftDiagnostic:
    return InstallDriftDiagnostic(drift_detected=False, entries=[])


class TestCheckGlobalLocalInstall:
    def test_blue_green_active_passes(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        with (
            patch(
                "tapps_mcp.diagnostics.check_install_drift",
                return_value=_no_drift_diagnostic(),
            ),
            patch(
                "tapps_mcp.distribution.blue_green.current_release_path",
                return_value=tmp_path,
            ),
        ):
            result = check_global_local_install()
        assert result.ok is True
        assert "Blue/green" in result.message

    def test_unmerged_worktree_fails_even_with_blue_green_active(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """TAP-7847: hooks call PATH directly, so a blue/green release being active
        must not mask a stale/unmerged global CLI on PATH."""
        drift = InstallDriftDiagnostic(
            drift_detected=True,
            entries=[
                InstallDriftEntry(
                    binary="tapps-mcp",
                    binary_path="/fake/tapps-mcp",
                    binary_version="3.12.90",
                    source_version="3.12.90",
                    drifted=True,
                    from_local_source=True,
                    install_source="/home/wtthornton/wt/tmcp-p2-prefix/packages/tapps-mcp",
                    install_head_sha="ac81e331",
                    install_branch="lane/tmcp-p2-prefix",
                    install_head_contained_in_default=False,
                )
            ],
            remediation_hint="unmerged worktree",
        )
        with (
            patch("tapps_mcp.diagnostics.check_install_drift", return_value=drift),
            patch(
                "tapps_mcp.distribution.blue_green.current_release_path",
                return_value=tmp_path,
            ),
        ):
            result = check_global_local_install()
        assert result.ok is False
        assert "UNMERGED" in result.message
        assert "lane/tmcp-p2-prefix" in result.message
        assert "tmcp-p2-prefix" in result.message

    def test_local_but_merged_still_warns_not_fails(self) -> None:
        drift = InstallDriftDiagnostic(
            drift_detected=False,
            entries=[
                InstallDriftEntry(
                    binary="tapps-mcp",
                    binary_path="/fake/tapps-mcp",
                    binary_version="3.12.90",
                    source_version="3.12.90",
                    drifted=False,
                    from_local_source=True,
                    install_source="/home/wtthornton/code/tapps-mcp/packages/tapps-mcp",
                    install_head_sha="deadbeef",
                    install_branch="master",
                    install_head_contained_in_default=True,
                )
            ],
        )
        with (
            patch("tapps_mcp.diagnostics.check_install_drift", return_value=drift),
            patch(
                "tapps_mcp.distribution.blue_green.current_release_path",
                return_value=None,
            ),
        ):
            result = check_global_local_install()
        assert result.ok is True
        assert "WARN" in result.message
