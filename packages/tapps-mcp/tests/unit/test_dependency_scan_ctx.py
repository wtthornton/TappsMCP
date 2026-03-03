"""Tests for ctx notifications in tapps_dependency_scan."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDependencyScanCtx:
    """Verify ctx notifications in tapps_dependency_scan."""

    @pytest.mark.asyncio
    async def test_ctx_info_called_after_scan(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dependency_scan

        ctx = MagicMock()
        ctx.info = AsyncMock()
        ctx.report_progress = AsyncMock()

        mock_result = MagicMock()
        mock_result.findings = []
        mock_result.scanned_packages = 42
        mock_result.vulnerable_packages = 0
        mock_result.scan_source = "pip-audit"
        mock_result.error = None

        with patch("tapps_mcp.server_analysis_tools._record_call"), \
             patch("tapps_mcp.server_analysis_tools._record_execution"), \
             patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r), \
             patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings, \
             patch("tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock), \
             patch("tapps_mcp.tools.pip_audit.run_pip_audit_async", new_callable=AsyncMock, return_value=mock_result):
            mock_settings.return_value = MagicMock(
                dependency_scan_enabled=True,
                dependency_scan_source="pip-audit",
                dependency_scan_severity_threshold="low",
                dependency_scan_ignore_ids=None,
                project_root="/fake",
            )
            await tapps_dependency_scan(ctx=ctx)

        ctx.info.assert_called_once()
        msg = ctx.info.call_args[0][0]
        assert "0 vulnerabilities" in msg
        assert "42" in msg

    @pytest.mark.asyncio
    async def test_ctx_noop_when_none(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dependency_scan

        mock_result = MagicMock()
        mock_result.findings = []
        mock_result.scanned_packages = 10
        mock_result.vulnerable_packages = 0
        mock_result.scan_source = "pip-audit"
        mock_result.error = None

        with patch("tapps_mcp.server_analysis_tools._record_call"), \
             patch("tapps_mcp.server_analysis_tools._record_execution"), \
             patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r), \
             patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings, \
             patch("tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock), \
             patch("tapps_mcp.tools.pip_audit.run_pip_audit_async", new_callable=AsyncMock, return_value=mock_result):
            mock_settings.return_value = MagicMock(
                dependency_scan_enabled=True,
                dependency_scan_source="pip-audit",
                dependency_scan_severity_threshold="low",
                dependency_scan_ignore_ids=None,
                project_root="/fake",
            )
            result = await tapps_dependency_scan(ctx=None)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ctx_info_exception_suppressed(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_dependency_scan

        ctx = MagicMock()
        ctx.info = AsyncMock(side_effect=RuntimeError("boom"))
        ctx.report_progress = AsyncMock()

        mock_result = MagicMock()
        mock_result.findings = []
        mock_result.scanned_packages = 5
        mock_result.vulnerable_packages = 0
        mock_result.scan_source = "pip-audit"
        mock_result.error = None

        with patch("tapps_mcp.server_analysis_tools._record_call"), \
             patch("tapps_mcp.server_analysis_tools._record_execution"), \
             patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r), \
             patch("tapps_mcp.server_analysis_tools.load_settings") as mock_settings, \
             patch("tapps_mcp.server_analysis_tools.ensure_session_initialized", new_callable=AsyncMock), \
             patch("tapps_mcp.tools.pip_audit.run_pip_audit_async", new_callable=AsyncMock, return_value=mock_result):
            mock_settings.return_value = MagicMock(
                dependency_scan_enabled=True,
                dependency_scan_source="pip-audit",
                dependency_scan_severity_threshold="low",
                dependency_scan_ignore_ids=None,
                project_root="/fake",
            )
            result = await tapps_dependency_scan(ctx=ctx)

        assert result["success"] is True
