"""Tests for ctx.info notifications in tapps_upgrade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUpgradeCtx:
    """Verify ctx.info notifications during tapps_upgrade."""

    @pytest.mark.asyncio
    async def test_ctx_info_called_for_backup_and_updates(self) -> None:
        """ctx.info should emit backup message and per-component updates."""
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        ctx = MagicMock()
        ctx.info = AsyncMock()

        mock_result = {
            "success": True,
            "components": {
                "agents_md": {"action": "merged", "detail": "missing sections: ..."},
                "platforms": [
                    {
                        "host": "claude-code",
                        "components": {
                            "mcp_config": "regenerated",
                            "settings": "created",
                        },
                    },
                ],
            },
            "errors": [],
            "backup": "/fake/.tapps-mcp/backups/20260303",
        }

        with (
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings,
            patch(
                "tapps_mcp.pipeline.upgrade.upgrade_pipeline",
                return_value=mock_result,
            ),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _n, r: r,
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(project_root=Path("/fake"))
            result = await tapps_upgrade(ctx=ctx)

        assert result["success"] is True
        # Should have: "Creating backup...", "Updated AGENTS.md (merged)",
        # "Updated claude-code/mcp_config", "Updated claude-code/settings"
        assert ctx.info.call_count >= 1
        call_messages = [c.args[0] for c in ctx.info.call_args_list]
        assert "Creating backup..." in call_messages

    @pytest.mark.asyncio
    async def test_ctx_noop_when_none(self) -> None:
        """tapps_upgrade should work when ctx is None."""
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        mock_result = {
            "success": True,
            "components": {"agents_md": {"action": "up-to-date"}, "platforms": []},
            "errors": [],
        }

        with (
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings,
            patch(
                "tapps_mcp.pipeline.upgrade.upgrade_pipeline",
                return_value=mock_result,
            ),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _n, r: r,
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(project_root=Path("/fake"))
            result = await tapps_upgrade(ctx=None)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ctx_noop_in_dry_run(self) -> None:
        """ctx.info should not be called in dry_run mode."""
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        ctx = MagicMock()
        ctx.info = AsyncMock()

        mock_result = {
            "success": True,
            "dry_run": True,
            "components": {
                "agents_md": {"action": "needs-update"},
                "platforms": [],
            },
            "errors": [],
        }

        with (
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings,
            patch(
                "tapps_mcp.pipeline.upgrade.upgrade_pipeline",
                return_value=mock_result,
            ),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _n, r: r,
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(project_root=Path("/fake"))
            result = await tapps_upgrade(dry_run=True, ctx=ctx)

        assert result["success"] is True
        ctx.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_ctx_info_exception_suppressed(self) -> None:
        """ctx.info exceptions should be suppressed and not break tapps_upgrade."""
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        ctx = MagicMock()
        ctx.info = AsyncMock(side_effect=RuntimeError("boom"))

        mock_result = {
            "success": True,
            "components": {
                "agents_md": {"action": "created"},
                "platforms": [],
            },
            "errors": [],
        }

        with (
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings,
            patch(
                "tapps_mcp.pipeline.upgrade.upgrade_pipeline",
                return_value=mock_result,
            ),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _n, r: r,
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(project_root=Path("/fake"))
            result = await tapps_upgrade(ctx=ctx)

        # Should still succeed despite ctx.info raising
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ctx_info_agents_md_up_to_date_skipped(self) -> None:
        """ctx.info should NOT emit for agents_md when action is up-to-date."""
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        ctx = MagicMock()
        ctx.info = AsyncMock()

        mock_result = {
            "success": True,
            "components": {
                "agents_md": {"action": "up-to-date"},
                "platforms": [],
            },
            "errors": [],
        }

        with (
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings,
            patch(
                "tapps_mcp.pipeline.upgrade.upgrade_pipeline",
                return_value=mock_result,
            ),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _n, r: r,
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(project_root=Path("/fake"))
            result = await tapps_upgrade(ctx=ctx)

        assert result["success"] is True
        # Only the "Creating backup..." message, no AGENTS.md update message
        call_messages = [c.args[0] for c in ctx.info.call_args_list]
        assert "Creating backup..." in call_messages
        assert all("AGENTS.md" not in m for m in call_messages)
