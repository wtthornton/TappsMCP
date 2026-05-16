"""TAP-1794: SecretScanner.scan_file must NOT silently pass on read errors.

A file the scanner could not read (OSError / PermissionError) used to come
back as ``SecretScanResult(scanned_files=0)`` with the default ``passed=True``
— callers had no way to distinguish "scanner ran and found nothing" from
"scanner could not see the file." Now the result carries an explicit
``error`` and ``passed=False``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_core.security.secret_scanner import SecretScanner


@pytest.fixture
def scanner() -> SecretScanner:
    return SecretScanner()


def test_oserror_returns_passed_false_with_error(
    scanner: SecretScanner, tmp_path: Path
) -> None:
    target = tmp_path / "unreadable.py"
    target.write_text("x = 1\n", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=OSError("simulated read failure")):
        result = scanner.scan_file(str(target))

    assert result.passed is False, "read errors must NOT report passed=True"
    assert result.error == "simulated read failure"
    assert result.scanned_files == 0
    assert result.findings == []


def test_permission_error_returns_passed_false_with_error(
    scanner: SecretScanner, tmp_path: Path
) -> None:
    target = tmp_path / "no-perm.py"
    target.write_text("x = 1\n", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=PermissionError("permission denied")):
        result = scanner.scan_file(str(target))

    assert result.passed is False
    assert result.error == "permission denied"


def test_read_error_logs_warning(
    scanner: SecretScanner,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=OSError("simulated")):
        scanner.scan_file(str(target))

    out, err = capsys.readouterr()
    combined = out + err
    assert "secret_scan_read_failed" in combined, (
        f"read failure must emit a WARNING log entry; captured:\n{combined!r}"
    )


def test_real_chmod_000_file_returns_error(scanner: SecretScanner, tmp_path: Path) -> None:
    """End-to-end: a 000-permission file produces the error path (skip on Windows)."""
    import os
    import sys

    if sys.platform == "win32":
        pytest.skip("chmod 000 not enforced on Windows")
    if os.geteuid() == 0:
        pytest.skip("root can read 000-permission files")

    target = tmp_path / "locked.py"
    target.write_text("x = 1\n", encoding="utf-8")
    target.chmod(0o000)
    try:
        result = scanner.scan_file(str(target))
    finally:
        target.chmod(0o644)

    assert result.passed is False
    assert result.error is not None
    assert result.scanned_files == 0


def test_clean_file_still_passes(scanner: SecretScanner, tmp_path: Path) -> None:
    """Sanity: the happy path is unchanged — clean file still passes with no error."""
    target = tmp_path / "clean.py"
    target.write_text("x = 1\n", encoding="utf-8")
    result = scanner.scan_file(str(target))
    assert result.passed is True
    assert result.error is None
    assert result.scanned_files == 1
