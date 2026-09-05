"""Tests for platform_hook_templates.py hook script generation.

Covers:
- TAP-6928: the bypass ledger (`.tapps-mcp/.bypass-log.jsonl`) must resolve
  to the primary checkout even from a linked worktree with
  ``CLAUDE_PROJECT_DIR`` unset, not the worktree's own cwd.

These tests render the actual template body and execute it via subprocess
(``bash -n`` is not enough — a grep against the template string proves
nothing about the generated hook's runtime behavior), matching the pattern
used by test_pre_bash_lane_guard.py and test_linear_hook_fail_closed.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.git_hooks import GIT_PRE_COMMIT_SCRIPT
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS_PS,
    LINEAR_GATE_SCRIPTS,
    LINEAR_GATE_SCRIPTS_PS,
)
from tapps_mcp.pipeline.platform_hook_templates_linear_gate import (
    LEDGER_ROOT_RESOLVE_BASH,
    LEDGER_ROOT_RESOLVE_PS,
    LINEAR_CACHE_GATE_SCRIPTS,
    LINEAR_CACHE_GATE_SCRIPTS_PS,
    SESSION_START_GATE_SCRIPTS,
    SESSION_START_GATE_SCRIPTS_PS,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="hook scripts under test are bash-specific",
)

LINEAR_WRITE_HOOK_BODY = LINEAR_GATE_SCRIPTS["tapps-pre-linear-write.sh"]

LINEAR_SAVE_ISSUE_PAYLOAD: dict[str, object] = {
    "tool_name": "mcp__plugin_linear_linear__save_issue",
    "tool_input": {"title": "x", "description": "y"},
}


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


def _make_primary_and_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A primary checkout plus one linked worktree off a dedicated branch."""
    primary = tmp_path / "primary"
    primary.mkdir()
    _git("init", "-q", cwd=primary)
    _git("config", "user.email", "test@example.com", cwd=primary)
    _git("config", "user.name", "Test", cwd=primary)
    (primary / "f.txt").write_text("x", encoding="utf-8")
    _git("add", ".", cwd=primary)
    _git("commit", "-q", "-m", "init", cwd=primary)
    _git("branch", "wt", cwd=primary)
    worktree = tmp_path / "wt"
    _git("worktree", "add", "-q", str(worktree), "wt", cwd=primary)
    return primary, worktree


def _run_script(
    script_body: str,
    hook_dir: Path,
    cwd: Path,
    payload: dict[str, object],
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    hook_path = hook_dir / "tapps-pre-linear-write.sh"
    hook_path.write_text(script_body, encoding="utf-8")
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["/usr/bin/bash", str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


# ---------------------------------------------------------------------------
# TAP-6928 — bypass ledger path resolution from a linked worktree
# ---------------------------------------------------------------------------


def test_bypass_ledger_worktree_lands_in_primary_checkout(tmp_path: Path) -> None:
    """A bypass taken from a linked worktree, with CLAUDE_PROJECT_DIR unset,
    must land in the PRIMARY checkout's ledger, not the worktree's own cwd."""
    primary, worktree = _make_primary_and_worktree(tmp_path)
    hook_dir = tmp_path / "hooks"
    hook_dir.mkdir()

    result = _run_script(
        LINEAR_WRITE_HOOK_BODY,
        hook_dir,
        worktree,
        LINEAR_SAVE_ISSUE_PAYLOAD,
        extra_env={"TAPPS_LINEAR_SKIP_VALIDATE": "1"},
    )

    assert result.returncode == 0, result.stderr
    primary_ledger = primary / ".tapps-mcp" / ".bypass-log.jsonl"
    worktree_ledger = worktree / ".tapps-mcp" / ".bypass-log.jsonl"
    assert primary_ledger.exists(), (
        f"expected the ledger in the primary checkout; stderr={result.stderr}"
    )
    assert not worktree_ledger.exists(), (
        "bypass ledger leaked into the linked worktree's own .tapps-mcp dir"
    )
    entry = json.loads(primary_ledger.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry["bypass"] == "TAPPS_LINEAR_SKIP_VALIDATE"


def test_bypass_ledger_worktree_negative_control_pre_fix_lands_in_worktree(
    tmp_path: Path,
) -> None:
    """Sensitivity check: substituting back the pre-fix
    ``${CLAUDE_PROJECT_DIR:-$PWD}`` resolution must reproduce the bug (the
    ledger lands in the worktree cwd, not the primary checkout) — proving the
    positive test above is actually exercising the TAP-6928 defect and not
    passing for an unrelated reason."""
    primary, worktree = _make_primary_and_worktree(tmp_path)
    hook_dir = tmp_path / "hooks"
    hook_dir.mkdir()

    buggy_script = LINEAR_WRITE_HOOK_BODY.replace(
        LEDGER_ROOT_RESOLVE_BASH,
        'ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"',
    )
    # Guard the test itself: the substitution must actually have applied,
    # else this "negative control" would silently just re-run the fixed hook.
    assert buggy_script != LINEAR_WRITE_HOOK_BODY
    assert LEDGER_ROOT_RESOLVE_BASH not in buggy_script

    result = _run_script(
        buggy_script,
        hook_dir,
        worktree,
        LINEAR_SAVE_ISSUE_PAYLOAD,
        extra_env={"TAPPS_LINEAR_SKIP_VALIDATE": "1"},
    )

    assert result.returncode == 0, result.stderr
    primary_ledger = primary / ".tapps-mcp" / ".bypass-log.jsonl"
    worktree_ledger = worktree / ".tapps-mcp" / ".bypass-log.jsonl"
    assert worktree_ledger.exists(), (
        "negative control: the pre-fix template should land the ledger "
        "in the worktree cwd"
    )
    assert not primary_ledger.exists()


def test_ledger_root_resolution_matches_git_hooks_shape() -> None:
    """The shared bash/PS resolution snippets must use the same
    --git-common-dir shape as git_hooks.py's GIT_PRE_COMMIT_SCRIPT
    (TAP-6931), not reinvent a different fallback."""
    assert "--git-common-dir" in LEDGER_ROOT_RESOLVE_BASH
    assert "--git-common-dir" in GIT_PRE_COMMIT_SCRIPT
    assert "--git-common-dir" in LEDGER_ROOT_RESOLVE_PS


# Every bash hook that writes to .bypass-log.jsonl must resolve ROOT through
# the shared LEDGER_ROOT_RESOLVE_BASH snippet — a single source of truth so
# no copy can silently drift back to the naive ${CLAUDE_PROJECT_DIR:-$PWD}.
BASH_LEDGER_SCRIPTS: dict[str, str] = {
    "tapps-pre-bash.sh": CLAUDE_HOOK_SCRIPTS["tapps-pre-bash.sh"],
    "tapps-pre-linear-write.sh": LINEAR_GATE_SCRIPTS["tapps-pre-linear-write.sh"],
    "tapps-pre-linear-list.sh": LINEAR_CACHE_GATE_SCRIPTS["tapps-pre-linear-list.sh"],
    "tapps-pre-session-start-gate.sh": SESSION_START_GATE_SCRIPTS[
        "tapps-pre-session-start-gate.sh"
    ],
}

PS_LEDGER_SCRIPTS: dict[str, str] = {
    "tapps-pre-linear-write.ps1": LINEAR_GATE_SCRIPTS_PS["tapps-pre-linear-write.ps1"],
    "tapps-pre-linear-list.ps1": LINEAR_CACHE_GATE_SCRIPTS_PS["tapps-pre-linear-list.ps1"],
    "tapps-pre-session-start-gate.ps1": SESSION_START_GATE_SCRIPTS_PS[
        "tapps-pre-session-start-gate.ps1"
    ],
}


@pytest.mark.parametrize("name", sorted(BASH_LEDGER_SCRIPTS))
def test_bash_ledger_writer_carries_shared_resolution(name: str) -> None:
    body = BASH_LEDGER_SCRIPTS[name]
    assert ".bypass-log.jsonl" in body, f"{name} no longer writes the ledger"
    assert LEDGER_ROOT_RESOLVE_BASH in body, (
        f"{name} does not use the shared LEDGER_ROOT_RESOLVE_BASH resolution"
    )
    assert '${CLAUDE_PROJECT_DIR:-$PWD}"\nmkdir' not in body, (
        f"{name} still has an un-shared naive fallback next to a bypass write"
    )


@pytest.mark.parametrize("name", sorted(PS_LEDGER_SCRIPTS))
def test_ps_ledger_writer_carries_shared_resolution(name: str) -> None:
    body = PS_LEDGER_SCRIPTS[name]
    assert ".bypass-log.jsonl" in body, f"{name} no longer writes the ledger"
    assert LEDGER_ROOT_RESOLVE_PS in body, (
        f"{name} does not use the shared LEDGER_ROOT_RESOLVE_PS resolution"
    )
