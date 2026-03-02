"""Tests for docs_mcp.analyzers.git_history."""

from __future__ import annotations

import os
from pathlib import Path

import git
import pytest

from docs_mcp.analyzers.git_history import (
    CommitInfo,
    GitHistoryAnalyzer,
    TagInfo,
    _parse_semver_tag,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(tmp_path: Path) -> git.Repo:
    """Create a temporary Git repository with several commits."""
    repo = git.Repo.init(tmp_path)
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()

    # Create initial commit
    readme = tmp_path / "README.md"
    readme.write_text("# Hello\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("feat: initial commit")

    # Second commit
    src = tmp_path / "main.py"
    src.write_text("print('hello')\n", encoding="utf-8")
    repo.index.add(["main.py"])
    repo.index.commit("fix: add main script")

    # Third commit
    readme.write_text("# Hello World\n\nUpdated.\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("docs: update readme")

    return repo


@pytest.fixture
def tagged_repo(git_repo: git.Repo) -> git.Repo:
    """Extend git_repo with tags."""
    git_repo.create_tag("v1.0.0", message="Release 1.0.0")

    # Add another commit after the tag
    repo_path = Path(git_repo.working_dir)
    changelog = repo_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    git_repo.index.add(["CHANGELOG.md"])
    git_repo.index.commit("chore: add changelog")

    git_repo.create_tag("v1.1.0", message="Release 1.1.0")

    return git_repo


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestCommitInfoModel:
    """Tests for the CommitInfo Pydantic model."""

    def test_create_commit_info(self) -> None:
        info = CommitInfo(
            hash="abc1234567890",
            short_hash="abc1234",
            author="Test User",
            author_email="test@example.com",
            date="2026-01-01T00:00:00+00:00",
            message="feat: test commit",
        )
        assert info.hash == "abc1234567890"
        assert info.short_hash == "abc1234"
        assert info.author == "Test User"
        assert info.message == "feat: test commit"
        assert info.files_changed == 0
        assert info.insertions == 0
        assert info.deletions == 0

    def test_commit_info_with_stats(self) -> None:
        info = CommitInfo(
            hash="def456",
            short_hash="def456",
            author="Dev",
            author_email="dev@test.com",
            date="2026-02-01T12:00:00",
            message="fix: something",
            files_changed=3,
            insertions=10,
            deletions=5,
        )
        assert info.files_changed == 3
        assert info.insertions == 10
        assert info.deletions == 5


class TestTagInfoModel:
    """Tests for the TagInfo Pydantic model."""

    def test_create_tag_info(self) -> None:
        tag = TagInfo(
            name="v1.0.0",
            commit_hash="abc123",
            date="2026-01-01T00:00:00",
            is_semver=True,
            version="1.0.0",
        )
        assert tag.name == "v1.0.0"
        assert tag.is_semver is True
        assert tag.version == "1.0.0"

    def test_non_semver_tag(self) -> None:
        tag = TagInfo(
            name="release-candidate",
            commit_hash="def456",
            date="2026-01-15T00:00:00",
        )
        assert tag.is_semver is False
        assert tag.version == ""


# ---------------------------------------------------------------------------
# Semver parsing tests
# ---------------------------------------------------------------------------


class TestSemverParsing:
    """Tests for _parse_semver_tag helper."""

    def test_standard_semver(self) -> None:
        assert _parse_semver_tag("v1.2.3") == (True, "1.2.3")

    def test_semver_no_v_prefix(self) -> None:
        assert _parse_semver_tag("1.2.3") == (True, "1.2.3")

    def test_semver_prerelease(self) -> None:
        is_semver, version = _parse_semver_tag("v1.2.3-rc.1")
        assert is_semver is True
        assert version == "1.2.3-rc.1"

    def test_non_semver_tag(self) -> None:
        assert _parse_semver_tag("release-candidate") == (False, "")

    def test_non_semver_partial(self) -> None:
        assert _parse_semver_tag("v1.2") == (False, "")


# ---------------------------------------------------------------------------
# GitHistoryAnalyzer tests
# ---------------------------------------------------------------------------


class TestGitHistoryAnalyzer:
    """Tests for GitHistoryAnalyzer."""

    def test_get_commits_returns_list(self, git_repo: git.Repo) -> None:
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        commits = analyzer.get_commits()
        assert len(commits) == 3
        assert all(isinstance(c, CommitInfo) for c in commits)

    def test_get_commits_newest_first(self, git_repo: git.Repo) -> None:
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        commits = analyzer.get_commits()
        assert "docs: update readme" in commits[0].message
        assert "feat: initial commit" in commits[-1].message

    def test_get_commits_with_limit(self, git_repo: git.Repo) -> None:
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        commits = analyzer.get_commits(limit=2)
        assert len(commits) == 2

    def test_get_commits_with_path_filter(self, git_repo: git.Repo) -> None:
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        commits = analyzer.get_commits(path="main.py")
        assert len(commits) == 1
        assert "main script" in commits[0].message

    def test_get_commits_has_author_info(self, git_repo: git.Repo) -> None:
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        commits = analyzer.get_commits()
        assert commits[0].author == "Test User"
        assert commits[0].author_email == "test@example.com"

    def test_get_commits_has_hash(self, git_repo: git.Repo) -> None:
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        commits = analyzer.get_commits()
        assert len(commits[0].hash) == 40
        assert len(commits[0].short_hash) == 7

    def test_get_commits_has_date(self, git_repo: git.Repo) -> None:
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        commits = analyzer.get_commits()
        # ISO 8601 dates contain 'T'
        assert "T" in commits[0].date

    def test_get_tags(self, tagged_repo: git.Repo) -> None:
        repo_path = Path(tagged_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        tags = analyzer.get_tags()
        assert len(tags) == 2
        tag_names = {t.name for t in tags}
        assert "v1.0.0" in tag_names
        assert "v1.1.0" in tag_names

    def test_get_tags_semver_detection(self, tagged_repo: git.Repo) -> None:
        repo_path = Path(tagged_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        tags = analyzer.get_tags()
        for tag in tags:
            assert tag.is_semver is True
            assert tag.version != ""

    def test_get_file_last_modified(self, git_repo: git.Repo) -> None:
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        last_mod = analyzer.get_file_last_modified("README.md")
        assert last_mod is not None
        assert "T" in last_mod  # ISO 8601

    def test_get_file_last_modified_nonexistent(self, git_repo: git.Repo) -> None:
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        result = analyzer.get_file_last_modified("nonexistent.txt")
        assert result is None

    def test_non_git_directory(self, tmp_path: Path) -> None:
        """Non-git directories should return empty results, not crash."""
        analyzer = GitHistoryAnalyzer(tmp_path)
        assert analyzer.get_commits() == []
        assert analyzer.get_tags() == []
        assert analyzer.get_file_last_modified("anything.txt") is None

    def test_empty_repo(self, tmp_path: Path) -> None:
        """An empty repo (no commits) should return empty results."""
        git.Repo.init(tmp_path)
        analyzer = GitHistoryAnalyzer(tmp_path)
        commits = analyzer.get_commits()
        assert commits == []

    def test_get_commits_stats(self, git_repo: git.Repo) -> None:
        """Commits should have file change statistics."""
        repo_path = Path(git_repo.working_dir)
        analyzer = GitHistoryAnalyzer(repo_path)
        commits = analyzer.get_commits()
        # At least the initial commit should have stats
        has_stats = any(c.files_changed > 0 for c in commits)
        assert has_stats

    def test_get_tags_empty_repo(self, tmp_path: Path) -> None:
        """Repo without tags returns empty list."""
        repo = git.Repo.init(tmp_path)
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "t@t.com").release()
        f = tmp_path / "f.txt"
        f.write_text("x", encoding="utf-8")
        repo.index.add(["f.txt"])
        repo.index.commit("init")

        analyzer = GitHistoryAnalyzer(tmp_path)
        assert analyzer.get_tags() == []
