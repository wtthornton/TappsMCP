"""Cross-language parity guard for the Linear cache-key algorithm.

The Linear cache-first read gate derives a sentinel/cache key from the
``(team, project, state, label, limit)`` slice in **four** places:

1. The authoritative Python — ``server_linear_tools._resolve_cache_key`` plus
   ``linear_list_gateway._alias_keys`` (read by the server tool
   ``tapps_linear_snapshot_get`` and the in-process gate).
2. The shared bash snippet ``LINEAR_CACHE_GATE_KEY_PY`` — embedded in the
   ``tapps-pre-linear-list.sh`` and ``tapps-post-linear-snapshot-get.sh`` hooks.
3. An inline copy in ``LINEAR_CACHE_GATE_POST_LIST_SCRIPT``
   (``tapps-post-linear-list.sh``, the TAP-1412 auto-populate hook).
4. The PowerShell variants (not exercised here — no interpreter on CI Linux).

``test_linear_cache_gate.py`` only checks bash-against-bash (the snapshot hook
writes a sentinel that the pre-list hook reads — same algorithm both sides, so
they trivially agree). If the bash key derivation ever drifts from the Python
``_resolve_cache_key``, the *server tool* writes the snapshot cache under one
key while the hook sentinel uses another: a silent cache miss / false gate
verdict with no loud failure. These tests turn that drift into a CI failure.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_CACHE_GATE_KEY_PY,
    LINEAR_CACHE_GATE_POST_LIST_SCRIPT,
)
from tapps_mcp.server_linear_tools import _resolve_cache_key
from tapps_mcp.tools.linear_list_gateway import _alias_keys, _sentinel_key

# (team, project, state, label, limit) — non-empty team/project so the bash
# snippet emits a real key (it returns '' to skip the gate when either is
# blank). Covers: empty/open/closed/triage states, labels, non-default
# limits, and slashes in identifiers.
_MATRIX: tuple[tuple[str, str, str, str, int], ...] = (
    ("TAP", "TappsMCP Platform", "", "", 50),
    ("TAP", "TappsMCP Platform", "open", "", 50),
    ("TAP", "TappsMCP Platform", "backlog", "", 50),
    ("TAP", "TappsMCP Platform", "started", "bug", 50),
    ("TAP", "TappsMCP Platform", "unstarted", "feature", 25),
    ("TAP", "TappsMCP Platform", "triage", "", 100),
    ("TAP", "TappsMCP Platform", "completed", "", 50),
    ("TAP", "TappsMCP Platform", "canceled", "urgent", 10),
    ("Eng/Core", "My/Project", "open", "p1", 50),
    ("TAP", "TappsMCP Platform", "", "urgent", 10),
)


def _run_key_snippet(
    team: str, project: str, state: str, label: str, limit: int
) -> tuple[str, list[str]]:
    """Execute ``LINEAR_CACHE_GATE_KEY_PY`` and return ``(key, alias_keys)``.

    Mirrors how the bash hooks invoke the snippet: pipe a tool-call envelope
    on stdin and read the newline-delimited fields back out. Output layout is
    ``name / key / team / project / '|'.join(aliases)`` (5 lines).
    """
    payload = {
        "tool_name": "mcp__plugin_linear_linear__list_issues",
        "tool_input": {
            "team": team,
            "project": project,
            "state": state,
            "label": label,
            "limit": limit,
        },
    }
    proc = subprocess.run(
        [sys.executable, "-c", LINEAR_CACHE_GATE_KEY_PY],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    lines = proc.stdout.split("\n")
    # splitlines-style parse; trailing newline yields an empty final element.
    key = lines[1] if len(lines) > 1 else ""
    alias_field = lines[4] if len(lines) > 4 else ""
    aliases = [a for a in alias_field.split("|") if a]
    return key, aliases


def _python_sentinel_set(
    team: str, project: str, state: str, label: str, limit: int
) -> set[str]:
    """The full set of sentinel keys the Python gate checks for a slice.

    ``check_snapshot_sentinel`` accepts a hit on the primary key OR any alias
    key, so the consistency invariant is set equality with the bash side.
    """
    primary = _sentinel_key(team, project, state, label, limit)
    aliases = _alias_keys(team, project, state, label, limit)
    return {primary, *aliases}


@pytest.mark.parametrize(("team", "project", "state", "label", "limit"), _MATRIX)
def test_bash_key_matches_python_resolve_cache_key(
    team: str, project: str, state: str, label: str, limit: int
) -> None:
    """Bash primary key == Python ``_resolve_cache_key`` for every slice.

    This is the exact key the server's ``tapps_linear_snapshot_get`` reads the
    cache file under; the hooks must agree byte-for-byte.
    """
    bash_key, _ = _run_key_snippet(team, project, state, label, limit)
    py_key = _resolve_cache_key(team, project, state, label, limit)
    assert bash_key == py_key, (
        f"bash key {bash_key!r} != python key {py_key!r} "
        f"for ({team!r}, {project!r}, {state!r}, {label!r}, {limit})"
    )


@pytest.mark.parametrize(("team", "project", "state", "label", "limit"), _MATRIX)
def test_bash_sentinel_set_matches_python(
    team: str, project: str, state: str, label: str, limit: int
) -> None:
    """The full sentinel set written by bash == the set the Python gate checks.

    The snapshot hook writes ``{key} union aliases``; the Python gate accepts a hit
    on ``{primary} union _alias_keys``. Set equality is the consistency invariant —
    drift here means a ``snapshot_get(state='open')`` no longer unlocks a
    concrete ``list_issues(state='backlog')`` (the TAP-1374 alias contract).
    """
    bash_key, bash_aliases = _run_key_snippet(team, project, state, label, limit)
    bash_set = {bash_key, *bash_aliases}
    py_set = _python_sentinel_set(team, project, state, label, limit)
    assert bash_set == py_set, (
        f"sentinel set mismatch for ({team!r}, {project!r}, {state!r}):\n"
        f"  bash only:   {sorted(bash_set - py_set)}\n"
        f"  python only: {sorted(py_set - bash_set)}"
    )


def test_bash_skips_gate_when_team_or_project_blank() -> None:
    """Bash returns an empty key (gate skip) when team or project is blank.

    Documents the intentional divergence from Python: ``_resolve_cache_key``
    always builds a key, but the hook cannot gate a slice with no team/project,
    so it emits '' and the pre-list hook exits 0 (fail-open for un-scopable
    reads). Encoded as a test so a future refactor cannot silently change it.
    """
    for team, project in (("", "Proj"), ("TAP", ""), ("", "")):
        key, aliases = _run_key_snippet(team, project, "open", "", 50)
        assert key == "", f"expected empty key for team={team!r} project={project!r}"
        assert aliases == []


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.parametrize(
    ("state", "label", "limit"),
    [("", "", 50), ("open", "", 50), ("backlog", "bug", 25), ("completed", "", 100)],
)
def test_post_list_autopopulate_writes_under_python_cache_key(
    tmp_path: Path, state: str, label: str, limit: int
) -> None:
    """End-to-end: the auto-populate hook writes the cache file under the same
    key the server's ``snapshot_get`` will read it from.

    Renders ``LINEAR_CACHE_GATE_POST_LIST_SCRIPT`` (which carries its own inline
    key derivation, separate from ``LINEAR_CACHE_GATE_KEY_PY``), runs it against
    a fake ``list_issues`` response, and asserts the cache file lands at exactly
    ``.tapps-mcp-cache/linear-snapshots/<_resolve_cache_key>.json``.
    """
    team, project = "TAP", "TappsMCP Platform"
    script = tmp_path / "tapps-post-linear-list.sh"
    script.write_text(LINEAR_CACHE_GATE_POST_LIST_SCRIPT, encoding="utf-8")

    payload = {
        "tool_name": "mcp__plugin_linear_linear__list_issues",
        "tool_input": {
            "team": team,
            "project": project,
            "state": state,
            "label": label,
            "limit": limit,
        },
        "tool_response": {
            "issues": [{"identifier": "TAP-1", "title": "demo", "state": state or "x"}]
        },
    }
    subprocess.run(
        ["bash", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env={"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": _path_env()},
    )

    py_key = _resolve_cache_key(team, project, state, label, limit)
    expected = tmp_path / ".tapps-mcp-cache" / "linear-snapshots" / f"{py_key}.json"
    assert expected.exists(), (
        f"auto-populate hook wrote no cache file at the python key {py_key!r}; "
        f"present: {sorted(p.name for p in (expected.parent.glob('*.json')))}"
    )
    written = json.loads(expected.read_text(encoding="utf-8"))
    assert written.get("auto_populated") is True
    assert written.get("issues")


def _path_env() -> str:
    """Return a PATH containing the python interpreter dir plus the defaults.

    The hook resolves ``python3``/``python`` from PATH; the test's interpreter
    may live in a venv that isn't on the default PATH inside the subprocess.
    """
    py_dir = str(Path(sys.executable).parent)
    return f"{py_dir}:/usr/local/bin:/usr/bin:/bin"
