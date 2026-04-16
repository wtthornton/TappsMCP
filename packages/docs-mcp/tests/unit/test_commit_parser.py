"""Tests for docs_mcp.analyzers.commit_parser."""

from __future__ import annotations

import pytest

from docs_mcp.analyzers.commit_parser import (
    ParsedCommit,
    classify_commit,
    parse_conventional_commit,
)

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestParsedCommitModel:
    """Tests for the ParsedCommit Pydantic model."""

    def test_default_values(self) -> None:
        commit = ParsedCommit()
        assert commit.type == ""
        assert commit.scope == ""
        assert commit.description == ""
        assert commit.body == ""
        assert commit.breaking is False
        assert commit.raw == ""
        assert commit.is_conventional is False

    def test_explicit_values(self) -> None:
        commit = ParsedCommit(
            type="feat",
            scope="parser",
            description="add new feature",
            raw="feat(parser): add new feature",
            is_conventional=True,
        )
        assert commit.type == "feat"
        assert commit.scope == "parser"
        assert commit.is_conventional is True


# ---------------------------------------------------------------------------
# Conventional commit parsing
# ---------------------------------------------------------------------------


class TestParseConventionalCommit:
    """Tests for parse_conventional_commit."""

    @pytest.mark.parametrize(
        "message,expected_type,expected_desc",
        [
            ("feat: add user login", "feat", "add user login"),
            ("fix: resolve null pointer", "fix", "resolve null pointer"),
            ("docs: update readme", "docs", "update readme"),
            ("chore: bump dependencies", "chore", "bump dependencies"),
            ("refactor: simplify parser", "refactor", "simplify parser"),
            ("test: add unit tests", "test", "add unit tests"),
        ],
        ids=["feat", "fix", "docs", "chore", "refactor", "test"],
    )
    def test_type_no_scope(self, message: str, expected_type: str, expected_desc: str) -> None:
        result = parse_conventional_commit(message)
        assert result.type == expected_type
        assert result.scope == ""
        assert result.description == expected_desc
        assert result.is_conventional is True

    def test_with_scope(self) -> None:
        result = parse_conventional_commit("feat(auth): add OAuth support")
        assert result.type == "feat"
        assert result.scope == "auth"
        assert result.description == "add OAuth support"
        assert result.is_conventional is True

    def test_breaking_bang(self) -> None:
        result = parse_conventional_commit("feat!: remove legacy API")
        assert result.type == "feat"
        assert result.breaking is True
        assert result.is_conventional is True

    def test_breaking_bang_with_scope(self) -> None:
        result = parse_conventional_commit("fix(api)!: change response format")
        assert result.type == "fix"
        assert result.scope == "api"
        assert result.breaking is True
        assert result.is_conventional is True

    def test_breaking_change_in_body(self) -> None:
        msg = "feat: new API\n\nBREAKING CHANGE: removed old endpoints"
        result = parse_conventional_commit(msg)
        assert result.type == "feat"
        assert result.breaking is True
        assert result.body == "BREAKING CHANGE: removed old endpoints"

    def test_breaking_change_hyphenated(self) -> None:
        msg = "feat: new API\n\nBREAKING-CHANGE: removed old endpoints"
        result = parse_conventional_commit(msg)
        assert result.breaking is True

    def test_multiline_body(self) -> None:
        msg = "feat: add feature\n\nThis is a detailed explanation\nof the change."
        result = parse_conventional_commit(msg)
        assert result.type == "feat"
        assert result.description == "add feature"
        assert "detailed explanation" in result.body
        assert result.is_conventional is True

    def test_preserves_raw(self) -> None:
        msg = "feat(scope): description"
        result = parse_conventional_commit(msg)
        assert result.raw == msg

    def test_non_conventional_returns_false(self) -> None:
        result = parse_conventional_commit("Updated the readme file")
        assert result.is_conventional is False
        assert result.type == ""
        assert result.raw == "Updated the readme file"

    def test_empty_message(self) -> None:
        result = parse_conventional_commit("")
        assert result.is_conventional is False
        assert result.type == ""
        assert result.raw == ""

    def test_type_case_insensitive(self) -> None:
        result = parse_conventional_commit("FEAT: uppercase type")
        assert result.type == "feat"
        assert result.is_conventional is True

    def test_no_breaking_when_not_present(self) -> None:
        result = parse_conventional_commit("feat: normal change")
        assert result.breaking is False

    def test_colon_without_space(self) -> None:
        # "feat:add something" - should still match (regex uses \s*)
        result = parse_conventional_commit("feat:add something")
        assert result.type == "feat"
        assert result.description == "add something"
        assert result.is_conventional is True

    def test_empty_scope(self) -> None:
        result = parse_conventional_commit("feat(): empty scope")
        assert result.scope == ""
        assert result.type == "feat"
        assert result.is_conventional is True


# ---------------------------------------------------------------------------
# Keyword-based classification
# ---------------------------------------------------------------------------


class TestClassifyCommit:
    """Tests for classify_commit (keyword heuristic fallback)."""

    def test_conventional_passthrough(self) -> None:
        """Conventional commits should be parsed as-is."""
        result = classify_commit("feat(auth): add login")
        assert result.is_conventional is True
        assert result.type == "feat"

    @pytest.mark.parametrize(
        "message,expected_type",
        [
            ("Fixed the login bug", "fix"),
            ("Bug in user registration", "fix"),
            ("Patch for security issue", "fix"),
            ("Add new dashboard feature", "feat"),
            ("New feature: dark mode", "feat"),
            ("Implement caching layer", "feat"),
            ("Updated documentation", "docs"),
            ("Update README with examples", "docs"),
            ("Refactor database module", "refactor"),
            ("Clean up unused imports", "refactor"),
            ("Unit tests for the parser module", "test"),
            ("Bump version to 2.0.0", "chore"),
        ],
        ids=[
            "fix-fixed",
            "fix-bug",
            "fix-patch",
            "feat-add",
            "feat-feature",
            "feat-implement",
            "docs-documentation",
            "docs-readme",
            "refactor-refactor",
            "refactor-clean",
            "test-keyword",
            "chore-default",
        ],
    )
    def test_keyword_classification(self, message: str, expected_type: str) -> None:
        result = classify_commit(message)
        assert result.type == expected_type
        assert result.is_conventional is False

    def test_empty_message_classify(self) -> None:
        result = classify_commit("")
        assert result.type == ""
        assert result.is_conventional is False

    def test_description_is_header(self) -> None:
        """For non-conventional, description should be the header line."""
        result = classify_commit("Fixed a login issue")
        assert result.description == "Fixed a login issue"

    def test_classify_with_body(self) -> None:
        msg = "Fixed the bug\n\nMore details about the fix here."
        result = classify_commit(msg)
        assert result.type == "fix"
        assert result.description == "Fixed the bug"
        assert result.body == "More details about the fix here."
