"""Tests for CLAUDE.md section surgery and the Cursor rule bootstrap (TAP-5733)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tapps_mcp.pipeline.init_claude_md import (
    _bootstrap_cursor,
    _replace_tapps_section,
    _split_by_h1_headings,
)

if TYPE_CHECKING:
    from pathlib import Path


_TAPPS_HEADING = "# TAPPS Quality Pipeline"


class TestSplitByH1Headings:
    def test_empty_content_yields_no_sections(self) -> None:
        assert _split_by_h1_headings("") == []

    def test_content_before_first_h1_gets_an_empty_heading(self) -> None:
        assert _split_by_h1_headings("intro line\n\n# First\nbody one\n") == [
            ("", "intro line\n\n"),
            ("# First\n", "body one\n"),
        ]

    def test_content_without_any_h1_is_a_single_headless_section(self) -> None:
        assert _split_by_h1_headings("just prose\n") == [("", "just prose\n")]

    def test_multiple_h1_headings_become_separate_sections(self) -> None:
        assert _split_by_h1_headings("# One\nalpha\n\n# Two\nbeta\n") == [
            ("# One\n", "alpha\n\n"),
            ("# Two\n", "beta\n"),
        ]

    def test_sub_headings_are_body_content(self) -> None:
        content = "# Top\n## Sub\ntext\n### Deeper\nmore\n"
        assert _split_by_h1_headings(content) == [
            ("# Top\n", "## Sub\ntext\n### Deeper\nmore\n"),
        ]

    def test_hash_without_a_space_is_not_a_boundary(self) -> None:
        assert _split_by_h1_headings("# Top\n#NotAHeading\n") == [
            ("# Top\n", "#NotAHeading\n"),
        ]

    def test_heading_without_trailing_newline_is_preserved(self) -> None:
        assert _split_by_h1_headings("# Only") == [("# Only", "")]

    def test_sections_reassemble_to_the_original(self) -> None:
        content = "intro\n\n# One\nalpha\n\n# Two\nbeta\n"
        sections = _split_by_h1_headings(content)
        assert "".join(heading + body for heading, body in sections) == content


class TestReplaceTappsSection:
    def test_appends_when_no_tapps_section_exists(self) -> None:
        result = _replace_tapps_section("# My Project\nintro\n", f"{_TAPPS_HEADING}\nnew")
        assert result == f"# My Project\nintro\n\n{_TAPPS_HEADING}\nnew"

    def test_replaces_an_existing_tapps_section(self) -> None:
        existing = f"# My Project\nintro\n\n{_TAPPS_HEADING}\nold rules\n"
        result = _replace_tapps_section(existing, f"{_TAPPS_HEADING}\nnew rules")
        assert result == f"# My Project\nintro\n\n{_TAPPS_HEADING}\nnew rules"
        assert "old rules" not in result

    def test_preserves_content_after_the_tapps_section(self) -> None:
        existing = f"# My Project\nintro\n\n{_TAPPS_HEADING}\nold rules\n\n# Notes\nkeep me\n"
        result = _replace_tapps_section(existing, f"{_TAPPS_HEADING}\nnew rules")
        assert result == f"# My Project\nintro\n\n{_TAPPS_HEADING}\nnew rules\n\n# Notes\nkeep me\n"
        assert "old rules" not in result

    def test_tapps_section_as_the_only_section_is_fully_replaced(self) -> None:
        result = _replace_tapps_section(f"{_TAPPS_HEADING}\nold\n", f"{_TAPPS_HEADING}\nnew")
        assert result == f"{_TAPPS_HEADING}\nnew"

    def test_preserves_content_before_the_first_heading(self) -> None:
        existing = f"preamble\n\n{_TAPPS_HEADING}\nold\n"
        result = _replace_tapps_section(existing, f"{_TAPPS_HEADING}\nnew")
        assert result == f"preamble\n\n{_TAPPS_HEADING}\nnew"

    def test_matches_heading_with_a_trailing_suffix(self) -> None:
        existing = f"{_TAPPS_HEADING} (v3)\nold\n"
        result = _replace_tapps_section(existing, f"{_TAPPS_HEADING}\nnew")
        assert result == f"{_TAPPS_HEADING}\nnew"

    def test_ignores_a_sub_heading_that_mentions_tapps(self) -> None:
        existing = f"# My Project\n#{_TAPPS_HEADING}\nnot a section\n"
        result = _replace_tapps_section(existing, f"{_TAPPS_HEADING}\nnew")
        assert result.endswith(f"\n\n{_TAPPS_HEADING}\nnew")
        assert "not a section" in result


@pytest.fixture
def platform_rules(monkeypatch: pytest.MonkeyPatch) -> str:
    content = "# Cursor Pipeline\nrendered rules\n"
    monkeypatch.setattr(
        "tapps_mcp.pipeline.init_claude_md.load_platform_rules",
        lambda platform, engagement_level="medium": content,
    )
    return content


class TestBootstrapCursor:
    def test_creates_the_rule_file(self, tmp_path: Path, platform_rules: str) -> None:
        assert _bootstrap_cursor(tmp_path) == "created"
        rules = tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc"
        assert rules.read_text(encoding="utf-8") == platform_rules

    def test_skips_an_existing_file_without_overwrite(
        self, tmp_path: Path, platform_rules: str
    ) -> None:
        del platform_rules
        rules = tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc"
        rules.parent.mkdir(parents=True)
        rules.write_text("hand-written", encoding="utf-8")

        assert _bootstrap_cursor(tmp_path) == "skipped"
        assert rules.read_text(encoding="utf-8") == "hand-written"

    def test_overwrites_an_existing_file_when_asked(
        self, tmp_path: Path, platform_rules: str
    ) -> None:
        rules = tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc"
        rules.parent.mkdir(parents=True)
        rules.write_text("hand-written", encoding="utf-8")

        assert _bootstrap_cursor(tmp_path, overwrite=True) == "updated"
        assert rules.read_text(encoding="utf-8") == platform_rules

    def test_passes_the_engagement_level_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple[str, str]] = []

        def _load(platform: str, engagement_level: str = "medium") -> str:
            seen.append((platform, engagement_level))
            return "rules"

        monkeypatch.setattr("tapps_mcp.pipeline.init_claude_md.load_platform_rules", _load)
        _bootstrap_cursor(tmp_path, engagement_level="high")
        assert seen == [("cursor", "high")]


class TestFacadeReExport:
    def test_init_still_exposes_the_claude_md_helpers(self) -> None:
        from tapps_mcp.pipeline import init

        assert init._split_by_h1_headings is _split_by_h1_headings
        assert init._replace_tapps_section is _replace_tapps_section
        assert init._bootstrap_cursor is _bootstrap_cursor
