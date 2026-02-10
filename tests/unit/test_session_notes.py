"""Unit tests for tapps_mcp.project.session_notes — SessionNoteStore."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from tapps_mcp.project.models import SessionNote, SessionNotesSnapshot
from tapps_mcp.project.session_notes import SessionNoteStore


class TestSessionNoteStoreCRUD:
    """Basic CRUD operations on SessionNoteStore."""

    @pytest.fixture()
    def store(self, tmp_path: Path) -> SessionNoteStore:
        return SessionNoteStore(project_root=tmp_path)

    # -- save -----------------------------------------------------------

    def test_save_creates_note(self, store: SessionNoteStore) -> None:
        note = store.save("arch", "microservices")
        assert isinstance(note, SessionNote)
        assert note.key == "arch"
        assert note.value == "microservices"

    def test_save_sets_timestamps(self, store: SessionNoteStore) -> None:
        note = store.save("lang", "python")
        assert note.created_at != ""
        assert note.updated_at != ""
        # Both timestamps should be ISO-8601 with timezone info
        assert "T" in note.created_at
        assert "T" in note.updated_at

    def test_save_updates_existing(self, store: SessionNoteStore) -> None:
        first = store.save("db", "postgres")
        original_created = first.created_at

        # Small delay so updated_at differs
        time.sleep(0.01)
        second = store.save("db", "mysql")

        assert second.value == "mysql"
        assert second.created_at == original_created, "created_at must not change on update"
        assert second.updated_at >= original_created

    # -- get ------------------------------------------------------------

    def test_get_existing_key(self, store: SessionNoteStore) -> None:
        store.save("framework", "fastapi")
        result = store.get("framework")
        assert result is not None
        assert result.key == "framework"
        assert result.value == "fastapi"

    def test_get_missing_key(self, store: SessionNoteStore) -> None:
        assert store.get("nonexistent") is None

    # -- list_all -------------------------------------------------------

    def test_list_all_empty(self, store: SessionNoteStore) -> None:
        assert store.list_all() == []

    def test_list_all_with_notes(self, store: SessionNoteStore) -> None:
        store.save("a", "1")
        store.save("b", "2")
        store.save("c", "3")
        notes = store.list_all()
        assert len(notes) == 3
        keys = {n.key for n in notes}
        assert keys == {"a", "b", "c"}

    # -- clear ----------------------------------------------------------

    def test_clear_single_key(self, store: SessionNoteStore) -> None:
        store.save("keep", "yes")
        store.save("drop", "yes")
        removed = store.clear("drop")
        assert removed == 1
        assert store.get("drop") is None
        assert store.get("keep") is not None

    def test_clear_missing_key(self, store: SessionNoteStore) -> None:
        removed = store.clear("ghost")
        assert removed == 0

    def test_clear_all(self, store: SessionNoteStore) -> None:
        store.save("x", "1")
        store.save("y", "2")
        store.save("z", "3")
        removed = store.clear()
        assert removed == 3
        assert store.list_all() == []
        assert store.note_count == 0

    # -- note_count -----------------------------------------------------

    def test_note_count(self, store: SessionNoteStore) -> None:
        assert store.note_count == 0
        store.save("a", "1")
        assert store.note_count == 1
        store.save("b", "2")
        assert store.note_count == 2
        store.clear("a")
        assert store.note_count == 1
        store.clear()
        assert store.note_count == 0


class TestSessionMetadata:
    """Session identity and metadata helpers."""

    @pytest.fixture()
    def store(self, tmp_path: Path) -> SessionNoteStore:
        return SessionNoteStore(project_root=tmp_path)

    def test_session_id_is_set(self, store: SessionNoteStore) -> None:
        assert isinstance(store.session_id, str)
        assert len(store.session_id) == 12
        assert re.fullmatch(r"[0-9a-f]{12}", store.session_id), (
            "session_id should be a 12-char lowercase hex string"
        )

    def test_session_started_is_set(self, store: SessionNoteStore) -> None:
        assert isinstance(store.session_started, str)
        assert "T" in store.session_started, "should be ISO-8601 format"
        # Should contain a timezone offset or 'Z'
        assert "+" in store.session_started or "Z" in store.session_started

    def test_metadata_returns_dict(self, store: SessionNoteStore) -> None:
        store.save("note1", "val1")
        meta = store.metadata()
        assert isinstance(meta, dict)
        assert meta["session_id"] == store.session_id
        assert meta["session_started"] == store.session_started
        assert meta["note_count"] == 1

    def test_metadata_note_count_tracks_changes(self, store: SessionNoteStore) -> None:
        assert store.metadata()["note_count"] == 0
        store.save("k", "v")
        assert store.metadata()["note_count"] == 1
        store.clear()
        assert store.metadata()["note_count"] == 0


class TestSnapshotAndPersistence:
    """Snapshot serialization and file-based persistence."""

    @pytest.fixture()
    def store(self, tmp_path: Path) -> SessionNoteStore:
        return SessionNoteStore(project_root=tmp_path)

    def test_snapshot_roundtrip(self, store: SessionNoteStore) -> None:
        store.save("key1", "value1")
        store.save("key2", "value2")

        snap = store.snapshot()
        assert isinstance(snap, SessionNotesSnapshot)
        assert snap.session_id == store.session_id
        assert snap.project_root == str(store.project_root)
        assert len(snap.notes) == 2
        assert snap.session_started == store.session_started

        # model_dump round-trip
        dumped = snap.model_dump()
        restored = SessionNotesSnapshot.model_validate(dumped)
        assert restored.session_id == snap.session_id
        assert restored.notes["key1"].value == "value1"
        assert restored.notes["key2"].value == "value2"

    def test_persistence_creates_file(self, tmp_path: Path) -> None:
        store = SessionNoteStore(project_root=tmp_path)
        store.save("persisted", "data")

        session_dir = tmp_path / ".tapps-mcp" / "sessions"
        assert session_dir.exists()

        json_files = list(session_dir.glob("*.json"))
        assert len(json_files) >= 1

        # Verify file content is valid JSON with expected structure
        content = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert content["session_id"] == store.session_id
        assert "persisted" in content["notes"]
        assert content["notes"]["persisted"]["value"] == "data"

    def test_recovery_from_crash(self, tmp_path: Path) -> None:
        """Simulate crash recovery: create store, save, destroy, create new store."""
        store1 = SessionNoteStore(project_root=tmp_path)
        original_session_id = store1.session_id
        store1.save("important", "do not lose this")
        store1.save("also", "keep me")

        # "Crash" — destroy the Python object, but files remain on disk
        del store1

        # New store on the SAME project root should recover
        store2 = SessionNoteStore(project_root=tmp_path)
        assert store2.session_id == original_session_id, "should recover the old session ID"
        assert store2.note_count == 2
        recovered = store2.get("important")
        assert recovered is not None
        assert recovered.value == "do not lose this"

    def test_recovery_preserves_session_started(self, tmp_path: Path) -> None:
        store1 = SessionNoteStore(project_root=tmp_path)
        original_started = store1.session_started
        store1.save("x", "y")
        del store1

        store2 = SessionNoteStore(project_root=tmp_path)
        assert store2.session_started == original_started

    def test_persistence_updates_on_clear(self, tmp_path: Path) -> None:
        store = SessionNoteStore(project_root=tmp_path)
        store.save("a", "1")
        store.save("b", "2")
        store.clear()

        # Read the persisted file — it should reflect cleared state
        json_file = store._store_path
        content = json.loads(json_file.read_text(encoding="utf-8"))
        assert content["notes"] == {}


class TestProjectScoping:
    """Ensure different project roots are isolated from each other."""

    def test_different_project_roots_are_isolated(self, tmp_path: Path) -> None:
        root_a = tmp_path / "project_a"
        root_b = tmp_path / "project_b"
        root_a.mkdir()
        root_b.mkdir()

        store_a = SessionNoteStore(project_root=root_a)
        store_b = SessionNoteStore(project_root=root_b)

        store_a.save("env", "production")
        store_b.save("env", "staging")

        assert store_a.get("env") is not None
        assert store_a.get("env").value == "production"  # type: ignore[union-attr]
        assert store_b.get("env") is not None
        assert store_b.get("env").value == "staging"  # type: ignore[union-attr]

        # IDs should differ
        assert store_a.session_id != store_b.session_id

    def test_recovery_ignores_different_project_root(self, tmp_path: Path) -> None:
        """If a session file exists from project A, a store for project B must not load it."""
        root_a = tmp_path / "alpha"
        root_b = tmp_path / "beta"
        root_a.mkdir()
        root_b.mkdir()

        store_a = SessionNoteStore(project_root=root_a)
        store_a.save("secret", "alpha-only")

        # Manually copy the session file into project B's sessions directory
        b_sessions = root_b / ".tapps-mcp" / "sessions"
        b_sessions.mkdir(parents=True, exist_ok=True)
        for f in (root_a / ".tapps-mcp" / "sessions").glob("*.json"):
            (b_sessions / f.name).write_bytes(f.read_bytes())

        store_b = SessionNoteStore(project_root=root_b)
        # store_b should NOT have recovered store_a's notes because project_root differs
        assert store_b.get("secret") is None
        assert store_b.note_count == 0


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    @pytest.fixture()
    def store(self, tmp_path: Path) -> SessionNoteStore:
        return SessionNoteStore(project_root=tmp_path)

    def test_save_empty_key(self, store: SessionNoteStore) -> None:
        note = store.save("", "empty key")
        assert note.key == ""
        assert store.get("") is not None

    def test_save_empty_value(self, store: SessionNoteStore) -> None:
        note = store.save("empty_val", "")
        assert note.value == ""

    def test_save_multiline_value(self, store: SessionNoteStore) -> None:
        multiline = "line1\nline2\nline3"
        note = store.save("multi", multiline)
        assert note.value == multiline
        retrieved = store.get("multi")
        assert retrieved is not None
        assert retrieved.value == multiline

    def test_save_unicode_value(self, store: SessionNoteStore) -> None:
        note = store.save("greeting", "Hello World")
        assert note.value == "Hello World"

    def test_clear_all_on_empty_store(self, store: SessionNoteStore) -> None:
        removed = store.clear()
        assert removed == 0

    def test_list_all_returns_copies(self, store: SessionNoteStore) -> None:
        """Mutating the returned list should not affect the store."""
        store.save("x", "1")
        notes = store.list_all()
        notes.clear()
        assert store.note_count == 1
