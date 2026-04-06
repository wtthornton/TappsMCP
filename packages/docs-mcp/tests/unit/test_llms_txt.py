"""Tests for the llms.txt generator (Epic 83)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.generators.llms_txt import LlmsTxtGenerator, LlmsTxtResult
from tests.helpers import make_settings


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_pyproject(root: Path, *, name: str = "my-project", **kwargs: Any) -> None:
    deps = kwargs.get("dependencies", [])
    deps_str = ", ".join(f'"{d}"' for d in deps)
    scripts = kwargs.get("scripts", {})
    scripts_lines = "\n".join(f'{k} = "{v}"' for k, v in scripts.items())
    content = f"""
[project]
name = "{name}"
version = "{kwargs.get('version', '1.0.0')}"
description = "{kwargs.get('description', 'A test project')}"
license = "{kwargs.get('license', 'MIT')}"
requires-python = "{kwargs.get('python_requires', '>=3.12')}"
dependencies = [{deps_str}]

[project.scripts]
{scripts_lines}
"""
    _write(root / "pyproject.toml", content)


# ---------------------------------------------------------------------------
# LlmsTxtGenerator unit tests
# ---------------------------------------------------------------------------


class TestLlmsTxtGeneratorInit:
    def test_default_mode(self) -> None:
        gen = LlmsTxtGenerator()
        assert gen.mode == "compact"

    def test_full_mode(self) -> None:
        gen = LlmsTxtGenerator(mode="full")
        assert gen.mode == "full"

    def test_invalid_mode_defaults_to_compact(self) -> None:
        gen = LlmsTxtGenerator(mode="invalid")
        assert gen.mode == "compact"


class TestLlmsTxtCompact:
    def test_minimal_project(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        gen = LlmsTxtGenerator()
        result = gen.generate(tmp_path)

        assert isinstance(result, LlmsTxtResult)
        assert result.mode == "compact"
        assert result.project_name == "my-project"
        assert result.section_count > 0
        assert "# my-project" in result.content
        assert "A test project" in result.content

    def test_tech_stack_detection(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["fastapi", "pydantic"])
        gen = LlmsTxtGenerator()
        result = gen.generate(tmp_path)

        assert "Tech Stack" in result.content
        assert "FastAPI" in result.content
        assert "Pydantic" in result.content

    def test_entry_points(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, scripts={"mycli": "my_project.cli:main"})
        gen = LlmsTxtGenerator()
        result = gen.generate(tmp_path)

        assert "Entry Points" in result.content
        assert "mycli" in result.content

    def test_key_files(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _write(tmp_path / "README.md", "# Hello")
        _write(tmp_path / "CHANGELOG.md", "# Changes")
        _write(tmp_path / "Dockerfile", "FROM python:3.12")

        gen = LlmsTxtGenerator()
        result = gen.generate(tmp_path)

        assert "Key Files" in result.content
        assert "README.md" in result.content
        assert "Dockerfile" in result.content

    def test_documentation_map(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _write(tmp_path / "README.md", "# Project")
        _write(tmp_path / "docs" / "guide.md", "# Guide")
        _write(tmp_path / "docs" / "api.md", "# API")

        gen = LlmsTxtGenerator()
        result = gen.generate(tmp_path)

        assert "Documentation Map" in result.content
        assert "docs/guide.md" in result.content
        assert "docs/api.md" in result.content

    def test_no_api_summary_in_compact(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        gen = LlmsTxtGenerator(mode="compact")
        result = gen.generate(tmp_path)

        assert "API Summary" not in result.content
        assert "Project Structure" not in result.content


class TestLlmsTxtFull:
    def test_includes_api_summary(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        module_map = MagicMock()
        module_map.total_modules = 15
        module_map.total_packages = 3
        module_map.public_api_count = 42

        gen = LlmsTxtGenerator(mode="full")
        result = gen.generate(tmp_path, module_map=module_map)

        assert "API Summary" in result.content
        assert "Modules: 15" in result.content
        assert "Packages: 3" in result.content
        assert "Public API symbols: 42" in result.content

    def test_includes_project_structure(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _write(tmp_path / "src" / "__init__.py", "")
        (tmp_path / "tests").mkdir()

        gen = LlmsTxtGenerator(mode="full")
        result = gen.generate(tmp_path)

        assert "Project Structure" in result.content
        assert "src/" in result.content

    def test_skips_hidden_and_cache_dirs(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / ".git").mkdir()
        (tmp_path / "node_modules").mkdir()

        gen = LlmsTxtGenerator(mode="full")
        result = gen.generate(tmp_path)

        assert "__pycache__" not in result.content
        assert "node_modules" not in result.content


class TestLlmsTxtEdgeCases:
    def test_empty_project(self, tmp_path: Path) -> None:
        gen = LlmsTxtGenerator()
        result = gen.generate(tmp_path)

        assert result.project_name == tmp_path.name
        assert result.section_count >= 1  # At least title

    def test_node_project(self, tmp_path: Path) -> None:
        _write(tmp_path / "package.json", '{"name": "my-app", "version": "2.0.0"}')
        gen = LlmsTxtGenerator()
        result = gen.generate(tmp_path)

        assert "my-app" in result.content
        assert "Node.js" in result.content

    def test_docker_detection(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _write(tmp_path / "Dockerfile", "FROM python:3.12")

        gen = LlmsTxtGenerator()
        result = gen.generate(tmp_path)

        assert "Docker" in result.content

    def test_github_actions_detection(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        (tmp_path / ".github" / "workflows").mkdir(parents=True)

        gen = LlmsTxtGenerator()
        result = gen.generate(tmp_path)

        assert "GitHub Actions" in result.content


# ---------------------------------------------------------------------------
# MCP tool handler tests
# ---------------------------------------------------------------------------


class TestDocsGenerateLlmsTxtTool:
    async def test_compact_mode(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        from docs_mcp.server_gen_tools import docs_generate_llms_txt

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_llms_txt(mode="compact", project_root=str(tmp_path))

        assert result["success"] is True
        assert result["data"]["mode"] == "compact"
        # Tier 1 (written_to) or Tier 2 (content inline) depending on write mode
        assert "written_to" in result["data"] or "content" in result["data"]

    async def test_full_mode(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _write(tmp_path / "src" / "__init__.py", "")
        from docs_mcp.server_gen_tools import docs_generate_llms_txt

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_llms_txt(mode="full", project_root=str(tmp_path))

        assert result["success"] is True
        assert result["data"]["mode"] == "full"

    async def test_invalid_mode(self, tmp_path: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_llms_txt

        result = await docs_generate_llms_txt(mode="bad")
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_MODE"

    async def test_invalid_root(self) -> None:
        from docs_mcp.server_gen_tools import docs_generate_llms_txt

        result = await docs_generate_llms_txt(project_root="/nonexistent/path")
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    async def test_output_path_content_return(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        from docs_mcp.server_gen_tools import docs_generate_llms_txt

        with (
            patch("docs_mcp.server_gen_tools._get_settings") as mock_settings,
            patch("docs_mcp.server_helpers.can_write_to_project", return_value=False),
        ):
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_llms_txt(
                mode="compact",
                output_path="llms.txt",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert "content" in result["data"]
