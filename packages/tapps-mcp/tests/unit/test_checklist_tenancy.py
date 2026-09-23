"""CallTracker multi-tenancy under a shared HTTP fleet process (TAP-7948).

``CallTracker`` is a flat, process-wide ClassVar-backed singleton, but this
server serves MANY projects over shared HTTP (``X-Tapps-Project-Root`` per
request). ``server._record_call`` used to bind the persist path once per
process lifetime (the first project to call wins forever); this file proves
the replacement -- resolve-and-rebind on every call, without ever discarding
another project's not-yet-flushed state.

Every reproduction here uses SCRATCH ``tmp_path`` directories for "the two
projects" -- never a shared/live tree -- and stays deterministic: sequential
calls in one process are sufficient to reproduce the original loss: no real
concurrency is required or exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_core.http.request_context import (
    mark_http_request,
    reset_http_request,
    reset_request_project_root,
    set_request_project_root,
)
from tapps_mcp.server import _record_call
from tapps_mcp.tools.checklist import CallTracker
from tapps_mcp.tools.usage import compute_gaps


def _ledger_path(project_root: Path) -> Path:
    return project_root / ".tapps-mcp" / "sessions" / "checklist_calls.jsonl"


def _simulate_fleet_request(project_root: Path, tool_name: str) -> None:
    """Record one tool call as an HTTP fleet request carrying
    ``X-Tapps-Project-Root: project_root`` would -- via the real production
    entry point (``server._record_call``), which resolves ``load_settings()``
    with no explicit override so it goes through the same
    ``http_request_root_override`` path a live request does.
    """
    _reset_settings_cache()
    http_token = mark_http_request()
    root_token = set_request_project_root(project_root)
    try:
        _record_call(tool_name)
    finally:
        reset_request_project_root(root_token)
        reset_http_request(http_token)
        _reset_settings_cache()


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:
    CallTracker.reset()


class TestCrossProjectIsolation:
    """Sequential requests for different projects must never cross-contaminate.

    Run this class against the UNFIXED ``checklist.py``/``server.py`` (revert
    ``git checkout -- packages/tapps-mcp/src/tapps_mcp/tools/checklist.py
    packages/tapps-mcp/src/tapps_mcp/server.py`` and re-run) to see it fail
    red: the one-shot bind means every call after the first lands in
    project A's own file regardless of which project it names, and project
    B's ledger is never even created.
    """

    def test_two_projects_never_cross_contaminate(self, tmp_path: Path) -> None:
        project_a = tmp_path / "project_a"
        project_b = tmp_path / "project_b"
        project_a.mkdir()
        project_b.mkdir()

        _simulate_fleet_request(project_a, "tapps_session_start")
        _simulate_fleet_request(project_b, "tapps_quick_check")
        _simulate_fleet_request(project_a, "tapps_checklist")

        ledger_a_path = _ledger_path(project_a)
        ledger_b_path = _ledger_path(project_b)

        assert ledger_a_path.is_file(), "project A never got its own ledger file"
        assert ledger_b_path.is_file(), (
            "project B never got its own ledger file -- its call was silently "
            "absorbed into whichever project bound first"
        )

        ledger_a = ledger_a_path.read_text(encoding="utf-8")
        ledger_b = ledger_b_path.read_text(encoding="utf-8")

        assert "tapps_session_start" in ledger_a
        assert "tapps_checklist" in ledger_a
        assert "tapps_quick_check" not in ledger_a, (
            "project A's persist file contains project B's record -- the "
            f"one-shot/first-project-wins bind leaked across tenants: {ledger_a!r}"
        )
        assert "tapps_quick_check" in ledger_b
        assert "tapps_session_start" not in ledger_b, (
            f"project B's persist file contains project A's record: {ledger_b!r}"
        )
        assert "tapps_checklist" not in ledger_b

    def test_pre_session_window_survives_an_intervening_foreign_bind(self, tmp_path: Path) -> None:
        """A's pre-session (no ``begin_session`` yet) window id must not be
        discarded by an intervening rebind to B and back -- the exact hazard
        the naive "just remove the one-shot guard, keep the unconditional
        ``cls._calls.clear()``" fix would reintroduce (see checklist.py's
        ``_bind_locked`` docstring). Two calls to A around one call to B are
        enough to prove it: A's second call must still count as the same
        session/window as its first once evaluated.
        """
        project_a = tmp_path / "project_a"
        project_b = tmp_path / "project_b"
        project_a.mkdir()
        project_b.mkdir()

        _simulate_fleet_request(project_a, "tapps_lookup_docs")
        _simulate_fleet_request(project_b, "tapps_quick_check")
        _simulate_fleet_request(project_a, "tapps_score_file")

        called = CallTracker.get_called_tools(project_root=project_a)
        assert "tapps_lookup_docs" in called, (
            "project A's pre-session call was orphaned by the intervening "
            f"rebind to project B; called={called!r}"
        )
        assert "tapps_score_file" in called


class TestSiblingServerSharedProject:
    """A session_start on one fleet server is counted by every sibling
    serving the SAME project -- asserted against the HTTP transport shape
    (two ``X-Tapps-Project-Root``-carrying calls into the same process, not
    only a shared tmp fixture)."""

    def test_second_request_sees_first_requests_session_start(self, tmp_path: Path) -> None:
        project = tmp_path / "shared_project"
        project.mkdir()

        _simulate_fleet_request(project, "tapps_session_start")
        # A second, independent "request" -- as a sibling server (nlt-memory,
        # nlt-release-ship, ...) serving the SAME project would present.
        _simulate_fleet_request(project, "tapps_quick_check")

        called = CallTracker.get_called_tools(project_root=project)
        assert "tapps_session_start" in called
        assert "tapps_quick_check" in called


class TestNegativeControl:
    """A session that genuinely never calls session_start still reports the
    gap -- proving the isolation fix does not accidentally manufacture false
    credit or false silence."""

    def test_never_called_session_start_reports_skip(self, tmp_path: Path) -> None:
        project = tmp_path / "never_started"
        project.mkdir()

        _simulate_fleet_request(project, "tapps_quick_check")

        report = compute_gaps(project)
        assert "session_start_skipped" in report["gaps"]

    def test_calling_session_start_clears_the_gap(self, tmp_path: Path) -> None:
        project = tmp_path / "did_start"
        project.mkdir()

        _simulate_fleet_request(project, "tapps_session_start")
        _simulate_fleet_request(project, "tapps_quick_check")

        report = compute_gaps(project)
        assert "session_start_skipped" not in report["gaps"]


class TestMarkerThreeStates:
    """An absent, empty, or unreadable ``checklist_active_session`` marker
    must be reported as three DISTINCT states rather than all silently
    falling back to the process window id (TAP-7948)."""

    def _bind(self, project: Path) -> None:
        ledger = _ledger_path(project)
        CallTracker.set_persist_path(ledger)

    def test_absent_marker(self, tmp_path: Path) -> None:
        self._bind(tmp_path)
        CallTracker.get_active_checklist_session_id()
        assert CallTracker.get_marker_state() == "absent"

    def test_empty_marker(self, tmp_path: Path) -> None:
        self._bind(tmp_path)
        marker = CallTracker._active_session_marker()
        assert marker is not None
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("", encoding="utf-8")

        self._bind(tmp_path)  # force a reload now that the marker exists
        assert CallTracker.get_marker_state() == "empty"

    def test_unreadable_marker(self, tmp_path: Path) -> None:
        self._bind(tmp_path)
        marker = CallTracker._active_session_marker()
        assert marker is not None
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("some-session-id\n", encoding="utf-8")
        marker.chmod(0o000)
        try:
            self._bind(tmp_path)
            assert CallTracker.get_marker_state() == "unreadable"
        finally:
            marker.chmod(0o644)

    def test_present_marker(self, tmp_path: Path) -> None:
        self._bind(tmp_path)
        marker = CallTracker._active_session_marker()
        assert marker is not None
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("some-session-id\n", encoding="utf-8")

        self._bind(tmp_path)
        assert CallTracker.get_marker_state() == "present"


class TestSingleProjectPositiveControl:
    """A single-project run must persist exactly as it did before this fix --
    one project, one process, records land in that project's file."""

    def test_single_project_unchanged(self, tmp_path: Path) -> None:
        project = tmp_path / "solo"
        project.mkdir()

        _simulate_fleet_request(project, "tapps_session_start")
        _simulate_fleet_request(project, "tapps_lookup_docs")
        _simulate_fleet_request(project, "tapps_quality_gate")

        ledger = _ledger_path(project).read_text(encoding="utf-8")
        lines = [json.loads(ln) for ln in ledger.strip().splitlines()]
        tool_names = {row["tool_name"] for row in lines}
        assert tool_names == {"tapps_session_start", "tapps_lookup_docs", "tapps_quality_gate"}

        called = CallTracker.get_called_tools(project_root=project)
        assert called == tool_names
