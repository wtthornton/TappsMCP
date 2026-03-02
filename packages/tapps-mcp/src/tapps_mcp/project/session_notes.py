"""Session notes - lightweight key-value store per MCP session.

In-memory for speed, persisted to JSON for crash recovery.
Notes are scoped to project_root to prevent cross-project leakage.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from tapps_mcp.project.models import SessionNote, SessionNotesSnapshot

logger = structlog.get_logger(__name__)


class SessionNoteStore:
    """In-memory note store with JSON persistence.

    Each instance is scoped to a *project_root*; a new *session_id* is
    generated on construction.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.session_id = uuid.uuid4().hex[:12]
        self.session_started = datetime.now(tz=timezone.utc).isoformat()
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
        now = datetime.now(tz=timezone.utc).isoformat()
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
        return SessionNotesSnapshot(
            session_id=self.session_id,
            project_root=str(self.project_root),
            notes=dict(self._notes),
            session_started=self.session_started,
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
                os.replace(tmp, str(self._store_path))
            except OSError:
                # Clean up temp on failure
                with contextlib.suppress(OSError):
                    Path(tmp).unlink()
                raise
        except OSError:
            logger.warning("session_notes_persist_failed", session_id=self.session_id)

    def _recover_latest(self) -> None:
        """Try to load notes from the most recent session file (crash recovery)."""
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
            # Only recover if same project root
            if snap.project_root == str(self.project_root):
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
