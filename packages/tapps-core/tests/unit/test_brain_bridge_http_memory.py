"""Tests for tapps_core.brain_bridge_http_memory — memory CRUD + KG reads for
HttpBrainBridge.

Split out of test_brain_bridge_http.py alongside the TAP-6736 megafile split
(and its own further split into session/health/memory/kg_hive mixins).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tapps_core.brain_bridge import HttpBrainBridge


def _make_bridge() -> HttpBrainBridge:
    bridge = HttpBrainBridge("http://brain:8080", {"Authorization": "Bearer t"})
    bridge._http_mcp_call = AsyncMock()
    return bridge


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_list_result(self) -> None:
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = [{"key": "k1"}]
        result = await bridge.search("query")
        assert result == [{"key": "k1"}]
        bridge._http_mcp_call.assert_called_once_with(
            "memory_search", {"query": "query", "limit": 10}, project_id=None
        )

    @pytest.mark.asyncio
    async def test_search_unwraps_dict_result(self) -> None:
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = {"results": [{"key": "k1"}]}
        result = await bridge.search("query")
        assert result == [{"key": "k1"}]

    @pytest.mark.asyncio
    async def test_search_defaults_to_empty_on_unexpected_shape(self) -> None:
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = "unexpected"
        assert await bridge.search("query") == []


class TestGet:
    @pytest.mark.asyncio
    async def test_get_returns_entry_on_success(self) -> None:
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = {"key": "k1", "value": "v"}
        result = await bridge.get("k1")
        assert result == {"key": "k1", "value": "v"}

    @pytest.mark.asyncio
    async def test_get_returns_none_on_error_envelope(self) -> None:
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = {"error": "not_found"}
        assert await bridge.get("missing") is None


class TestDocsAndResearch:
    @pytest.mark.asyncio
    async def test_docs_lookup_wraps_non_dict_result(self) -> None:
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = "raw text"
        result = await bridge.docs_lookup("some-lib")
        assert result == {"content": "raw text"}

    @pytest.mark.asyncio
    async def test_web_research_passes_through_dict_result(self) -> None:
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = {"results": []}
        result = await bridge.web_research("query")
        assert result == {"results": []}


class TestFindRelated:
    @pytest.mark.asyncio
    async def test_find_related_extracts_entries_from_dict(self) -> None:
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = {"entries": [{"key": "k2"}]}
        result = await bridge.find_related("k1")
        assert result == [{"key": "k2"}]
