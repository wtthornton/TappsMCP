"""Tests for docs_mcp.analyzers.version_detector."""

from __future__ import annotations

from pathlib import Path

import git
import pytest

from docs_mcp.analyzers.version_detector import (
    VersionBoundary,
    VersionDetector,
    _semver_sort_key,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def versioned_repo(tmp_path: Path) -> Path:
    """Create a repo with multiple semver tags."""
    repo = git.Repo.init(tmp_path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "t@t.com").release()

    # v1.0.0
    f = tmp_path / "file.txt"
    f.write_text("v1\n", encoding="utf-8")
    repo.index.add(["file.txt"])
    repo.index.commit("feat: initial release")
    repo.create_tag("v1.0.0", message="Release 1.0.0")

    # v1.1.0
    f.write_text("v1.1\n", encoding="utf-8")
    repo.index.add(["file.txt"])
    repo.index.commit("feat: minor feature")
    repo.create_tag("v1.1.0", message="Release 1.1.0")

    # v2.0.0
    f.write_text("v2\n", encoding="utf-8")
    repo.index.add(["file.txt"])
    repo.index.commit("feat!: breaking change")
    repo.create_tag("v2.0.0", message="Release 2.0.0")

    return tmp_path


@pytest.fixture
def prerelease_repo(tmp_path: Path) -> Path:
    """Create a repo with pre-release tags."""
    repo = git.Repo.init(tmp_path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "t@t.com").release()

    f = tmp_path / "file.txt"
    f.write_text("rc1\n", encoding="utf-8")
    repo.index.add(["file.txt"])
    repo.index.commit("feat: release candidate")
    repo.create_tag("v1.0.0-rc.1", message="RC 1")

    f.write_text("release\n", encoding="utf-8")
    repo.index.add(["file.txt"])
    repo.index.commit("feat: stable release")
    repo.create_tag("v1.0.0", message="Release 1.0.0")

    return tmp_path


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestVersionBoundaryModel:
    """Tests for the VersionBoundary Pydantic model."""

    def test_create(self) -> None:
        boundary = VersionBoundary(
            version="1.0.0",
            tag="v1.0.0",
            date="2026-01-01T00:00:00",
            commit_count=5,
        )
        assert boundary.version == "1.0.0"
        assert boundary.tag == "v1.0.0"
        assert boundary.commit_count == 5
        assert boundary.commits == []


# ---------------------------------------------------------------------------
# Semver sort key tests
# ---------------------------------------------------------------------------


class TestSemverSortKey:
    """Tests for _semver_sort_key."""

    def test_basic_ordering(self) -> None:
        assert _semver_sort_key("1.0.0") < _semver_sort_key("2.0.0")
        assert _semver_sort_key("1.0.0") < _semver_sort_key("1.1.0")
        assert _semver_sort_key("1.0.0") < _semver_sort_key("1.0.1")

    def test_prerelease_before_release(self) -> None:
        assert _semver_sort_key("1.0.0-rc.1") < _semver_sort_key("1.0.0")

    def test_non_semver_fallback(self) -> None:
        key = _semver_sort_key("not-a-version")
        assert key == (0, 0, 0, "not-a-version")


# ---------------------------------------------------------------------------
# VersionDetector tests
# ---------------------------------------------------------------------------


class TestVersionDetector:
    """Tests for VersionDetector."""

    def test_detect_versions(self, versioned_repo: Path) -> None:
        detector = VersionDetector()
        boundaries = detector.detect_versions(versioned_repo)
        assert len(boundaries) == 3
        # Newest first
        assert boundaries[0].version == "2.0.0"
        assert boundaries[1].version == "1.1.0"
        assert boundaries[2].version == "1.0.0"

    def test_detect_versions_has_tags(self, versioned_repo: Path) -> None:
        detector = VersionDetector()
        boundaries = detector.detect_versions(versioned_repo)
        assert boundaries[0].tag == "v2.0.0"

    def test_detect_versions_has_dates(self, versioned_repo: Path) -> None:
        detector = VersionDetector()
        boundaries = detector.detect_versions(versioned_repo)
        for b in boundaries:
            assert "T" in b.date  # ISO 8601

    def test_detect_versions_without_commits(self, versioned_repo: Path) -> None:
        detector = VersionDetector()
        boundaries = detector.detect_versions(versioned_repo, include_commits=False)
        assert len(boundaries) == 3
        for b in boundaries:
            assert b.commit_count == 0
            assert b.commits == []

    def test_detect_versions_with_commits(self, versioned_repo: Path) -> None:
        detector = VersionDetector()
        boundaries = detector.detect_versions(versioned_repo, include_commits=True)
        assert len(boundaries) == 3
        # At least one boundary should have commits
        has_commits = any(b.commit_count > 0 for b in boundaries)
        assert has_commits

    def test_prerelease_tags(self, prerelease_repo: Path) -> None:
        detector = VersionDetector()
        boundaries = detector.detect_versions(prerelease_repo)
        assert len(boundaries) == 2
        # Release comes first (newest first after sort)
        assert boundaries[0].version == "1.0.0"
        assert boundaries[1].version == "1.0.0-rc.1"

    def test_empty_repo_no_tags(self, tmp_path: Path) -> None:
        """Repo without tags returns empty list."""
        repo = git.Repo.init(tmp_path)
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "t@t.com").release()
        f = tmp_path / "f.txt"
        f.write_text("x", encoding="utf-8")
        repo.index.add(["f.txt"])
        repo.index.commit("init")

        detector = VersionDetector()
        assert detector.detect_versions(tmp_path) == []

    def test_non_git_directory(self, tmp_path: Path) -> None:
        """Non-git directory returns empty list."""
        detector = VersionDetector()
        assert detector.detect_versions(tmp_path) == []

    def test_non_semver_tags_ignored(self, tmp_path: Path) -> None:
        """Tags that are not semver should be excluded."""
        repo = git.Repo.init(tmp_path)
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "t@t.com").release()
        f = tmp_path / "f.txt"
        f.write_text("x", encoding="utf-8")
        repo.index.add(["f.txt"])
        repo.index.commit("init")
        repo.create_tag("release-candidate", message="RC")
        repo.create_tag("latest", message="Latest")

        detector = VersionDetector()
        assert detector.detect_versions(tmp_path) == []

    def test_mixed_semver_and_non_semver(self, tmp_path: Path) -> None:
        """Only semver tags should appear in results."""
        repo = git.Repo.init(tmp_path)
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "t@t.com").release()
        f = tmp_path / "f.txt"
        f.write_text("x", encoding="utf-8")
        repo.index.add(["f.txt"])
        repo.index.commit("init")
        repo.create_tag("v1.0.0", message="Release")
        repo.create_tag("latest", message="Latest")

        detector = VersionDetector()
        boundaries = detector.detect_versions(tmp_path)
        assert len(boundaries) == 1
        assert boundaries[0].version == "1.0.0"
