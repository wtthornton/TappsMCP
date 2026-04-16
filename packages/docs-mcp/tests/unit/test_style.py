"""Tests for style and tone validation (Epic 84)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from docs_mcp.validators.style import (
    FileStyleResult,
    HeadingConsistencyRule,
    JargonRule,
    PassiveVoiceRule,
    SentenceLengthRule,
    StyleChecker,
    StyleConfig,
    StyleIssue,
    StyleReport,
    TenseConsistencyRule,
    _calculate_file_score,
    _content_lines,
    _is_sentence_case,
    _is_title_case,
)
from tests.helpers import make_settings


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_style_issue_defaults(self) -> None:
        issue = StyleIssue(rule="test", severity="warning", line=1, message="msg")
        assert issue.column == 0
        assert issue.suggestion == ""
        assert issue.context == ""

    def test_file_style_result_defaults(self) -> None:
        result = FileStyleResult(file_path="test.md")
        assert result.issues == []
        assert result.score == 100.0

    def test_style_report_defaults(self) -> None:
        report = StyleReport()
        assert report.total_files == 0
        assert report.total_issues == 0
        assert report.aggregate_score == 100.0

    def test_style_config_defaults(self) -> None:
        config = StyleConfig()
        assert len(config.enabled_rules) == 5
        assert config.max_sentence_words == 40
        assert config.heading_style == "sentence"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestContentLines:
    def test_strips_code_blocks(self) -> None:
        content = "line1\n```python\ncode here\n```\nline2"
        lines = _content_lines(content)
        assert lines[0] == "line1"
        assert lines[1] == ""  # ``` fence
        assert lines[2] == ""  # code
        assert lines[3] == ""  # ``` fence
        assert lines[4] == "line2"

    def test_strips_frontmatter(self) -> None:
        content = "---\ntitle: Test\n---\nActual content"
        lines = _content_lines(content)
        assert lines[0] == ""  # ---
        assert lines[1] == ""  # title
        assert lines[2] == ""  # ---
        assert lines[3] == "Actual content"

    def test_normal_content_preserved(self) -> None:
        content = "Hello world\nSecond line"
        lines = _content_lines(content)
        assert lines[0] == "Hello world"
        assert lines[1] == "Second line"


class TestSentenceCase:
    def test_valid_sentence_case(self) -> None:
        assert _is_sentence_case("Getting started with the API", []) is True

    def test_invalid_sentence_case(self) -> None:
        assert _is_sentence_case("Getting Started With The API", []) is False

    def test_allows_acronyms(self) -> None:
        assert _is_sentence_case("Configure the MCP server", []) is True

    def test_allows_custom_terms(self) -> None:
        assert _is_sentence_case("Configure DocsMCP settings", ["DocsMCP"]) is True

    def test_empty_string(self) -> None:
        assert _is_sentence_case("", []) is True

    def test_single_word(self) -> None:
        assert _is_sentence_case("Hello", []) is True

    def test_camel_case_identifier(self) -> None:
        assert _is_sentence_case("Using camelCase in code", []) is True


class TestTitleCase:
    def test_valid_title_case(self) -> None:
        assert _is_title_case("Getting Started With Docker", []) is True

    def test_articles_lowercase(self) -> None:
        assert _is_title_case("The Art of the Deal", []) is True

    def test_invalid_title_case(self) -> None:
        assert _is_title_case("getting started", []) is False

    def test_first_word_must_be_capitalized(self) -> None:
        assert _is_title_case("the Start", []) is False

    def test_allows_acronyms(self) -> None:
        assert _is_title_case("Using the MCP Protocol", []) is True

    def test_empty_string(self) -> None:
        assert _is_title_case("", []) is True


class TestCalculateFileScore:
    def test_no_issues(self) -> None:
        assert _calculate_file_score([]) == 100.0

    def test_error_deducts_10(self) -> None:
        issues = [StyleIssue(rule="test", severity="error", line=1, message="x")]
        assert _calculate_file_score(issues) == 90.0

    def test_warning_deducts_5(self) -> None:
        issues = [StyleIssue(rule="test", severity="warning", line=1, message="x")]
        assert _calculate_file_score(issues) == 95.0

    def test_suggestion_deducts_2(self) -> None:
        issues = [StyleIssue(rule="test", severity="suggestion", line=1, message="x")]
        assert _calculate_file_score(issues) == 98.0

    def test_score_floors_at_zero(self) -> None:
        issues = [StyleIssue(rule="test", severity="error", line=i, message="x") for i in range(15)]
        assert _calculate_file_score(issues) == 0.0


# ---------------------------------------------------------------------------
# PassiveVoiceRule tests
# ---------------------------------------------------------------------------


class TestPassiveVoiceRule:
    def setup_method(self) -> None:
        self.rule = PassiveVoiceRule()
        self.config = StyleConfig()

    def test_detects_passive_voice(self) -> None:
        content = "The file was created by the system."
        issues = self.rule.check(content, self.config)
        assert len(issues) >= 1
        assert issues[0].rule == "passive_voice"

    def test_ignores_active_voice(self) -> None:
        content = "The system creates the file."
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_ignores_code_blocks(self) -> None:
        content = "Normal text\n```\nwas created\n```\nMore text"
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_ignores_frontmatter(self) -> None:
        content = "---\ntitle: was created\n---\nActive text here."
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_reports_correct_line(self) -> None:
        content = "First line.\nThe data is processed by the server."
        issues = self.rule.check(content, self.config)
        assert len(issues) >= 1
        assert issues[0].line == 2

    def test_severity_is_suggestion(self) -> None:
        content = "The file was deleted."
        issues = self.rule.check(content, self.config)
        assert len(issues) >= 1
        assert issues[0].severity == "suggestion"


# ---------------------------------------------------------------------------
# JargonRule tests
# ---------------------------------------------------------------------------


class TestJargonRule:
    def setup_method(self) -> None:
        self.rule = JargonRule()
        self.config = StyleConfig()

    def test_detects_jargon(self) -> None:
        content = "We need to leverage this technology."
        issues = self.rule.check(content, self.config)
        assert len(issues) == 1
        assert "leverage" in issues[0].message.lower()

    def test_detects_multi_word_jargon(self) -> None:
        content = "Let's circle back on this tomorrow."
        issues = self.rule.check(content, self.config)
        assert len(issues) >= 1

    def test_ignores_clean_text(self) -> None:
        content = "Install the package and configure settings."
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_custom_terms_exclude_jargon(self) -> None:
        config = StyleConfig(custom_terms=["leverage"])
        content = "We leverage this technology."
        issues = self.rule.check(content, config)
        assert len(issues) == 0

    def test_custom_jargon_terms(self) -> None:
        config = StyleConfig(jargon_terms=["foobar"])
        content = "We use foobar here."
        issues = self.rule.check(content, config)
        assert len(issues) == 1

    def test_ignores_code_blocks(self) -> None:
        content = "Text\n```\nleverage\n```\nMore text"
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_severity_is_warning(self) -> None:
        content = "We utilize this feature."
        issues = self.rule.check(content, self.config)
        assert len(issues) >= 1
        assert issues[0].severity == "warning"


# ---------------------------------------------------------------------------
# SentenceLengthRule tests
# ---------------------------------------------------------------------------


class TestSentenceLengthRule:
    def setup_method(self) -> None:
        self.rule = SentenceLengthRule()
        self.config = StyleConfig()

    def test_flags_long_sentence(self) -> None:
        words = " ".join(f"word{i}" for i in range(45))
        content = f"{words}."
        issues = self.rule.check(content, self.config)
        assert len(issues) >= 1
        assert "45 words" in issues[0].message

    def test_accepts_short_sentence(self) -> None:
        content = "This is a short sentence."
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_custom_max_words(self) -> None:
        config = StyleConfig(max_sentence_words=5)
        content = "This sentence has exactly six words."
        issues = self.rule.check(content, config)
        # The sentence before the period has 6 words
        assert len(issues) >= 1

    def test_ignores_headings(self) -> None:
        words = " ".join(f"word{i}" for i in range(50))
        content = f"# {words}"
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_ignores_tables(self) -> None:
        words = " ".join(f"word{i}" for i in range(50))
        content = f"| {words} |"
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_ignores_code_blocks(self) -> None:
        words = " ".join(f"word{i}" for i in range(50))
        content = f"Text\n```\n{words}\n```\nMore text"
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# HeadingConsistencyRule tests
# ---------------------------------------------------------------------------


class TestHeadingConsistencyRule:
    def setup_method(self) -> None:
        self.rule = HeadingConsistencyRule()

    def test_sentence_case_valid(self) -> None:
        config = StyleConfig(heading_style="sentence")
        content = "# Getting started with the server"
        issues = self.rule.check(content, config)
        assert len(issues) == 0

    def test_sentence_case_with_custom_term(self) -> None:
        config = StyleConfig(heading_style="sentence", custom_terms=["Docker"])
        content = "# Getting started with Docker"
        issues = self.rule.check(content, config)
        assert len(issues) == 0

    def test_sentence_case_invalid(self) -> None:
        config = StyleConfig(heading_style="sentence")
        content = "# Getting Started With Everything"
        issues = self.rule.check(content, config)
        assert len(issues) == 1
        assert "not sentence case" in issues[0].message

    def test_title_case_valid(self) -> None:
        config = StyleConfig(heading_style="title")
        content = "# Getting Started With Docker"
        issues = self.rule.check(content, config)
        assert len(issues) == 0

    def test_title_case_invalid(self) -> None:
        config = StyleConfig(heading_style="title")
        content = "# getting started with docker"
        issues = self.rule.check(content, config)
        assert len(issues) == 1
        assert "not title case" in issues[0].message

    def test_allows_acronyms(self) -> None:
        config = StyleConfig(heading_style="sentence")
        content = "# Configure the MCP server"
        issues = self.rule.check(content, config)
        assert len(issues) == 0

    def test_allows_all_caps_heading(self) -> None:
        config = StyleConfig(heading_style="sentence")
        content = "# FAQ"
        issues = self.rule.check(content, config)
        assert len(issues) == 0

    def test_multiple_heading_levels(self) -> None:
        config = StyleConfig(heading_style="sentence")
        content = "# Valid heading\n\n## Also Valid\n\n### Another One"
        issues = self.rule.check(content, config)
        # "Also Valid" and "Another One" have capitals after first word
        assert len(issues) == 2

    def test_custom_terms_in_heading(self) -> None:
        config = StyleConfig(heading_style="sentence", custom_terms=["FastMCP"])
        content = "# Using FastMCP decorators"
        issues = self.rule.check(content, config)
        assert len(issues) == 0

    def test_heading_with_trailing_punctuation(self) -> None:
        config = StyleConfig(heading_style="sentence")
        content = "# What is this?"
        issues = self.rule.check(content, config)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# TenseConsistencyRule tests
# ---------------------------------------------------------------------------


class TestTenseConsistencyRule:
    def setup_method(self) -> None:
        self.rule = TenseConsistencyRule()
        self.config = StyleConfig()

    def test_consistent_imperative(self) -> None:
        lines = [
            "Install the package.",
            "Configure the settings.",
            "Run the tests.",
            "Check the output.",
            "Verify the results.",
            "Deploy the application.",
        ]
        content = "\n".join(lines)
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_consistent_declarative(self) -> None:
        lines = [
            "This tool checks style.",
            "The system validates input.",
            "It processes the request.",
            "The function returns a value.",
            "This module handles errors.",
            "The config defines settings.",
        ]
        content = "\n".join(lines)
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_mixed_tense_flags_minority(self) -> None:
        lines = [
            "Install the package.",
            "Configure the settings.",
            "Run the tests.",
            "Check the output.",
            "This module handles errors.",
            "Verify the results.",
        ]
        content = "\n".join(lines)
        issues = self.rule.check(content, self.config)
        # "This module handles errors" is the minority (declarative)
        assert len(issues) >= 1
        assert issues[0].rule == "tense_consistency"

    def test_too_few_lines_no_issues(self) -> None:
        content = "Install the package.\nThis is a note."
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0

    def test_ignores_headings(self) -> None:
        lines = [
            "# Heading",
            "Install the package.",
            "Configure the settings.",
            "Run the tests.",
            "Check the output.",
            "Verify the results.",
        ]
        content = "\n".join(lines)
        issues = self.rule.check(content, self.config)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# StyleChecker tests
# ---------------------------------------------------------------------------


class TestStyleChecker:
    def test_default_config(self) -> None:
        checker = StyleChecker()
        assert len(checker.rules) == 5

    def test_custom_config(self) -> None:
        config = StyleConfig(enabled_rules=["jargon", "passive_voice"])
        checker = StyleChecker(config)
        assert len(checker.rules) == 2

    def test_unknown_rule_ignored(self) -> None:
        config = StyleConfig(enabled_rules=["nonexistent", "jargon"])
        checker = StyleChecker(config)
        assert len(checker.rules) == 1

    def test_check_content_returns_result(self) -> None:
        checker = StyleChecker()
        result = checker.check_content("# Hello\n\nThis is clean text.", file_path="test.md")
        assert isinstance(result, FileStyleResult)
        assert result.file_path == "test.md"

    def test_check_content_finds_issues(self) -> None:
        config = StyleConfig(enabled_rules=["jargon"])
        checker = StyleChecker(config)
        result = checker.check_content("We need to leverage this feature.")
        assert len(result.issues) >= 1

    def test_check_file(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("# Hello\n\nClean content here.", encoding="utf-8")
        checker = StyleChecker()
        result = checker.check_file(md, relative_to=tmp_path)
        assert result.file_path == "test.md"

    def test_check_file_missing(self, tmp_path: Path) -> None:
        checker = StyleChecker()
        result = checker.check_file(tmp_path / "missing.md", relative_to=tmp_path)
        assert result.score == 100.0

    def test_check_project(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nWe leverage this tool.")
        _write(tmp_path / "docs" / "guide.md", "# Guide\n\nClean text.")
        checker = StyleChecker(StyleConfig(enabled_rules=["jargon"]))
        report = checker.check_project(tmp_path)
        assert isinstance(report, StyleReport)
        assert report.total_files == 2
        assert report.total_issues >= 1

    def test_check_project_empty(self, tmp_path: Path) -> None:
        checker = StyleChecker()
        report = checker.check_project(tmp_path)
        assert report.total_files == 0
        assert report.aggregate_score == 100.0

    def test_check_project_with_doc_dirs(self, tmp_path: Path) -> None:
        _write(tmp_path / "custom" / "guide.md", "# Guide\n\nContent.")
        checker = StyleChecker()
        report = checker.check_project(tmp_path, doc_dirs=["custom"])
        assert report.total_files >= 1

    def test_issues_sorted_by_line(self) -> None:
        content = "We leverage this.\nNormal line.\nWe utilize that.\n"
        config = StyleConfig(enabled_rules=["jargon"])
        checker = StyleChecker(config)
        result = checker.check_content(content)
        if len(result.issues) >= 2:
            assert result.issues[0].line <= result.issues[1].line

    def test_config_property(self) -> None:
        config = StyleConfig(max_sentence_words=20)
        checker = StyleChecker(config)
        assert checker.config.max_sentence_words == 20

    def test_report_top_issues(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "README.md",
            "# README\n\nWe leverage this. We utilize that. Let's circle back.",
        )
        config = StyleConfig(enabled_rules=["jargon"])
        checker = StyleChecker(config)
        report = checker.check_project(tmp_path)
        assert "jargon" in report.issue_counts

    def test_report_issue_counts(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "README.md",
            "# README\n\nThe file was created. We leverage this.",
        )
        checker = StyleChecker()
        report = checker.check_project(tmp_path)
        assert isinstance(report.issue_counts, dict)

    def test_skips_license(self, tmp_path: Path) -> None:
        _write(tmp_path / "LICENSE.md", "# License\n\nWe leverage everything.")
        config = StyleConfig(enabled_rules=["jargon"])
        checker = StyleChecker(config)
        report = checker.check_project(tmp_path)
        assert report.total_files == 0


# ---------------------------------------------------------------------------
# Integration: all rules together
# ---------------------------------------------------------------------------


class TestAllRulesTogether:
    def test_multiple_issues_in_one_file(self) -> None:
        content = (
            "---\ntitle: Test\n---\n"
            "# Getting Started With Docker\n\n"
            "We need to leverage this robust technology "
            "to utilize the synergy of our platform.\n\n"
            "The configuration was created by the system. "
            "The file is processed automatically.\n"
        )
        checker = StyleChecker()
        result = checker.check_content(content, file_path="test.md")
        # Should find heading inconsistency, jargon, and passive voice
        rules_found = {i.rule for i in result.issues}
        assert "jargon" in rules_found
        assert result.score < 100.0

    def test_clean_file_gets_perfect_score(self) -> None:
        content = (
            "# Getting started\n\n"
            "Install the package using pip.\n\n"
            "Configure the settings file.\n\n"
            "Run the test suite.\n"
        )
        config = StyleConfig(enabled_rules=["jargon", "sentence_length"])
        checker = StyleChecker(config)
        result = checker.check_content(content)
        assert result.score == 100.0
        assert len(result.issues) == 0


# ---------------------------------------------------------------------------
# MCP tool handler tests (Story 84.2)
# ---------------------------------------------------------------------------


class TestDocsCheckStyleTool:
    async def test_success_project_scan(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nWe leverage this tool.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(project_root=str(tmp_path))

        assert result["success"] is True
        assert "total_files" in result["data"]
        assert "total_issues" in result["data"]
        assert "aggregate_score" in result["data"]

    async def test_invalid_root(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_style

        bad_path = str(tmp_path / "nonexistent_dir_xyz")
        result = await docs_check_style(project_root=bad_path)
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    async def test_specific_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "doc.md", "# Doc\n\nWe utilize synergy here.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                files="doc.md",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["total_files"] == 1
        assert result["data"]["total_issues"] >= 1

    async def test_custom_rules(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nWe leverage this.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                rules="jargon",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        # Only jargon rule should fire
        for f in result["data"].get("files", []):
            for issue in f.get("issues", []):
                assert issue["rule"] == "jargon"

    async def test_custom_terms(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nWe leverage this.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                rules="jargon",
                custom_terms="leverage",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        # leverage is excluded via custom_terms
        assert result["data"]["total_issues"] == 0

    async def test_vale_format(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nWe leverage this.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                rules="jargon",
                output_format="vale",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["format"] == "vale"
        assert "results" in result["data"]

    async def test_heading_style_param(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# getting started\n\nContent.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                rules="heading_consistency",
                heading_style="title",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        # "getting started" is not title case
        assert result["data"]["total_issues"] >= 1

    async def test_max_sentence_words_param(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nThis has exactly five words.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                rules="sentence_length",
                max_sentence_words=3,
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["total_issues"] >= 1

    async def test_loads_terms_file(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nWe leverage this.")
        _write(tmp_path / ".docsmcp-terms.txt", "# Project terms\nleverage\n")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                rules="jargon",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        # "leverage" is in .docsmcp-terms.txt so should be excluded
        assert result["data"]["total_issues"] == 0

    async def test_settings_custom_terms(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nWe leverage this.")
        from docs_mcp.server_val_tools import docs_check_style

        mock = make_settings(tmp_path)
        mock.style_custom_terms = ["leverage"]
        mock.style_enabled_rules = []
        mock.style_heading = "sentence"
        mock.style_max_sentence_words = 40
        mock.style_jargon_terms = []

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = mock
            result = await docs_check_style(
                rules="jargon",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["total_issues"] == 0

    async def test_next_steps_included(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nContent.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(project_root=str(tmp_path))

        assert result["success"] is True
        assert "next_steps" in result["data"]


# ---------------------------------------------------------------------------
# Project scan style summary (Story 84.4)
# ---------------------------------------------------------------------------


class TestProjectScanStyleSummary:
    async def test_scan_includes_style_summary(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nWe leverage this tool.")
        _write(tmp_path / ".git" / "config", "")  # fake git dir
        from docs_mcp.server import docs_project_scan

        with patch("docs_mcp.config.settings.load_docs_settings") as mock_load:
            mock_load.return_value = make_settings(tmp_path)
            result = await docs_project_scan(project_root=str(tmp_path))

        assert result["success"] is True
        assert "style_summary" in result["data"]
        summary = result["data"]["style_summary"]
        assert "total_files" in summary
        assert "total_issues" in summary
        assert "aggregate_score" in summary

    async def test_scan_no_docs_no_style_summary(self, tmp_path: Path) -> None:
        from docs_mcp.server import docs_project_scan

        with patch("docs_mcp.config.settings.load_docs_settings") as mock_load:
            mock_load.return_value = make_settings(tmp_path)
            result = await docs_project_scan(project_root=str(tmp_path))

        assert result["success"] is True
        # No docs = no style_summary key (or 0 files)
        if "style_summary" in result["data"]:
            assert result["data"]["style_summary"]["total_files"] == 0

    async def test_scan_skips_style_when_disabled_in_config(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Readme\n\nWe leverage this tool.")
        from docs_mcp.server import docs_project_scan

        with patch("docs_mcp.config.settings.load_docs_settings") as mock_load:
            mock_load.return_value = make_settings(
                tmp_path,
                style_include_in_project_scan=False,
            )
            result = await docs_project_scan(project_root=str(tmp_path))

        assert result["success"] is True
        assert "style_summary" not in result["data"]


@pytest.mark.asyncio
class TestStyleCheckPathResolution:
    """Issue #84: docs_check_style must not silently return 0 files."""

    async def test_nonexistent_relative_path_returns_error(self, tmp_path: Path) -> None:
        """Relative path that doesn't resolve should return NO_FILES_FOUND."""
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                files="nonexistent/doc.md",
                project_root=str(tmp_path),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "NO_FILES_FOUND"
        assert "nonexistent/doc.md" in result["error"]["message"]

    async def test_nonexistent_absolute_path_returns_error(self, tmp_path: Path) -> None:
        """Absolute path that doesn't exist should return NO_FILES_FOUND."""
        from docs_mcp.server_val_tools import docs_check_style

        bad_path = str(tmp_path / "does_not_exist.md")
        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                files=bad_path,
                project_root=str(tmp_path),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "NO_FILES_FOUND"

    async def test_mixed_existing_and_missing_files(self, tmp_path: Path) -> None:
        """When some files exist and others don't, check existing + warn about missing."""
        _write(tmp_path / "real.md", "# Real doc\n\nThis is real content.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                files="real.md,ghost.md",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["total_files"] == 1
        assert "warnings" in result["data"]
        assert any("ghost.md" in w for w in result["data"]["warnings"])

    async def test_all_files_missing_returns_zero_score(self, tmp_path: Path) -> None:
        """Score should NOT be 100 when zero files were checked."""
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                files="a.md,b.md,c.md",
                project_root=str(tmp_path),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "NO_FILES_FOUND"

    async def test_error_includes_requested_files(self, tmp_path: Path) -> None:
        """NO_FILES_FOUND error should include which files were requested."""
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                files="missing.md",
                project_root=str(tmp_path),
            )

        assert result["success"] is False
        assert "missing.md" in result["error"]["requested_files"]
        assert str(tmp_path) in result["error"]["project_root"]

    async def test_existing_file_still_works(self, tmp_path: Path) -> None:
        """Regression: existing relative paths should still be checked normally."""
        _write(tmp_path / "doc.md", "# Doc\n\nWe utilize synergy here.")
        from docs_mcp.server_val_tools import docs_check_style

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_style(
                files="doc.md",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert result["data"]["total_files"] == 1
        assert result["data"]["total_issues"] >= 1
