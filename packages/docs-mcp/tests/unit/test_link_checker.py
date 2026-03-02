"""Tests for docs_mcp.validators.link_checker — link validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.validators.link_checker import (
    BrokenLink,
    LinkChecker,
    LinkReport,
    _extract_headings,
    _is_anchor_only,
    _is_external_link,
)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestBrokenLinkModel:
    """Test BrokenLink Pydantic model."""

    def test_construction(self) -> None:
        bl = BrokenLink(
            source_file="README.md",
            line=5,
            link_text="Guide",
            link_target="guide.md",
            reason="file_not_found",
        )
        assert bl.source_file == "README.md"
        assert bl.line == 5
        assert bl.reason == "file_not_found"


class TestLinkReportModel:
    """Test LinkReport Pydantic model."""

    def test_defaults(self) -> None:
        report = LinkReport()
        assert report.total_links == 0
        assert report.valid_links == 0
        assert report.broken_links == []


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test helper functions."""

    def test_is_external_link_http(self) -> None:
        assert _is_external_link("http://example.com") is True

    def test_is_external_link_https(self) -> None:
        assert _is_external_link("https://example.com") is True

    def test_is_external_link_mailto(self) -> None:
        assert _is_external_link("mailto:user@example.com") is True

    def test_is_external_link_relative(self) -> None:
        assert _is_external_link("./docs/guide.md") is False

    def test_is_external_link_protocol_relative(self) -> None:
        assert _is_external_link("//example.com/path") is True

    def test_is_anchor_only(self) -> None:
        assert _is_anchor_only("#section") is True
        assert _is_anchor_only("file.md#section") is False
        assert _is_anchor_only("file.md") is False

    def test_extract_headings_simple(self) -> None:
        content = "# Introduction\n## Getting Started\n### Step 1\n"
        anchors = _extract_headings(content)
        assert "introduction" in anchors
        assert "getting-started" in anchors
        assert "step-1" in anchors

    def test_extract_headings_with_special_chars(self) -> None:
        content = "# What's New?\n## FAQ & Help\n"
        anchors = _extract_headings(content)
        assert "whats-new" in anchors
        assert "faq-help" in anchors

    def test_extract_headings_empty(self) -> None:
        anchors = _extract_headings("")
        assert anchors == set()

    def test_extract_headings_no_headings(self) -> None:
        content = "Just some text.\nMore text.\n"
        anchors = _extract_headings(content)
        assert anchors == set()


# ---------------------------------------------------------------------------
# LinkChecker tests
# ---------------------------------------------------------------------------


class TestLinkChecker:
    """Test LinkChecker.check()."""

    def test_nonexistent_root(self) -> None:
        checker = LinkChecker()
        report = checker.check(Path("/nonexistent/path"))
        assert report.total_links == 0

    def test_empty_project(self, tmp_path: Path) -> None:
        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 0
        assert report.valid_links == 0

    def test_valid_internal_link(self, tmp_path: Path) -> None:
        """Valid link to an existing file should pass."""
        (tmp_path / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [the guide](guide.md).\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 1
        assert report.valid_links == 1
        assert report.broken_links == []

    def test_broken_file_reference(self, tmp_path: Path) -> None:
        """Link to a non-existent file should be broken."""
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [missing guide](guide.md).\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 1
        assert report.valid_links == 0
        assert len(report.broken_links) == 1
        assert report.broken_links[0].reason == "file_not_found"

    def test_valid_anchor_link(self, tmp_path: Path) -> None:
        """Same-file anchor link to an existing heading should pass."""
        (tmp_path / "README.md").write_text(
            "# Project\n\n[Jump to setup](#setup)\n\n## Setup\n\nSetup instructions.\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 1
        assert report.valid_links == 1

    def test_broken_anchor_link(self, tmp_path: Path) -> None:
        """Same-file anchor link to a non-existent heading should be broken."""
        (tmp_path / "README.md").write_text(
            "# Project\n\n[Jump to nowhere](#nonexistent)\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 1
        assert len(report.broken_links) == 1
        assert report.broken_links[0].reason == "anchor_not_found"

    def test_external_links_skipped(self, tmp_path: Path) -> None:
        """External HTTP links should be skipped entirely."""
        (tmp_path / "README.md").write_text(
            "# Project\n\n[Google](https://google.com)\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 0  # External links are not counted

    def test_non_markdown_files_skipped(self, tmp_path: Path) -> None:
        """Non-doc files should not be scanned."""
        (tmp_path / "app.py").write_text(
            '# [link](missing.md)\n',
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 0

    def test_cross_file_anchor(self, tmp_path: Path) -> None:
        """Link to a heading in another file should be checked."""
        (tmp_path / "guide.md").write_text(
            "# Guide\n\n## Installation\n\nInstall steps.\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [installation](guide.md#installation).\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 1
        assert report.valid_links == 1

    def test_cross_file_broken_anchor(self, tmp_path: Path) -> None:
        """Link to a non-existent heading in another file should be broken."""
        (tmp_path / "guide.md").write_text(
            "# Guide\n\n## Installation\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [usage](guide.md#usage).\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 1
        assert len(report.broken_links) == 1
        assert report.broken_links[0].reason == "anchor_not_found"

    def test_specific_files_parameter(self, tmp_path: Path) -> None:
        """files parameter should restrict which files are checked."""
        (tmp_path / "good.md").write_text("# Good\n", encoding="utf-8")
        (tmp_path / "a.md").write_text("[link](good.md)\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("[broken](missing.md)\n", encoding="utf-8")

        checker = LinkChecker()
        # Only check a.md
        report = checker.check(tmp_path, files=["a.md"])
        assert report.total_links == 1
        assert report.valid_links == 1
        assert report.broken_links == []

    def test_multiple_links_per_line(self, tmp_path: Path) -> None:
        """Multiple links on one line should all be checked."""
        (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [A](a.md) and [B](b.md).\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 2
        assert report.valid_links == 1
        assert len(report.broken_links) == 1

    def test_subdirectory_link(self, tmp_path: Path) -> None:
        """Links to files in subdirectories should work."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [guide](docs/guide.md).\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 1
        assert report.valid_links == 1
