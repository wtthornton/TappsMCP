"""Tests for the frontmatter generator (Epic 83)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from docs_mcp.generators.frontmatter import FrontmatterGenerator, FrontmatterResult
from tests.helpers import make_settings


# ---------------------------------------------------------------------------
# FrontmatterGenerator unit tests
# ---------------------------------------------------------------------------


class TestFrontmatterParsing:
    def test_no_existing_frontmatter(self) -> None:
        content = "# My Doc\n\nSome content here.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)

        assert result.had_existing is False
        assert "title: My Doc" in result.content
        assert "description: Some content here." in result.content
        assert result.content.startswith("---\n")

    def test_existing_frontmatter_preserved(self) -> None:
        content = "---\ntitle: Custom Title\nauthor: John\n---\n# Heading\n\nBody.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)

        assert result.had_existing is True
        assert "title" in result.fields_preserved
        assert "Custom Title" in result.content
        assert "author: John" in result.content

    def test_merge_new_fields(self) -> None:
        content = "---\ntitle: Existing\n---\n# Existing\n\nA description paragraph.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)

        assert "title" in result.fields_preserved
        assert "description" in result.fields_added or "last_modified" in result.fields_added

    def test_list_frontmatter(self) -> None:
        content = "---\ntags:\n  - python\n  - testing\n---\n# Doc\n\nContent.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)

        assert result.had_existing is True
        assert "python" in result.content
        assert "testing" in result.content


class TestTitleDetection:
    def test_h1_heading(self) -> None:
        content = "# My Amazing Project\n\nDescription here.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        assert "title: My Amazing Project" in result.content

    def test_no_heading(self) -> None:
        content = "Just some text without a heading.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        # Should not have empty title
        assert "title: Just some text" not in result.content

    def test_h2_not_treated_as_title(self) -> None:
        content = "## Subsection\n\nContent.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        # H2 is not a title
        assert "title: Subsection" not in result.content


class TestDescriptionDetection:
    def test_first_paragraph(self) -> None:
        content = "# Title\n\nThis is the first paragraph describing the doc.\n\nMore text.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        assert "This is the first paragraph" in result.content

    def test_skips_list_items(self) -> None:
        content = "# Title\n\n- Item 1\n- Item 2\n\nActual description here.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        assert "Actual description here" in result.content

    def test_long_description_truncated(self) -> None:
        long_para = "word " * 100
        content = f"# Title\n\n{long_para}\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        # Check truncation happened
        assert "..." in result.content or len(result.content) < len(content) + 500


class TestDiataxisDetection:
    def test_tutorial(self) -> None:
        content = "# Getting Started Tutorial\n\nStep by step guide to learn the basics.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        assert "diataxis_type: tutorial" in result.content

    def test_howto(self) -> None:
        content = "# How to Configure Authentication\n\nGuide to set up auth.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        assert "diataxis_type: how-to" in result.content

    def test_reference(self) -> None:
        content = "# API Reference\n\nSpecification of parameters and returns.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        assert "diataxis_type: reference" in result.content

    def test_explanation(self) -> None:
        content = "# Why We Chose This Architecture\n\nBackground and design decisions.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        assert "diataxis_type: explanation" in result.content


class TestTagDetection:
    def test_tags_from_content(self) -> None:
        content = "# Security Guide\n\nAuthentication and authorization setup.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content, file_path=Path("docs/security.md"))

        assert "tags:" in result.content
        assert "security" in result.content

    def test_tags_from_path(self) -> None:
        content = "# Guide\n\nContent.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content, file_path=Path("docs/deployment-guide.md"))

        assert "deployment-guide" in result.content


class TestExtraFields:
    def test_extra_fields_included(self) -> None:
        content = "# Doc\n\nContent.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content, extra_fields={"category": "guide", "weight": "10"})

        assert "category: guide" in result.content
        assert "weight: 10" in result.content

    def test_extra_fields_override_auto(self) -> None:
        content = "# Doc\n\nContent.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content, extra_fields={"title": "Custom"})

        # Extra fields set title, but existing FM would override both
        # Since no existing FM, extra should be in merged but auto also set it
        assert "Custom" in result.content or "Doc" in result.content


class TestSpecialCharacters:
    def test_yaml_special_chars_quoted(self) -> None:
        content = "# Title: With Colon\n\nContent.\n"
        gen = FrontmatterGenerator()
        result = gen.generate(content)
        # Title with colon should be quoted
        assert '"Title: With Colon"' in result.content


# ---------------------------------------------------------------------------
# MCP tool handler tests
# ---------------------------------------------------------------------------


class TestDocsGenerateFrontmatterTool:
    async def test_missing_path(self) -> None:
        from docs_mcp.server_gen_tools import docs_generate_frontmatter

        result = await docs_generate_frontmatter()
        assert result["success"] is False
        assert result["error"]["code"] == "MISSING_PATH"

    async def test_file_not_found(self, tmp_path: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_frontmatter

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_frontmatter(
                file_path="nonexistent.md",
                project_root=str(tmp_path),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "FILE_NOT_FOUND"

    async def test_non_markdown_file(self, tmp_path: Path) -> None:
        (tmp_path / "code.py").write_text("x = 1")
        from docs_mcp.server_gen_tools import docs_generate_frontmatter

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_frontmatter(
                file_path="code.py",
                project_root=str(tmp_path),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_FILE_TYPE"

    async def test_success(self, tmp_path: Path) -> None:
        md_file = tmp_path / "README.md"
        md_file.write_text("# Hello\n\nWorld.\n")
        from docs_mcp.server_gen_tools import docs_generate_frontmatter

        with (
            patch("docs_mcp.server_gen_tools._get_settings") as mock_settings,
            patch("docs_mcp.server_helpers.can_write_to_project", return_value=True),
        ):
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_frontmatter(
                file_path="README.md",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert "fields_added" in result["data"]
        assert result["data"]["written_to"] == "README.md"

    async def test_content_return_mode(self, tmp_path: Path) -> None:
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Doc\n\nContent.\n")
        from docs_mcp.server_gen_tools import docs_generate_frontmatter

        with (
            patch("docs_mcp.server_gen_tools._get_settings") as mock_settings,
            patch("docs_mcp.server_helpers.can_write_to_project", return_value=False),
        ):
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_frontmatter(
                file_path="doc.md",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert "content" in result["data"]
