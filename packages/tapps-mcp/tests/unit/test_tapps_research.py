"""Tests for deprecated expert/research tool stubs (Issues #82, #83).

Verifies that ``tapps_research`` and ``tapps_consult_expert`` return
structured TOOL_DEPRECATED errors with actionable alternatives instead
of raising unhandled ``ImportError`` exceptions.
"""

from __future__ import annotations

import pytest


class TestTappsResearchDeprecated:
    """Issue #83: tapps_research returns structured deprecation error."""

    @pytest.mark.asyncio
    async def test_returns_deprecated_error(self) -> None:
        from tapps_mcp.server_metrics_tools import tapps_research

        result = await tapps_research(question="How to prevent SQL injection?")
        assert result["success"] is False
        assert result["error"]["code"] == "TOOL_DEPRECATED"
        assert "EPIC-94" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_includes_alternatives(self) -> None:
        from tapps_mcp.server_metrics_tools import tapps_research

        result = await tapps_research(question="test", domain="security")
        alternatives = result["error"]["alternatives"]
        tool_names = [a["tool"] for a in alternatives]
        assert "tapps_lookup_docs" in tool_names
        assert "AgentForge" in tool_names

    @pytest.mark.asyncio
    async def test_includes_deprecated_since(self) -> None:
        from tapps_mcp.server_metrics_tools import tapps_research

        result = await tapps_research(question="test")
        assert result["error"]["deprecated_since"] == "EPIC-94"

    @pytest.mark.asyncio
    async def test_elapsed_ms_zero(self) -> None:
        from tapps_mcp.server_metrics_tools import tapps_research

        result = await tapps_research(question="test")
        assert result["elapsed_ms"] == 0


class TestTappsConsultExpertDeprecated:
    """Issue #82: tapps_consult_expert returns structured deprecation error."""

    @pytest.mark.asyncio
    async def test_returns_deprecated_error(self) -> None:
        from tapps_mcp.server_metrics_tools import tapps_consult_expert

        result = await tapps_consult_expert(question="How to prevent SQL injection?")
        assert result["success"] is False
        assert result["error"]["code"] == "TOOL_DEPRECATED"
        assert "EPIC-94" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_includes_alternatives(self) -> None:
        from tapps_mcp.server_metrics_tools import tapps_consult_expert

        result = await tapps_consult_expert(question="test", domain="security")
        alternatives = result["error"]["alternatives"]
        tool_names = [a["tool"] for a in alternatives]
        assert "tapps_lookup_docs" in tool_names

    @pytest.mark.asyncio
    async def test_includes_deprecated_since(self) -> None:
        from tapps_mcp.server_metrics_tools import tapps_consult_expert

        result = await tapps_consult_expert(question="test")
        assert result["error"]["deprecated_since"] == "EPIC-94"

    @pytest.mark.asyncio
    async def test_no_import_error(self) -> None:
        """Calling the tool should never raise ImportError (the original bug)."""
        from tapps_mcp.server_metrics_tools import tapps_consult_expert

        result = await tapps_consult_expert(
            question="Review this plan",
            domain="software-architecture",
        )
        assert isinstance(result, dict)
        assert result["success"] is False
        assert "ImportError" not in result["error"]["message"]


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
