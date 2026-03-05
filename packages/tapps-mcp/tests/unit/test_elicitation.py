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
    WizardConfigScope,
    WizardResult,
    elicit_init_confirmation,
    elicit_preset,
    run_init_wizard,
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


# ---------------------------------------------------------------------------
# Story 47.3: Wizard scope question
# ---------------------------------------------------------------------------


class TestWizardConfigScope:
    """Tests for WizardConfigScope schema (Epic 47.3)."""

    def test_valid_project_scope(self):
        model = WizardConfigScope(scope="project")
        assert model.scope == "project"

    def test_valid_user_scope(self):
        model = WizardConfigScope(scope="user")
        assert model.scope == "user"

    def test_schema_has_enum(self):
        schema = WizardConfigScope.model_json_schema()
        assert "scope" in schema["properties"]


class TestWizardResultScope:
    """Tests for WizardResult config_scope field (Epic 47.3)."""

    def test_default_scope_is_project(self):
        result = WizardResult()
        assert result.config_scope == "project"

    def test_scope_in_slots(self):
        assert "config_scope" in WizardResult.__slots__


class TestWizardScopeQuestion:
    """Tests for scope question in run_init_wizard (Epic 47.3)."""

    @pytest.mark.asyncio
    async def test_scope_question_asked_when_claude_detected(self):
        """Wizard asks scope question when claude_code_detected=True."""
        ctx = MagicMock()
        mock_result = MagicMock()
        mock_result.action = "accept"
        mock_result.data = MagicMock()
        mock_result.data.preset = "standard"
        mock_result.data.level = "medium"
        mock_result.data.scope = "project"
        mock_result.data.enabled = False
        mock_result.data.tier = "core"
        ctx.elicit = AsyncMock(return_value=mock_result)

        result = await run_init_wizard(ctx, claude_code_detected=True)
        assert result.config_scope == "project"

    @pytest.mark.asyncio
    async def test_scope_defaults_project_when_not_claude(self):
        """Wizard defaults to project scope when claude_code_detected=False."""
        ctx = MagicMock()
        mock_result = MagicMock()
        mock_result.action = "accept"
        mock_result.data = MagicMock()
        mock_result.data.preset = "standard"
        mock_result.data.level = "medium"
        mock_result.data.enabled = False
        mock_result.data.tier = "core"
        ctx.elicit = AsyncMock(return_value=mock_result)

        result = await run_init_wizard(ctx, claude_code_detected=False)
        assert result.config_scope == "project"
