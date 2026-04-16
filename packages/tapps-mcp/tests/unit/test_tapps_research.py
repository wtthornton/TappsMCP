"""Tests for error_response helper (formerly also tested deprecated expert/research stubs).

The ``tapps_research`` and ``tapps_consult_expert`` tools were removed in TAP-483.
This file retains the ``error_response`` extra-metadata tests that were co-located here.
"""

from __future__ import annotations


class TestErrorResponseExtra:
    """Verify error_response supports extra metadata."""

    def test_extra_merged_into_error(self) -> None:
        from tapps_mcp.server_helpers import error_response

        result = error_response(
            "test_tool",
            "TEST_CODE",
            "test message",
            extra={"hint": "try X", "severity": "low"},
        )
        assert result["error"]["code"] == "TEST_CODE"
        assert result["error"]["message"] == "test message"
        assert result["error"]["hint"] == "try X"
        assert result["error"]["severity"] == "low"

    def test_extra_none_preserves_original(self) -> None:
        from tapps_mcp.server_helpers import error_response

        result = error_response("test_tool", "TEST_CODE", "msg")
        # Actionable envelope (STORY-101.4) always includes category/retryable/remediation
        assert "code" in result["error"]
        assert "message" in result["error"]
        assert "category" in result["error"]
        assert "retryable" in result["error"]
        assert "remediation" in result["error"]
