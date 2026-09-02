"""Behavioral tests for the bypass ledger resolving to the primary checkout,
not a linked worktree's own cwd (TAP-6931).

Every bypass-logging git hook used to resolve its ledger directory relative
to the *current* checkout (``LOG_DIR=".tapps-mcp"``). From a linked
worktree that wrote ``<worktree>/.tapps-mcp/.bypass-log.jsonl`` -- a fresh,
throwaway file -- instead of appending to the primary checkout's ledger the
operator actually audits, so bypasses taken from lanes were invisible.

These tests exercise the actual on-disk ``.githooks/pre-commit`` hook (not a
reimplementation of its logic) against a hermetic scratch repo under
``tmp_path``, so a regression in the shipped hook fails this suite the same
way it would fail an operator's real audit.

The scratch repo is deliberate: writing a synthetic entry into this repo's
real ``.bypass-log.jsonl`` would falsify an audit record, and taking a real
``TAPPS_SKIP_GATE=1`` bypass here needs operator authorization. Neither
happens -- everything below runs inside ``tmp_path``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOK_PATH = _REPO_ROOT / ".githooks" / "pre-commit"


def _run_git(
    args: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def scratch_primary(tmp_path: Path) -> Path:
    """A hermetic primary checkout with the real pre-commit hook installed."""
    if not _HOOK_PATH.exists():  # pragma: no cover - source checkouts only
        pytest.skip(f"no .githooks/pre-commit at {_HOOK_PATH}")

    primary = tmp_path / "primary"
    primary.mkdir()
    _run_git(["init", "-q"], cwd=primary)
    _run_git(["config", "user.email", "test@example.com"], cwd=primary)
    _run_git(["config", "user.name", "Test"], cwd=primary)
    (primary / "README.md").write_text("init\n", encoding="utf-8")
    _run_git(["add", "README.md"], cwd=primary)
    _run_git(["commit", "-q", "-m", "init"], cwd=primary)

    # core.hooksPath is a relative path in this repo (".githooks"), which git
    # resolves against each worktree's OWN top level -- not the primary's.
    # A linked worktree only gets tracked files checked out, so .githooks
    # must be committed here before any worktree is created off this repo,
    # or the hook silently never fires from the worktree at all.
    githooks_dir = primary / ".githooks"
    githooks_dir.mkdir()
    hook_path = githooks_dir / "pre-commit"
    hook_path.write_text(_HOOK_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    hook_path.chmod(0o755)
    _run_git(["add", ".githooks/pre-commit"], cwd=primary)
    _run_git(["commit", "-q", "-m", "add pre-commit hook"], cwd=primary)
    _run_git(["config", "core.hooksPath", ".githooks"], cwd=primary)
    return primary


def _bypass_env() -> dict[str, str]:
    return {**os.environ, "TAPPS_SKIP_GATE": "1"}


class TestBypassLedgerFromLinkedWorktree:
    def test_val01_worktree_bypass_lands_in_primary_ledger_not_worktree(
        self, scratch_primary: Path, tmp_path: Path
    ) -> None:
        worktree = tmp_path / "wt"
        _run_git(
            ["worktree", "add", "-q", "-b", "lane-branch", str(worktree)],
            cwd=scratch_primary,
        )

        ledger = scratch_primary / ".tapps-mcp" / ".bypass-log.jsonl"
        assert not ledger.exists()

        (worktree / "file.txt").write_text("hello\n", encoding="utf-8")
        _run_git(["add", "file.txt"], cwd=worktree)
        result = _run_git(
            ["commit", "-q", "-m", "wip"],
            cwd=worktree,
            env=_bypass_env(),
            check=False,
        )

        # Validate the instrument: the hook must have actually fired (its
        # bypass message on stderr), not silently no-op'd because hooksPath
        # wasn't picked up in the worktree.
        assert result.returncode == 0, result.stderr
        assert "bypassed via TAPPS_SKIP_GATE=1" in result.stderr
        assert "Logged to" in result.stderr

        found = sorted(str(p) for p in tmp_path.rglob(".bypass-log.jsonl"))
        print(f"find result: {found}")
        assert found == [str(ledger)]

        lines = ledger.read_text(encoding="utf-8").splitlines()
        print(f"ledger line count: {len(lines)}")
        assert len(lines) == 1
        assert '"hook":"pre-commit"' in lines[0]

        rival = worktree / ".tapps-mcp" / ".bypass-log.jsonl"
        assert not rival.exists()

    def test_val02_primary_bypass_still_appends_to_the_same_single_ledger(
        self, scratch_primary: Path, tmp_path: Path
    ) -> None:
        """Negative control: a worktree bypass must not fork the ledger.

        Seed the ledger from a worktree bypass first, then take a second
        bypass from the primary checkout itself. Both must land in the one
        ledger at the primary root -- the worktree fix must not regress the
        primary-checkout path that already worked.
        """
        worktree = tmp_path / "wt"
        _run_git(
            ["worktree", "add", "-q", "-b", "lane-branch", str(worktree)],
            cwd=scratch_primary,
        )
        (worktree / "file.txt").write_text("hello\n", encoding="utf-8")
        _run_git(["add", "file.txt"], cwd=worktree)
        worktree_result = _run_git(
            ["commit", "-q", "-m", "wip"],
            cwd=worktree,
            env=_bypass_env(),
            check=False,
        )
        assert worktree_result.returncode == 0, worktree_result.stderr

        ledger = scratch_primary / ".tapps-mcp" / ".bypass-log.jsonl"
        lines_after_worktree = ledger.read_text(encoding="utf-8").splitlines()
        print(f"ledger line count after worktree bypass: {len(lines_after_worktree)}")
        assert len(lines_after_worktree) == 1

        (scratch_primary / "second.txt").write_text("hello\n", encoding="utf-8")
        _run_git(["add", "second.txt"], cwd=scratch_primary)
        primary_result = _run_git(
            ["commit", "-q", "-m", "wip2"],
            cwd=scratch_primary,
            env=_bypass_env(),
            check=False,
        )
        assert primary_result.returncode == 0, primary_result.stderr
        assert "bypassed via TAPPS_SKIP_GATE=1" in primary_result.stderr

        found = sorted(str(p) for p in tmp_path.rglob(".bypass-log.jsonl"))
        print(f"find result: {found}")
        assert found == [str(ledger)]

        lines_after_both = ledger.read_text(encoding="utf-8").splitlines()
        print(f"ledger line count after both bypasses: {len(lines_after_both)}")
        assert len(lines_after_both) == 2
