"""Tests for the tapps_research handler's route/memory/bridge orchestration (TAP-5365-5367).

Argument validation and the ``register`` hook live in test_server_research_tools.py;
pure router/memory helpers live in test_tapps_research.py and test_research_memory.py.
This module covers end-to-end behavior of the handler itself: docs/web/fetch routing,
brain-down degradation, and memory hit/miss/save paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_core.config.settings import MemorySettings

pytestmark = pytest.mark.usefixtures("envelope_guard")


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
            patch("tapps_mcp.server_research_tools._maybe_record_lookup_telemetry"),
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

    async def test_docs_route_cache_miss_source_docs(self) -> None:
        from tapps_core.knowledge.models import LookupResult
        from tapps_mcp.server import tapps_research

        lookup = LookupResult(
            library="pydantic",
            topic="validators",
            success=True,
            content="fresh docs",
            source="context7",
            cache_hit=False,
            response_time_ms=12.0,
        )
        engine = MagicMock()
        engine.lookup = AsyncMock(return_value=lookup)

        with (
            patch("tapps_mcp.server_helpers._get_lookup_engine", return_value=engine),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
            patch("tapps_mcp.server_research_tools._maybe_record_lookup_telemetry"),
        ):
            result = await tapps_research(
                query="pydantic validators",
                library="pydantic",
                topic="validators",
            )

        assert result["success"] is True
        assert result["data"]["route"] == "docs"
        assert result["data"]["source"] == "docs"

    async def test_web_route_calls_bridge(self) -> None:
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.get = AsyncMock(return_value=None)
        bridge.save = AsyncMock(return_value={"success": True})
        bridge.web_research = AsyncMock(
            return_value={
                "success": True,
                "cache_hit": False,
                "source": "api",
                "provider": "tavily",
                "results": [],
            }
        )
        memory = MemorySettings(enabled=True, auto_save_quality=True)
        settings = MagicMock()
        settings.memory = memory

        with (
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server_research_tools.load_settings", return_value=settings),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(query="latest changes in MCP protocol")

        assert result["success"] is True
        assert result["data"]["route"] == "web"
        assert result["data"]["source"] == "web"
        bridge.web_research.assert_awaited_once()
        bridge.save.assert_awaited_once()

    async def test_web_route_cache_hit_source(self) -> None:
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.get = AsyncMock(return_value=None)
        bridge.save = AsyncMock(return_value={"success": True})
        bridge.web_research = AsyncMock(
            return_value={
                "success": True,
                "cache_hit": True,
                "source": "cache",
                "provider": "tavily",
                "results": [{"title": "cached"}],
            }
        )
        memory = MemorySettings(enabled=True, auto_save_quality=True)
        settings = MagicMock()
        settings.memory = memory

        with (
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server_research_tools.load_settings", return_value=settings),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(query="latest changes in MCP protocol")

        assert result["success"] is True
        assert result["data"]["route"] == "web"
        assert result["data"]["source"] == "cache-hit"

    async def test_fetch_ssrf_blocked_does_not_save(self) -> None:
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.get = AsyncMock(return_value=None)
        bridge.save = AsyncMock(return_value={"success": True})
        bridge.research_fetch = AsyncMock(
            return_value={
                "success": False,
                "error": "ssrf_blocked",
                "detail": "blocked host 127.0.0.1",
                "degraded": True,
                "retryable": False,
                "freshness_tier": "evergreen",
                "url": "http://127.0.0.1:8080/admin",
            }
        )
        memory = MemorySettings(enabled=True, auto_save_quality=True)
        settings = MagicMock()
        settings.memory = memory
        record_exec = MagicMock()

        with (
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server_research_tools.load_settings", return_value=settings),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution", record_exec),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(
                query="",
                url="http://127.0.0.1:8080/admin",
                freshness="evergreen",
            )

        assert result["success"] is False
        assert result["degraded"] is True
        assert result["retryable"] is False
        assert result["data"]["error"] == "ssrf_blocked"
        assert result["data"]["source"] == "web"
        bridge.research_fetch.assert_awaited_once()
        bridge.save.assert_not_awaited()
        record_exec.assert_called_once()
        assert record_exec.call_args.kwargs["status"] == "failed"
        assert record_exec.call_args.kwargs["error_code"] == "ssrf_blocked"

    async def test_fetch_rag_safety_blocked_does_not_save(self) -> None:
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.get = AsyncMock(return_value=None)
        bridge.save = AsyncMock(return_value={"success": True})
        bridge.research_fetch = AsyncMock(
            return_value={
                "success": False,
                "error": "rag_safety_blocked",
                "detail": "content failed safety filter",
                "degraded": True,
                "retryable": False,
                "url": "https://example.com/unsafe",
            }
        )
        memory = MemorySettings(enabled=True, auto_save_quality=True)
        settings = MagicMock()
        settings.memory = memory

        with (
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server_research_tools.load_settings", return_value=settings),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(
                query="",
                url="https://example.com/unsafe",
                freshness="evergreen",
            )

        assert result["success"] is False
        assert result["retryable"] is False
        assert result["data"]["error"] == "rag_safety_blocked"
        bridge.save.assert_not_awaited()

    async def test_brain_down_degrades(self) -> None:
        from tapps_core.brain_bridge import BrainBridgeUnavailable
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.get = AsyncMock(return_value=None)
        bridge.web_research = AsyncMock(side_effect=BrainBridgeUnavailable("circuit open"))
        memory = MemorySettings(enabled=True, auto_save_quality=True)
        settings = MagicMock()
        settings.memory = memory

        with (
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server_research_tools.load_settings", return_value=settings),
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
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=None),
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
        bridge.get = AsyncMock(return_value=None)
        bridge.save = AsyncMock(return_value={"success": True})
        bridge.research_fetch = AsyncMock(
            return_value={
                "success": True,
                "cache_hit": True,
                "source": "cache",
                "provider": "firecrawl",
                "results": [{"url": "https://example.com", "content": "x"}],
            }
        )
        memory = MemorySettings(
            enabled=True,
            auto_save_quality=True,
            research_volatile_ttl_hours=24,
            research_evergreen_ttl_days=30,
        )
        settings = MagicMock()
        settings.memory = memory

        with (
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server_research_tools.load_settings", return_value=settings),
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
        bridge.save.assert_awaited_once()

    async def test_evergreen_memory_hit_skips_web_research(self) -> None:
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.web_research = AsyncMock()
        bridge.save = AsyncMock()
        memory = MemorySettings(enabled=True, auto_save_quality=True)
        settings = MagicMock()
        settings.memory = memory
        memory_hit = {
            "tool": "tapps_research",
            "success": True,
            "elapsed_ms": 0,
            "data": {
                "route": "web",
                "source": "memory-hit",
                "memory_hit": True,
                "freshness": "evergreen",
                "answer": "from memory",
            },
        }

        with (
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server_research_tools.load_settings", return_value=settings),
            patch(
                "tapps_mcp.tools.research_memory.maybe_recall_research_answer",
                new_callable=AsyncMock,
                return_value=memory_hit,
            ),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(
                query="what is the model context protocol",
                route="web",
                freshness="evergreen",
            )

        assert result["success"] is True
        assert result["data"]["source"] == "memory-hit"
        assert result["data"]["answer"] == "from memory"
        bridge.web_research.assert_not_awaited()
        bridge.save.assert_not_awaited()

    async def test_stale_volatile_misses_then_saves(self) -> None:
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.web_research = AsyncMock(
            return_value={
                "success": True,
                "cache_hit": False,
                "source": "api",
                "provider": "tavily",
                "results": [{"title": "new"}],
            }
        )
        bridge.save = AsyncMock(return_value={"success": True})
        memory = MemorySettings(
            enabled=True,
            auto_save_quality=True,
            research_volatile_ttl_hours=24,
        )
        settings = MagicMock()
        settings.memory = memory

        with (
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server_research_tools.load_settings", return_value=settings),
            patch(
                "tapps_mcp.tools.research_memory.maybe_recall_research_answer",
                new_callable=AsyncMock,
                return_value=None,
            ) as recall_mock,
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(
                query="latest mcp changes",
                route="web",
                freshness="volatile",
            )

        assert result["success"] is True
        assert result["data"]["source"] == "web"
        assert result["data"]["freshness"] == "volatile"
        recall_mock.assert_awaited_once()
        assert recall_mock.await_args.kwargs["freshness"] == "volatile"
        bridge.web_research.assert_awaited_once()
        bridge.save.assert_awaited_once()
        save_kwargs = bridge.save.await_args.kwargs
        assert save_kwargs["tier"] == "pattern"
        assert "freshness:volatile" in save_kwargs["tags"]

    async def test_auto_save_quality_false_skips_recall_and_save(self) -> None:
        from tapps_mcp.server import tapps_research

        bridge = MagicMock()
        bridge.get = AsyncMock()
        bridge.save = AsyncMock()
        bridge.web_research = AsyncMock(
            return_value={"success": True, "source": "api", "results": []}
        )
        memory = MemorySettings(enabled=True, auto_save_quality=False)
        settings = MagicMock()
        settings.memory = memory

        with (
            patch("tapps_mcp.server_research_tools._get_brain_bridge", return_value=bridge),
            patch("tapps_mcp.server_research_tools.load_settings", return_value=settings),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _t, r: r),
        ):
            result = await tapps_research(query="latest news", route="web")

        assert result["success"] is True
        bridge.get.assert_not_awaited()
        bridge.save.assert_not_awaited()
        bridge.web_research.assert_awaited_once()
