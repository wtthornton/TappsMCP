"""Tests for docs_session_start tool."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestDocsSessionStart:
    @pytest.mark.asyncio
    async def test_session_start_returns_success(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(sample_project))
        assert result["success"] is True
        assert result["tool"] == "docs_session_start"

    @pytest.mark.asyncio
    async def test_session_start_detects_readme(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(sample_project))
        data = result["data"]

        existing_paths = [d["path"] for d in data["existing_docs"]]
        assert "README.md" in existing_paths

    @pytest.mark.asyncio
    async def test_session_start_recommends_missing_docs(
        self, sample_project: Path
    ) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(sample_project))
        data = result["data"]

        # sample_project has README but no CHANGELOG, LICENSE, etc.
        assert "CHANGELOG.md" in data["missing_recommended"]

    @pytest.mark.asyncio
    async def test_session_start_data_shape(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(sample_project))
        data = result["data"]

        assert "project_name" in data
        assert "project_root" in data
        assert "docs_config" in data
        assert "existing_docs" in data
        assert "missing_recommended" in data
        assert "recommendations" in data

    @pytest.mark.asyncio
    async def test_session_start_records_call(self, sample_project: Path) -> None:
        from docs_mcp.server import _tool_calls, docs_session_start

        await docs_session_start(project_root=str(sample_project))
        assert _tool_calls.get("docs_session_start", 0) >= 1

    @pytest.mark.asyncio
    async def test_session_start_detects_project_name(
        self, sample_project: Path
    ) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(sample_project))
        assert result["data"]["project_name"] == "test-project"

    @pytest.mark.asyncio
    async def test_session_start_has_docs_config(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(sample_project))
        config = result["data"]["docs_config"]

        assert "output_dir" in config
        assert "default_style" in config
        assert "default_format" in config
        assert "include_toc" in config
        assert "include_badges" in config
        assert "changelog_format" in config
        assert "adr_format" in config
        assert "diagram_format" in config
        assert "git_log_limit" in config

    @pytest.mark.asyncio
    async def test_session_start_has_elapsed_ms(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(sample_project))
        assert "elapsed_ms" in result
        assert isinstance(result["elapsed_ms"], int)
        assert result["elapsed_ms"] >= 0

    @pytest.mark.asyncio
    async def test_session_start_well_documented_project(
        self, docs_project: Path
    ) -> None:
        from docs_mcp.server import docs_session_start

        result = await docs_session_start(project_root=str(docs_project))
        data = result["data"]

        # Well-documented project should have fewer missing recommendations
        existing_paths = [d["path"] for d in data["existing_docs"]]
        assert "README.md" in existing_paths
        assert "CHANGELOG.md" in existing_paths
        assert "CONTRIBUTING.md" in existing_paths
