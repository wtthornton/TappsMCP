"""TAP-1794: run_security_scan must surface secret-scan read errors."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_core.security.secret_scanner import SecretScanResult
from tapps_mcp.security.security_scanner import run_security_scan


def test_aggregated_summary_surfaces_secret_scan_error(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")

    error_result = SecretScanResult(scanned_files=0, passed=False, error="simulated")

    with patch(
        "tapps_mcp.security.security_scanner.SecretScanner.scan_file",
        return_value=error_result,
    ):
        agg = run_security_scan(str(target), scan_secrets=True)

    assert agg.secret_scan_error == "simulated"
    assert agg.passed is False, (
        "TAP-1794: a secret-scan read error must fail the aggregated gate"
    )


def test_no_secret_error_means_passed_drives_on_findings(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")

    # Default SecretScanResult: passed=True, error=None.
    clean = SecretScanResult()
    with patch(
        "tapps_mcp.security.security_scanner.SecretScanner.scan_file",
        return_value=clean,
    ):
        agg = run_security_scan(str(target), scan_secrets=True)

    assert agg.secret_scan_error is None
    assert agg.passed is True


def test_scan_secrets_disabled_leaves_error_none(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")

    agg = run_security_scan(str(target), scan_secrets=False)
    assert agg.secret_scan_error is None
