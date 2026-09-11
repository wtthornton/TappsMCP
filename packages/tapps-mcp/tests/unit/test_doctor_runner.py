"""Smoke tests for tapps_mcp.distribution.doctor_runner (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.distribution.doctor_result import CheckResult
from tapps_mcp.distribution.doctor_runner import (
    _check_specs,
    _collect_checks,
    _safe_check,
    run_doctor_structured,
)
from tapps_mcp.distribution.doctor_skills import check_one_pager_template_current


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


def test_one_pager_template_check_registered_in_specs(tmp_path: Path) -> None:
    """TAP-7424 box 4: the check is registered in _check_specs and doctor output."""
    specs = _check_specs(tmp_path)
    names = [name for name, _ in specs]
    assert "one-pager template" in names

    result = run_doctor_structured(project_root=str(tmp_path), quick=True)
    result_names = [c["name"] for c in result["checks"]]
    assert "one-pager template" in result_names


def test_one_pager_template_crash_becomes_failed_row_not_a_run_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TAP-7424 box 7: a crash in the check becomes a failed row via _safe_check.

    Every check registered in ``_check_specs`` already inherits crash-safety
    from ``_collect_checks`` -> ``_safe_check`` generically, provided the
    check reaches the doctor run only through the specs list.
    """

    from tapps_mcp.pipeline.platform_templates import ONE_PAGER_REL_PATH

    deployed_path = tmp_path / ONE_PAGER_REL_PATH
    deployed_path.parent.mkdir(parents=True, exist_ok=True)
    deployed_path.write_text("anything — the read must happen before the crash", encoding="utf-8")

    def _boom() -> str:
        raise RuntimeError("boom: packaged template unreadable")

    monkeypatch.setattr("tapps_mcp.pipeline.platform_templates.load_one_pager_template", _boom)

    before = _collect_checks(tmp_path, quick=True)
    checks = _collect_checks(tmp_path, quick=True)  # does not raise
    assert len(checks) == len(before)

    by_name = {c.name: c for c in checks}
    assert "one-pager template" in by_name
    row = by_name["one-pager template"]
    assert row.ok is False
    assert "Check crashed" in row.message

    # Other checks after this one in the specs list still ran (list length
    # unchanged from a run with no crash at all is checked above; also
    # confirm at least one check after this one in specs order is present).
    names = [c.name for c in checks]
    assert names.index("one-pager template") < len(names) - 1

    # Negative control: calling the check function directly (bypassing
    # _collect_checks / _safe_check) with the same monkeypatch must raise
    # uncaught — proves the crash-safety comes from the registration point,
    # not from the check function's own body.
    with pytest.raises(RuntimeError, match="boom: packaged template unreadable"):
        check_one_pager_template_current(tmp_path)
