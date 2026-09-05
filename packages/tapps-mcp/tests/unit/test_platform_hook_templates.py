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
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.git_hooks import GIT_PRE_COMMIT_SCRIPT
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS_PS,
    CURSOR_HOOK_SCRIPTS,
    LINEAR_GATE_SCRIPTS,
    LINEAR_GATE_SCRIPTS_PS,
    SCORABLE_EXT_BASH_CASE,
    SCORABLE_EXT_PY_TUPLE,
    _stop_hook_gate_scan_py,
    scorable_extensions,
)
from tapps_mcp.pipeline.platform_hook_templates_linear_gate import (
    LEDGER_ROOT_RESOLVE_BASH,
    LEDGER_ROOT_RESOLVE_PS,
    LINEAR_CACHE_GATE_SCRIPTS,
    LINEAR_CACHE_GATE_SCRIPTS_PS,
    SESSION_START_GATE_SCRIPTS,
    SESSION_START_GATE_SCRIPTS_PS,
)

@pytest.fixture(autouse=True)
def _require_posix() -> None:
    """These hook scripts assume ``/usr/bin/bash``; skip at runtime on
    Windows rather than via a collection-time marker."""
    if sys.platform == "win32":
        pytest.skip("hook scripts under test are bash-specific")

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


# ---------------------------------------------------------------------------
# TAP-6739 — post-edit hooks derive their extension list from
# get_supported_extensions() instead of hand-restating it
# ---------------------------------------------------------------------------


def _run_post_edit_hook(script_body: str, hook_dir: Path, file_path: str) -> subprocess.CompletedProcess[str]:
    hook_path = hook_dir / "post-edit.sh"
    hook_path.write_text(script_body, encoding="utf-8")
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": file_path}})
    env = dict(os.environ)
    env["TAPPS_HOOK_INPUT"] = payload
    return subprocess.run(
        ["/usr/bin/bash", str(hook_path)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.parametrize(
    ("scripts", "name"),
    [
        (CLAUDE_HOOK_SCRIPTS, "tapps-post-edit.sh"),
        (CURSOR_HOOK_SCRIPTS, "tapps-after-edit.sh"),
    ],
)
@pytest.mark.parametrize("ext", [".mjs", ".cjs"])
def test_mjs_and_cjs_trigger_post_edit_reminder(
    tmp_path: Path, scripts: dict[str, str], name: str, ext: str
) -> None:
    result = _run_post_edit_hook(scripts[name], tmp_path, f"foo{ext}")
    assert result.returncode == 0, result.stderr
    assert "tapps_quick_check" in result.stderr, (
        f"{name} did not trigger the post-edit reminder for a {ext} edit: "
        f"stderr={result.stderr!r}"
    )


def test_extension_set_equals_supported_on_every_generated_hook() -> None:
    """Every generated hook's extension set must equal get_supported_extensions(),
    so adding a scorable extension there cannot leave one of these sites behind."""
    expected = set(scorable_extensions())
    case_exts = {token.removeprefix("*") for token in SCORABLE_EXT_BASH_CASE.split("|")}
    assert case_exts == expected

    for scripts, name in (
        (CLAUDE_HOOK_SCRIPTS, "tapps-post-edit.sh"),
        (CURSOR_HOOK_SCRIPTS, "tapps-after-edit.sh"),
    ):
        body = scripts[name]
        assert SCORABLE_EXT_BASH_CASE in body, f"{name} does not use the shared case pattern"


# ---------------------------------------------------------------------------
# TAP-6737 — PowerShell warn Stop hook completion gate
# ---------------------------------------------------------------------------
#
# pwsh is not on this host (`command -v pwsh` finds nothing), so the
# execution test (box 4) and the CI parse job (box 6) are
# `blocked: pwsh not on host` per the lane instructions — only the template
# change and this Python-side parse-shape check (boxes 1-3) are delivered.


def test_ps1_stop_hook_shares_the_bash_gate_scan_source() -> None:
    """Parse-shape check (boxes 1-3): the ps1 Stop hook embeds the exact same
    _stop_hook_gate_scan_py() source the bash branch uses (needs_gate, the
    scorable-extension list, gate_called/checklist_called, and the
    .completion-gate-violations.jsonl write), so the two branches cannot
    independently drift the way the PR 304 regression did."""
    ps1_body = CLAUDE_HOOK_SCRIPTS_PS["tapps-stop.ps1"]
    bash_body = CLAUDE_HOOK_SCRIPTS["tapps-stop.sh"]
    shared_py = _stop_hook_gate_scan_py()

    assert shared_py in ps1_body, "ps1 Stop hook does not embed the shared gate-scan source"
    assert shared_py in bash_body, "bash Stop hook drifted from the shared gate-scan source"

    for marker in (
        "CHECKLIST_MISSING",
        "QUALITY_GATE_SKIP",
        ".completion-gate-violations.jsonl",
        "'mode': 'warn'",
        SCORABLE_EXT_PY_TUPLE,
    ):
        assert marker in ps1_body, f"ps1 Stop hook missing {marker!r}"


def test_ps1_stop_hook_invokes_python_for_the_scan() -> None:
    """The ps1 branch must actually run the shared scan (not just embed the
    text inertly) via the same Get-Command python3/python fallback pattern
    used elsewhere in this file's PowerShell hooks."""
    ps1_body = CLAUDE_HOOK_SCRIPTS_PS["tapps-stop.ps1"]
    assert "Get-Command python3" in ps1_body
    assert "& $py.Source -" in ps1_body
    assert "TAPPS_STOP_TRANSCRIPT" in ps1_body
    assert "TAPPS_STOP_PROJECT_DIR" in ps1_body


def test_ps1_stop_hook_parses_under_pwsh() -> None:
    """Box 5: the generated .ps1 must parse cleanly under
    System.Management.Automation.Language.Parser, guarding the PR 304 failure
    mode where a parse error survived seven green CI checks."""
    if shutil.which("pwsh") is None:
        pytest.skip("blocked: pwsh not on host (TAP-6737 boxes 4-6 need a real PowerShell)")
    ps1_body = CLAUDE_HOOK_SCRIPTS_PS["tapps-stop.ps1"]
    script_path = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "tapps-stop-parse-check.ps1"
    script_path.write_text(ps1_body, encoding="utf-8")
    check = (
        "$errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 } else { exit 0 }"
    )
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", check],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_ps1_stop_hook_writes_violation_for_python_edit_with_no_checklist(tmp_path: Path) -> None:
    """Box 4: execute the generated .ps1 (not merely read the template) and
    assert a violation line is written for a Python edit with no checklist
    call — the same VAL this issue's proof command targets on the bash side."""
    if shutil.which("pwsh") is None:
        pytest.skip("blocked: pwsh not on host (TAP-6737 box 4 needs a real PowerShell)")
    project = tmp_path / "project"
    project.mkdir()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": str(project / "foo.py")},
                        }
                    ]
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    script_path = tmp_path / "tapps-stop.ps1"
    script_path.write_text(CLAUDE_HOOK_SCRIPTS_PS["tapps-stop.ps1"], encoding="utf-8")
    payload = json.dumps({"stop_hook_active": False, "transcript_path": str(transcript)})
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(script_path)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    violations = project / ".tapps-mcp" / ".completion-gate-violations.jsonl"
    assert violations.exists(), result.stderr
    last = json.loads(violations.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert "CHECKLIST_MISSING" in last["reasons"]
    assert "QUALITY_GATE_SKIP" in "|".join(last["reasons"])
