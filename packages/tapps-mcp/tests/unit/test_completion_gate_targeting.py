"""TAP-7014 / TAP-7015 — the warn-mode completion gate targets the project root
and stops re-logging an unresolved violation on every Stop.

Kept as its own file rather than growing ``test_completion_gate_mechanism.py``:
that file is already at the edge of the maintainability/complexity gate (45
functions), and these six tests would tip it over — see project memory
"Gate splits need test splits".

1. TAP-7014: ``needs_gate`` tested file extension alone, so a throwaway file
   written outside the project root (e.g. ``/tmp``, a scratchpad) demanded a
   repo quality-gate run that could never legitimately be satisfied.
2. TAP-7015: the violation log appended a row on every Stop, even when the
   ``(files, reasons)`` state was unchanged from the last logged row, because
   ``edits`` accumulates over the whole transcript — doctor's 24h counter then
   roughly doubled the real number of unresolved states.

Every permissive assertion here is paired with its negative control.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks

_OUTSIDE_ROOT_FILE = "/tmp/tap-7014-outside-project-root-scratch.py"


def _write_transcript(root: Path, edited: list[str], name: str = "transcript.jsonl") -> Path:
    path = root / name
    path.write_text(
        "".join(
            json.dumps(
                {
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "Edit", "input": {"file_path": fp}}
                        ]
                    }
                }
            )
            + "\n"
            for fp in edited
        ),
        encoding="utf-8",
    )
    return path


def _run_warn_stop_hook(root: Path, transcript: Path) -> subprocess.CompletedProcess[str]:
    hook = root / ".claude" / "hooks" / "tapps-stop.sh"
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps({"stop_hook_active": False, "transcript_path": str(transcript)}),
        cwd=str(root),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "CLAUDE_PROJECT_DIR": str(root)},
        capture_output=True,
        text=True,
    )


def _violations(root: Path) -> list[dict[str, Any]]:
    path = root / ".tapps-mcp" / ".completion-gate-violations.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


@pytest.fixture
def warn_hooked(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    generate_claude_hooks(root, force_windows=False, engagement_level="medium")
    return root


# ---------------------------------------------------------------------------
# TAP-7014 — the gate is project-root scoped
# ---------------------------------------------------------------------------


def test_executed_hook_ignores_edits_outside_project_root(warn_hooked: Path) -> None:
    """A throwaway file outside the project root can never satisfy a repo gate run."""
    transcript = _write_transcript(warn_hooked, [_OUTSIDE_ROOT_FILE])

    proc = _run_warn_stop_hook(warn_hooked, transcript)

    assert proc.returncode == 0, proc.stderr
    assert _violations(warn_hooked) == []
    assert "completion-gate (warn)" not in proc.stderr


def test_executed_hook_still_gates_a_scorable_file_inside_project_root(warn_hooked: Path) -> None:
    """Negative control: the original in-project case must keep firing."""
    transcript = _write_transcript(warn_hooked, ["src/app.py"])

    proc = _run_warn_stop_hook(warn_hooked, transcript)

    assert proc.returncode == 0, proc.stderr
    entries = _violations(warn_hooked)
    assert len(entries) == 1
    assert entries[0]["files_edited"] == ["src/app.py"]


def test_executed_hook_still_gates_a_mixed_inside_and_outside_session(warn_hooked: Path) -> None:
    """An in-project scorable edit alongside an outside one still gates, and the
    outside file is not reported as part of the violation."""
    transcript = _write_transcript(warn_hooked, [_OUTSIDE_ROOT_FILE, "src/app.py"])

    proc = _run_warn_stop_hook(warn_hooked, transcript)

    assert proc.returncode == 0, proc.stderr
    entries = _violations(warn_hooked)
    assert len(entries) == 1
    assert entries[0]["files_edited"] == ["src/app.py"]


# ---------------------------------------------------------------------------
# TAP-7015 — an unresolved violation signature is not re-logged every Stop
# ---------------------------------------------------------------------------


def test_executed_hook_dedupes_an_unchanged_violation_signature(warn_hooked: Path) -> None:
    """A second Stop with the same (files, reasons) appends no new row."""
    transcript = _write_transcript(warn_hooked, ["src/app.py"])

    _run_warn_stop_hook(warn_hooked, transcript)
    proc2 = _run_warn_stop_hook(warn_hooked, transcript)

    assert proc2.returncode == 0, proc2.stderr
    assert len(_violations(warn_hooked)) == 1


def test_executed_hook_logs_again_when_the_file_set_changes(warn_hooked: Path) -> None:
    """Negative control: a changed file set is a new state and must append."""
    transcript1 = _write_transcript(warn_hooked, ["src/app.py"], name="t1.jsonl")
    _run_warn_stop_hook(warn_hooked, transcript1)

    transcript2 = _write_transcript(warn_hooked, ["src/app.py", "src/other.py"], name="t2.jsonl")
    proc2 = _run_warn_stop_hook(warn_hooked, transcript2)

    assert proc2.returncode == 0, proc2.stderr
    entries = _violations(warn_hooked)
    assert len(entries) == 2
    assert entries[0]["files_edited"] != entries[1]["files_edited"]


def test_executed_hook_logs_again_when_the_reason_set_changes(warn_hooked: Path) -> None:
    """Negative control: a changed reason set (checklist now called) is a new state."""
    transcript1 = _write_transcript(warn_hooked, ["src/app.py"], name="t1.jsonl")
    _run_warn_stop_hook(warn_hooked, transcript1)

    transcript2 = warn_hooked / "t2.jsonl"
    transcript2.write_text(
        json.dumps(
            {
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/app.py"}},
                        {"type": "tool_use", "name": "tapps_checklist", "input": {}},
                    ]
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    proc2 = _run_warn_stop_hook(warn_hooked, transcript2)

    assert proc2.returncode == 0, proc2.stderr
    entries = _violations(warn_hooked)
    assert len(entries) == 2
    assert entries[0]["reasons"] != entries[1]["reasons"]
    assert "CHECKLIST_MISSING" not in entries[1]["reasons"]
