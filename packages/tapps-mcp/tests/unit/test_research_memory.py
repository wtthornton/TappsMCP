"""Tests for tapps_mcp.tools.research_memory — freshness TTLs and answer recall (TAP-5366)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from tapps_mcp.tools.research_memory import (
    build_answer_memory_value,
    is_answer_fresh,
    parse_answer_memory_value,
    recall_research_answer,
    research_answer_memory_key,
)


class TestAnswerFreshnessHelpers:
    def test_memory_key_stable(self) -> None:
        a = research_answer_memory_key(route="web", query="Latest MCP Changes")
        b = research_answer_memory_key(route="web", query="latest mcp changes")
        assert a == b
        assert a.startswith("research-answer:web:")

    def test_is_answer_fresh_volatile_and_evergreen(self) -> None:
        now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
        fresh_vol = now - timedelta(hours=2)
        stale_vol = now - timedelta(hours=25)
        fresh_ever = now - timedelta(days=10)
        stale_ever = now - timedelta(days=31)
        assert is_answer_fresh(
            freshness="volatile", saved_at=fresh_vol, now=now, volatile_ttl_hours=24
        )
        assert not is_answer_fresh(
            freshness="volatile", saved_at=stale_vol, now=now, volatile_ttl_hours=24
        )
        assert is_answer_fresh(
            freshness="evergreen", saved_at=fresh_ever, now=now, evergreen_ttl_days=30
        )
        assert not is_answer_fresh(
            freshness="evergreen", saved_at=stale_ever, now=now, evergreen_ttl_days=30
        )

    def test_build_and_parse_roundtrip(self) -> None:
        payload = {
            "success": True,
            "provider": "tavily",
            "results": [{"title": "t", "url": "https://example.com"}],
        }
        saved_at = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
        value = build_answer_memory_value(
            payload,
            freshness="evergreen",
            route="web",
            query="latest mcp",
            saved_at=saved_at,
        )
        parsed = parse_answer_memory_value(value)
        assert parsed is not None
        assert parsed["freshness"] == "evergreen"
        assert parsed["answer"]["provider"] == "tavily"
        assert parsed["saved_at"].startswith("2026-08-01T10:00:00")

    @pytest.mark.asyncio
    async def test_recall_skips_stale_volatile(self) -> None:
        now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
        value = build_answer_memory_value(
            {"success": True, "provider": "tavily", "results": []},
            freshness="volatile",
            route="web",
            query="latest news",
            saved_at=now - timedelta(hours=48),
        )
        bridge = MagicMock()
        bridge.get = AsyncMock(
            return_value={"key": "k", "value": value, "tags": ["research-answer"]}
        )
        hit = await recall_research_answer(
            bridge,
            route="web",
            query="latest news",
            freshness="volatile",
            volatile_ttl_hours=24,
            now=now,
        )
        assert hit is None

    @pytest.mark.asyncio
    async def test_recall_returns_fresh_evergreen(self) -> None:
        now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
        value = build_answer_memory_value(
            {"success": True, "provider": "tavily", "answer": "stable fact"},
            freshness="evergreen",
            route="web",
            query="what is mcp",
            saved_at=now - timedelta(days=3),
        )
        key = research_answer_memory_key(route="web", query="what is mcp")
        bridge = MagicMock()
        bridge.get = AsyncMock(
            return_value={"key": key, "value": value, "tags": ["research-answer"]}
        )
        hit = await recall_research_answer(
            bridge,
            route="web",
            query="what is mcp",
            freshness="evergreen",
            evergreen_ttl_days=30,
            now=now,
        )
        assert hit is not None
        assert hit["data"]["source"] == "memory-hit"
        assert hit["data"]["answer"] == "stable fact"
