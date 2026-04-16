"""Tests for ctx.info and heartbeat in tapps_report."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestReportCtxInfo:
    """Verify ctx.info notifications in tapps_report."""

    @pytest.mark.asyncio
    async def test_ctx_info_called_per_file(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_report

        ctx = MagicMock()
        ctx.info = AsyncMock()
        ctx.report_progress = AsyncMock()

        mock_score = MagicMock()
        mock_score.overall_score = 85.0
        mock_score.security_issues = []

        mock_gate = MagicMock()
        mock_gate.passed = True
        mock_gate.failures = []

        with (
            patch("tapps_mcp.server_analysis_tools._record_call"),
            patch("tapps_mcp.server_analysis_tools._record_execution"),
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server_helpers._get_scorer") as mock_get_scorer,
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(
                project_root=Path("/fake/project"),
                quality_preset="standard",
            )
            mock_scorer = MagicMock()
            mock_scorer.score_file = AsyncMock(return_value=mock_score)
            mock_get_scorer.return_value = mock_scorer

            with (
                patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
                patch("tapps_core.common.utils.should_skip_path", return_value=False),
                patch(
                    "pathlib.Path.rglob",
                    return_value=[Path("/fake/project/a.py"), Path("/fake/project/b.py")],
                ),
                patch("tapps_mcp.project.report.generate_report", return_value={"report": "ok"}),
            ):
                result = await tapps_report(report_format="json", max_files=5, ctx=ctx)

        assert result["success"] is True
        assert ctx.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_ctx_noop_when_none(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_report

        with (
            patch("tapps_mcp.server_analysis_tools._record_call"),
            patch("tapps_mcp.server_analysis_tools._record_execution"),
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server_helpers._get_scorer") as mock_get_scorer,
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"), quality_preset="standard"
            )
            mock_scorer = MagicMock()
            mock_score = MagicMock(overall_score=80.0, security_issues=[])
            mock_scorer.score_file = AsyncMock(return_value=mock_score)
            mock_get_scorer.return_value = mock_scorer
            mock_gate = MagicMock(passed=True, failures=[])

            with (
                patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
                patch("tapps_core.common.utils.should_skip_path", return_value=False),
                patch("pathlib.Path.rglob", return_value=[Path("/fake/a.py")]),
                patch("tapps_mcp.project.report.generate_report", return_value={"report": "ok"}),
            ):
                result = await tapps_report(report_format="json", ctx=None)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ctx_info_exception_suppressed(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_report

        ctx = MagicMock()
        ctx.info = AsyncMock(side_effect=RuntimeError("boom"))
        ctx.report_progress = AsyncMock()

        with (
            patch("tapps_mcp.server_analysis_tools._record_call"),
            patch("tapps_mcp.server_analysis_tools._record_execution"),
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server_helpers._get_scorer") as mock_get_scorer,
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"), quality_preset="standard"
            )
            mock_scorer = MagicMock()
            mock_score = MagicMock(overall_score=80.0, security_issues=[])
            mock_scorer.score_file = AsyncMock(return_value=mock_score)
            mock_get_scorer.return_value = mock_scorer
            mock_gate = MagicMock(passed=True, failures=[])

            with (
                patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
                patch("tapps_core.common.utils.should_skip_path", return_value=False),
                patch("pathlib.Path.rglob", return_value=[Path("/fake/a.py")]),
                patch("tapps_mcp.project.report.generate_report", return_value={"report": "ok"}),
            ):
                result = await tapps_report(report_format="json", ctx=ctx)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_single_file_mode_no_ctx_calls(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_report

        ctx = MagicMock()
        ctx.info = AsyncMock()

        with (
            patch("tapps_mcp.server_analysis_tools._record_call"),
            patch("tapps_mcp.server_analysis_tools._record_execution"),
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server_helpers._get_scorer") as mock_get_scorer,
            patch("tapps_mcp.server_analysis_tools._validate_file_path_lazy") as mock_validate,
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"), quality_preset="standard"
            )
            mock_validate.return_value = Path("/fake/single.py")
            mock_scorer = MagicMock()
            mock_score = MagicMock(overall_score=80.0, security_issues=[])
            mock_scorer.score_file = AsyncMock(return_value=mock_score)
            mock_get_scorer.return_value = mock_scorer
            mock_gate = MagicMock(passed=True, failures=[])

            with (
                patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
                patch("tapps_mcp.project.report.generate_report", return_value={"report": "ok"}),
            ):
                result = await tapps_report(file_path="/fake/single.py", ctx=ctx)

        assert result["success"] is True
        ctx.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_ctx_info_message_contains_filename(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_report

        ctx = MagicMock()
        ctx.info = AsyncMock()
        ctx.report_progress = AsyncMock()

        mock_score = MagicMock(overall_score=75.0, security_issues=[])
        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_analysis_tools._record_call"),
            patch("tapps_mcp.server_analysis_tools._record_execution"),
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server_helpers._get_scorer") as mock_get_scorer,
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock
            ),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"), quality_preset="standard"
            )
            mock_scorer = MagicMock()
            mock_scorer.score_file = AsyncMock(return_value=mock_score)
            mock_get_scorer.return_value = mock_scorer

            with (
                patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
                patch("tapps_core.common.utils.should_skip_path", return_value=False),
                patch("pathlib.Path.rglob", return_value=[Path("/fake/project/myfile.py")]),
                patch("tapps_mcp.project.report.generate_report", return_value={"report": "ok"}),
            ):
                await tapps_report(report_format="json", max_files=5, ctx=ctx)

        found = any("myfile.py" in str(c) for c in ctx.info.call_args_list)
        assert found, f"Expected 'myfile.py' in ctx.info calls: {ctx.info.call_args_list}"
