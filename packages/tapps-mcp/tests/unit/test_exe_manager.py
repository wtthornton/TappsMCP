"""Tests for distribution.exe_manager (rename-then-replace exe upgrade)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution.exe_manager import (
    _choose_old_path,
    _validate_frozen,
    _validate_new_exe,
    cleanup_stale_old_exes,
    detect_stale_backups,
    replace_exe,
    run_replace_exe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_FAKE_SIZE = 10 * 1024 * 1024  # 10 MB


def _create_fake_exe(path: Path, size: int = _DEFAULT_FAKE_SIZE) -> Path:
    """Create a fake exe file of the given size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size)
    return path


# ---------------------------------------------------------------------------
# cleanup_stale_old_exes
# ---------------------------------------------------------------------------


class TestCleanupStaleOldExes:
    """Tests for startup cleanup of .old exe backups."""

    def test_noop_when_not_frozen(self) -> None:
        """Does nothing when not running as a frozen exe."""
        with patch.object(sys, "frozen", False, create=True):
            result = cleanup_stale_old_exes()
        assert result == []

    def test_cleans_old_file(self, tmp_path: Path) -> None:
        """Deletes .old file next to the running exe."""
        exe = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        old = tmp_path / "tapps-mcp.exe.old"
        old.write_bytes(b"\x00" * 100)
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            result = cleanup_stale_old_exes()
        assert len(result) == 1
        assert not old.exists()

    def test_cleans_timestamped_old_file(self, tmp_path: Path) -> None:
        """Deletes timestamped .old files."""
        exe = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        old = tmp_path / "tapps-mcp.exe.old.1708800000"
        old.write_bytes(b"\x00" * 100)
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            result = cleanup_stale_old_exes()
        assert len(result) == 1
        assert not old.exists()

    def test_skips_locked_file(self, tmp_path: Path) -> None:
        """Silently skips files that cannot be deleted."""
        exe = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        old = tmp_path / "tapps-mcp.exe.old"
        old.write_bytes(b"\x00" * 100)
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
            patch.object(Path, "unlink", side_effect=OSError("locked")),
        ):
            result = cleanup_stale_old_exes()
        assert result == []

    def test_no_old_files(self, tmp_path: Path) -> None:
        """Returns empty list when no .old files exist."""
        exe = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            result = cleanup_stale_old_exes()
        assert result == []


# ---------------------------------------------------------------------------
# detect_stale_backups
# ---------------------------------------------------------------------------


class TestDetectStaleBackups:
    """Tests for stale backup detection."""

    def test_empty_when_not_frozen(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            result = detect_stale_backups()
        assert result == []

    def test_detects_old_file(self, tmp_path: Path) -> None:
        exe = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        (tmp_path / "tapps-mcp.exe.old").write_bytes(b"\x00")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            result = detect_stale_backups()
        assert len(result) == 1

    def test_empty_when_no_old_files(self, tmp_path: Path) -> None:
        exe = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            result = detect_stale_backups()
        assert result == []


# ---------------------------------------------------------------------------
# _validate_frozen
# ---------------------------------------------------------------------------


class TestValidateFrozen:
    """Tests for frozen exe validation."""

    def test_raises_when_not_frozen(self) -> None:
        with (
            patch.object(sys, "frozen", False, create=True),
            pytest.raises(click.ClickException, match="frozen executable"),
        ):
            _validate_frozen()

    def test_returns_exe_path_when_frozen(self, tmp_path: Path) -> None:
        exe = tmp_path / "tapps-mcp.exe"
        exe.write_bytes(b"\x00")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            result = _validate_frozen()
        assert result == exe.resolve()


# ---------------------------------------------------------------------------
# _validate_new_exe
# ---------------------------------------------------------------------------


class TestValidateNewExe:
    """Tests for new exe validation."""

    def test_rejects_nonexistent_file(self, tmp_path: Path) -> None:
        current = tmp_path / "current.exe"
        with pytest.raises(click.ClickException, match="not found"):
            _validate_new_exe(tmp_path / "missing.exe", current)

    def test_rejects_same_file(self, tmp_path: Path) -> None:
        exe = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        with pytest.raises(click.ClickException, match="same file"):
            _validate_new_exe(exe, exe)

    def test_rejects_too_small(self, tmp_path: Path) -> None:
        current = tmp_path / "current.exe"
        new_exe = tmp_path / "new.exe"
        new_exe.write_bytes(b"\x00" * 100)  # 100 bytes -- too small
        with pytest.raises(click.ClickException, match="suspiciously small"):
            _validate_new_exe(new_exe, current)

    def test_rejects_non_exe_extension_on_windows(self, tmp_path: Path) -> None:
        current = tmp_path / "current.exe"
        new_file = _create_fake_exe(tmp_path / "new.bin")
        with (
            patch("tapps_mcp.distribution.exe_manager.sys.platform", "win32"),
            pytest.raises(click.ClickException, match=".exe extension"),
        ):
            _validate_new_exe(new_file, current)

    def test_accepts_valid_exe(self, tmp_path: Path) -> None:
        current = tmp_path / "current.exe"
        new_exe = _create_fake_exe(tmp_path / "new.exe")
        result = _validate_new_exe(new_exe, current)
        assert result == new_exe.resolve()


# ---------------------------------------------------------------------------
# _choose_old_path
# ---------------------------------------------------------------------------


class TestChooseOldPath:
    """Tests for backup path selection."""

    def test_default_old_suffix(self, tmp_path: Path) -> None:
        exe = tmp_path / "tapps-mcp.exe"
        result = _choose_old_path(exe)
        assert result.name == "tapps-mcp.exe.old"

    def test_removes_existing_old(self, tmp_path: Path) -> None:
        exe = tmp_path / "tapps-mcp.exe"
        old = tmp_path / "tapps-mcp.exe.old"
        old.write_bytes(b"\x00")
        result = _choose_old_path(exe)
        assert result.name == "tapps-mcp.exe.old"
        assert not old.exists()

    def test_falls_back_to_timestamp_when_locked(self, tmp_path: Path) -> None:
        exe = tmp_path / "tapps-mcp.exe"
        old = tmp_path / "tapps-mcp.exe.old"
        old.write_bytes(b"\x00")
        with patch.object(Path, "unlink", side_effect=OSError("locked")):
            result = _choose_old_path(exe)
        assert result.name.startswith("tapps-mcp.exe.old.")
        # Should have a timestamp suffix
        ts_part = result.name.split(".")[-1]
        assert ts_part.isdigit()


# ---------------------------------------------------------------------------
# replace_exe (integration)
# ---------------------------------------------------------------------------


class TestReplaceExe:
    """Tests for the core replace_exe function."""

    def test_successful_replacement(self, tmp_path: Path) -> None:
        current = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        new_exe = _create_fake_exe(tmp_path / "downloads" / "tapps-mcp-new.exe")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(current)),
        ):
            result = replace_exe(new_exe)
        assert result["status"] == "success"
        assert (tmp_path / "tapps-mcp.exe").exists()
        assert (tmp_path / "tapps-mcp.exe.old").exists()

    def test_rename_failure_reports_error(self, tmp_path: Path) -> None:
        current = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        new_exe = _create_fake_exe(tmp_path / "downloads" / "tapps-mcp-new.exe")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(current)),
            patch.object(Path, "rename", side_effect=OSError("permission denied")),
            pytest.raises(click.ClickException, match="Failed to rename"),
        ):
            replace_exe(new_exe)

    def test_copy_failure_triggers_rollback(self, tmp_path: Path) -> None:
        current = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        new_exe = _create_fake_exe(tmp_path / "downloads" / "tapps-mcp-new.exe")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(current)),
            patch(
                "tapps_mcp.distribution.exe_manager.shutil.copy2",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(click.ClickException, match="original exe has been restored"),
        ):
            replace_exe(new_exe)
        # Original file should be restored via rollback rename
        assert current.exists()

    def test_not_frozen_raises(self, tmp_path: Path) -> None:
        new_exe = _create_fake_exe(tmp_path / "new.exe")
        with (
            patch.object(sys, "frozen", False, create=True),
            pytest.raises(click.ClickException, match="frozen executable"),
        ):
            replace_exe(new_exe)


# ---------------------------------------------------------------------------
# run_replace_exe (CLI wrapper)
# ---------------------------------------------------------------------------


class TestRunReplaceExe:
    """Tests for the CLI entry point wrapper."""

    def test_success_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        current = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        new_exe = _create_fake_exe(tmp_path / "downloads" / "tapps-mcp-new.exe")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(current)),
        ):
            ok = run_replace_exe(str(new_exe))
        assert ok is True
        captured = capsys.readouterr()
        assert "replaced successfully" in captured.out
        assert "Next steps" in captured.out


# ---------------------------------------------------------------------------
# CLI integration (Click CliRunner)
# ---------------------------------------------------------------------------


class TestCliReplaceExe:
    """Tests for the replace-exe CLI command."""

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["replace-exe", "--help"])
        assert result.exit_code == 0
        assert "Replace the running exe" in result.output

    def test_missing_argument(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["replace-exe"])
        assert result.exit_code != 0

    def test_nonexistent_file(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["replace-exe", "/nonexistent/path/tapps-mcp.exe"])
        assert result.exit_code != 0

    def test_successful_via_cli(self, tmp_path: Path) -> None:
        current = _create_fake_exe(tmp_path / "tapps-mcp.exe")
        new_exe = _create_fake_exe(tmp_path / "downloads" / "tapps-mcp-new.exe")
        runner = CliRunner()
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(current)),
        ):
            result = runner.invoke(main, ["replace-exe", str(new_exe)])
        assert result.exit_code == 0
        assert "replaced successfully" in result.output

    def test_not_frozen_via_cli(self, tmp_path: Path) -> None:
        new_exe = _create_fake_exe(tmp_path / "new.exe")
        runner = CliRunner()
        with patch.object(sys, "frozen", False, create=True):
            result = runner.invoke(main, ["replace-exe", str(new_exe)])
        assert result.exit_code != 0
        assert "frozen" in result.output
