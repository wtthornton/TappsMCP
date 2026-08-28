"""TAP-6586 — the completion gate stops failing open and stops passing vacuously.

Three defects, one issue:

1. ``CallTracker._filtered_calls`` read a *project-level* ledger. With no active
   session it returned every record ever persisted; with one, ``or not
   c.session_id`` adopted every un-stamped row, so a prior session's calls
   satisfied the current one.
2. ``tapps_checklist(auto_run=True)`` credited its required tools even when the
   run it triggered validated **0 files** — the code detected that case and only
   narrated it.
3. The remediation was opt-in, which made passing the flag the same skippable
   step the gate exists to catch.

Every permissive assertion here is paired with its negative control: a stricter
gate that also blocks honest work is not a fix.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from tapps_mcp.distribution.doctor_pipeline import (
    _count_completion_gate_violations_24h,
    _detect_completion_gate_mode,
)
from tapps_mcp.distribution.doctor_telemetry import check_completion_gate_violations
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS_BLOCKING,
    scorable_extensions,
)
from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks
from tapps_mcp.tools import nothing_to_gate as ntg
from tapps_mcp.tools.checklist import CallTracker

# ---------------------------------------------------------------------------
# 1. Session scoping — the ledger is project-level, the checklist is not
# ---------------------------------------------------------------------------


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    """A hermetic call ledger. Never the developer's real one."""
    CallTracker.reset()
    path = tmp_path / "state" / "checklist_calls.jsonl"
    CallTracker.set_persist_path(path)
    yield path
    CallTracker.reset()
    CallTracker._persist_path = None
    CallTracker._calls.clear()


def _evaluate(project_root: Path | None = None) -> Any:
    return CallTracker.evaluate("feature", engagement_level="medium", project_root=project_root)


def _rebind(path: Path) -> None:
    """Simulate a fresh MCP process binding the same project ledger."""
    CallTracker._calls.clear()
    CallTracker._window_id = None
    CallTracker._active_session_id = None
    CallTracker._adopted_window_ids = frozenset()
    CallTracker.set_persist_path(path)


def test_unattributed_rows_do_not_satisfy_a_later_session(ledger: Path) -> None:
    """Leak (a): rows with an empty ``session_id`` belonged to whoever asked.

    This is the case that PASSED before TAP-6586 — ``or not c.session_id`` let
    a prior session's un-stamped rows complete session B — and must now fail.
    """
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        "".join(
            json.dumps(
                {"tool_name": t, "timestamp": time.time(), "session_id": "", "success": True}
            )
            + "\n"
            for t in ("tapps_score_file", "tapps_quality_gate")
        ),
        encoding="utf-8",
    )
    _rebind(ledger)
    CallTracker.begin_session("sess-b")

    result = _evaluate()

    assert result.complete is False
    assert set(result.missing_required) >= {"tapps_score_file", "tapps_quality_gate"}
    assert result.total_calls == 0


def test_prior_session_rows_do_not_satisfy_with_no_active_session(ledger: Path) -> None:
    """Leak (b): ``_active_session_id is None`` returned the entire ledger.

    This is the ``total_calls: 175`` observation — a checklist reading a
    project-level ledger and reporting tools the session never invoked.
    """
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        "".join(
            json.dumps(
                {
                    "tool_name": t,
                    "timestamp": time.time(),
                    "session_id": "sess-old",
                    "success": True,
                }
            )
            + "\n"
            for t in ("tapps_score_file", "tapps_quality_gate")
        ),
        encoding="utf-8",
    )
    _rebind(ledger)
    assert CallTracker.get_active_checklist_session_id() is None

    result = _evaluate()

    assert result.complete is False
    assert result.total_calls == 0
    assert "tapps_score_file" not in result.called


def test_a_sessions_own_calls_still_satisfy_it(ledger: Path) -> None:
    """Negative control: closing the leaks must not starve a real session."""
    CallTracker.begin_session("sess-a")
    CallTracker.record("tapps_score_file")
    CallTracker.record("tapps_quality_gate")

    result = _evaluate()

    assert result.complete is True
    assert result.total_calls == 2


def test_pre_session_calls_are_still_adopted(ledger: Path) -> None:
    """Regression guard: ``begin_session`` adoption is legitimate and stays.

    Agents invoke tools before ``tapps_session_start``; dropping those records
    would trade one dishonest verdict for another.
    """
    CallTracker.record("tapps_score_file")
    CallTracker.begin_session()
    CallTracker.record("tapps_quality_gate")

    result = _evaluate()

    assert result.complete is True
    assert {"tapps_score_file", "tapps_quality_gate"} <= set(result.called)


def test_adoption_survives_a_rebind_of_the_same_ledger(ledger: Path) -> None:
    """A server restart mid-session keeps the adopted pre-session window."""
    CallTracker.record("tapps_score_file")
    sid = CallTracker.begin_session()
    CallTracker.record("tapps_quality_gate")

    CallTracker._calls.clear()
    CallTracker.set_persist_path(ledger)

    assert CallTracker.get_active_checklist_session_id() == sid
    assert _evaluate().complete is True


def test_a_second_session_does_not_inherit_the_first_window(ledger: Path) -> None:
    """Two sessions, one process: B must not be satisfied by A's evidence."""
    CallTracker.record("tapps_score_file")
    CallTracker.begin_session("sess-a")
    CallTracker.record("tapps_quality_gate")
    assert _evaluate().complete is True

    CallTracker.begin_session("sess-b")

    result = _evaluate()
    assert result.complete is False
    assert result.total_calls == 0


def test_only_the_first_boundary_adopts(ledger: Path) -> None:
    CallTracker.record("tapps_score_file")
    CallTracker.begin_session("sess-a")
    assert CallTracker._adopted_window_ids
    CallTracker.begin_session("sess-b")
    assert CallTracker._adopted_window_ids == frozenset()


def test_marker_carries_the_adopted_windows(ledger: Path) -> None:
    CallTracker.record("tapps_score_file")
    sid = CallTracker.begin_session("sess-a")
    marker = ledger.parent / "checklist_active_session"

    lines = marker.read_text(encoding="utf-8").splitlines()

    assert lines[0] == sid
    assert lines[1:] == sorted(CallTracker._adopted_window_ids)


def test_single_line_marker_from_an_older_build_still_loads(ledger: Path) -> None:
    """Markers written before TAP-6586 parse as "active id, nothing adopted"."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    (ledger.parent / "checklist_active_session").write_text("legacy-sid", encoding="utf-8")
    _rebind(ledger)

    assert CallTracker.get_active_checklist_session_id() == "legacy-sid"
    assert CallTracker._adopted_window_ids == frozenset()


# ---------------------------------------------------------------------------
# 2. An auto-run that validated 0 files credits nothing
# ---------------------------------------------------------------------------


class _Result:
    """Minimal stand-in for ChecklistResult's mutable verdict fields."""

    def __init__(self) -> None:
        self.missing_required: list[str] = []
        self.missing_required_hints: list[Any] = []
        self.satisfied_required_tools = ["tapps_score_file", "tapps_quality_gate"]
        self.not_applicable_tools: list[str] = []
        self.complete = True


def test_revoking_an_empty_autorun_restores_the_gap() -> None:
    from tapps_mcp.server_checklist_tools import _revoke_uncredited_autorun

    result = _Result()
    revoked = _revoke_uncredited_autorun(result, {"tapps_score_file", "tapps_quality_gate"})

    assert revoked == ["tapps_quality_gate", "tapps_score_file"]
    assert result.complete is False
    assert set(result.missing_required) == {"tapps_score_file", "tapps_quality_gate"}
    assert result.satisfied_required_tools == []
    assert [h.tool for h in result.missing_required_hints] == sorted(result.missing_required)


def test_revoking_leaves_tap_6606_not_applicable_tools_alone() -> None:
    """0 files is the honest answer when there was nothing to gate (#308)."""
    from tapps_mcp.server_checklist_tools import _revoke_uncredited_autorun

    result = _Result()
    result.not_applicable_tools = ["tapps_score_file", "tapps_quality_gate"]

    assert _revoke_uncredited_autorun(result, {"tapps_score_file", "tapps_quality_gate"}) == []
    assert result.complete is True
    assert result.missing_required == []


@pytest.mark.asyncio
async def test_autorun_with_zero_files_validated_is_not_a_pass(
    ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tapps_mcp import server_checklist_tools as sct

    async def _fake_validate(**_kwargs: Any) -> dict[str, Any]:
        CallTracker.record("tapps_validate_changed")
        return {"success": True, "data": {"files_validated": 0, "all_gates_passed": False}}

    monkeypatch.setattr(
        "tapps_mcp.server_pipeline_tools.tapps_validate_changed", _fake_validate, raising=False
    )
    CallTracker.begin_session("sess-a")
    before = _evaluate()
    assert before.complete is False

    result, auto = await sct._run_auto_run(True, before, _evaluate, _Settings())

    assert auto["validate_changed"]["files_validated"] == 0
    assert auto["validate_changed"]["credited"] is False
    assert "tapps_score_file" in auto["validate_changed"]["uncredited_tools"]
    assert result.complete is False
    assert "tapps_score_file" in result.missing_required


@pytest.mark.asyncio
async def test_autorun_that_validated_files_does_credit(
    ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: real evidence still completes the checklist."""
    from tapps_mcp import server_checklist_tools as sct

    async def _fake_validate(**_kwargs: Any) -> dict[str, Any]:
        CallTracker.record("tapps_validate_changed")
        return {"success": True, "data": {"files_validated": 3, "all_gates_passed": True}}

    monkeypatch.setattr(
        "tapps_mcp.server_pipeline_tools.tapps_validate_changed", _fake_validate, raising=False
    )
    CallTracker.begin_session("sess-a")
    before = _evaluate()

    result, auto = await sct._run_auto_run(True, before, _evaluate, _Settings())

    assert auto["validate_changed"]["files_validated"] == 3
    assert "credited" not in auto["validate_changed"]
    assert result.complete is True


@pytest.mark.asyncio
async def test_autorun_that_raised_credits_nothing(
    ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tapps_mcp import server_checklist_tools as sct

    async def _boom(**_kwargs: Any) -> dict[str, Any]:
        CallTracker.record("tapps_validate_changed")
        raise RuntimeError("checker unavailable")

    monkeypatch.setattr(
        "tapps_mcp.server_pipeline_tools.tapps_validate_changed", _boom, raising=False
    )
    CallTracker.begin_session("sess-a")
    before = _evaluate()

    result, auto = await sct._run_auto_run(True, before, _evaluate, _Settings())

    assert auto["validate_changed"]["success"] is False
    assert auto["validate_changed"]["credited"] is False
    assert result.complete is False


class _Settings:
    quality_preset = "standard"


# ---------------------------------------------------------------------------
# 3. The remediation is the default path, not a flag
# ---------------------------------------------------------------------------


def test_auto_run_defaults_to_true() -> None:
    import inspect

    from tapps_mcp.server_checklist_tools import tapps_checklist

    assert inspect.signature(tapps_checklist).parameters["auto_run"].default is True


@pytest.mark.asyncio
async def test_checklist_auto_runs_without_being_asked(
    ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate path calls ``tapps_checklist()`` — no ``auto_run=True``."""
    from tapps_mcp.server_checklist_tools import tapps_checklist

    calls: list[str] = []

    async def _fake_validate(**_kwargs: Any) -> dict[str, Any]:
        calls.append("validate")
        CallTracker.record("tapps_validate_changed")
        return {"success": True, "data": {"files_validated": 2, "all_gates_passed": True}}

    monkeypatch.setattr(
        "tapps_mcp.server_pipeline_tools.tapps_validate_changed", _fake_validate, raising=False
    )
    CallTracker.begin_session("sess-a")

    resp = await tapps_checklist(task_type="feature", output_format="json")

    assert calls == ["validate"]
    assert resp["data"]["auto_run_results"]["validate_changed"]["files_validated"] == 2


# ---------------------------------------------------------------------------
# 4. doctor reports the 24 h count, the way it does for the cache gate
# ---------------------------------------------------------------------------


def _write_violations(root: Path, timestamps: list[float]) -> Path:
    path = root / ".tapps-mcp" / ".completion-gate-violations.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps({"ts": int(ts), "mode": "warn", "reasons": ["CHECKLIST_MISSING"]}) + "\n"
            for ts in timestamps
        ),
        encoding="utf-8",
    )
    return path


def test_counter_ignores_entries_older_than_24h(tmp_path: Path) -> None:
    now = time.time()
    _write_violations(tmp_path, [now - 60, now - 3600, now - 25 * 3600])

    assert _count_completion_gate_violations_24h(tmp_path) == 2


def test_counter_is_zero_without_a_log(tmp_path: Path) -> None:
    assert _count_completion_gate_violations_24h(tmp_path) == 0


def test_counter_skips_unparseable_lines(tmp_path: Path) -> None:
    path = _write_violations(tmp_path, [time.time()])
    with path.open("a", encoding="utf-8") as fh:
        fh.write("not json\n")
        fh.write(json.dumps({"no_ts": 1}) + "\n")
        fh.write(json.dumps({"ts": "not-a-number"}) + "\n")
        fh.write("\n")

    assert _count_completion_gate_violations_24h(tmp_path) == 1


def test_doctor_reports_the_count(tmp_path: Path) -> None:
    _write_violations(tmp_path, [time.time(), time.time() - 100])

    result = check_completion_gate_violations(tmp_path)

    assert result.ok is True
    assert "2 completion-gate violations in 24h" in result.message
    assert "/tapps-finish-task" in result.detail


def test_doctor_message_is_quiet_when_clean(tmp_path: Path) -> None:
    result = check_completion_gate_violations(tmp_path)

    assert "0 completion-gate violations in 24h" in result.message
    assert not result.detail


def test_mode_detection_reads_the_deployed_hook(tmp_path: Path) -> None:
    assert _detect_completion_gate_mode(tmp_path) == "off"

    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    stop = hooks / "tapps-stop.sh"

    stop.write_text(CLAUDE_HOOK_SCRIPTS["tapps-stop.sh"], encoding="utf-8")
    assert _detect_completion_gate_mode(tmp_path) == "warn"

    stop.write_text(CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-stop.sh"], encoding="utf-8")
    assert _detect_completion_gate_mode(tmp_path) == "block"

    stop.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    assert _detect_completion_gate_mode(tmp_path) == "off"


# ---------------------------------------------------------------------------
# 5. The generated stop hook — executed, not read
# ---------------------------------------------------------------------------


def test_stop_hook_extension_list_matches_the_scorer() -> None:
    """The gate's "did this session touch code?" list may not drift again.

    ``.mjs`` / ``.cjs`` were missing from the warn variant while the blocking
    variant had them, so a session editing only those files never tripped it.
    """
    body = CLAUDE_HOOK_SCRIPTS["tapps-stop.sh"]
    line = next(ln for ln in body.splitlines() if ln.startswith("needs_gate="))

    for ext in scorable_extensions():
        assert f"'{ext}'" in line, f"{ext} missing from the completion gate"


def test_blocking_stop_hook_extension_regex_matches_the_scorer() -> None:
    body = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-stop.sh"]

    for ext in scorable_extensions():
        assert f"{ext.lstrip('.')}|" in body or f"{ext.lstrip('.')})" in body


def _write_transcript(root: Path, edited: list[str]) -> Path:
    path = root / "transcript.jsonl"
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


def test_executed_hook_logs_a_violation_for_an_mjs_only_session(warn_hooked: Path) -> None:
    """The fail-open hole: ``.mjs`` edits used to escape the gate entirely."""
    transcript = _write_transcript(warn_hooked, ["src/app.mjs", "src/util.cjs"])

    proc = _run_warn_stop_hook(warn_hooked, transcript)

    assert proc.returncode == 0, proc.stderr
    entries = _violations(warn_hooked)
    assert len(entries) == 1
    assert "CHECKLIST_MISSING" in entries[0]["reasons"]
    assert "completion-gate (warn)" in proc.stderr


def test_executed_hook_logs_nothing_for_a_markdown_and_shell_session(warn_hooked: Path) -> None:
    """The 2026-08-27 shape: prose plus one shell script is not a code session."""
    transcript = _write_transcript(warn_hooked, ["docs/NOTES.md", "scripts/deploy.sh"])

    proc = _run_warn_stop_hook(warn_hooked, transcript)

    assert proc.returncode == 0, proc.stderr
    assert _violations(warn_hooked) == []
    assert "completion-gate (warn)" not in proc.stderr


def test_executed_hook_still_logs_for_a_python_session(warn_hooked: Path) -> None:
    """Negative control: the original case must keep firing."""
    transcript = _write_transcript(warn_hooked, ["src/app.py"])

    _run_warn_stop_hook(warn_hooked, transcript)

    entries = _violations(warn_hooked)
    assert len(entries) == 1
    assert entries[0]["files_edited"] == ["src/app.py"]


def test_executed_hook_and_the_doctor_counter_agree(warn_hooked: Path) -> None:
    """End to end: what the hook writes is what doctor reports."""
    transcript = _write_transcript(warn_hooked, ["src/app.mjs"])

    _run_warn_stop_hook(warn_hooked, transcript)

    assert _count_completion_gate_violations_24h(warn_hooked) == 1
    assert "1 completion-gate violations in 24h" in (
        check_completion_gate_violations(warn_hooked).message
    )


# ---------------------------------------------------------------------------
# 6. TAP-6606 interaction — N/A is not a violation, and that already holds
# ---------------------------------------------------------------------------


def test_not_applicable_is_not_a_violation(tmp_path: Path, ledger: Path) -> None:
    """Already satisfied by #308; asserted here so this lane cannot regress it."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "README.md").write_text("# base\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, check=True)
    (root / "README.md").write_text("# base\nmore prose\n", encoding="utf-8")
    ntg.record(root, ntg.census(root))

    CallTracker.begin_session("sess-a")
    CallTracker.record("tapps_validate_changed")
    result = CallTracker.evaluate("review", engagement_level="medium", project_root=root)

    assert result.complete is True
    assert result.nothing_to_gate is True
    assert "tapps_security_scan" in result.not_applicable_tools
