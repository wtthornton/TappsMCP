"""TAP-7225 / VAL-09: the PRE session-start gate resolves $ROOT to the
LINKED WORKTREE's own top, not the primary checkout's ``.git``.

The POST hook (``tapps-post-session-start.sh``) writes the sentinel under
``${CLAUDE_PROJECT_DIR:-$PWD}`` -- i.e. the worktree's own root when run
from inside a worktree with ``CLAUDE_PROJECT_DIR`` unset. Before this fix
the PRE hook resolved ``$ROOT`` via ``git rev-parse --git-common-dir``,
which is the PRIMARY checkout's ``.git`` in any linked worktree, so the PRE
gate could never find a sentinel the POST hook wrote in the worktree.

These tests drive the real ``.claude/hooks/tapps-pre-session-start-gate.sh``
under ``bash`` (not a string-match against the template) across the three
``$ROOT`` branches: ``CLAUDE_PROJECT_DIR`` set, unset in a linked worktree,
and unset in a ``.git``-less scratch dir.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
PRE_GATE_HOOK = REPO_ROOT / ".claude" / "hooks" / "tapps-pre-session-start-gate.sh"

PAYLOAD: dict[str, object] = {
    "tool_name": "mcp__nlt-build__tapps_quick_check",
    "session_id": "sid-7225",
    "tool_input": {},
}


@pytest.fixture(autouse=True)
def _require_posix() -> None:
    if sys.platform == "win32":
        pytest.skip("hook script under test is bash-specific")


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _make_primary_and_worktree(tmp_path: Path) -> tuple[Path, Path]:
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


def _run_gate(script_body: str, hook_dir: Path, cwd: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    import os

    hook_path = hook_dir / "tapps-pre-session-start-gate.sh"
    hook_path.write_text(script_body, encoding="utf-8")
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.update(extra_env)
    return subprocess.run(
        ["/usr/bin/bash", str(hook_path)],
        input=json.dumps(PAYLOAD),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def test_worktree_no_env_resolves_sentinel_path_to_worktree_root(tmp_path: Path) -> None:
    """Branch: CLAUDE_PROJECT_DIR unset, run from a linked worktree."""
    primary, worktree = _make_primary_and_worktree(tmp_path)
    hook_dir = tmp_path / "hooks"
    hook_dir.mkdir()
    script_body = PRE_GATE_HOOK.read_text(encoding="utf-8")

    result = _run_gate(script_body, hook_dir, worktree, extra_env={})

    expected_sentinel = worktree / ".tapps-mcp" / ".session-start-gate-violations.jsonl"
    assert result.returncode == 0, result.stderr
    assert expected_sentinel.exists(), (
        f"expected the gate to record its violation under the worktree, not the primary; "
        f"stderr={result.stderr}"
    )
    assert not (primary / ".tapps-mcp" / ".session-start-gate-violations.jsonl").exists()


def test_worktree_sentinel_already_written_is_admitted(tmp_path: Path) -> None:
    """The gate reads the sentinel path a real POST-hook write would produce:
    <worktree>/.tapps-mcp/.session-start-done-<SID> -- proving PRE and POST
    now agree, not just that PRE writes somewhere in the worktree."""
    _primary, worktree = _make_primary_and_worktree(tmp_path)
    hook_dir = tmp_path / "hooks"
    hook_dir.mkdir()
    script_body = PRE_GATE_HOOK.read_text(encoding="utf-8")

    sentinel_dir = worktree / ".tapps-mcp"
    sentinel_dir.mkdir()
    (sentinel_dir / ".session-start-done-sid-7225").touch()

    result = _run_gate(script_body, hook_dir, worktree, extra_env={})

    assert result.returncode == 0, result.stderr
    assert not (sentinel_dir / ".session-start-gate-violations.jsonl").exists(), (
        "gate logged a violation despite the worktree-local sentinel existing"
    )


def test_env_set_wins_over_git_resolution(tmp_path: Path) -> None:
    """Branch: CLAUDE_PROJECT_DIR set -- always wins, matching the POST hook."""
    _primary, worktree = _make_primary_and_worktree(tmp_path)
    explicit_root = tmp_path / "explicit-root"
    explicit_root.mkdir()
    hook_dir = tmp_path / "hooks"
    hook_dir.mkdir()
    script_body = PRE_GATE_HOOK.read_text(encoding="utf-8")

    result = _run_gate(
        script_body, hook_dir, worktree, extra_env={"CLAUDE_PROJECT_DIR": str(explicit_root)}
    )

    assert result.returncode == 0, result.stderr
    assert (explicit_root / ".tapps-mcp" / ".session-start-gate-violations.jsonl").exists()


def test_non_git_scratch_dir_falls_back_to_pwd(tmp_path: Path) -> None:
    """Branch: no CLAUDE_PROJECT_DIR, no .git anywhere above cwd -- PWD wins."""
    scratch = tmp_path / "scratch-no-git"
    scratch.mkdir()
    hook_dir = tmp_path / "hooks"
    hook_dir.mkdir()
    script_body = PRE_GATE_HOOK.read_text(encoding="utf-8")

    result = _run_gate(script_body, hook_dir, scratch, extra_env={})

    assert result.returncode == 0, result.stderr
    assert (scratch / ".tapps-mcp" / ".session-start-gate-violations.jsonl").exists()


def test_base_script_negative_control_resolves_to_primary_not_worktree(tmp_path: Path) -> None:
    """Sensitivity check: the pre-fix ``--git-common-dir`` resolution must
    reproduce the TAP-7225 defect (sentinel path under the PRIMARY, not the
    worktree) -- proving the positive tests above exercise the real defect."""
    primary, worktree = _make_primary_and_worktree(tmp_path)
    hook_dir = tmp_path / "hooks"
    hook_dir.mkdir()
    fixed_body = PRE_GATE_HOOK.read_text(encoding="utf-8")
    buggy_body = fixed_body.replace(
        (
            'ROOT="${CLAUDE_PROJECT_DIR:-}"\n'
            "if [ -z \"$ROOT\" ]; then\n"
            "  ROOT=\"$(git rev-parse --show-toplevel 2>/dev/null || true)\"\n"
            "  if [ -z \"$ROOT\" ]; then\n"
            "    ROOT=\"$PWD\"\n"
            "  fi\n"
            "fi\n"
        ),
        (
            'ROOT="${CLAUDE_PROJECT_DIR:-}"\n'
            "if [ -z \"$ROOT\" ]; then\n"
            "  _common=\"$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)\"\n"
            "  if [ -n \"$_common\" ]; then\n"
            "    ROOT=\"$(cd \"$_common/..\" && pwd)\"\n"
            "  else\n"
            "    ROOT=\"$PWD\"\n"
            "  fi\n"
            "fi\n"
        ),
    )
    assert buggy_body != fixed_body, "substitution did not apply -- test would be vacuous"

    result = _run_gate(buggy_body, hook_dir, worktree, extra_env={})

    assert result.returncode == 0, result.stderr
    assert (primary / ".tapps-mcp" / ".session-start-gate-violations.jsonl").exists(), (
        "negative control: the pre-fix script should resolve to the primary checkout"
    )
    assert not (worktree / ".tapps-mcp" / ".session-start-gate-violations.jsonl").exists()
