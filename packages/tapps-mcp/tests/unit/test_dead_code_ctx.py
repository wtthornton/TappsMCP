"""Tests for ctx notifications in tapps_dead_code."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDeadCodeCtx:
    """Verify ctx.info notifications in tapps_dead_code."""

    @pytest.mark.asyncio
    async def test_ctx_info_called_for_project_scope(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dead_code

        ctx = MagicMock()
        ctx.info = AsyncMock()

        mock_result = MagicMock()
        mock_result.findings = []
        mock_result.files_scanned = 5
        mock_result.degraded = False

        with patch("tapps_mcp.server_analysis_tools._record_call"), \
             patch("tapps_mcp.server_analysis_tools._record_execution"), \
             patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r), \
             patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings, \
             patch("tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock), \
             patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True), \
             patch("tapps_mcp.tools.vulture.collect_python_files", return_value=["/a.py", "/b.py"]), \
             patch("tapps_mcp.tools.vulture.run_vulture_multi_async", new_callable=AsyncMock, return_value=mock_result):
            from pathlib import Path
            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"),
                dead_code_whitelist_patterns=[],
            )
            await tapps_dead_code(scope="project", ctx=ctx)

        assert ctx.info.call_count >= 1

    @pytest.mark.asyncio
    async def test_ctx_info_not_called_for_file_scope(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dead_code

        ctx = MagicMock()
        ctx.info = AsyncMock()

        with patch("tapps_mcp.server_analysis_tools._record_call"), \
             patch("tapps_mcp.server_analysis_tools._record_execution"), \
             patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r), \
             patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings, \
             patch("tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock), \
             patch("tapps_mcp.server_analysis_tools._validate_file_path_lazy") as mock_validate, \
             patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True), \
             patch("tapps_mcp.tools.vulture.run_vulture_async", new_callable=AsyncMock, return_value=[]):
            from pathlib import Path
            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"),
                dead_code_whitelist_patterns=[],
            )
            mock_validate.return_value = Path("/fake/test.py")
            await tapps_dead_code(file_path="/fake/test.py", scope="file", ctx=ctx)

        ctx.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_ctx_noop_when_none(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dead_code

        mock_result = MagicMock()
        mock_result.findings = []
        mock_result.files_scanned = 3
        mock_result.degraded = False

        with patch("tapps_mcp.server_analysis_tools._record_call"), \
             patch("tapps_mcp.server_analysis_tools._record_execution"), \
             patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r), \
             patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings, \
             patch("tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock), \
             patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True), \
             patch("tapps_mcp.tools.vulture.collect_python_files", return_value=["/a.py"]), \
             patch("tapps_mcp.tools.vulture.run_vulture_multi_async", new_callable=AsyncMock, return_value=mock_result):
            from pathlib import Path
            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"),
                dead_code_whitelist_patterns=[],
            )
            result = await tapps_dead_code(scope="project", ctx=None)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ctx_info_exception_suppressed(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dead_code

        ctx = MagicMock()
        ctx.info = AsyncMock(side_effect=RuntimeError("boom"))

        mock_result = MagicMock()
        mock_result.findings = []
        mock_result.files_scanned = 2
        mock_result.degraded = False

        with patch("tapps_mcp.server_analysis_tools._record_call"), \
             patch("tapps_mcp.server_analysis_tools._record_execution"), \
             patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r), \
             patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings, \
             patch("tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock), \
             patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True), \
             patch("tapps_mcp.tools.vulture.collect_python_files", return_value=["/a.py"]), \
             patch("tapps_mcp.tools.vulture.run_vulture_multi_async", new_callable=AsyncMock, return_value=mock_result):
            from pathlib import Path
            mock_settings.return_value = MagicMock(
                project_root=Path("/fake"),
                dead_code_whitelist_patterns=[],
            )
            result = await tapps_dead_code(scope="project", ctx=ctx)

        assert result["success"] is True
