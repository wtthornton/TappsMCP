"""Tests for the one-time gitignored-backup untrack step (TAP-7427).

``.tapps-mcp/backups`` and ``.tapps-mcp/hook-backups`` are gitignored but a
checkout that tracked them before the ignore entry existed keeps them in the
index forever. ``untrack_gitignored_backup_paths`` must stage (never commit)
their removal, scoped to exactly those two paths, and be idempotent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tapps_mcp.distribution.setup_secrets import (
    _TAPPS_BACKUP_UNTRACK_PATHS,
    untrack_gitignored_backup_paths,
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _tracked_paths(repo: Path, rel: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", rel],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in out.stdout.splitlines() if line]


@pytest.fixture
def repo_with_tracked_backups(tmp_path: Path) -> Path:
    """A repo with backups committed *before* .gitignore covered them."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")

    (tmp_path / ".tapps-mcp" / "backups" / "20260101-000000").mkdir(parents=True)
    (tmp_path / ".tapps-mcp" / "hook-backups").mkdir(parents=True)
    (tmp_path / ".tapps-mcp" / "backups" / "20260101-000000" / "manifest.json").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / ".tapps-mcp" / "hook-backups" / "pre-commit.bak").write_text(
        "old hook", encoding="utf-8"
    )
    (tmp_path / ".tapps-mcp" / "keepme.txt").write_text("keep me", encoding="utf-8")
    (tmp_path / "README.md").write_text("# fixture\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "seed: backups committed pre-fix")

    (tmp_path / ".gitignore").write_text(
        ".tapps-mcp/backups/\n.tapps-mcp/hook-backups/\n", encoding="utf-8"
    )
    _git(tmp_path, "add", ".gitignore")
    _git(tmp_path, "commit", "-q", "-m", "add gitignore for backup trees")
    return tmp_path


class TestUntrackGitignoredBackupPaths:
    def test_stages_removal_without_committing(self, repo_with_tracked_backups: Path) -> None:
        repo = repo_with_tracked_backups
        result = untrack_gitignored_backup_paths(repo)

        assert sorted(result["untracked"]) == sorted(_TAPPS_BACKUP_UNTRACK_PATHS)
        assert result["skipped"] == []
        assert result["error"] is None

        # Staged (index no longer has them) but not committed.
        assert _tracked_paths(repo, ".tapps-mcp/backups") == []
        assert _tracked_paths(repo, ".tapps-mcp/hook-backups") == []
        status = _git(repo, "status", "--porcelain").stdout
        assert "D  .tapps-mcp/backups/20260101-000000/manifest.json" in status
        assert "D  .tapps-mcp/hook-backups/pre-commit.bak" in status

        # Never commits on the consumer's behalf.
        log = _git(repo, "log", "--oneline").stdout
        assert "untrack" not in log.lower()

    def test_idempotent_second_run_is_a_noop(self, repo_with_tracked_backups: Path) -> None:
        repo = repo_with_tracked_backups
        untrack_gitignored_backup_paths(repo)
        _git(repo, "commit", "-q", "-m", "consumer commits the staged deletion")

        second = untrack_gitignored_backup_paths(repo)

        assert second["untracked"] == []
        assert sorted(second["skipped"]) == sorted(_TAPPS_BACKUP_UNTRACK_PATHS)
        assert second["error"] is None
        # No re-dirtying of the tree.
        assert _git(repo, "status", "--porcelain").stdout == ""

    def test_unrelated_tracked_file_survives(self, repo_with_tracked_backups: Path) -> None:
        """VAL-05: an unrelated file under .tapps-mcp/ is untouched."""
        repo = repo_with_tracked_backups
        untrack_gitignored_backup_paths(repo)

        assert _tracked_paths(repo, ".tapps-mcp/keepme.txt") == [".tapps-mcp/keepme.txt"]
        assert (repo / ".tapps-mcp" / "keepme.txt").read_text(encoding="utf-8") == "keep me"
        status = _git(repo, "status", "--porcelain", "--", ".tapps-mcp/keepme.txt").stdout
        assert status == ""

    def test_negative_control_broad_git_rm_would_also_remove_keepme(
        self, repo_with_tracked_backups: Path
    ) -> None:
        """Proves the scope is exactly the two named paths, not the whole tree.

        A broad ``git rm -r --cached .`` (the forbidden shape) untracks
        *everything* under the repo root, including the unrelated
        ``.tapps-mcp/keepme.txt`` file that the scoped implementation must
        preserve. This asserts that failure mode directly against git,
        independent of the scoped function, then leaves the repo untouched
        (the removal here is never committed).
        """
        repo = repo_with_tracked_backups
        subprocess.run(
            ["git", "rm", "-r", "--cached", "."],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert _tracked_paths(repo, ".tapps-mcp/keepme.txt") == [], (
            "broad git rm -r --cached . removed the unrelated file too — "
            "this is exactly the scope violation the real fix must avoid"
        )
        # Revert the broad removal — this test only demonstrates the failure mode.
        _git(repo, "reset", "--hard", "HEAD")

    def test_skips_paths_that_are_not_gitignored(self, tmp_path: Path) -> None:
        """A tracked backup path with no covering .gitignore entry is left alone."""
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "config", "user.email", "test@example.com")
        _git(tmp_path, "config", "user.name", "Test")
        (tmp_path / ".tapps-mcp" / "backups").mkdir(parents=True)
        (tmp_path / ".tapps-mcp" / "backups" / "f.txt").write_text("x", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "seed, no gitignore")

        result = untrack_gitignored_backup_paths(tmp_path)

        assert result["untracked"] == []
        assert ".tapps-mcp/backups" in result["skipped"]
        assert _tracked_paths(tmp_path, ".tapps-mcp/backups") == [".tapps-mcp/backups/f.txt"]

    def test_skips_when_not_a_git_repo(self, tmp_path: Path) -> None:
        result = untrack_gitignored_backup_paths(tmp_path)
        assert result["untracked"] == []
        assert sorted(result["skipped"]) == sorted(_TAPPS_BACKUP_UNTRACK_PATHS)
        assert result["error"] is None
