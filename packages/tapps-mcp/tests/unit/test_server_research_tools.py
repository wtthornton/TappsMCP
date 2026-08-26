"""Tests for server_research_tools — argument validation and tool registration.

Router/memory behaviour for ``tapps_research`` lives in ``test_tapps_research.py``;
this module covers the handler's own input contract and its ``register`` hook.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tapps_mcp.server_research_tools import register, tapps_research

pytestmark = pytest.mark.usefixtures("envelope_guard")


class TestArgumentValidation:
    @pytest.mark.asyncio
    async def test_invalid_route_rejected(self) -> None:
        result = await tapps_research("q", route="sideways")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_args"

    @pytest.mark.asyncio
    async def test_invalid_source_rejected(self) -> None:
        result = await tapps_research("q", source="altavista")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_args"

    @pytest.mark.asyncio
    async def test_invalid_freshness_rejected(self) -> None:
        result = await tapps_research("q", freshness="whenever")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_args"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [0, 21, -1, "five"])
    async def test_max_results_out_of_range_rejected(self, bad: object) -> None:
        result = await tapps_research("q", max_results=bad)  # type: ignore[arg-type]
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_args"

    @pytest.mark.asyncio
    async def test_docs_route_without_library_rejected(self) -> None:
        result = await tapps_research("q", route="docs")
        assert result["success"] is False
        assert result["error"]["code"] == "missing_params"

    @pytest.mark.asyncio
    async def test_docs_route_invalid_mode_rejected(self) -> None:
        result = await tapps_research("q", route="docs", library="httpx", mode="nope")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_mode"

    @pytest.mark.asyncio
    async def test_fetch_route_without_url_rejected(self) -> None:
        result = await tapps_research("not a url", route="fetch")
        assert result["success"] is False
        assert result["error"]["code"] == "missing_params"

    @pytest.mark.asyncio
    async def test_web_route_with_empty_query_rejected(self) -> None:
        result = await tapps_research("   ", route="web")
        assert result["success"] is False
        assert result["error"]["code"] == "missing_params"


class TestRegister:
    def test_registers_when_allowed(self) -> None:
        mcp = MagicMock()
        register(mcp, frozenset({"tapps_research"}))
        assert mcp.add_tool.called or mcp.tool.called

    def test_skipped_when_not_allowed(self) -> None:
        mcp = MagicMock()
        register(mcp, frozenset())
        assert not mcp.add_tool.called
        assert not mcp.tool.called
