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
