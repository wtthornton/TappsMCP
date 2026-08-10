"""Tests for tapps_mcp.tools.research route classification and telemetry (TAP-5365-5367).

Freshness/memory-key helpers live in test_research_memory.py; end-to-end
``tapps_research`` handler behavior lives in test_tapps_research_handler.py;
argument validation lives in test_server_research_tools.py; BrainBridge-level
web_research/research_fetch wiring lives in test_research_brain_bridge.py.
"""

from __future__ import annotations

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
        assert telemetry_source_for_web({"memory_hit": True}) == "memory-hit"
        assert telemetry_source_for_web({"source": "memory-hit"}) == "memory-hit"

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

    def test_wrap_ssrf_blocked_not_retryable(self) -> None:
        payload = {
            "success": False,
            "error": "ssrf_blocked",
            "detail": "blocked host 127.0.0.1",
            "degraded": True,
            "retryable": False,
            "url": "http://127.0.0.1:8080/admin",
        }
        out = wrap_brain_research_payload(payload, route="fetch", elapsed_ms=4)
        assert out["success"] is False
        assert out["degraded"] is True
        assert out["retryable"] is False
        assert out["data"]["error"] == "ssrf_blocked"
        assert out["data"]["source"] == "web"

    def test_bridge_degraded_shape(self) -> None:
        out = bridge_degraded_response(route="web", detail="circuit open", elapsed_ms=5)
        assert out["success"] is False
        assert out["degraded"] is True
        assert out["retryable"] is True
        assert out["data"]["error"] == "brain_bridge_call_failed"


def test_research_in_all_tool_names() -> None:
    from tapps_mcp.server import ALL_TOOL_NAMES, TOOL_PROFILE_NLT_BUILD

    assert "tapps_research" in ALL_TOOL_NAMES
    assert "tapps_research" in TOOL_PROFILE_NLT_BUILD


def test_checklist_reason_present() -> None:
    from tapps_mcp.tools.checklist import _TOOL_EQUIVALENTS, TOOL_REASONS

    assert "tapps_research" in TOOL_REASONS
    assert "tapps_lookup_docs" in _TOOL_EQUIVALENTS["tapps_research"]
