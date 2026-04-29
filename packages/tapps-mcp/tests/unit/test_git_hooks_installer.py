"""Tests for the git pre-commit hook installer (TAP-979)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tapps_mcp.pipeline.git_hooks import (
    GIT_PRE_COMMIT_SCRIPT,
    install_git_pre_commit,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-q"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


class TestInstallGitPreCommit:
    def test_writes_executable_hook_in_git_repo(self, git_repo: Path) -> None:
        result = install_git_pre_commit(git_repo)
        assert result["installed"] is True
        hook_path = git_repo / ".githooks" / "pre-commit"
        assert hook_path.exists()
        assert hook_path.read_text(encoding="utf-8") == GIT_PRE_COMMIT_SCRIPT
        assert hook_path.stat().st_mode & 0o111, "hook must be executable"

    def test_sets_core_hooks_path(self, git_repo: Path) -> None:
        install_git_pre_commit(git_repo)
        out = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert out.stdout.strip() == ".githooks"

    def test_skips_when_not_a_git_repo(self, tmp_path: Path) -> None:
        result = install_git_pre_commit(tmp_path)
        assert result["installed"] is False
        assert "not a git repository" in result["skipped_reason"]
        assert not (tmp_path / ".githooks").exists()

    def test_dry_run_does_not_write(self, git_repo: Path) -> None:
        result = install_git_pre_commit(git_repo, dry_run=True)
        assert result["installed"] is True
        assert result["skipped_reason"] == "dry_run"
        assert not (git_repo / ".githooks" / "pre-commit").exists()

    def test_content_return_returns_script_without_writing(self, git_repo: Path) -> None:
        result = install_git_pre_commit(git_repo, content_return=True)
        assert result["installed"] is True
        assert result["content"] == GIT_PRE_COMMIT_SCRIPT
        assert not (git_repo / ".githooks" / "pre-commit").exists()


class TestPreCommitScriptContract:
    def test_honors_tapps_skip_gate_env_var(self) -> None:
        assert "TAPPS_SKIP_GATE" in GIT_PRE_COMMIT_SCRIPT

    def test_invokes_validate_changed_subcommand(self) -> None:
        assert "validate-changed" in GIT_PRE_COMMIT_SCRIPT
        assert "--quick" in GIT_PRE_COMMIT_SCRIPT

    def test_filters_to_python_files_only(self) -> None:
        assert "\\.py$" in GIT_PRE_COMMIT_SCRIPT

    def test_uses_uv_run_when_available(self) -> None:
        assert "uv run tapps-mcp" in GIT_PRE_COMMIT_SCRIPT

    def test_uses_diff_filter_for_added_modified_files(self) -> None:
        assert "--cached" in GIT_PRE_COMMIT_SCRIPT
        assert "--diff-filter=ACM" in GIT_PRE_COMMIT_SCRIPT
