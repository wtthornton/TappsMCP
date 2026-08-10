"""Tests for BrainBridge/HttpBrainBridge.web_research and .research_fetch wiring (TAP-5365)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


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
    out = await HttpBrainBridge.research_fetch(bridge, "https://example.com", freshness="evergreen")
    assert out["success"] is True
    bridge._http_mcp_call.assert_awaited_once_with(  # type: ignore[attr-defined]
        "research_fetch",
        {"url": "https://example.com", "freshness": "evergreen"},
    )
