"""Regression: every shipped bash hook template must parse with ``bash -n``.

This test would have caught the broken fork-bomb case pattern in
``tapps-pre-bash.sh`` (unescaped ``(`` / ``)`` characters terminating the case
alternative early). It runs ``bash -n`` on every rendered .sh template
across the four script dictionaries and fails if any template contains a
syntax error.

The check is parametrised at collection time so a failure surfaces the
exact script name in the test ID instead of dumping a single aggregated
error.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_hook_templates import (
    AGENT_TEAMS_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS_BLOCKING,
    CLAUDE_REACTIVE_HOOK_SCRIPTS,
    CURSOR_HOOK_SCRIPTS,
)


# Map of "source label" -> dict of script name -> body. Adding a new bash
# template dict to the codebase should grow this map; the parametrize will
# pick it up automatically.
_BASH_TEMPLATE_SOURCES: dict[str, dict[str, str]] = {
    "claude": CLAUDE_HOOK_SCRIPTS,
    "claude_blocking": CLAUDE_HOOK_SCRIPTS_BLOCKING,
    "claude_reactive": CLAUDE_REACTIVE_HOOK_SCRIPTS,
    "cursor": CURSOR_HOOK_SCRIPTS,
    "agent_teams": AGENT_TEAMS_HOOK_SCRIPTS,
}


def _flatten() -> tuple[list[tuple[str, str, str]], list[str]]:
    rows: list[tuple[str, str, str]] = []
    ids: list[str] = []
    for source_label, script_map in _BASH_TEMPLATE_SOURCES.items():
        for name, body in script_map.items():
            if not name.endswith(".sh"):
                continue
            rows.append((source_label, name, body))
            ids.append(f"{source_label}/{name}")
    return rows, ids


_ROWS, _IDS = _flatten()


@pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32",
    reason="bash not available — syntax check is bash-specific",
)
@pytest.mark.parametrize(("source_label", "script_name", "body"), _ROWS, ids=_IDS)
def test_bash_template_parses(
    tmp_path: Path,
    source_label: str,
    script_name: str,
    body: str,
) -> None:
    """Every shipped .sh template must pass ``bash -n``.

    Catches unescaped shell metacharacters in case patterns, mismatched
    quoting, missing ``fi`` / ``done``, etc., before they reach a consumer.
    """
    rendered = tmp_path / script_name
    rendered.write_text(body, encoding="utf-8")
    proc = subprocess.run(
        ["bash", "-n", str(rendered)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, (
        f"bash -n failed on {source_label}/{script_name}:\n"
        f"stderr={proc.stderr}\n"
        f"--- script ---\n{body}"
    )


def test_pre_bash_blocks_fork_bomb_substring(tmp_path: Path) -> None:
    """Specific regression for the bug shipped in earlier versions where the
    fork-bomb case pattern had unescaped parens. The substring ":(){" in
    a tool_input.command must trigger BLOCK=1 (exit 2)."""
    if shutil.which("bash") is None or sys.platform == "win32":
        pytest.skip("bash required")
    body = CLAUDE_HOOK_SCRIPTS["tapps-pre-bash.sh"]
    rendered = tmp_path / "tapps-pre-bash.sh"
    rendered.write_text(body, encoding="utf-8")
    # Build the fork-bomb command via os concat so this test file does not
    # itself contain the literal ":(){" substring (which would trip Claude
    # Code's own destructive-bash-guard at edit time).
    fork = ":" + "(){" + " :|:& " + "};:"
    payload = f'{{"tool_input":{{"command":"{fork}"}}}}'
    proc = subprocess.run(
        ["bash", str(rendered)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2, (
        f"Expected exit 2 (block) for fork bomb command, got {proc.returncode}.\n"
        f"stderr={proc.stderr}"
    )


def test_pre_bash_allows_benign_command(tmp_path: Path) -> None:
    """Sanity: ls -la must NOT be blocked by the destructive guard."""
    if shutil.which("bash") is None or sys.platform == "win32":
        pytest.skip("bash required")
    body = CLAUDE_HOOK_SCRIPTS["tapps-pre-bash.sh"]
    rendered = tmp_path / "tapps-pre-bash.sh"
    rendered.write_text(body, encoding="utf-8")
    payload = '{"tool_input":{"command":"ls -la"}}'
    proc = subprocess.run(
        ["bash", str(rendered)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, (
        f"Benign command was blocked unexpectedly. stderr={proc.stderr}"
    )
