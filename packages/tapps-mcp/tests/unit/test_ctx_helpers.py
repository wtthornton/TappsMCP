"""Tests for the shared emit_ctx_info helper in server_helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tapps_mcp.server_helpers import emit_ctx_info


class TestEmitCtxInfo:
    """Tests for the shared emit_ctx_info helper."""

    @pytest.mark.asyncio
    async def test_calls_info_with_message(self) -> None:
        ctx = MagicMock()
        ctx.info = AsyncMock()

        await emit_ctx_info(ctx, "hello world")

        ctx.info.assert_called_once_with("hello world")

    @pytest.mark.asyncio
    async def test_noop_when_ctx_is_none(self) -> None:
        await emit_ctx_info(None, "should not crash")

    @pytest.mark.asyncio
    async def test_noop_when_no_info_method(self) -> None:
        ctx = MagicMock(spec=[])
        await emit_ctx_info(ctx, "should not crash")

    @pytest.mark.asyncio
    async def test_suppresses_exception(self) -> None:
        ctx = MagicMock()
        ctx.info = AsyncMock(side_effect=RuntimeError("boom"))

        await emit_ctx_info(ctx, "should not raise")

    @pytest.mark.asyncio
    async def test_awaits_async_info(self) -> None:
        """Confirms the function awaits the async info call."""
        ctx = MagicMock()
        ctx.info = AsyncMock(return_value=None)

        await emit_ctx_info(ctx, "test message")

        ctx.info.assert_awaited_once_with("test message")
