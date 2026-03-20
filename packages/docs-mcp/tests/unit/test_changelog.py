"""Tests for changelog generation."""

from __future__ import annotations

import pytest

from docs_mcp.analyzers.commit_parser import ParsedCommit
from docs_mcp.generators.changelog import (
    ChangelogEntry,
    ChangelogGenerator,
    ChangelogVersion,
)
from tests.helpers import make_commit as _commit
from tests.helpers import make_version as _version


@pytest.fixture
def generator() -> ChangelogGenerator:
    return ChangelogGenerator()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestChangelogModels:
    def test_changelog_entry_defaults(self) -> None:
        entry = ChangelogEntry(type="Added", description="New feature")
        assert entry.type == "Added"
        assert entry.description == "New feature"
        assert entry.scope == ""
        assert entry.commit_hash == ""
        assert entry.breaking is False

    def test_changelog_entry_with_all_fields(self) -> None:
        entry = ChangelogEntry(
            type="Fixed",
            description="Bug fix",
            scope="auth",
            commit_hash="abc1234",
            breaking=True,
        )
        assert entry.type == "Fixed"
        assert entry.scope == "auth"
        assert entry.commit_hash == "abc1234"
        assert entry.breaking is True

    def test_changelog_version_defaults(self) -> None:
        v = ChangelogVersion(version="1.0.0", date="2026-01-01")
        assert v.version == "1.0.0"
        assert v.date == "2026-01-01"
        assert v.entries == []


# ---------------------------------------------------------------------------
# Keep-a-Changelog format tests
# ---------------------------------------------------------------------------


class TestKeepAChangelog:
    def test_empty_versions(self, generator: ChangelogGenerator) -> None:
        result = generator.generate([], format="keep-a-changelog")
        assert "# Changelog" in result
        assert "Keep a Changelog" in result

    def test_single_version_with_feat(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("1.0.0", "2026-01-15T00:00:00+00:00", [
                _commit("feat: add user auth"),
            ]),
        ]
        result = generator.generate(versions, format="keep-a-changelog", include_unreleased=False)
        assert "## [1.0.0] - 2026-01-15" in result
        assert "### Added" in result
        assert "add user auth" in result

    def test_single_version_with_fix(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("1.0.1", "2026-01-20T00:00:00+00:00", [
                _commit("fix: resolve login bug"),
            ]),
        ]
        result = generator.generate(versions, format="keep-a-changelog", include_unreleased=False)
        assert "## [1.0.1] - 2026-01-20" in result
        assert "### Fixed" in result
        assert "resolve login bug" in result

    def test_multiple_versions(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("2.0.0", "2026-02-15T00:00:00+00:00", [
                _commit("feat: new dashboard"),
            ]),
            _version("1.0.0", "2026-01-01T00:00:00+00:00", [
                _commit("feat: initial release"),
            ]),
        ]
        result = generator.generate(versions, format="keep-a-changelog", include_unreleased=False)
        assert "## [2.0.0] - 2026-02-15" in result
        assert "## [1.0.0] - 2026-01-01" in result
        # Newer version should appear first
        pos_2 = result.index("[2.0.0]")
        pos_1 = result.index("[1.0.0]")
        assert pos_2 < pos_1

    def test_breaking_change_highlighted(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("2.0.0", "2026-02-15T00:00:00+00:00", [
                _commit("feat!: redesign API"),
            ]),
        ]
        result = generator.generate(versions, format="keep-a-changelog", include_unreleased=False)
        assert "**BREAKING**" in result

    def test_scope_included(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("1.1.0", "2026-02-01T00:00:00+00:00", [
                _commit("feat(auth): add OAuth support"),
            ]),
        ]
        result = generator.generate(versions, format="keep-a-changelog", include_unreleased=False)
        assert "auth" in result
        assert "add OAuth support" in result

    def test_commit_type_mapping(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("1.2.0", "2026-02-10T00:00:00+00:00", [
                _commit("feat: new feature"),
                _commit("fix: bug fix"),
                _commit("docs: update readme"),
                _commit("refactor: clean code"),
                _commit("revert: undo change"),
                _commit("security: patch vuln"),
            ]),
        ]
        result = generator.generate(versions, format="keep-a-changelog", include_unreleased=False)
        assert "### Added" in result
        assert "### Fixed" in result
        assert "### Changed" in result
        assert "### Removed" in result
        assert "### Security" in result

    def test_unreleased_section_included(self, generator: ChangelogGenerator) -> None:
        unreleased = [
            _commit("feat: work in progress"),
        ]
        versions = [
            _version("1.0.0", "2026-01-01T00:00:00+00:00", [
                _commit("feat: initial release"),
            ]),
        ]
        result = generator.generate(
            versions,
            format="keep-a-changelog",
            include_unreleased=True,
            unreleased_commits=unreleased,
        )
        assert "## [Unreleased]" in result
        assert "work in progress" in result

    def test_unreleased_section_excluded(self, generator: ChangelogGenerator) -> None:
        unreleased = [
            _commit("feat: work in progress"),
        ]
        versions = [
            _version("1.0.0", "2026-01-01T00:00:00+00:00", [
                _commit("feat: initial release"),
            ]),
        ]
        result = generator.generate(
            versions,
            format="keep-a-changelog",
            include_unreleased=False,
            unreleased_commits=unreleased,
        )
        assert "[Unreleased]" not in result

    def test_empty_version_no_commits(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("1.0.0", "2026-01-01T00:00:00+00:00", []),
        ]
        result = generator.generate(versions, format="keep-a-changelog", include_unreleased=False)
        assert "## [1.0.0] - 2026-01-01" in result
        # No category headers for empty version
        assert "### Added" not in result

    def test_non_conventional_commit_classified(self, generator: ChangelogGenerator) -> None:
        """Non-conventional commits fall back to keyword classification."""
        versions = [
            _version("1.0.0", "2026-01-01T00:00:00+00:00", [
                _commit("Add new login page"),
            ]),
        ]
        result = generator.generate(versions, format="keep-a-changelog", include_unreleased=False)
        # "Add" keyword -> feat -> "Added"
        assert "### Added" in result


# ---------------------------------------------------------------------------
# Conventional format tests
# ---------------------------------------------------------------------------


class TestConventionalFormat:
    def test_empty_versions(self, generator: ChangelogGenerator) -> None:
        result = generator.generate([], format="conventional")
        assert "# Changelog" in result

    def test_single_version(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("1.0.0", "2026-01-15T00:00:00+00:00", [
                _commit("feat: add user auth"),
                _commit("fix: resolve login bug"),
            ]),
        ]
        result = generator.generate(versions, format="conventional", include_unreleased=False)
        assert "## 1.0.0 (2026-01-15)" in result
        assert "### Features" in result
        assert "### Bug Fixes" in result

    def test_scope_in_conventional(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("1.0.0", "2026-01-15T00:00:00+00:00", [
                _commit("feat(api): add endpoint", short_hash="abc1234"),
            ]),
        ]
        result = generator.generate(versions, format="conventional", include_unreleased=False)
        assert "**api:**" in result
        assert "add endpoint" in result
        assert "abc1234" in result

    def test_breaking_changes_section(self, generator: ChangelogGenerator) -> None:
        versions = [
            _version("2.0.0", "2026-02-01T00:00:00+00:00", [
                _commit("feat!: redesign API"),
            ]),
        ]
        result = generator.generate(versions, format="conventional", include_unreleased=False)
        assert "### BREAKING CHANGES" in result

    def test_conventional_unreleased(self, generator: ChangelogGenerator) -> None:
        unreleased = [
            _commit("feat: WIP feature"),
        ]
        result = generator.generate(
            [],
            format="conventional",
            include_unreleased=True,
            unreleased_commits=unreleased,
        )
        assert "## Unreleased" in result
        assert "WIP feature" in result


# ---------------------------------------------------------------------------
# Helper method tests
# ---------------------------------------------------------------------------


class TestHelperMethods:
    def test_format_date_iso(self, generator: ChangelogGenerator) -> None:
        assert generator._format_date("2026-02-15T10:00:00+00:00") == "2026-02-15"

    def test_format_date_plain(self, generator: ChangelogGenerator) -> None:
        assert generator._format_date("2026-02-15") == "2026-02-15"

    def test_format_date_empty(self, generator: ChangelogGenerator) -> None:
        assert generator._format_date("") == "unknown"

    def test_group_entries_preserves_order(self, generator: ChangelogGenerator) -> None:
        entries = [
            ChangelogEntry(type="Fixed", description="fix 1"),
            ChangelogEntry(type="Added", description="feat 1"),
            ChangelogEntry(type="Fixed", description="fix 2"),
        ]
        categories = ["Added", "Fixed"]
        grouped = generator._group_entries(entries, categories)
        keys = list(grouped.keys())
        assert keys == ["Added", "Fixed"]
        assert len(grouped["Added"]) == 1
        assert len(grouped["Fixed"]) == 2

    def test_group_entries_empty(self, generator: ChangelogGenerator) -> None:
        grouped = generator._group_entries([], ["Added", "Fixed"])
        assert grouped == {}

    def test_commits_to_entries_keep_a_changelog(self, generator: ChangelogGenerator) -> None:
        commits = [
            _commit("feat: add feature"),
            _commit("fix: bug fix"),
        ]
        entries = generator._commits_to_entries(commits, format="keep-a-changelog")
        assert len(entries) == 2
        assert entries[0].type == "Added"
        assert entries[1].type == "Fixed"

    def test_commits_to_entries_conventional(self, generator: ChangelogGenerator) -> None:
        commits = [
            _commit("feat: add feature"),
            _commit("fix: bug fix"),
        ]
        entries = generator._commits_to_entries(commits, format="conventional")
        assert len(entries) == 2
        assert entries[0].type == "Features"
        assert entries[1].type == "Bug Fixes"

    def test_type_map_coverage(self) -> None:
        """All mapped types should produce valid Keep-a-Changelog categories."""
        valid_categories = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
        for commit_type, category in ChangelogGenerator.TYPE_MAP.items():
            assert category in valid_categories, (
                f"TYPE_MAP[{commit_type!r}] = {category!r} is not a valid category"
            )

    def test_conventional_type_map_coverage(self) -> None:
        """All mapped types should produce valid conventional categories."""
        valid_categories = {
            "Features", "Bug Fixes", "Documentation", "Refactoring",
            "Performance", "Tests", "Build", "CI", "Chores", "Reverts",
            "Deprecated", "Security",
        }
        for commit_type, category in ChangelogGenerator.CONVENTIONAL_TYPE_MAP.items():
            assert category in valid_categories, (
                f"CONVENTIONAL_TYPE_MAP[{commit_type!r}] = {category!r} is not valid"
            )
