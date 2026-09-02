"""Behavioral tests for the TAP-6889 lane guard in ``tapps-pre-bash.sh``.

The hook already blocks a fixed set of destructive command substrings
unconditionally. TAP-6889 adds three more checks — backgrounding, leaving
the project directory, and a few suppression markers — but only when
``ORCHESTRATOR_GOAL_DISPATCH=1`` (a dispatched lane), so interactive
sessions are never affected.

These tests render the current template body (not the deployed copy under
``.claude/hooks/``, which only refreshes on ``tapps_upgrade``) and exercise
it via subprocess, matching the pattern in test_hook_script_syntax.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOK_SCRIPTS

HOOK_BODY = CLAUDE_HOOK_SCRIPTS["tapps-pre-bash.sh"]


def _run(
    tmp_path: Path,
    command: str,
    *,
    dispatch: bool,
    run_in_background: bool = False,
) -> subprocess.CompletedProcess[str]:
    hook_path = tmp_path / "tapps-pre-bash.sh"
    hook_path.write_text(HOOK_BODY, encoding="utf-8")
    tool_input: dict[str, object] = {"command": command}
    if run_in_background:
        tool_input["run_in_background"] = True
    payload = json.dumps({"tool_input": tool_input})
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(tmp_path)}
    if dispatch:
        env["ORCHESTRATOR_GOAL_DISPATCH"] = "1"
    return subprocess.run(
        ["/usr/bin/bash", str(hook_path)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="hook script is bash-specific",
)


# ---------------------------------------------------------------------------
# Shape 1: backgrounding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "sleep 5 &",
        "sleep 5 & ",
        "sleep 5 &;",
        "sleep 5&",
        "nohup pytest packages/tapps-mcp/tests -v",
        "setsid env FOO=1 claude -p hello",
        "disown %1",
    ],
)
def test_backgrounding_blocked_under_dispatch(tmp_path: Path, command: str) -> None:
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 2, f"expected block for {command!r}: {result.stderr}"


@pytest.mark.parametrize(
    "command",
    [
        "sleep 5 &",
        "nohup pytest packages/tapps-mcp/tests -v",
    ],
)
def test_backgrounding_allowed_without_dispatch(tmp_path: Path, command: str) -> None:
    result = _run(tmp_path, command, dispatch=False)
    assert result.returncode == 0, f"expected allow for {command!r}: {result.stderr}"


def test_run_in_background_flag_blocked_under_dispatch(tmp_path: Path) -> None:
    result = _run(
        tmp_path, "pytest packages/tapps-mcp/tests -v", dispatch=True, run_in_background=True
    )
    assert result.returncode == 2
    assert "run_in_background" in result.stderr


def test_run_in_background_flag_allowed_without_dispatch(tmp_path: Path) -> None:
    result = _run(
        tmp_path, "pytest packages/tapps-mcp/tests -v", dispatch=False, run_in_background=True
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Must-allow set: real-world command shapes that merely contain an "&"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "a && b",
        "cmd 2>&1",
        'echo "x & y"',
        "cmd &> log",
        "echo done && echo more",
        "pytest packages/tapps-mcp/tests -v",
    ],
)
def test_must_allow_shapes_pass_under_dispatch(tmp_path: Path, command: str) -> None:
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 0, f"expected allow for {command!r}: {result.stderr}"


# ---------------------------------------------------------------------------
# Shape 2: cd leaving the project directory
# ---------------------------------------------------------------------------


def test_cd_outside_project_dir_blocked_under_dispatch(tmp_path: Path) -> None:
    result = _run(tmp_path, "cd /tmp/some-sibling-checkout && git status", dispatch=True)
    assert result.returncode == 2


def test_cd_outside_project_dir_allowed_without_dispatch(tmp_path: Path) -> None:
    result = _run(tmp_path, "cd /tmp/some-sibling-checkout && git status", dispatch=False)
    assert result.returncode == 0


@pytest.mark.parametrize(
    "command",
    [
        "cd packages/tapps-mcp && pytest tests -v",
        "cd ./packages && ls",
        "cd -",
        "cd ~",
        "cd",
        "pytest packages/tapps-mcp/tests -v",
    ],
)
def test_cd_inside_or_ambiguous_allowed_under_dispatch(tmp_path: Path, command: str) -> None:
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 0, f"expected allow for {command!r}: {result.stderr}"


def test_cd_parent_of_project_root_blocked_under_dispatch(tmp_path: Path) -> None:
    result = _run(tmp_path, "cd .. && ls", dispatch=True)
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Shape 3: green-by-suppression markers (partial coverage by design)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "sed -i 's/import foo/import foo  # noqa/' packages/tapps-mcp/src/x.py",
        "echo '# type: ignore' >> packages/tapps-mcp/src/x.py",
        "python -c \"open('x.py','a').write('@pytest.mark.skip\\n')\"",
        "echo 'xfail' >> test_x.py",
    ],
)
def test_suppression_markers_blocked_under_dispatch(tmp_path: Path, command: str) -> None:
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 2, f"expected block for {command!r}: {result.stderr}"


def test_suppression_marker_allowed_without_dispatch(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "sed -i 's/import foo/import foo  # noqa/' packages/tapps-mcp/src/x.py",
        dispatch=False,
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Tokenizer bypass regression (TAP-6889 round 2): squishing a guarded word
# against the previous command with no space defeated shlex.split, which
# does not split a word off a bare ";" the way a real shell does. Both prior
# verifications (this file's first version, and an independent 18-case
# harness) held the separator fixed at "; " and varied only the command, so
# neither could see the bug. This section makes the separator an explicit
# axis, crossed against every guarded shape.
# ---------------------------------------------------------------------------

_SEPARATORS = {
    "none": "",  # the shape stands alone -- the historical positive control
    "semicolon": ";",
    "semicolon_space": "; ",
    "double_amp": "&&",
    "double_pipe": "||",
    "newline": "\n",
    "tab": "\t",
}


def _prefixed(sep: str, body: str) -> str:
    # Gluing "hi" directly onto the next word with zero characters between
    # is not a shell separator at all -- it is one word, and must stay
    # allowed. "none" therefore uses the shape as the whole command instead
    # of prefixing it, matching the pre-existing positive-control shape.
    if sep == "":
        return body
    return f"echo hi{sep}{body}"


_GUARDED_SHAPES = {
    "nohup": "nohup pytest -v",
    "disown": "disown",
    "setsid": "setsid pytest -v",
    "cd_escape": "cd /tmp/some-sibling-checkout",
    "noqa": "echo '# noqa' >> x.py",
    "type_ignore": "echo '# type: ignore' >> x.py",
    "pytest_skip": "echo '@pytest.mark.skip' >> x.py",
    "xfail": "echo 'xfail' >> x.py",
}


@pytest.mark.parametrize("sep_name", sorted(_SEPARATORS))
@pytest.mark.parametrize("shape_name", sorted(_GUARDED_SHAPES))
def test_guarded_shapes_blocked_across_every_separator(
    tmp_path: Path, shape_name: str, sep_name: str
) -> None:
    command = _prefixed(_SEPARATORS[sep_name], _GUARDED_SHAPES[shape_name])
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 2, (
        f"expected block for shape={shape_name} sep={sep_name} command={command!r}: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        "   nohup pytest -v",
        "\tdisown",
        "  setsid pytest -v",
        "   cd /tmp/some-sibling-checkout",
    ],
)
def test_guarded_shapes_blocked_with_leading_whitespace(tmp_path: Path, command: str) -> None:
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 2, f"expected block for {command!r}: {result.stderr}"


@pytest.mark.parametrize(
    "command",
    [
        "echo hi;nohup pytest -v",
        "echo hi;setsid pytest -v",
        "echo hi;disown",
        "echo hi;cd /tmp/some-sibling-checkout",
        "nohup pytest -v",
        "sleep 5 &",
        "echo hi;echo '# noqa' >> x.py",
    ],
)
def test_guarded_shapes_allowed_without_dispatch(tmp_path: Path, command: str) -> None:
    """Lane-scoping control: with the gate env var unset, every squished
    bypass shape (and the plain positive controls) still exits 0."""
    result = _run(tmp_path, command, dispatch=False)
    assert result.returncode == 0, f"expected allow for {command!r}: {result.stderr}"


@pytest.mark.parametrize(
    "command",
    [
        "a && b",
        "cmd 2>&1",
        "cmd &> log",
        'echo "x & y"',
        "cd packages/tapps-mcp",
        "cd -",
        "cd ~",
        "cd",
        "make lint && make test",
        "echo done && echo more",
        "pytest packages/tapps-mcp/tests -v",
        "cd packages/tapps-mcp && pytest tests -v",
        "cd ./packages && ls",
        "git commit -m 'fix: a;b'",
        "find . -name '*.py'",
    ],
)
def test_must_allow_set_survives_stricter_tokenizer(tmp_path: Path, command: str) -> None:
    """The punctuation-aware tokenizer must not start blocking ordinary
    shell idioms that merely contain an operator character."""
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 0, f"expected allow for {command!r}: {result.stderr}"


def test_grep_for_xfail_is_a_known_false_positive_ceiling(tmp_path: Path) -> None:
    """The suppression-marker check is a plain substring match on command
    text, so it cannot distinguish a write from a read: ``grep -rn xfail``
    blocks even though it never writes a suppression marker anywhere. This
    is the documented, accepted ceiling of the check (see the PR's Known
    limitations) -- pinned here so a later change to the marker check
    cannot silently flip it one way or the other without a test noticing.
    """
    result = _run(tmp_path, "grep -rn xfail packages/tapps-mcp/tests", dispatch=True)
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# TAP-6908: mid-compound "&" and subshell backgrounding, plus a recursive
# check into a literal `bash -c '...'` payload. Every case here runs through
# the real emitted hook script via `_run` (REACHABILITY), the same helper
# used above -- not a standalone parsing function.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "pytest packages/tapps-mcp/tests -v & echo done",
        "sleep 5 & echo next",
        "( pytest -v & )",
        "( sleep 5 & )",
        "true&false",
        "cmd&;echo done",
    ],
)
def test_mid_compound_and_subshell_backgrounding_blocked_under_dispatch(
    tmp_path: Path, command: str
) -> None:
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 2, f"expected block for {command!r}: {result.stderr}"


@pytest.mark.parametrize(
    "command",
    [
        "pytest packages/tapps-mcp/tests -v & echo done",
        "( pytest -v & )",
    ],
)
def test_mid_compound_and_subshell_backgrounding_allowed_without_dispatch(
    tmp_path: Path, command: str
) -> None:
    result = _run(tmp_path, command, dispatch=False)
    assert result.returncode == 0, f"expected allow for {command!r}: {result.stderr}"


@pytest.mark.parametrize(
    "command",
    [
        "a && b",
        "cmd 2>&1",
        'echo "a & b"',
    ],
)
def test_amp_negative_controls_pass_under_dispatch(tmp_path: Path, command: str) -> None:
    """The exact negative controls called out in the TAP-6908 lane brief."""
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 0, f"expected allow for {command!r}: {result.stderr}"


@pytest.mark.parametrize(
    "command",
    [
        "bash -c 'nohup pytest -v'",
        "bash -c 'sleep 5 &'",
        "sh -c 'disown %1'",
        "zsh -c 'setsid pytest -v'",
        "bash -c 'cd /tmp/some-sibling-checkout && ls'",
    ],
)
def test_bash_c_payload_recursively_checked_under_dispatch(
    tmp_path: Path, command: str
) -> None:
    result = _run(tmp_path, command, dispatch=True)
    assert result.returncode == 2, f"expected block for {command!r}: {result.stderr}"


def test_bash_c_payload_allowed_without_dispatch(tmp_path: Path) -> None:
    result = _run(tmp_path, "bash -c 'nohup pytest -v'", dispatch=False)
    assert result.returncode == 0


def test_bash_c_variable_indirection_not_recursively_checked(tmp_path: Path) -> None:
    """Documented, tested gap: the recursive bash -c check only follows a
    literal string argument resolved by shlex. It does not expand shell
    variables, so smuggling a guarded word through a variable defeats it.
    This is pinned (a deliberate, tested decision -- not silence) so a
    future change to the recursion cannot silently widen or narrow it
    without a test noticing."""
    result = _run(
        tmp_path,
        "CMD='nohup pytest -v'; bash -c \"$CMD\"",
        dispatch=True,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Existing destructive-command blocks and fail-closed path (must be unchanged)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "format c:",
        "del /f /s /q C:\\",
        ":(){ :|:& };:",
    ],
)
@pytest.mark.parametrize("dispatch", [True, False])
def test_existing_destructive_blocks_unchanged(
    tmp_path: Path, command: str, dispatch: bool
) -> None:
    result = _run(tmp_path, command, dispatch=dispatch)
    assert result.returncode == 2, f"expected block for {command!r}: {result.stderr}"


def test_no_python_still_fails_closed(tmp_path: Path) -> None:
    hook_path = tmp_path / "tapps-pre-bash.sh"
    hook_path.write_text(HOOK_BODY, encoding="utf-8")
    payload = json.dumps({"tool_input": {"command": "echo hi"}})
    sandbox = tmp_path / "_no_python_sandbox_does_not_exist"
    result = subprocess.run(
        ["/usr/bin/bash", str(hook_path)],
        input=payload,
        capture_output=True,
        text=True,
        env={"PATH": str(sandbox)},
        check=False,
    )
    assert result.returncode == 2
    assert "no python interpreter" in result.stderr.lower()
