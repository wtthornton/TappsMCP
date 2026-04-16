"""Tests for ctx.info notifications in tapps_dependency_graph."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDepGraphCtx:
    """Verify ctx.info phase notifications in tapps_dependency_graph."""

    @pytest.mark.asyncio
    async def test_ctx_info_called_per_phase(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dependency_graph

        ctx = MagicMock()
        ctx.info = AsyncMock()

        mock_graph = MagicMock()
        mock_graph.modules = {"a": MagicMock(), "b": MagicMock()}
        mock_graph.edges = []
        mock_graph.external_imports = {}

        mock_analysis = MagicMock()
        mock_analysis.cycles = []
        mock_analysis.runtime_cycles = 0
        mock_analysis.type_checking_cycles = 0

        mock_couplings = []

        with (
            patch("tapps_mcp.server_analysis_tools._record_call"),
            patch("tapps_mcp.server_analysis_tools._record_execution"),
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock
            ),
            patch("tapps_mcp.project.import_graph.build_import_graph", return_value=mock_graph),
            patch("tapps_mcp.project.cycle_detector.detect_cycles", return_value=mock_analysis),
            patch("tapps_mcp.project.cycle_detector.suggest_cycle_fixes", return_value=[]),
            patch(
                "tapps_mcp.project.coupling_metrics.calculate_coupling", return_value=mock_couplings
            ),
            patch("tapps_mcp.project.coupling_metrics.suggest_coupling_fixes", return_value=[]),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(project_root=Path("/fake"))
            result = await tapps_dependency_graph(
                detect_cycles=True, include_coupling=True, ctx=ctx
            )

        assert result["success"] is True
        # Should have: "Building import graph..." + cycle result + coupling result + final
        assert ctx.info.call_count >= 3

    @pytest.mark.asyncio
    async def test_ctx_info_skips_disabled_phases(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dependency_graph

        ctx = MagicMock()
        ctx.info = AsyncMock()

        mock_graph = MagicMock()
        mock_graph.modules = {"a": MagicMock()}
        mock_graph.edges = []
        mock_graph.external_imports = {}

        with (
            patch("tapps_mcp.server_analysis_tools._record_call"),
            patch("tapps_mcp.server_analysis_tools._record_execution"),
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock
            ),
            patch("tapps_mcp.project.import_graph.build_import_graph", return_value=mock_graph),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(project_root=Path("/fake"))
            result = await tapps_dependency_graph(
                detect_cycles=False, include_coupling=False, ctx=ctx
            )

        assert result["success"] is True
        # No cycle/coupling messages, just "Building..." and "Analysis complete"
        messages = [str(c) for c in ctx.info.call_args_list]
        assert not any("Cycle" in m for m in messages)
        assert not any("Coupling" in m for m in messages)

    @pytest.mark.asyncio
    async def test_ctx_noop_when_none(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dependency_graph

        mock_graph = MagicMock()
        mock_graph.modules = {}
        mock_graph.edges = []
        mock_graph.external_imports = {}

        with (
            patch("tapps_mcp.server_analysis_tools._record_call"),
            patch("tapps_mcp.server_analysis_tools._record_execution"),
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock
            ),
            patch("tapps_mcp.project.import_graph.build_import_graph", return_value=mock_graph),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(project_root=Path("/fake"))
            result = await tapps_dependency_graph(
                detect_cycles=False, include_coupling=False, ctx=None
            )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ctx_info_exception_suppressed(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dependency_graph

        ctx = MagicMock()
        ctx.info = AsyncMock(side_effect=RuntimeError("boom"))

        mock_graph = MagicMock()
        mock_graph.modules = {}
        mock_graph.edges = []
        mock_graph.external_imports = {}

        with (
            patch("tapps_mcp.server_analysis_tools._record_call"),
            patch("tapps_mcp.server_analysis_tools._record_execution"),
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock
            ),
            patch("tapps_mcp.project.import_graph.build_import_graph", return_value=mock_graph),
        ):
            from pathlib import Path

            mock_settings.return_value = MagicMock(project_root=Path("/fake"))
            result = await tapps_dependency_graph(
                detect_cycles=False, include_coupling=False, ctx=ctx
            )

        assert result["success"] is True
