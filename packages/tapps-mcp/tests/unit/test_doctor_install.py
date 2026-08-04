"""Smoke tests for tapps_mcp.distribution.doctor_install (TAP-5606 split)."""

from __future__ import annotations

from unittest.mock import patch

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


class TestCheckGlobalLocalInstall:
    def test_blue_green_active_passes(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        with patch(
            "tapps_mcp.distribution.blue_green.current_release_path",
            return_value=tmp_path,
        ):
            result = check_global_local_install()
        assert result.ok is True
        assert "Blue/green" in result.message
