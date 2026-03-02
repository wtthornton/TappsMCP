"""Tests for Epic 37.1 — Interactive first-run wizard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.common.elicitation import (
    WizardResult,
    run_init_wizard,
)


@dataclass
class _ElicitResult:
    action: str
    data: Any = None


def _make_ctx(responses: list[_ElicitResult]) -> MagicMock:
    """Create a mock MCP Context that yields sequential elicit responses."""
    ctx = MagicMock()
    ctx.elicit = AsyncMock(side_effect=responses)
    return ctx


class TestWizardResult:
    def test_defaults(self) -> None:
        r = WizardResult()
        assert r.quality_preset == "standard"
        assert r.engagement_level == "medium"
        assert r.agent_teams is False
        assert r.skill_tier == "full"
        assert r.prompt_hooks is False
        assert r.completed is False


class TestRunInitWizard:
    @pytest.mark.asyncio()
    async def test_full_wizard_completion(self) -> None:
        responses = [
            _ElicitResult("accept", MagicMock(preset="strict")),
            _ElicitResult("accept", MagicMock(level="high")),
            _ElicitResult("accept", MagicMock(enabled=True)),
            _ElicitResult("accept", MagicMock(tier="core")),
            _ElicitResult("accept", MagicMock(enabled=True)),
        ]
        ctx = _make_ctx(responses)
        result = await run_init_wizard(ctx)

        assert result.completed is True
        assert result.quality_preset == "strict"
        assert result.engagement_level == "high"
        assert result.agent_teams is True
        assert result.skill_tier == "core"
        assert result.prompt_hooks is True

    @pytest.mark.asyncio()
    async def test_decline_on_first_question(self) -> None:
        responses = [
            _ElicitResult("decline"),
        ]
        ctx = _make_ctx(responses)
        result = await run_init_wizard(ctx)

        assert result.completed is False
        assert result.quality_preset == "standard"  # default

    @pytest.mark.asyncio()
    async def test_decline_on_second_question(self) -> None:
        responses = [
            _ElicitResult("accept", MagicMock(preset="framework")),
            _ElicitResult("decline"),
        ]
        ctx = _make_ctx(responses)
        result = await run_init_wizard(ctx)

        assert result.completed is False
        assert result.quality_preset == "framework"  # kept first answer
        assert result.engagement_level == "medium"  # default

    @pytest.mark.asyncio()
    async def test_exception_returns_defaults(self) -> None:
        ctx = MagicMock()
        ctx.elicit = AsyncMock(side_effect=Exception("unsupported"))
        result = await run_init_wizard(ctx)

        assert result.completed is False

    @pytest.mark.asyncio()
    async def test_each_question_maps_correctly(self) -> None:
        """Verify each wizard question produces the expected field."""
        responses = [
            _ElicitResult("accept", MagicMock(preset="standard")),
            _ElicitResult("accept", MagicMock(level="low")),
            _ElicitResult("accept", MagicMock(enabled=False)),
            _ElicitResult("accept", MagicMock(tier="full")),
            _ElicitResult("accept", MagicMock(enabled=False)),
        ]
        ctx = _make_ctx(responses)
        result = await run_init_wizard(ctx)

        assert result.completed is True
        assert result.quality_preset == "standard"
        assert result.engagement_level == "low"
        assert result.agent_teams is False
        assert result.skill_tier == "full"
        assert result.prompt_hooks is False


class TestMaybeRunWizard:
    @pytest.mark.asyncio()
    async def test_skips_when_params_provided(self) -> None:
        from tapps_mcp.server_pipeline_tools import _maybe_run_wizard

        ctx = MagicMock()
        result = await _maybe_run_wizard(
            ctx,
            llm_engagement_level="high",
            platform="",
            agent_teams=False,
        )
        assert result is None

    @pytest.mark.asyncio()
    async def test_skips_when_platform_set(self) -> None:
        from tapps_mcp.server_pipeline_tools import _maybe_run_wizard

        ctx = MagicMock()
        result = await _maybe_run_wizard(
            ctx,
            llm_engagement_level=None,
            platform="claude",
            agent_teams=False,
        )
        assert result is None

    @pytest.mark.asyncio()
    async def test_skips_when_config_exists(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _maybe_run_wizard

        (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")

        ctx = MagicMock()
        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(project_root=tmp_path)
            result = await _maybe_run_wizard(
                ctx,
                llm_engagement_level=None,
                platform="",
                agent_teams=False,
            )
        assert result is None

    @pytest.mark.asyncio()
    async def test_runs_wizard_on_fresh_project(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _maybe_run_wizard

        responses = [
            _ElicitResult("accept", MagicMock(preset="strict")),
            _ElicitResult("accept", MagicMock(level="high")),
            _ElicitResult("accept", MagicMock(enabled=False)),
            _ElicitResult("accept", MagicMock(tier="full")),
            _ElicitResult("accept", MagicMock(enabled=False)),
        ]
        ctx = _make_ctx(responses)

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(project_root=tmp_path)
            result = await _maybe_run_wizard(
                ctx,
                llm_engagement_level=None,
                platform="",
                agent_teams=False,
            )

        assert result is not None
        assert result.completed is True
        assert result.engagement_level == "high"

    @pytest.mark.asyncio()
    async def test_wizard_persists_yaml(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _maybe_run_wizard

        responses = [
            _ElicitResult("accept", MagicMock(preset="framework")),
            _ElicitResult("accept", MagicMock(level="low")),
            _ElicitResult("accept", MagicMock(enabled=True)),
            _ElicitResult("accept", MagicMock(tier="core")),
            _ElicitResult("accept", MagicMock(enabled=True)),
        ]
        ctx = _make_ctx(responses)

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(project_root=tmp_path)
            await _maybe_run_wizard(
                ctx,
                llm_engagement_level=None,
                platform="",
                agent_teams=False,
            )

        yaml_path = tmp_path / ".tapps-mcp.yaml"
        assert yaml_path.exists()
        content = yaml_path.read_text(encoding="utf-8")
        assert "low" in content
        assert "framework" in content
