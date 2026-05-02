"""Tests for docs_mcp.validators.link_checker — link validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.validators.link_checker import (
    BacktickReference,
    BrokenLink,
    LinkChecker,
    LinkReport,
    _check_backtick_refs,
    _extract_headings,
    _find_fenced_blocks,
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


class TestBacktickReferenceModel:
    """Test BacktickReference Pydantic model."""

    def test_construction(self) -> None:
        ref = BacktickReference(
            source_file="README.md",
            line=10,
            reference="src/foo/bar.py",
            exists=True,
            reason="found",
        )
        assert ref.source_file == "README.md"
        assert ref.line == 10
        assert ref.reference == "src/foo/bar.py"
        assert ref.exists is True
        assert ref.reason == "found"


class TestLinkReportModel:
    """Test LinkReport Pydantic model."""

    def test_defaults(self) -> None:
        report = LinkReport()
        assert report.total_links == 0
        assert report.valid_links == 0
        assert report.broken_links == []
        assert report.backtick_references == []
        assert report.total_backtick_refs == 0
        assert report.valid_backtick_refs == 0
        assert report.missing_backtick_refs == 0
        assert report.warnings == []


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test helper functions."""

    @pytest.mark.parametrize(
        "link,expected",
        [
            ("http://example.com", True),
            ("https://example.com", True),
            ("mailto:user@example.com", True),
            ("./docs/guide.md", False),
            ("//example.com/path", True),
        ],
        ids=["http", "https", "mailto", "relative", "protocol-relative"],
    )
    def test_is_external_link(self, link: str, expected: bool) -> None:
        assert _is_external_link(link) is expected

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
        # GitHub maps each space to a hyphen without collapsing repeats, so
        # `FAQ & Help` becomes `faq--help` (the `&` is stripped, the
        # surrounding spaces both become hyphens).
        content = "# What's New?\n## FAQ & Help\n"
        anchors = _extract_headings(content)
        assert "whats-new" in anchors
        assert "faq--help" in anchors

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
            "# [link](missing.md)\n",
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


# ---------------------------------------------------------------------------
# Fenced code block detection tests
# ---------------------------------------------------------------------------


class TestFencedBlocks:
    """Test _find_fenced_blocks()."""

    def test_no_fences(self) -> None:
        content = "line 1\nline 2\nline 3\n"
        assert _find_fenced_blocks(content) == set()

    def test_simple_fence(self) -> None:
        content = "before\n```\ncode line\n```\nafter\n"
        fenced = _find_fenced_blocks(content)
        # Lines 2 (```), 3 (code), 4 (```) are inside/part of fence
        assert 2 in fenced
        assert 3 in fenced
        assert 4 in fenced
        assert 1 not in fenced
        assert 5 not in fenced

    def test_fence_with_language(self) -> None:
        content = "text\n```python\nimport os\n```\nmore text\n"
        fenced = _find_fenced_blocks(content)
        assert 2 in fenced
        assert 3 in fenced
        assert 4 in fenced
        assert 1 not in fenced

    def test_tilde_fence(self) -> None:
        content = "text\n~~~\ncode\n~~~\n"
        fenced = _find_fenced_blocks(content)
        assert 2 in fenced
        assert 3 in fenced
        assert 4 in fenced

    def test_unclosed_fence(self) -> None:
        content = "text\n```\ncode\nmore code\n"
        fenced = _find_fenced_blocks(content)
        assert 2 in fenced
        assert 3 in fenced
        assert 4 in fenced


# ---------------------------------------------------------------------------
# Backtick reference detection tests
# ---------------------------------------------------------------------------


class TestBacktickRefs:
    """Test _check_backtick_refs() and backtick integration."""

    def test_backtick_ref_existing_file(self, tmp_path: Path) -> None:
        """Backtick ref to existing file is detected and validated."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "upgrade.py").write_text("# upgrade\n", encoding="utf-8")
        md_file = tmp_path / "README.md"
        md_file.write_text(
            "# Project\n\nSee `src/upgrade.py` for details.\n",
            encoding="utf-8",
        )

        content = md_file.read_text(encoding="utf-8")
        fenced = _find_fenced_blocks(content)
        refs = _check_backtick_refs(md_file, tmp_path, content, fenced)

        assert len(refs) == 1
        assert refs[0].reference == "src/upgrade.py"
        assert refs[0].exists is True
        assert refs[0].reason == "found"

    def test_backtick_ref_missing_file(self, tmp_path: Path) -> None:
        """Backtick ref to non-existent file reports not_found."""
        md_file = tmp_path / "README.md"
        md_file.write_text(
            "# Project\n\nSee `pipeline/upgrade.py` for details.\n",
            encoding="utf-8",
        )

        content = md_file.read_text(encoding="utf-8")
        fenced = _find_fenced_blocks(content)
        refs = _check_backtick_refs(md_file, tmp_path, content, fenced)

        assert len(refs) == 1
        assert refs[0].reference == "pipeline/upgrade.py"
        assert refs[0].exists is False
        assert refs[0].reason == "not_found"

    def test_backtick_ref_inside_code_block_skipped(self, tmp_path: Path) -> None:
        """Backtick refs inside fenced code blocks are skipped."""
        md_file = tmp_path / "README.md"
        md_file.write_text(
            "# Project\n\n```\nSee `src/foo.py` here\n```\n",
            encoding="utf-8",
        )

        content = md_file.read_text(encoding="utf-8")
        fenced = _find_fenced_blocks(content)
        refs = _check_backtick_refs(md_file, tmp_path, content, fenced)

        assert len(refs) == 1
        assert refs[0].reason == "skipped_code_block"

    def test_non_path_backtick_ignored(self, tmp_path: Path) -> None:
        """Non-path backtick content like `variable_name` is not a file ref."""
        md_file = tmp_path / "README.md"
        md_file.write_text(
            "# Project\n\nUse the `variable_name` variable.\n",
            encoding="utf-8",
        )

        content = md_file.read_text(encoding="utf-8")
        fenced = _find_fenced_blocks(content)
        refs = _check_backtick_refs(md_file, tmp_path, content, fenced)

        assert len(refs) == 0

    def test_triple_backtick_not_matched(self, tmp_path: Path) -> None:
        """Triple backtick (```) should not be matched as a file ref."""
        md_file = tmp_path / "README.md"
        md_file.write_text(
            "# Project\n\n```foo.py```\n",
            encoding="utf-8",
        )

        content = md_file.read_text(encoding="utf-8")
        fenced = _find_fenced_blocks(content)
        refs = _check_backtick_refs(md_file, tmp_path, content, fenced)

        # The regex excludes triple-backtick wrapping
        assert len(refs) == 0

    def test_backtick_ref_relative_to_file_dir(self, tmp_path: Path) -> None:
        """Backtick ref resolved relative to file's directory."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "helper.py").write_text("# helper\n", encoding="utf-8")
        md_file = docs / "guide.md"
        md_file.write_text(
            "# Guide\n\nSee `helper.py` for details.\n",
            encoding="utf-8",
        )

        content = md_file.read_text(encoding="utf-8")
        fenced = _find_fenced_blocks(content)
        refs = _check_backtick_refs(md_file, tmp_path, content, fenced)

        assert len(refs) == 1
        assert refs[0].exists is True
        assert refs[0].reason == "found"


# ---------------------------------------------------------------------------
# Integration: backtick refs in LinkChecker.check()
# ---------------------------------------------------------------------------


class TestLinkCheckerBacktickIntegration:
    """Test backtick reference detection via LinkChecker.check()."""

    def test_backtick_ref_counted_in_report(self, tmp_path: Path) -> None:
        """Backtick file refs should appear in the report."""
        (tmp_path / "config.yaml").write_text("key: val\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nEdit `config.yaml` to configure.\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_backtick_refs == 1
        assert report.valid_backtick_refs == 1
        assert report.missing_backtick_refs == 0
        assert len(report.backtick_references) == 1

    def test_missing_backtick_ref_counted(self, tmp_path: Path) -> None:
        """Missing backtick file refs are counted."""
        (tmp_path / "README.md").write_text(
            "# Project\n\nEdit `nonexistent.yaml` to configure.\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_backtick_refs == 1
        assert report.valid_backtick_refs == 0
        assert report.missing_backtick_refs == 1

    def test_mix_of_markdown_links_and_backtick_refs(self, tmp_path: Path) -> None:
        """Both markdown links and backtick refs are counted."""
        (tmp_path / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (tmp_path / "config.toml").write_text("[tool]\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [guide](guide.md) and `config.toml`.\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.total_links == 1
        assert report.valid_links == 1
        assert report.total_backtick_refs == 1
        assert report.valid_backtick_refs == 1

    def test_zero_link_warning(self, tmp_path: Path) -> None:
        """A doc with no links and no backtick refs gets a warning."""
        (tmp_path / "README.md").write_text(
            "# Project\n\nJust plain text here.\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert len(report.warnings) == 1
        assert "README.md" in report.warnings[0]
        assert "No links or file references" in report.warnings[0]

    def test_no_warning_when_links_present(self, tmp_path: Path) -> None:
        """A doc with links should not get a zero-link warning for that file."""
        (tmp_path / "other.txt").write_text("Other content\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [other](other.txt).\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        # Only check README.md which has a link
        report = checker.check(tmp_path, files=["README.md"])
        assert len(report.warnings) == 0

    def test_no_warning_when_backtick_refs_present(self, tmp_path: Path) -> None:
        """A doc with backtick refs should not get a zero-link warning."""
        (tmp_path / "setup.py").write_text("# setup\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee `setup.py` for build config.\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert len(report.warnings) == 0

    def test_code_block_refs_dont_prevent_warning(self, tmp_path: Path) -> None:
        """Backtick refs inside code blocks are skipped, so zero-link warning fires."""
        (tmp_path / "README.md").write_text(
            "# Project\n\n```\n`foo.py`\n```\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        # The only backtick ref is inside a code block (skipped),
        # so the file has 0 effective refs
        assert len(report.warnings) == 1
        assert "No links or file references" in report.warnings[0]


# ---------------------------------------------------------------------------
# Pagination / filtering options
# ---------------------------------------------------------------------------


def _write_project_with_broken_links(tmp_path: Path, n_broken: int) -> None:
    """Create a README with ``n_broken`` markdown links pointing at missing files."""
    lines = ["# Project", ""]
    for i in range(n_broken):
        lines.append(f"[dead-{i}](missing-{i}.md)")
    (tmp_path / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestLinkCheckerPaginationAndFiltering:
    """Test summary_only, max_items, broken_only, include_backtick_refs."""

    def test_default_behavior_unchanged_snapshot(self, tmp_path: Path) -> None:
        """Baseline: defaults still return full lists and scalar counts."""
        (tmp_path / "config.yaml").write_text("key: val\n", encoding="utf-8")
        (tmp_path / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\n"
            "See [guide](guide.md) and [missing](nope.md).\n"
            "Also `config.yaml` and `missing.yaml`.\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)

        # Scalar counts match pre-change semantics.
        assert report.total_links == 2
        assert report.valid_links == 1
        assert report.total_backtick_refs == 2
        assert report.valid_backtick_refs == 1
        assert report.missing_backtick_refs == 1
        # New scalar must mirror missing_backtick_refs by default.
        assert report.missing_backtick_ref_count == 1
        # Detail lists are fully populated by default.
        assert len(report.broken_links) == 1
        assert len(report.backtick_references) == 2
        assert report.truncated is False

    def test_summary_only_zero_detail_items_correct_counts(self, tmp_path: Path) -> None:
        """summary_only=True empties detail lists but preserves counts/score."""
        _write_project_with_broken_links(tmp_path, n_broken=5)

        checker = LinkChecker()
        report = checker.check(tmp_path, summary_only=True)

        assert report.total_links == 5
        assert report.valid_links == 0
        # Detail lists are empty.
        assert report.broken_links == []
        assert report.backtick_references == []
        assert report.warnings == []
        # Scalar totals still reflect the true universe.
        assert report.total_available_broken_links == 5
        # Score is still populated.
        assert report.score == 0

    def test_max_items_truncates_and_sets_flag(self, tmp_path: Path) -> None:
        """max_items caps detail lists and sets truncated=True."""
        _write_project_with_broken_links(tmp_path, n_broken=10)

        checker = LinkChecker()
        report = checker.check(tmp_path, max_items=3)

        assert report.total_links == 10
        assert len(report.broken_links) == 3
        assert report.truncated is True
        assert report.total_available_broken_links == 10

    def test_max_items_no_truncation_when_under_cap(self, tmp_path: Path) -> None:
        """No truncation flag when list is under the cap."""
        _write_project_with_broken_links(tmp_path, n_broken=2)

        checker = LinkChecker()
        report = checker.check(tmp_path, max_items=10)

        assert len(report.broken_links) == 2
        assert report.truncated is False
        assert report.total_available_broken_links == 2

    def test_broken_only_excludes_non_broken_backtick_refs(self, tmp_path: Path) -> None:
        """broken_only=True drops valid / skipped backtick refs from the list."""
        (tmp_path / "config.yaml").write_text("key: val\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nEdit `config.yaml` and also `missing.yaml`.\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path, broken_only=True)

        # Scalar counts unaffected.
        assert report.total_backtick_refs == 2
        assert report.valid_backtick_refs == 1
        assert report.missing_backtick_refs == 1
        assert report.missing_backtick_ref_count == 1
        # Detail list only has the missing one.
        assert len(report.backtick_references) == 1
        assert report.backtick_references[0].exists is False
        assert report.backtick_references[0].reference == "missing.yaml"
        assert report.total_available_backtick_references == 1

    def test_include_backtick_refs_false_hides_items_but_keeps_count(self, tmp_path: Path) -> None:
        """include_backtick_refs=False drops the list but the count stays accurate."""
        (tmp_path / "config.yaml").write_text("key: val\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nEdit `config.yaml` and also `missing.yaml` and `also-missing.toml`.\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path, include_backtick_refs=False)

        assert report.backtick_references == []
        # But the dashboard signal is still present.
        assert report.missing_backtick_ref_count == 2
        assert report.missing_backtick_refs == 2
        assert report.total_backtick_refs == 3
        assert report.valid_backtick_refs == 1
        assert report.total_available_backtick_references == 0

    def test_score_perfect_when_all_valid(self, tmp_path: Path) -> None:
        """Score is 100 when every link and ref resolves."""
        (tmp_path / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [guide](guide.md).\n",
            encoding="utf-8",
        )

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.score == 100

    def test_score_zero_when_all_broken(self, tmp_path: Path) -> None:
        """Score is 0 when every link is broken."""
        _write_project_with_broken_links(tmp_path, n_broken=4)

        checker = LinkChecker()
        report = checker.check(tmp_path)
        assert report.score == 0
