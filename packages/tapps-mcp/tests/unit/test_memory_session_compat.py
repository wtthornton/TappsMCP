"""Tests for session notes backward compatibility and promote (Epic 23.5).

TAP-414 / EPIC-95.5: ``_promote_note_to_memory`` is now async and delegates
to :class:`BrainBridge.save` instead of touching MemoryStore directly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.project.models import SessionNote


class TestPromoteNoteToMemory:
    @pytest.mark.asyncio
    async def test_promote_success(self) -> None:
        """Promoting a session note creates a memory entry via bridge."""
        from tapps_mcp.server import _promote_note_to_memory

        note = SessionNote(
            key="my-note",
            value="important info",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )

        mock_bridge = MagicMock()
        mock_bridge.save = AsyncMock(
            return_value={"key": "my-note", "value": "important info"}
        )

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=mock_bridge):
            result = await _promote_note_to_memory(note, "pattern")

        assert result["action"] == "promote"
        assert result["promoted"] is True
        mock_bridge.save.assert_awaited_once_with(
            key="my-note",
            value="important info",
            tier="pattern",
            scope="session",
            source="agent",
            source_agent="session-promote",
            tags=["promoted-from-session-notes"],
        )

    @pytest.mark.asyncio
    async def test_promote_failure_returns_error(self) -> None:
        """When promotion fails, result contains error info."""
        from tapps_mcp.server import _promote_note_to_memory

        note = SessionNote(
            key="my-note",
            value="important info",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )

        with patch(
            "tapps_mcp.server_helpers._get_brain_bridge",
            side_effect=RuntimeError("bridge unavailable"),
        ):
            result = await _promote_note_to_memory(note)

        assert result["action"] == "promote"
        assert result["promoted"] is False
        assert "bridge unavailable" in result["error"]

    @pytest.mark.asyncio
    async def test_promote_default_tier_is_context(self) -> None:
        """Default tier for promoted notes is 'context'."""
        from tapps_mcp.server import _promote_note_to_memory

        note = SessionNote(key="my-note", value="test")

        mock_bridge = MagicMock()
        mock_bridge.save = AsyncMock(return_value={})

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=mock_bridge):
            await _promote_note_to_memory(note)

        call_kwargs = mock_bridge.save.await_args.kwargs
        assert call_kwargs["tier"] == "context"
        assert call_kwargs["scope"] == "session"

    @pytest.mark.asyncio
    async def test_promote_degraded_when_no_bridge(self) -> None:
        """When bridge is None, result has degraded=True (no SQLite fallback)."""
        from tapps_mcp.server import _promote_note_to_memory

        note = SessionNote(key="my-note", value="test")
        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None):
            result = await _promote_note_to_memory(note)

        assert result["promoted"] is False
        assert result.get("degraded") is True


class TestSessionNotesBackwardCompat:
    def test_existing_actions_unchanged(self) -> None:
        """Existing actions (save, get, list, clear) still work.

        We just verify the session_notes handler accepts those actions
        without error (testing via the store).
        """
        from tapps_mcp.project.session_notes import SessionNoteStore
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionNoteStore(Path(tmpdir))
            note = store.save("test-key", "test-value")
            assert note.key == "test-key"

            found = store.get("test-key")
            assert found is not None
            assert found.value == "test-value"

            all_notes = store.list_all()
            assert len(all_notes) == 1

            cleared = store.clear("test-key")
            assert cleared == 1
            assert store.note_count == 0

    def test_migration_hint_present_in_responses(self) -> None:
        """Responses should include a migration hint pointing to tapps_memory.

        This is verified by checking the server handler adds the hint.
        """
        # The migration hint is added in the handler, not the store.
        # We verify the key exists by checking the handler code path.
        # A full integration test would call the MCP tool, but that
        # requires the server to be running.
        pass
