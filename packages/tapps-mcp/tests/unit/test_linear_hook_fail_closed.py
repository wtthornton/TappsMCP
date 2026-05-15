"""Smoke tests for the linear/bash hooks fail-closed on missing python (TAP-1785).

The TappsMCP PreToolUse hooks ``tapps-pre-linear-write.sh`` (write gate) and
``tapps-pre-bash.sh`` (destructive command guard) used to resolve a PYBIN and
invoke it unguarded; when no python interpreter was on PATH, the inline call
produced no parsed output and the case statement's catch-all ``exit 0`` let
the gated call through.

These tests assert the hooks now check ``[ -z "$PYBIN" ]`` and exit 2 — i.e.
fail closed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
LINEAR_WRITE_HOOK = REPO_ROOT / ".claude" / "hooks" / "tapps-pre-linear-write.sh"
PRE_BASH_HOOK = REPO_ROOT / ".claude" / "hooks" / "tapps-pre-bash.sh"

LINEAR_WRITE_TEMPLATE_SOURCE = (
    REPO_ROOT
    / "packages"
    / "tapps-mcp"
    / "src"
    / "tapps_mcp"
    / "pipeline"
    / "platform_hook_templates.py"
)


def _run_hook_without_python(hook_path: Path, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    """Invoke *hook_path* with PATH set to a directory that has no python."""
    sandbox = hook_path.parent / "_no_python_sandbox_does_not_exist"
    # We do NOT actually create the directory — a missing PATH entry has the
    # same effect (command -v finds nothing) and avoids accidentally picking
    # up a python the test harness shipped.
    env = {"PATH": str(sandbox)}
    return subprocess.run(
        ["/usr/bin/bash", str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.skipif(
    not LINEAR_WRITE_HOOK.exists(),
    reason=f"deployed hook not present at {LINEAR_WRITE_HOOK}",
)
def test_linear_write_hook_fails_closed_when_python_missing() -> None:
    result = _run_hook_without_python(
        LINEAR_WRITE_HOOK,
        {
            "tool_name": "mcp__plugin_linear_linear__save_issue",
            "tool_input": {"title": "x", "description": "y"},
        },
    )
    assert result.returncode == 2, (
        f"expected exit 2 when python missing; got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert "no python interpreter" in result.stderr.lower()


@pytest.mark.skipif(
    not PRE_BASH_HOOK.exists(),
    reason=f"deployed hook not present at {PRE_BASH_HOOK}",
)
def test_pre_bash_hook_fails_closed_when_python_missing() -> None:
    result = _run_hook_without_python(
        PRE_BASH_HOOK,
        {"tool_input": {"command": "echo hello"}},
    )
    assert result.returncode == 2, (
        f"expected exit 2 when python missing; got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert "no python interpreter" in result.stderr.lower()


def test_template_source_contains_guard() -> None:
    """The template source — not just the deployed copy — must encode the fix."""
    body = LINEAR_WRITE_TEMPLATE_SOURCE.read_text(encoding="utf-8")
    assert body.count('if [ -z "$PYBIN" ]; then') >= 2, (
        "Both the LINEAR_GATE_PRE_SAVE_SCRIPT template and the tapps-pre-bash.sh "
        "template should add the PYBIN guard."
    )
    assert "TAP-1785" in body
