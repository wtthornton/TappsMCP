"""Tests for restored tapps_research router (TAP-5365 / ADR-0030)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.research import (
    bridge_degraded_response,
    classify_research_route,
    looks_like_url,
    telemetry_source_for_docs,
    telemetry_source_for_web,
    wrap_brain_research_payload,
)


class TestClassifyResearchRoute:
    def test_explicit_routes(self) -> None:
        assert classify_research_route("x", route="docs") == "docs"
        assert classify_research_route("x", route="web") == "web"
        assert classify_research_route("x", route="fetch") == "fetch"

    def test_library_forces_docs(self) -> None:
        assert classify_research_route("anything", library="httpx") == "docs"

    def test_url_forces_fetch(self) -> None:
        assert classify_research_route("", url="https://example.com/a") == "fetch"
        assert classify_research_route("https://example.com/a") == "fetch"

    def test_latest_forces_web(self) -> None:
        assert classify_research_route("latest pydantic release notes") == "web"

    def test_docs_hints(self) -> None:
        assert classify_research_route("fastapi middleware documentation") == "docs"

    def test_open_ended_defaults_web(self) -> None:
        assert classify_research_route("why do agents hallucinate APIs") == "web"


class TestLooksLikeUrl:
    def test_http_https(self) -> None:
        assert looks_like_url("https://example.com/path")
        assert looks_like_url("http://example.com")
        assert not looks_like_url("example.com")
        assert not looks_like_url("ftp://example.com")


class TestTelemetryAndWrap:
    def test_docs_source(self) -> None:
        assert telemetry_source_for_docs(cache_hit=True) == "cache-hit"
        assert telemetry_source_for_docs(cache_hit=False) == "docs"

    def test_web_source(self) -> None:
        assert telemetry_source_for_web({"cache_hit": True}) == "cache-hit"
        assert telemetry_source_for_web({"source": "api"}) == "web"
        assert telemetry_source_for_web({"source": "stale_fallback"}) == "web"

    def test_wrap_success(self) -> None:
        payload = {
            "success": True,
            "cache_hit": False,
            "source": "api",
            "provider": "tavily",
            "results": [{"title": "t", "url": "https://example.com", "snippet": "s"}],
        }
        out = wrap_brain_research_payload(payload, route="web", elapsed_ms=12)
        assert out["success"] is True
        assert out["data"]["route"] == "web"
        assert out["data"]["source"] == "web"
        assert out["data"]["provider"] == "tavily"

    def test_wrap_failure_retryable(self) -> None:
        payload = {
            "success": False,
            "error": "not_configured",
            "degraded": True,
            "retryable": True,
        }
        out = wrap_brain_research_payload(payload, route="web", elapsed_ms=3)
        assert out["success"] is False
        assert out["degraded"] is True
        assert out["retryable"] is True

    def test_bridge_degraded_shape(self) -> None:
        out = bridge_degraded_response(route="web", detail="circuit open", elapsed_ms=5)
        assert out["success"] is False
        assert out["degraded"] is True
        assert out["retryable"] is True
        assert out["data"]["error"] == "brain_bridge_call_failed"


class TestErrorResponseExtra:
    """Retain error_response extra-metadata coverage from the pre-EPIC-94 file."""

    def test_extra_merged_into_error(self) -> None:
        from tapps_mcp.server_helpers import error_response

        result = error_response(
            "test_tool",
            "TEST_CODE",
            "test message",
            extra={"hint": "try X", "severity": "low"},
        )
        assert result["error"]["code"] == "TEST_CODE"
        assert result["error"]["hint"] == "try X"


@pytest.mark.asyncio
class TestTappsResearchHandler:
    async def test_docs_route_uses_lookup_engine(self) -> None:
        from tapps_core.knowledge.models import LookupResult
        from tapps_mcp.server import tapps_research

        lookup = LookupResult(
            library="httpx",
            topic="async client",
            success=True,
            content="docs body",
            source="cache",
            cache_hit=True,
            response_time_ms=1.0,
        )
        engine = MagicMock()
        engine.lookup = AsyncMock(return_value=lookup)

        with (
            patch("tapps_mcp.server_helpers._get_lookup_engine", return_value=engine),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
            patch("tapps_mcp.server._maybe_record_lookup_telemetry"),
        ):
            result = await tapps_research(
                query="httpx async client",
                library="httpx",
                topic="async client",
            )

        assert result["success"] is True
        assert result["data"]["route"] == "docs"
        assert result["data"]["source"] == "cache-hit"
        engine.lookup.assert_awaited_once()

    async def test_web_route_calls_bridge(self) -> None:
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.web_research = AsyncMock(
            return_value={
                "success": True,
                "cache_hit": False,
                "source": "api",
                "provider": "tavily",
                "results": [],
            }
        )

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(query="latest changes in MCP protocol")

        assert result["success"] is True
        assert result["data"]["route"] == "web"
        bridge.web_research.assert_awaited_once()

    async def test_brain_down_degrades(self) -> None:
        from tapps_core.brain_bridge import BrainBridgeUnavailable
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.web_research = AsyncMock(side_effect=BrainBridgeUnavailable("circuit open"))

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(query="latest news", route="web")

        assert result["success"] is False
        assert result["degraded"] is True
        assert result["retryable"] is True
        assert result["data"]["error"] == "brain_bridge_call_failed"

    async def test_bridge_unconfigured_degrades(self) -> None:
        from tapps_mcp.server import tapps_research

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=None),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(query="latest news", route="web")

        assert result["success"] is False
        assert result["degraded"] is True
        assert result["data"]["error"] == "brain_bridge_unconfigured"

    async def test_fetch_route_calls_research_fetch(self) -> None:
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.research_fetch = AsyncMock(
            return_value={
                "success": True,
                "cache_hit": True,
                "source": "cache",
                "provider": "firecrawl",
                "results": [{"url": "https://example.com", "content": "x"}],
            }
        )

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(
                query="",
                url="https://example.com/doc",
                freshness="evergreen",
            )

        assert result["success"] is True
        assert result["data"]["route"] == "fetch"
        assert result["data"]["source"] == "cache-hit"
        bridge.research_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_inprocess_bridge_web_research_unavailable() -> None:
    from tapps_core.brain_bridge import BrainBridge, BrainBridgeUnavailable

    bridge = object.__new__(BrainBridge)
    with pytest.raises(BrainBridgeUnavailable, match="web_research requires HTTP"):
        await BrainBridge.web_research(bridge, "q")
    with pytest.raises(BrainBridgeUnavailable, match="research_fetch requires HTTP"):
        await BrainBridge.research_fetch(bridge, "https://example.com")


@pytest.mark.asyncio
async def test_http_bridge_web_research_calls_mcp() -> None:
    from tapps_core.brain_bridge import HttpBrainBridge

    bridge = object.__new__(HttpBrainBridge)
    bridge._http_mcp_call = AsyncMock(  # type: ignore[method-assign]
        return_value={"success": True, "results": []}
    )
    out = await HttpBrainBridge.web_research(
        bridge, "q", source="auto", freshness="volatile", max_results=3
    )
    assert out["success"] is True
    bridge._http_mcp_call.assert_awaited_once_with(  # type: ignore[attr-defined]
        "web_research",
        {"query": "q", "source": "auto", "freshness": "volatile", "max_results": 3},
    )


@pytest.mark.asyncio
async def test_http_bridge_research_fetch_calls_mcp() -> None:
    from tapps_core.brain_bridge import HttpBrainBridge

    bridge = object.__new__(HttpBrainBridge)
    bridge._http_mcp_call = AsyncMock(  # type: ignore[method-assign]
        return_value={"success": True, "results": []}
    )
    out = await HttpBrainBridge.research_fetch(
        bridge, "https://example.com", freshness="evergreen"
    )
    assert out["success"] is True
    bridge._http_mcp_call.assert_awaited_once_with(  # type: ignore[attr-defined]
        "research_fetch",
        {"url": "https://example.com", "freshness": "evergreen"},
    )


def test_research_in_all_tool_names() -> None:
    from tapps_mcp.server import ALL_TOOL_NAMES, TOOL_PROFILE_NLT_BUILD

    assert "tapps_research" in ALL_TOOL_NAMES
    assert "tapps_research" in TOOL_PROFILE_NLT_BUILD


def test_checklist_reason_present() -> None:
    from tapps_mcp.tools.checklist import _TOOL_EQUIVALENTS, TOOL_REASONS

    assert "tapps_research" in TOOL_REASONS
    assert "tapps_lookup_docs" in _TOOL_EQUIVALENTS["tapps_research"]
