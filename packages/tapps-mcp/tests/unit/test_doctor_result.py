"""Smoke tests for tapps_mcp.distribution.doctor_result (TAP-5606 split)."""

from __future__ import annotations

import pytest

from tapps_mcp.distribution.doctor_result import CheckResult, consumer_staleness
from tapps_mcp.distribution.doctor_runner import _safe_check


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


def test_category_defaults_to_release_health() -> None:
    """TAP-6965: unknown/untagged checks must gate, so the default is release-health."""
    result = CheckResult("name", False, "broken")
    assert result.category == "release-health"


def test_invalid_category_raises() -> None:
    with pytest.raises(ValueError, match="invalid CheckResult category"):
        CheckResult("name", False, "message", category="bogus")


def test_consumer_staleness_decorator_tags_the_returned_result() -> None:
    @consumer_staleness
    def check_something() -> CheckResult:
        return CheckResult("Something", False, "stale on disk")

    result = check_something()

    assert result.category == "consumer-staleness"
    assert result.name == "Something"
    assert result.severity == "fail"


def test_safe_check_crash_defaults_to_release_health_even_for_a_staleness_check() -> None:
    """TAP-6965 PROBE-B: a crash never inherits its check's usual category.

    ``_safe_check`` builds a *new* ``CheckResult`` on exception -- it has no
    way to know what category the check that raised would have set -- so it
    always gets the release-health default, which gates the post-flip smoke
    test regardless of which check crashed.
    """

    @consumer_staleness
    def _boom() -> CheckResult:
        raise RuntimeError("boom")

    result = _safe_check("Some consumer-staleness check", _boom)

    assert result.category == "release-health"
    assert result.severity == "fail"
    assert "Check crashed" in result.message
