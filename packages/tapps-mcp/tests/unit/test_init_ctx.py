"""Tests for ctx.info notifications in tapps_init."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestInitCtxInfo:
    """Verify ctx.info notifications during tapps_init."""

    @pytest.mark.asyncio
    async def test_ctx_info_called_for_created_files(self) -> None:
        """ctx.info should be called for each file that was created."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        ctx = MagicMock()
        ctx.info = AsyncMock()

        mock_init_result = {
            "success": True,
            "created": ["AGENTS.md", "TECH_STACK.md", ".claude/settings.json"],
            "skipped": [],
            "errors": [],
        }

        with (
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _n, r: r,
            ),
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings,
            patch(
                "tapps_mcp.common.elicitation.elicit_init_confirmation",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "tapps_mcp.server_pipeline_tools._maybe_run_wizard",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "tapps_mcp.pipeline.init.bootstrap_pipeline",
                return_value=mock_init_result,
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"),
                quality_preset="standard",
                llm_engagement_level="medium",
                destructive_guard=False,
            )
            result = await tapps_init(
                create_handoff=False,
                create_runlog=False,
                warm_cache_from_tech_stack=False,
                warm_expert_rag_from_tech_stack=False,
                ctx=ctx,
            )

        assert result["success"] is True
        # Should have ctx.info calls for each of the 3 created files
        assert ctx.info.call_count == 3
        call_messages = [c.args[0] for c in ctx.info.call_args_list]
        assert "Created AGENTS.md" in call_messages
        assert "Created TECH_STACK.md" in call_messages
        assert "Created .claude/settings.json" in call_messages

    @pytest.mark.asyncio
    async def test_ctx_noop_when_none(self) -> None:
        """tapps_init should work fine when ctx is None (no ctx.info calls)."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_init_result = {
            "success": True,
            "created": ["AGENTS.md"],
            "skipped": [],
            "errors": [],
        }

        with (
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _n, r: r,
            ),
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings,
            patch(
                "tapps_mcp.pipeline.init.bootstrap_pipeline",
                return_value=mock_init_result,
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"),
                quality_preset="standard",
                llm_engagement_level="medium",
                destructive_guard=False,
            )
            # ctx=None skips the elicitation and wizard code paths entirely
            result = await tapps_init(
                create_handoff=False,
                create_runlog=False,
                warm_cache_from_tech_stack=False,
                warm_expert_rag_from_tech_stack=False,
                ctx=None,
            )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ctx_info_exception_suppressed(self) -> None:
        """ctx.info exceptions should be suppressed and not break tapps_init."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        ctx = MagicMock()
        ctx.info = AsyncMock(side_effect=RuntimeError("boom"))

        mock_init_result = {
            "success": True,
            "created": ["AGENTS.md"],
            "skipped": [],
            "errors": [],
        }

        with (
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _n, r: r,
            ),
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings,
            patch(
                "tapps_mcp.common.elicitation.elicit_init_confirmation",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "tapps_mcp.server_pipeline_tools._maybe_run_wizard",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "tapps_mcp.pipeline.init.bootstrap_pipeline",
                return_value=mock_init_result,
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"),
                quality_preset="standard",
                llm_engagement_level="medium",
                destructive_guard=False,
            )
            result = await tapps_init(
                create_handoff=False,
                create_runlog=False,
                warm_cache_from_tech_stack=False,
                warm_expert_rag_from_tech_stack=False,
                ctx=ctx,
            )

        # Should still succeed despite ctx.info raising
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ctx_info_not_called_for_empty_created(self) -> None:
        """ctx.info should not be called when no files are created."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        ctx = MagicMock()
        ctx.info = AsyncMock()

        mock_init_result = {
            "success": True,
            "created": [],
            "skipped": ["AGENTS.md"],
            "errors": [],
        }

        with (
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _n, r: r,
            ),
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings,
            patch(
                "tapps_mcp.common.elicitation.elicit_init_confirmation",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "tapps_mcp.server_pipeline_tools._maybe_run_wizard",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "tapps_mcp.pipeline.init.bootstrap_pipeline",
                return_value=mock_init_result,
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"),
                quality_preset="standard",
                llm_engagement_level="medium",
                destructive_guard=False,
            )
            result = await tapps_init(
                create_handoff=False,
                create_runlog=False,
                warm_cache_from_tech_stack=False,
                warm_expert_rag_from_tech_stack=False,
                ctx=ctx,
            )

        assert result["success"] is True
        ctx.info.assert_not_called()
