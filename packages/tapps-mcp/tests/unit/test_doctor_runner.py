"""Smoke tests for tapps_mcp.distribution.doctor_runner (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_result import CheckResult
from tapps_mcp.distribution.doctor_runner import (
    _collect_checks,
    _safe_check,
    run_doctor_structured,
)


def test_safe_check_returns_fn_result_on_success() -> None:
    result = _safe_check("demo", lambda: CheckResult("demo", True, "ok"))
    assert result.ok is True
    assert result.name == "demo"


def test_safe_check_converts_crash_to_failed_result() -> None:
    def _boom() -> CheckResult:
        raise RuntimeError("kaboom")

    result = _safe_check("demo", _boom)
    assert result.ok is False
    assert "kaboom" in result.message


def test_collect_checks_returns_nonempty_list(tmp_path: Path) -> None:
    checks = _collect_checks(tmp_path, quick=True)
    assert isinstance(checks, list)
    assert len(checks) > 20
    assert all(isinstance(c, CheckResult) for c in checks)


def test_run_doctor_structured_shape(tmp_path: Path) -> None:
    result = run_doctor_structured(project_root=str(tmp_path), quick=True)
    assert "checks" in result
    assert "pass_count" in result
    assert "fail_count" in result
    assert "all_passed" in result
    assert result["quick_mode"] is True
    assert result["pass_count"] + result["fail_count"] + result["warn_count"] == len(
        result["checks"]
    )
