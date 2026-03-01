"""Integration tests for DocsMCP server.

Tests the full tool flow: tool call -> validation -> execution -> response.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
class TestSessionStartFullFlow:
    @pytest.mark.asyncio
    async def test_session_start_full_flow(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(sample_project))

        assert result["success"] is True
        assert result["tool"] == "docs_session_start"
        assert isinstance(result["elapsed_ms"], int)

        data = result["data"]
        assert data["project_name"] == "test-project"
        assert "README.md" in [d["path"] for d in data["existing_docs"]]

    @pytest.mark.asyncio
    async def test_session_start_with_docs_project(self, docs_project: Path) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(docs_project))

        assert result["success"] is True
        data = result["data"]
        assert data["project_name"] == "docs-test-project"
        assert len(data["existing_docs"]) >= 5


@pytest.mark.integration
class TestProjectScanFullFlow:
    @pytest.mark.asyncio
    async def test_project_scan_full_flow(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(sample_project))

        assert result["success"] is True
        assert result["tool"] == "docs_project_scan"
        assert isinstance(result["elapsed_ms"], int)

        data = result["data"]
        assert data["total_docs"] >= 1
        assert data["completeness_score"] >= 15  # README = 15 pts
        assert data["critical_docs"]["README.md"]["exists"] is True

    @pytest.mark.asyncio
    async def test_project_scan_completeness_comparison(
        self, sample_project: Path, docs_project: Path
    ) -> None:
        from docs_mcp.server import docs_project_scan

        minimal = await docs_project_scan(project_root=str(sample_project))
        full = await docs_project_scan(project_root=str(docs_project))

        # Well-documented project should score higher
        assert (
            full["data"]["completeness_score"]
            > minimal["data"]["completeness_score"]
        )


@pytest.mark.integration
class TestMCPInstanceIntegration:
    def test_mcp_has_tools_registered(self) -> None:
        from docs_mcp.server import mcp

        try:
            tool_manager = mcp._tool_manager
            tools = list(tool_manager._tools.keys())
            assert "docs_session_start" in tools
            assert "docs_project_scan" in tools
        except AttributeError:
            # Internal API may change; verify functions exist instead
            from docs_mcp.server import docs_project_scan, docs_session_start

            assert callable(docs_session_start)
            assert callable(docs_project_scan)
