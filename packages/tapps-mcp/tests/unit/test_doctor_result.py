"""Smoke tests for tapps_mcp.distribution.doctor_result (TAP-5606 split)."""

from __future__ import annotations

import pytest

from tapps_mcp.distribution.doctor_result import CheckResult


def test_pass_result_has_pass_severity() -> None:
    result = CheckResult("name", True, "all good")
    assert result.severity == "pass"
    assert result.ok is True


def test_fail_result_has_fail_severity() -> None:
    result = CheckResult("name", False, "broken")
    assert result.severity == "fail"
    assert result.ok is False


def test_warn_prefixed_message_classified_as_warn() -> None:
    result = CheckResult("name", False, "WARN: something advisory")
    assert result.severity == "warn"
    assert result.ok is False


def test_explicit_severity_overrides_message_prefix() -> None:
    result = CheckResult("name", False, "WARN: still fails", severity="fail")
    assert result.severity == "fail"
    assert result.ok is False


def test_invalid_severity_raises() -> None:
    with pytest.raises(ValueError, match="invalid CheckResult severity"):
        CheckResult("name", False, "message", severity="bogus")


def test_detail_defaults_to_empty_string() -> None:
    result = CheckResult("name", True, "ok")
    assert result.detail == ""
