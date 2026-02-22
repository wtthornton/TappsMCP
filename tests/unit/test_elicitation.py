"""Tests for MCP Elicitation Support (Story 12.15).

Verifies the elicitation helper functions, schema models,
and graceful degradation on unsupported clients.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tapps_mcp.common.elicitation import (
    InitConfirmation,
    PresetElicitation,
    elicit_init_confirmation,
    elicit_preset,
)


class TestPresetElicitationSchema:
    """Tests for the PresetElicitation Pydantic model."""

    def test_valid_preset(self):
        model = PresetElicitation(preset="staging")
        assert model.preset == "staging"

    def test_schema_has_enum_info(self):
        schema = PresetElicitation.model_json_schema()
        assert "preset" in schema["properties"]


class TestInitConfirmationSchema:
    """Tests for the InitConfirmation Pydantic model."""

    def test_confirm_true(self):
        model = InitConfirmation(confirm=True)
        assert model.confirm is True

    def test_confirm_false(self):
        model = InitConfirmation(confirm=False)
        assert model.confirm is False


class TestElicitPreset:
    """Tests for the elicit_preset helper."""

    @pytest.mark.asyncio
    async def test_accept_returns_preset(self):
        ctx = MagicMock()
        result_mock = MagicMock()
        result_mock.action = "accept"
        result_mock.data = PresetElicitation(preset="production")
        ctx.elicit = AsyncMock(return_value=result_mock)

        result = await elicit_preset(ctx)
        assert result == "production"

    @pytest.mark.asyncio
    async def test_decline_returns_none(self):
        ctx = MagicMock()
        result_mock = MagicMock()
        result_mock.action = "decline"
        result_mock.data = None
        ctx.elicit = AsyncMock(return_value=result_mock)

        result = await elicit_preset(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_returns_none(self):
        ctx = MagicMock()
        result_mock = MagicMock()
        result_mock.action = "cancel"
        result_mock.data = None
        ctx.elicit = AsyncMock(return_value=result_mock)

        result = await elicit_preset(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        """Unsupported client raises — should degrade gracefully."""
        ctx = MagicMock()
        ctx.elicit = AsyncMock(side_effect=Exception("not supported"))

        result = await elicit_preset(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_calls_elicit_with_message(self):
        ctx = MagicMock()
        result_mock = MagicMock()
        result_mock.action = "accept"
        result_mock.data = PresetElicitation(preset="staging")
        ctx.elicit = AsyncMock(return_value=result_mock)

        await elicit_preset(ctx)
        ctx.elicit.assert_called_once()
        call_args = ctx.elicit.call_args
        assert "preset" in call_args.kwargs["message"].lower()


class TestElicitInitConfirmation:
    """Tests for the elicit_init_confirmation helper."""

    @pytest.mark.asyncio
    async def test_accept_true(self):
        ctx = MagicMock()
        result_mock = MagicMock()
        result_mock.action = "accept"
        result_mock.data = InitConfirmation(confirm=True)
        ctx.elicit = AsyncMock(return_value=result_mock)

        result = await elicit_init_confirmation(ctx, "/project")
        assert result is True

    @pytest.mark.asyncio
    async def test_accept_false(self):
        ctx = MagicMock()
        result_mock = MagicMock()
        result_mock.action = "accept"
        result_mock.data = InitConfirmation(confirm=False)
        ctx.elicit = AsyncMock(return_value=result_mock)

        result = await elicit_init_confirmation(ctx, "/project")
        assert result is False

    @pytest.mark.asyncio
    async def test_decline_returns_none(self):
        ctx = MagicMock()
        result_mock = MagicMock()
        result_mock.action = "decline"
        result_mock.data = None
        ctx.elicit = AsyncMock(return_value=result_mock)

        result = await elicit_init_confirmation(ctx, "/project")
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        ctx = MagicMock()
        ctx.elicit = AsyncMock(side_effect=Exception("not supported"))

        result = await elicit_init_confirmation(ctx, "/project")
        assert result is None

    @pytest.mark.asyncio
    async def test_message_includes_project_root(self):
        ctx = MagicMock()
        result_mock = MagicMock()
        result_mock.action = "accept"
        result_mock.data = InitConfirmation(confirm=True)
        ctx.elicit = AsyncMock(return_value=result_mock)

        await elicit_init_confirmation(ctx, "/my/project")
        call_args = ctx.elicit.call_args
        assert "/my/project" in call_args.kwargs["message"]
