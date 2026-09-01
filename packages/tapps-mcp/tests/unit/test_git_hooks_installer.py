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


class TestPreCommitRatchet:
    """TAP-6904/TAP-6911: the hook must ratchet, and both copies must keep it.

    CI passes ``--baseline-ref`` (the PR base) but the hook did not, so a
    commit that *improved* an already-below-threshold file was rejected
    locally and accepted by CI. That gap is a standing incentive to reach for
    TAPPS_SKIP_GATE=1 on exactly the changes the ratchet exists to reward.

    TAP-6904's first fix passed ``--baseline-ref HEAD``, but
    ``gates/ratchet.py``'s own "Monotonicity" contract requires
    ``baseline_ref`` to be a stable merge target, not the immediately
    preceding local commit -- ``HEAD`` moves with every commit, so a
    multi-commit branch could still deadlock on an intermediate commit CI
    would accept. TAP-6911 derives the actual merge target instead: the
    branch's upstream, else the remote's default branch, else a common
    default-branch name, then the merge-base of ``HEAD`` against it.
    """

    def test_template_derives_a_merge_target_baseline(self):
        assert "resolve_baseline_ref" in GIT_PRE_COMMIT_SCRIPT
        assert "git merge-base HEAD" in GIT_PRE_COMMIT_SCRIPT
        assert '--baseline-ref "$BASELINE_REF"' in GIT_PRE_COMMIT_SCRIPT

    def test_template_resolution_order_has_all_three_fallbacks(self):
        """Upstream, then origin/HEAD, then common default-branch names."""
        assert "@{upstream}" in GIT_PRE_COMMIT_SCRIPT
        assert "refs/remotes/origin/HEAD" in GIT_PRE_COMMIT_SCRIPT
        assert "origin/master" in GIT_PRE_COMMIT_SCRIPT
        assert "origin/main" in GIT_PRE_COMMIT_SCRIPT

    def test_template_guards_the_undeterminable_case(self):
        """No target resolves (or no merge-base exists) -> stay off, don't skip."""
        assert '[ -z "$target" ] && return 0' in GIT_PRE_COMMIT_SCRIPT

    def test_template_expansion_is_safe_when_empty(self):
        """``${A+"${A[@]}"}`` so an empty array does not break under set -u."""
        assert '${BASELINE_ARGS+"${BASELINE_ARGS[@]}"}' in GIT_PRE_COMMIT_SCRIPT

    def test_this_repo_hook_has_not_drifted_from_the_template(self):
        """The repo's own hook is a hand-maintained copy of the template.

        They differ deliberately (this one logs bypasses to a jsonl ledger),
        so byte equality is wrong — but a behavioural flag present in one and
        missing from the other is exactly the drift that caused TAP-6904's
        gap. Assert the ratchet specifically, in both.
        """
        repo_root = Path(__file__).resolve().parents[4]
        hook = repo_root / ".githooks" / "pre-commit"
        if not hook.exists():  # pragma: no cover - source checkouts only
            pytest.skip(f"no .githooks/pre-commit at {hook}")
        text = hook.read_text(encoding="utf-8")
        assert "resolve_baseline_ref" in text
        assert "git merge-base HEAD" in text
        assert '--baseline-ref "$BASELINE_REF"' in text
        assert "@{upstream}" in text
        assert "refs/remotes/origin/HEAD" in text
        assert "origin/master" in text
        assert "origin/main" in text
        assert '[ -z "$target" ] && return 0' in text
