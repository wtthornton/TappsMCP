"""Tests for architecture templates, doc index, and cross-ref validation (Epic 85)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from docs_mcp.generators.purpose import PurposeGenerator
from docs_mcp.generators.doc_index import DocIndexGenerator
from docs_mcp.validators.cross_ref import CrossRefValidator
from tests.helpers import make_settings


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_pyproject(root: Path, **kwargs: Any) -> None:
    deps = kwargs.get("dependencies", [])
    deps_str = ", ".join(f'"{d}"' for d in deps)
    content = f"""
[project]
name = "{kwargs.get('name', 'my-project')}"
version = "1.0.0"
description = "{kwargs.get('description', 'A test project')}"
dependencies = [{deps_str}]
"""
    if "python_version" in kwargs:
        content += f'\nrequires-python = ">={kwargs["python_version"]}"\n'
    _write(root / "pyproject.toml", content)


# ---------------------------------------------------------------------------
# PurposeGenerator (Epic 85.1)
# ---------------------------------------------------------------------------


class TestPurposeGenerator:
    def test_basic_generation(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, description="A quality tool")
        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert result.content
        assert not result.degraded
        assert "purpose" in result.sections
        assert "principles" in result.sections
        assert "decisions" in result.sections
        assert "audience" in result.sections
        assert "quality_attributes" in result.sections
        assert "my-project" in result.content
        assert "A quality tool" in result.content

    def test_infers_principles_from_deps(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["fastapi", "pydantic", "structlog"])
        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "API-first" in result.content
        assert "Data validation" in result.content
        assert "Structured logging" in result.content

    def test_detects_monorepo(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _make_pyproject(tmp_path / "packages" / "core", name="core")
        _make_pyproject(tmp_path / "packages" / "api", name="api")

        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "Monorepo" in result.content

    def test_detects_docker(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _write(tmp_path / "Dockerfile", "FROM python:3.12")

        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "Docker" in result.content

    def test_detects_quality_attributes(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()

        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "Testability" in result.content
        assert "Maintainability" in result.content

    def test_invalid_root_degraded(self, tmp_path: Path) -> None:
        gen = PurposeGenerator()
        result = gen.generate(tmp_path / "nonexistent_xyz")

        assert result.degraded
        assert result.content == ""

    def test_custom_project_name(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        gen = PurposeGenerator()
        result = gen.generate(tmp_path, project_name="CustomName")

        assert "CustomName" in result.content

    def test_audience_table(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "Developers" in result.content
        assert "Operators" in result.content
        assert "Users" in result.content


# ---------------------------------------------------------------------------
# DocIndexGenerator (Epic 85.2)
# ---------------------------------------------------------------------------


class TestDocIndexGenerator:
    def test_basic_scan(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# My Project\n\nWelcome to the project.")
        _write(tmp_path / "docs" / "guide.md", "# Getting Started\n\nSetup instructions.")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.total_files == 2
        assert result.content
        assert "My Project" in result.content
        assert "Getting Started" in result.content

    def test_categorization(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "api-reference.md", "# API Reference\n\nEndpoints.")
        _write(tmp_path / "docs" / "deployment.md", "# Deployment\n\nHow to deploy.")
        _write(tmp_path / "CHANGELOG.md", "# Changelog\n\n## 1.0.0")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert "API Reference" in result.categories
        assert "Operations" in result.categories
        assert "Release" in result.categories

    def test_specific_doc_dirs(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "guide.md", "# Guide")
        _write(tmp_path / "other" / "notes.md", "# Notes")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path, doc_dirs=["docs"])

        assert result.total_files == 1

    def test_empty_project(self, tmp_path: Path) -> None:
        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.total_files == 0

    def test_invalid_root(self, tmp_path: Path) -> None:
        gen = DocIndexGenerator()
        result = gen.generate(tmp_path / "nonexistent_xyz")

        assert result.total_files == 0

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        _write(tmp_path / ".git" / "config.md", "# Git Config")
        _write(tmp_path / "docs" / "real.md", "# Real Doc")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.total_files == 1

    def test_word_count(self, tmp_path: Path) -> None:
        _write(tmp_path / "doc.md", "one two three four five")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.entries[0].word_count == 5

    def test_title_extraction_fallback(self, tmp_path: Path) -> None:
        _write(tmp_path / "my-cool-doc.md", "No heading here, just content.")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.entries[0].title == "My Cool Doc"


# ---------------------------------------------------------------------------
# CrossRefValidator (Epic 85.4)
# ---------------------------------------------------------------------------


class TestCrossRefValidator:
    def test_no_issues(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nSee [guide](docs/guide.md).")
        _write(tmp_path / "docs" / "guide.md", "# Guide\n\nBack to [README](../README.md).")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        broken = [i for i in report.issues if i.issue_type == "broken_ref"]
        assert len(broken) == 0
        assert report.score >= 80

    def test_broken_ref(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nSee [guide](docs/nonexistent.md).")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.broken_count == 1
        assert any(i.issue_type == "broken_ref" for i in report.issues)

    def test_orphan_detection(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nMain page.")
        _write(tmp_path / "docs" / "orphan.md", "# Orphan\n\nNobody links here.")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.orphan_count >= 1
        orphans = [i for i in report.issues if i.issue_type == "orphan"]
        assert any("orphan.md" in i.source_file for i in orphans)

    def test_entry_points_not_orphans(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nMain page.")
        _write(tmp_path / "CHANGELOG.md", "# Changelog\n\n## 1.0.0")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        orphans = [i for i in report.issues if i.issue_type == "orphan"]
        assert not any("README" in i.source_file for i in orphans)
        assert not any("CHANGELOG" in i.source_file for i in orphans)

    def test_missing_backlink(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "a.md", "# A\n\nSee [B](b.md).")
        _write(tmp_path / "docs" / "b.md", "# B\n\nNo link back to A.")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.missing_backlink_count >= 1

    def test_backlink_check_disabled(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "a.md", "# A\n\nSee [B](b.md).")
        _write(tmp_path / "docs" / "b.md", "# B\n\nNo link back.")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path, check_backlinks=False)

        assert report.missing_backlink_count == 0

    def test_empty_project(self, tmp_path: Path) -> None:
        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.total_files == 0
        assert report.score == 100

    def test_invalid_root(self, tmp_path: Path) -> None:
        validator = CrossRefValidator()
        report = validator.validate(tmp_path / "nonexistent_xyz")

        assert report.score == 100

    def test_skips_external_urls(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "doc.md",
            "# Doc\n\n[Google](https://google.com) and [local](other.md).",
        )

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        # Only the local ref should be counted, not the external URL
        broken = [i for i in report.issues if i.issue_type == "broken_ref"]
        assert all("google.com" not in i.target for i in broken)

    def test_skips_code_blocks(self, tmp_path: Path) -> None:
        content = "# Doc\n\n```\n[not a link](fake.md)\n```\n\nReal content."
        _write(tmp_path / "doc.md", content)

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        broken = [i for i in report.issues if i.issue_type == "broken_ref"]
        assert not any("fake.md" in i.target for i in broken)


# ---------------------------------------------------------------------------
# MCP tool handler tests
# ---------------------------------------------------------------------------


class TestDocsGeneratePurposeTool:
    async def test_success(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["fastapi"])
        from docs_mcp.server_gen_tools import docs_generate_purpose

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_purpose(project_root=str(tmp_path))

        assert result["success"] is True
        assert "purpose" in result["data"]["sections"]
        assert result["data"]["content_length"] > 0

    async def test_invalid_root(self, tmp_path: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_purpose

        bad_path = str(tmp_path / "nonexistent_xyz")
        result = await docs_generate_purpose(project_root=bad_path)
        assert result["success"] is False


class TestDocsGenerateDocIndexTool:
    async def test_success(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Test Project")
        from docs_mcp.server_gen_tools import docs_generate_doc_index

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_doc_index(project_root=str(tmp_path))

        assert result["success"] is True
        assert result["data"]["total_files"] >= 1

    async def test_invalid_root(self, tmp_path: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_doc_index

        bad_path = str(tmp_path / "nonexistent_xyz")
        result = await docs_generate_doc_index(project_root=bad_path)
        assert result["success"] is False


class TestDocsCheckCrossRefsTool:
    async def test_success(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nSee [guide](guide.md).")
        _write(tmp_path / "guide.md", "# Guide\n\nContent.")
        from docs_mcp.server_val_tools import docs_check_cross_refs

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_cross_refs(project_root=str(tmp_path))

        assert result["success"] is True
        assert "score" in result["data"]

    async def test_invalid_root(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_cross_refs

        bad_path = str(tmp_path / "nonexistent_xyz")
        result = await docs_check_cross_refs(project_root=bad_path)
        assert result["success"] is False
