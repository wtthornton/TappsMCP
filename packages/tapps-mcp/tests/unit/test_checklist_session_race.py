"""TAP-7850 (VAL-08) — the checklist active-session marker had no
per-Claude-session dimension.

``CallTracker.begin_session()`` unconditionally overwrote a single
project-level marker file. Two genuinely different Claude Code sessions
sharing one ``project_root`` silently clobbered each other's active
checklist session: whichever session started second stole the marker, and
the first session's own subsequent reads (which, since TAP-7849, re-read the
marker on every check) picked up the wrong session's id and lost credit for
its own recorded calls.

Fixed by keying the marker with ``CLAUDE_CODE_SESSION_ID`` (inherited by
every MCP server process Claude Code spawns) when present, so distinct
Claude sessions never share a marker file. Sibling MCP server processes for
the *same* session still share one ``CLAUDE_CODE_SESSION_ID`` and therefore
one marker file, so the TAP-6738/TAP-7849 sibling-adoption tests in
``test_checklist.py`` (``TestCrossProcessChecklistCredit`` /
``TestStaleActiveSessionCacheAcrossServers``) stay green unchanged.

Kept in its own small module rather than appended to the already
near-the-gate ``test_checklist.py`` megafile (the same class of debt as
TAP-5847); the process-simulation helpers below are duplicated in miniature
from that file's ``TestCrossProcessChecklistCredit`` rather than imported
across it, since the three packages' identically-named ``tests`` trees are
deliberately not cross-importable (see the ``pythonpath``/``consider_namespace_packages``
notes in the repo's root ``pyproject.toml``, TAP-4575).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tapps_mcp.tools.checklist import CallTracker


@pytest.fixture(autouse=True)
def _ledger(tmp_path: Path) -> Iterator[Path]:
    CallTracker.reset()
    path = tmp_path / "state" / "checklist_calls.jsonl"
    CallTracker.set_persist_path(path)
    yield path
    CallTracker.reset()
    CallTracker._persist_path = None
    CallTracker._calls.clear()


def _rebind(path: Path) -> None:
    """Simulate a fresh process binding the same project ledger."""
    CallTracker._calls.clear()
    CallTracker._window_id = None
    CallTracker._active_session_id = None
    CallTracker._adopted_window_ids = frozenset()
    CallTracker.set_persist_path(path)


def _snapshot() -> dict[str, Any]:
    return {
        "active_session_id": CallTracker._active_session_id,
        "adopted_window_ids": CallTracker._adopted_window_ids,
        "window_id": CallTracker._window_id,
        "calls": list(CallTracker._calls),
    }


def _restore(snap: dict[str, Any]) -> None:
    CallTracker._active_session_id = snap["active_session_id"]
    CallTracker._adopted_window_ids = snap["adopted_window_ids"]
    CallTracker._window_id = snap["window_id"]
    CallTracker._calls = list(snap["calls"])


class TestConcurrentSessionsDoNotClobberMarker:
    """See module docstring."""

    def test_two_distinct_claude_sessions_keep_independent_markers(
        self, _ledger: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: reproduces the two-process clobber from the
        lane doc against a scratch ``project_root``. Must fail at base
        (session A silently loses credit for its own call) and pass after
        the fix (session A keeps its own marker, unaffected by session B).
        """
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session-A")
        _rebind(_ledger)
        sid_a = CallTracker.begin_session("sess-a")
        CallTracker.record("tapps_score_file")
        assert "tapps_score_file" in CallTracker.get_called_tools()
        session_a_state = _snapshot()

        # A genuinely different Claude Code session (different
        # CLAUDE_CODE_SESSION_ID) shares the same project_root and starts
        # its own checklist session, as a concurrent `claude` process would.
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session-B")
        _rebind(_ledger)
        sid_b = CallTracker.begin_session("sess-b")
        CallTracker.record("tapps_quality_gate")
        assert sid_b != sid_a

        # Back to session A's own environment and in-memory state -- no
        # rebind, exactly as a real long-lived server process would sit
        # between two tool calls.
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session-A")
        _restore(session_a_state)

        assert CallTracker._active_session_id == sid_a, (
            "session A's own active id was clobbered by session B's begin_session()"
        )
        assert "tapps_score_file" in CallTracker.get_called_tools(), (
            "session A lost credit for its own recorded call after session B minted"
        )
        assert "tapps_quality_gate" not in CallTracker.get_called_tools(), (
            "session A must not pick up session B's unrelated call"
        )

        marker_a = _ledger.parent / "checklist_active_session.claude-session-A"
        marker_b = _ledger.parent / "checklist_active_session.claude-session-B"
        assert marker_a.is_file()
        assert marker_b.is_file()
        assert marker_a.read_text(encoding="utf-8").splitlines()[0] == sid_a
        assert marker_b.read_text(encoding="utf-8").splitlines()[0] == sid_b

    def test_single_session_mint_and_read_cycle_unchanged(
        self, _ledger: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive control: a solo session's mint-then-read cycle is
        unaffected by per-session marker keying."""
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session-solo")
        _rebind(_ledger)
        sid = CallTracker.begin_session()
        CallTracker.record("tapps_score_file")

        assert CallTracker.get_active_checklist_session_id() == sid
        assert "tapps_score_file" in CallTracker.get_called_tools()
