"""Tests for docs_mcp.generators.smart_merge — smart README merging."""

from __future__ import annotations

import pytest

from docs_mcp.generators.smart_merge import MergeResult, SmartMerger


@pytest.fixture
def merger() -> SmartMerger:
    return SmartMerger()


# ---------------------------------------------------------------------------
# Fresh generation (no existing README)
# ---------------------------------------------------------------------------


class TestFreshGeneration:
    """Tests for when there is no existing README."""

    def test_empty_existing_returns_wrapped_generated(self, merger: SmartMerger) -> None:
        generated = "# My Project\n\nDescription\n\n## Installation\n\npip install foo\n"
        result = merger.merge("", generated)
        assert result.sections_added == ["Installation"]
        assert result.sections_preserved == []
        assert result.sections_updated == []
        assert "# My Project" in result.content
        assert "<!-- docsmcp:start:installation -->" in result.content
        assert "<!-- docsmcp:end:installation -->" in result.content

    def test_whitespace_only_existing(self, merger: SmartMerger) -> None:
        generated = "# Proj\n\n## Features\n\n- feature 1\n"
        result = merger.merge("   \n\n  ", generated)
        assert result.sections_added == ["Features"]
        assert "<!-- docsmcp:start:features -->" in result.content


# ---------------------------------------------------------------------------
# Preserve human sections
# ---------------------------------------------------------------------------


class TestPreserveHumanSections:
    """Tests for preserving human-written sections."""

    def test_human_section_preserved(self, merger: SmartMerger) -> None:
        existing = (
            "# Old Title\n\n## Custom Notes\n\nThis is my custom section that should be kept.\n"
        )
        generated = "# New Title\n\n## Installation\n\npip install foo\n"
        result = merger.merge(existing, generated)
        assert "Custom Notes" in result.sections_preserved
        assert "This is my custom section that should be kept." in result.content
        # Title should be updated
        assert "# New Title" in result.content

    def test_multiple_human_sections_preserved(self, merger: SmartMerger) -> None:
        existing = "# Title\n\n## My Notes\n\nNotes content\n\n## My FAQ\n\nFAQ content\n"
        generated = "# New Title\n\n## Installation\n\npip install\n"
        result = merger.merge(existing, generated)
        assert "My Notes" in result.sections_preserved
        assert "My FAQ" in result.sections_preserved
        assert "Notes content" in result.content
        assert "FAQ content" in result.content


# ---------------------------------------------------------------------------
# Update machine sections (between markers)
# ---------------------------------------------------------------------------


class TestUpdateMachineSections:
    """Tests for updating machine-managed sections."""

    def test_marked_section_is_updated(self, merger: SmartMerger) -> None:
        existing = (
            "# Title\n\n"
            "<!-- docsmcp:start:installation -->\n"
            "## Installation\n\nOLD pip install foo\n"
            "<!-- docsmcp:end:installation -->\n"
        )
        generated = "# New Title\n\n## Installation\n\nNEW pip install bar\n"
        result = merger.merge(existing, generated)
        assert "Installation" in result.sections_updated
        assert "NEW pip install bar" in result.content
        assert "OLD pip install foo" not in result.content

    def test_multiple_marked_sections_updated(self, merger: SmartMerger) -> None:
        existing = (
            "# Title\n\n"
            "<!-- docsmcp:start:installation -->\n"
            "## Installation\n\nOLD install\n"
            "<!-- docsmcp:end:installation -->\n\n"
            "<!-- docsmcp:start:features -->\n"
            "## Features\n\nOLD features\n"
            "<!-- docsmcp:end:features -->\n"
        )
        generated = "# Title\n\n## Installation\n\nNEW install\n\n## Features\n\nNEW features\n"
        result = merger.merge(existing, generated)
        assert "Installation" in result.sections_updated
        assert "Features" in result.sections_updated
        assert "NEW install" in result.content
        assert "NEW features" in result.content


# ---------------------------------------------------------------------------
# Add new sections
# ---------------------------------------------------------------------------


class TestAddNewSections:
    """Tests for adding new sections from generated content."""

    def test_new_section_added_at_end(self, merger: SmartMerger) -> None:
        existing = "# Title\n\n## Existing\n\nSome content\n"
        generated = (
            "# Title\n\n## Existing\n\nUpdated content\n\n## Brand New\n\nNew section content\n"
        )
        result = merger.merge(existing, generated)
        assert "Brand New" in result.sections_added
        assert "New section content" in result.content

    def test_multiple_new_sections_added(self, merger: SmartMerger) -> None:
        existing = "# Title\n"
        generated = "# Title\n\n## Section A\n\nContent A\n\n## Section B\n\nContent B\n"
        result = merger.merge(existing, generated)
        assert "Section A" in result.sections_added
        assert "Section B" in result.sections_added


# ---------------------------------------------------------------------------
# Title always updated
# ---------------------------------------------------------------------------


class TestTitleUpdate:
    """Tests for title behavior."""

    def test_title_always_updated(self, merger: SmartMerger) -> None:
        existing = "# Old Title\n\n## Section\n\nContent\n"
        generated = "# New Title\n\n## Section\n\nNew content\n"
        result = merger.merge(existing, generated)
        assert "# New Title" in result.content
        # Old title should not be present
        assert "# Old Title" not in result.content

    def test_title_from_generated_even_if_existing_has_none(self, merger: SmartMerger) -> None:
        existing = "## Section\n\nContent\n"
        generated = "# My Project\n\n## Section\n\nNew content\n"
        result = merger.merge(existing, generated)
        assert "# My Project" in result.content


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_generated(self, merger: SmartMerger) -> None:
        existing = "# Title\n\n## Section\n\nContent\n"
        result = merger.merge(existing, "")
        # Should preserve existing content when generated is empty
        assert "# Title" in result.content

    def test_both_empty(self, merger: SmartMerger) -> None:
        result = merger.merge("", "")
        assert result.content == ""
        assert result.sections_added == []

    def test_content_before_first_section_not_duplicated(self, merger: SmartMerger) -> None:
        existing = "# Title\n\nSome intro text\n\n## Section\n\nContent\n"
        generated = "# Title\n\nNew intro\n\n## Section\n\nNew content\n"
        result = merger.merge(existing, generated)
        # Title should appear exactly once
        assert result.content.count("# Title") == 1

    def test_trailing_newline_ensured(self, merger: SmartMerger) -> None:
        existing = "# Title\n\n## Section\n\nContent"
        generated = "# New\n\n## Section\n\nNew"
        result = merger.merge(existing, generated)
        assert result.content.endswith("\n")

    def test_merge_result_model(self) -> None:
        """MergeResult is a valid Pydantic model."""
        result = MergeResult(
            content="# Hello\n",
            sections_preserved=["A"],
            sections_updated=["B"],
            sections_added=["C"],
        )
        assert result.content == "# Hello\n"
        assert result.sections_preserved == ["A"]

    def test_section_marker_format(self) -> None:
        """Verify marker format constants."""
        assert "{section}" in SmartMerger.SECTION_MARKER_START
        assert "{section}" in SmartMerger.SECTION_MARKER_END
        start = SmartMerger.SECTION_MARKER_START.format(section="installation")
        assert start == "<!-- docsmcp:start:installation -->"

    def test_wrap_with_markers_wraps_all_sections(self, merger: SmartMerger) -> None:
        content = "# Title\n\nDesc\n\n## A\n\nContent A\n\n## B\n\nContent B\n"
        wrapped = merger._wrap_with_markers(content)
        assert "<!-- docsmcp:start:a -->" in wrapped
        assert "<!-- docsmcp:end:a -->" in wrapped
        assert "<!-- docsmcp:start:b -->" in wrapped
        assert "<!-- docsmcp:end:b -->" in wrapped

    def test_marked_section_not_in_generated_is_preserved(self, merger: SmartMerger) -> None:
        """If existing has a marked section not present in generated, keep it."""
        existing = (
            "# Title\n\n"
            "<!-- docsmcp:start:custom -->\n"
            "## Custom\n\nCustom content\n"
            "<!-- docsmcp:end:custom -->\n"
        )
        generated = "# Title\n\n## Installation\n\npip install\n"
        result = merger.merge(existing, generated)
        assert "Custom" in result.sections_preserved
        assert "Custom content" in result.content
