"""STORY-101.4 — actionable error envelope.

Every ``error_response`` now carries ``category``, ``retryable``, and
``remediation`` fields derived from a code registry, with caller-provided
``extra`` winning over the defaults.
"""

from __future__ import annotations

from tapps_mcp.server_helpers import error_response


def test_known_code_injects_category_and_remediation() -> None:
    resp = error_response("tapps_quick_check", "path_denied", "bad path")
    err = resp["error"]
    assert resp["success"] is False
    assert err["code"] == "path_denied"
    assert err["message"] == "bad path"
    assert err["category"] == "user_input"
    assert err["retryable"] is False
    assert err["remediation"].startswith("Pass an absolute path")


def test_unknown_code_falls_back_to_internal_retryable() -> None:
    resp = error_response("tapps_quick_check", "wat_was_that", "boom")
    err = resp["error"]
    assert err["category"] == "internal"
    assert err["retryable"] is True
    assert "Retry" in err["remediation"]


def test_extra_overrides_registry_defaults() -> None:
    resp = error_response(
        "tapps_quick_check",
        "path_denied",
        "bad path",
        extra={"retryable": True, "remediation": "custom hint", "hint_files": ["a.py"]},
    )
    err = resp["error"]
    assert err["retryable"] is True
    assert err["remediation"] == "custom hint"
    assert err["hint_files"] == ["a.py"]
    # Non-overridden defaults survive.
    assert err["category"] == "user_input"


def test_scoring_failed_is_retryable() -> None:
    resp = error_response("tapps_score_file", "scoring_failed", "segfault")
    err = resp["error"]
    assert err["category"] == "internal"
    assert err["retryable"] is True


def test_deprecated_tool_envelope() -> None:
    resp = error_response(
        "old_tool",
        "TOOL_DEPRECATED",
        "removed in v2.6",
        extra={"alternatives": ["tapps_quick_check"]},
    )
    err = resp["error"]
    assert err["category"] == "deprecated"
    assert err["retryable"] is False
    assert err["alternatives"] == ["tapps_quick_check"]


def test_unsupported_language_envelope() -> None:
    resp = error_response(
        "tapps_quick_check", "unsupported_language", "File extension not supported: .rb"
    )
    err = resp["error"]
    assert err["category"] == "unsupported"
    assert err["retryable"] is False
    assert ".py" in err["remediation"]
