"""Session notes - lightweight key-value store per MCP session.

In-memory for speed, persisted to JSON for crash recovery.
Notes are scoped to project_root to prevent cross-project leakage.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from tapps_mcp.project.models import SessionNote, SessionNotesSnapshot

logger = structlog.get_logger(__name__)


def _machine_identity(project_root: Path) -> tuple[str, str, str]:
    """Return (host, os, cwd) used to gate cross-machine session recovery.

    TAP-1377: session-state files written on a different machine or for a
    different project root must not be loaded silently.
    """
    try:
        host = socket.gethostname()
    except OSError:
        host = "unknown"
    return host, sys.platform, str(project_root)


class SessionNoteStore:
    """In-memory note store with JSON persistence.

    Each instance is scoped to a *project_root*; a new *session_id* is
    generated on construction.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.session_id = uuid.uuid4().hex[:12]
        self.session_started = datetime.now(tz=UTC).isoformat()
        self._notes: dict[str, SessionNote] = {}
        self._lock = threading.Lock()

        # Persistence directory
        self._store_dir = project_root / ".tapps-mcp" / "sessions"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self._store_dir / f"{self.session_id}.json"

        # Attempt to recover notes from a previous crash (latest file)
        self._recover_latest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, key: str, value: str) -> SessionNote:
        """Store or update a note."""
        now = datetime.now(tz=UTC).isoformat()
        with self._lock:
            existing = self._notes.get(key)
            note = SessionNote(
                key=key,
                value=value,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            self._notes[key] = note
        self._persist()
        return note

    def get(self, key: str) -> SessionNote | None:
        """Retrieve a single note by key."""
        with self._lock:
            return self._notes.get(key)

    def list_all(self) -> list[SessionNote]:
        """Return all notes for the current session."""
        with self._lock:
            return list(self._notes.values())

    def clear(self, key: str | None = None) -> int:
        """Clear a single note or all notes.

        Returns:
            Number of notes cleared.
        """
        with self._lock:
            if key is not None:
                if key in self._notes:
                    del self._notes[key]
                    self._persist()
                    return 1
                return 0
            count = len(self._notes)
            self._notes.clear()
        self._persist()
        return count

    @property
    def note_count(self) -> int:
        return len(self._notes)

    def snapshot(self) -> SessionNotesSnapshot:
        """Return a serialisable snapshot."""
        host, os_name, cwd = _machine_identity(self.project_root)
        return SessionNotesSnapshot(
            session_id=self.session_id,
            project_root=str(self.project_root),
            notes=dict(self._notes),
            session_started=self.session_started,
            host=host,
            os=os_name,
            cwd=cwd,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Atomic write to JSON (tempfile + os.replace)."""
        data = self.snapshot().model_dump()
        try:
            fd, tmp = tempfile.mkstemp(dir=str(self._store_dir), suffix=".tmp", prefix="session_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                Path(tmp).replace(self._store_path)
            except OSError:
                # Clean up temp on failure
                with contextlib.suppress(OSError):
                    Path(tmp).unlink()
                raise
        except OSError:
            logger.warning("session_notes_persist_failed", session_id=self.session_id)

    def _recover_latest(self) -> None:
        """Try to load notes from the most recent session file (crash recovery).

        TAP-1377: validates host/os/cwd against the current machine before
        loading. Mismatched files (cross-machine, cross-project, or legacy
        files missing the identity fields) are skipped — never deleted, so
        they remain available as debug evidence.
        """
        if not self._store_dir.exists():
            return
        try:
            files = sorted(
                self._store_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not files:
                return
            latest = files[0]
            raw = json.loads(latest.read_text(encoding="utf-8"))
            snap = SessionNotesSnapshot.model_validate(raw)

            current_host, current_os, current_cwd = _machine_identity(self.project_root)

            # Legacy file: identity fields missing → discard with one-time
            # migration log.
            if snap.host is None or snap.os is None or snap.cwd is None:
                logger.warning(
                    "session_notes_recovery_legacy_discarded",
                    file=str(latest),
                    session_id=snap.session_id,
                    reason="missing_machine_identity",
                )
                return

            if (
                snap.host != current_host
                or snap.os != current_os
                or snap.cwd != current_cwd
            ):
                logger.warning(
                    "session_notes_recovery_mismatch_discarded",
                    file=str(latest),
                    session_id=snap.session_id,
                    expected_host=current_host,
                    expected_os=current_os,
                    expected_cwd=current_cwd,
                    found_host=snap.host,
                    found_os=snap.os,
                    found_cwd=snap.cwd,
                )
                return

            # Defence-in-depth: also check the legacy project_root field.
            if snap.project_root != str(self.project_root):
                logger.warning(
                    "session_notes_recovery_project_root_mismatch",
                    file=str(latest),
                    expected=str(self.project_root),
                    found=snap.project_root,
                )
                return

            self._notes = snap.notes
            self.session_id = snap.session_id
            self.session_started = snap.session_started
            self._store_path = self._store_dir / f"{self.session_id}.json"
            logger.info(
                "session_notes_recovered",
                session_id=self.session_id,
                note_count=len(self._notes),
            )
        except Exception as e:
            logger.debug("session_notes_recovery_skipped", reason=str(e), exc_info=True)

    # ------------------------------------------------------------------
    # Convenience dict for tool response
    # ------------------------------------------------------------------

    def metadata(self) -> dict[str, Any]:
        """Return metadata suitable for embedding in a tool response."""
        return {
            "session_id": self.session_id,
            "session_started": self.session_started,
            "note_count": self.note_count,
        }
