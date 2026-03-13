"""Tests for DocsMCP content-return mode — Epic 87 Story 87.4."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from docs_mcp.server_helpers import (
    build_generator_manifest,
    can_write_to_project,
)


class TestCanWriteToProject:
    """Test write mode detection helper."""

    def test_writable_dir(self, tmp_path: Path) -> None:
        assert can_write_to_project(tmp_path) is True

    def test_content_return_via_env(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            assert can_write_to_project(tmp_path) is False

    def test_direct_via_env(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "direct"}):
            assert can_write_to_project(tmp_path) is True


class TestBuildGeneratorManifest:
    """Test manifest builder for generators."""

    def test_manifest_structure(self) -> None:
        manifest = build_generator_manifest(
            "docs_generate_readme",
            "# README\n",
            "README.md",
            description="Project README.",
        )

        assert manifest["mode"] == "content_return"
        assert manifest["file_count"] == 1
        assert len(manifest["files"]) == 1
        assert manifest["files"][0]["path"] == "README.md"
        assert manifest["files"][0]["content"] == "# README\n"
        assert manifest["files"][0]["mode"] == "create"
        assert "agent_instructions" in manifest

    def test_persona_for_readme(self) -> None:
        manifest = build_generator_manifest(
            "docs_generate_readme", "content", "README.md"
        )
        persona = manifest["agent_instructions"]["persona"]
        assert "Technical writer" in persona

    def test_persona_for_changelog(self) -> None:
        manifest = build_generator_manifest(
            "docs_generate_changelog", "content", "CHANGELOG.md"
        )
        persona = manifest["agent_instructions"]["persona"]
        assert "Release manager" in persona

    def test_unknown_tool_gets_default_persona(self) -> None:
        manifest = build_generator_manifest(
            "docs_generate_unknown", "content", "output.md"
        )
        persona = manifest["agent_instructions"]["persona"]
        assert "Documentation generator" in persona


class TestGeneratorContentReturn:
    """Integration tests for generators in content-return mode."""

    def test_onboarding_content_return(self, tmp_path: Path) -> None:
        """docs_generate_onboarding returns manifest when can't write."""
        import asyncio

        from docs_mcp.server_gen_tools import docs_generate_onboarding

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = asyncio.get_event_loop().run_until_complete(
                docs_generate_onboarding(project_root=str(tmp_path))
            )

        data = result["data"]
        assert data.get("content_return") is True
        assert "file_manifest" in data
        assert data["file_manifest"]["file_count"] == 1
        assert "content" in data  # Content still in response
        # No files should be written
        assert not list(tmp_path.rglob("*.md"))

    def test_contributing_content_return(self, tmp_path: Path) -> None:
        import asyncio

        from docs_mcp.server_gen_tools import docs_generate_contributing

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = asyncio.get_event_loop().run_until_complete(
                docs_generate_contributing(project_root=str(tmp_path))
            )

        data = result["data"]
        assert data.get("content_return") is True
        assert "file_manifest" in data

    def test_changelog_content_return_with_output_path(self, tmp_path: Path) -> None:
        """Optional-write generators include manifest when output_path + Docker."""
        import asyncio

        from docs_mcp.server_gen_tools import docs_generate_changelog

        # Need a git repo for changelog
        (tmp_path / ".git").mkdir()

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = asyncio.get_event_loop().run_until_complete(
                docs_generate_changelog(
                    output_path="CHANGELOG.md",
                    project_root=str(tmp_path),
                )
            )

        data = result["data"]
        assert data.get("content_return") is True
        assert "file_manifest" in data
        assert not (tmp_path / "CHANGELOG.md").exists()

    def test_changelog_no_manifest_without_output_path(self, tmp_path: Path) -> None:
        """Optional-write generators skip manifest when no output_path."""
        import asyncio

        from docs_mcp.server_gen_tools import docs_generate_changelog

        (tmp_path / ".git").mkdir()

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = asyncio.get_event_loop().run_until_complete(
                docs_generate_changelog(project_root=str(tmp_path))
            )

        data = result["data"]
        # No output_path, so no manifest — content is just returned normally
        assert data.get("content_return") is None
        assert "file_manifest" not in data
        assert "content" in data

    def test_direct_write_unchanged(self, tmp_path: Path) -> None:
        """Direct-write mode still writes files normally."""
        import asyncio

        from docs_mcp.server_gen_tools import docs_generate_contributing

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            result = asyncio.get_event_loop().run_until_complete(
                docs_generate_contributing(project_root=str(tmp_path))
            )

        data = result["data"]
        assert data.get("content_return") is None
        assert "written_to" in data
        assert (tmp_path / "CONTRIBUTING.md").exists()

    def test_readme_content_return(self, tmp_path: Path) -> None:
        """README generator returns manifest in content-return mode."""
        import asyncio

        from docs_mcp.server_gen_tools import docs_generate_readme

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = asyncio.get_event_loop().run_until_complete(
                docs_generate_readme(project_root=str(tmp_path))
            )

        data = result["data"]
        assert data.get("content_return") is True
        assert "file_manifest" in data
        assert not (tmp_path / "README.md").exists()
