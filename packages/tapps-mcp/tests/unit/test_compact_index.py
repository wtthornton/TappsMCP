"""Unit tests for compaction resilience (TAP-2017).

Tests cover:
  - compact_index.py: session-id extraction, chunk building, marker writes,
    and run_compact_index orchestration (with bridge mocked).
  - session_start_helpers._check_compaction_rehydration: marker detection,
    brain search, and cleanup.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers shared across test modules
# ---------------------------------------------------------------------------

class _FakeBridge:
    """Minimal mock BrainBridge that supports index_session and search_sessions."""

    def __init__(self, index_result: Any = None, search_result: Any = None) -> None:
        self._index_result = index_result or {"ok": True}
        self._search_result = search_result or {"results": []}
        self.index_calls: list[tuple[str, list[str]]] = []
        self.search_calls: list[tuple[str, int]] = []

    async def index_session(self, session_id: str, chunks: list[str]) -> Any:
        self.index_calls.append((session_id, chunks))
        return self._index_result

    async def search_sessions(self, query: str, *, limit: int = 10) -> Any:
        self.search_calls.append((query, limit))
        return self._search_result

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# compact_index — unit tests
# ---------------------------------------------------------------------------

class TestExtractSessionId:
    def test_extracts_session_id_key(self) -> None:
        from tapps_mcp.memory.compact_index import _extract_session_id

        result = _extract_session_id({"session_id": "abc-123"})
        assert result == "abc-123"

    def test_extracts_sessionId_camel(self) -> None:
        from tapps_mcp.memory.compact_index import _extract_session_id

        result = _extract_session_id({"sessionId": "xyz-789"})
        assert result == "xyz-789"

    def test_falls_back_to_timestamp(self) -> None:
        from tapps_mcp.memory.compact_index import _extract_session_id

        before = int(time.time())
        result = _extract_session_id({})
        after = int(time.time())
        assert result.startswith("compact-")
        ts = int(result.split("-", 1)[1])
        assert before <= ts <= after

    def test_ignores_empty_string(self) -> None:
        from tapps_mcp.memory.compact_index import _extract_session_id

        result = _extract_session_id({"session_id": ""})
        # Falls back because the value is empty
        assert result.startswith("compact-")


class TestBuildCompactionChunks:
    def test_always_includes_boundary_chunk(self) -> None:
        from tapps_mcp.memory.compact_index import _build_compaction_chunks

        chunks = _build_compaction_chunks({}, "session-99")
        assert any("compaction_boundary:session-99" in c for c in chunks)

    def test_includes_summary_when_present(self) -> None:
        from tapps_mcp.memory.compact_index import _build_compaction_chunks

        chunks = _build_compaction_chunks({"summary": "Big summary text"}, "s1")
        assert any("compaction_summary:Big summary text" in c for c in chunks)

    def test_truncates_long_summary(self) -> None:
        from tapps_mcp.memory.compact_index import _build_compaction_chunks

        long_text = "x" * 5000
        chunks = _build_compaction_chunks({"summary": long_text}, "s1")
        summary_chunks = [c for c in chunks if c.startswith("compaction_summary:")]
        assert summary_chunks  # at least one
        # The text after the prefix should be capped at 2000 chars
        content = summary_chunks[0].split(":", 1)[1]
        assert len(content) <= 2000

    def test_falls_back_to_context_when_no_summary(self) -> None:
        from tapps_mcp.memory.compact_index import _build_compaction_chunks

        chunks = _build_compaction_chunks({"context": "context text"}, "s1")
        assert any("compaction_context:context text" in c for c in chunks)

    def test_includes_trigger(self) -> None:
        from tapps_mcp.memory.compact_index import _build_compaction_chunks

        chunks = _build_compaction_chunks({"trigger": "manual"}, "s1")
        assert any("compaction_trigger:manual" in c for c in chunks)

    def test_default_trigger_is_auto(self) -> None:
        from tapps_mcp.memory.compact_index import _build_compaction_chunks

        chunks = _build_compaction_chunks({}, "s1")
        assert any("compaction_trigger:auto" in c for c in chunks)


class TestWriteCompactionMarker:
    def test_writes_marker_file(self, tmp_path: Path) -> None:
        from tapps_mcp.memory.compact_index import _write_compaction_marker

        _write_compaction_marker(tmp_path, "sess-1", ["chunk-a"], indexed=True)
        marker_path = tmp_path / ".tapps-mcp" / "compaction-marker.json"
        assert marker_path.exists()
        data = json.loads(marker_path.read_text())
        assert data["session_id"] == "sess-1"
        assert data["chunks"] == ["chunk-a"]
        assert data["indexed_in_brain"] is True
        assert "compacted_at" in data

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        from tapps_mcp.memory.compact_index import _write_compaction_marker

        new_root = tmp_path / "subdir"
        _write_compaction_marker(new_root, "sess-2", [], indexed=False)
        assert (new_root / ".tapps-mcp" / "compaction-marker.json").exists()


class TestRunCompactIndex:
    def test_disabled_by_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from tapps_mcp.memory.compact_index import run_compact_index  # noqa: PLC0415

        monkeypatch.setenv("TAPPS_MCP_COMPACTION_REHYDRATE", "false")

        result = asyncio.run(run_compact_index("{}", tmp_path))
        assert result["skipped"] is True
        assert result["reason"] == "disabled_by_env"

    def test_writes_marker_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.memory.compact_index import run_compact_index  # noqa: PLC0415

        monkeypatch.setenv("TAPPS_MCP_COMPACTION_REHYDRATE", "true")
        bridge = _FakeBridge()
        payload = json.dumps({"session_id": "test-sess", "summary": "some context"})

        with patch(
            "tapps_mcp.memory.compact_index._create_bridge",
            return_value=bridge,
        ):
            result = asyncio.run(run_compact_index(payload, tmp_path))

        assert result["success"] is True
        assert result["session_id"] == "test-sess"
        assert result["chunks"] > 0
        assert result["indexed_in_brain"] is True

        marker_path = tmp_path / ".tapps-mcp" / "compaction-marker.json"
        assert marker_path.exists()

    def test_writes_marker_even_on_brain_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.memory.compact_index import run_compact_index  # noqa: PLC0415

        monkeypatch.setenv("TAPPS_MCP_COMPACTION_REHYDRATE", "true")

        def _fail_bridge(project_root: Any) -> None:
            raise RuntimeError("brain is down")

        with patch("tapps_mcp.memory.compact_index._create_bridge", _fail_bridge):
            result = asyncio.run(run_compact_index("{}", tmp_path))

        assert result["success"] is True
        assert result["indexed_in_brain"] is False
        assert "brain_error" in result
        marker_path = tmp_path / ".tapps-mcp" / "compaction-marker.json"
        assert marker_path.exists()

    def test_handles_invalid_json_stdin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.memory.compact_index import run_compact_index  # noqa: PLC0415

        monkeypatch.setenv("TAPPS_MCP_COMPACTION_REHYDRATE", "true")
        bridge = _FakeBridge()

        with patch("tapps_mcp.memory.compact_index._create_bridge", return_value=bridge):
            result = asyncio.run(run_compact_index("not-json", tmp_path))

        # Should succeed — gracefully handles parse failure
        assert result["success"] is True

    def test_handles_empty_stdin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.memory.compact_index import run_compact_index  # noqa: PLC0415

        monkeypatch.setenv("TAPPS_MCP_COMPACTION_REHYDRATE", "true")
        bridge = _FakeBridge()

        with patch("tapps_mcp.memory.compact_index._create_bridge", return_value=bridge):
            result = asyncio.run(run_compact_index("", tmp_path))

        assert result["success"] is True


# ---------------------------------------------------------------------------
# session_start_helpers._check_compaction_rehydration — unit tests
# ---------------------------------------------------------------------------

class TestCheckCompactionRehydration:
    def test_returns_none_when_no_marker(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_start_helpers import _check_compaction_rehydration

        result = asyncio.run(_check_compaction_rehydration(tmp_path))
        assert result is None

    def test_returns_none_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TAPPS_MCP_COMPACTION_REHYDRATE", "false")
        from tapps_mcp.tools.session_start_helpers import _check_compaction_rehydration

        result = asyncio.run(_check_compaction_rehydration(tmp_path))
        assert result is None

    def _write_marker(
        self,
        marker_dir: Path,
        *,
        session_id: str = "sess-abc",
        indexed: bool = False,
    ) -> Path:
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker_path = marker_dir / "compaction-marker.json"
        marker_path.write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "compacted_at": 1700000000.0,
                    "chunks": [f"compaction_boundary:{session_id}"],
                    "indexed_in_brain": indexed,
                }
            )
        )
        return marker_path

    def test_reads_marker_and_deletes_it(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_start_helpers import _check_compaction_rehydration

        marker_path = self._write_marker(tmp_path / ".tapps-mcp")

        # Patch tapps_mcp.server_helpers._get_brain_bridge at the source
        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None):
            result = asyncio.run(_check_compaction_rehydration(tmp_path))

        assert result is not None
        assert result["session_id"] == "sess-abc"
        assert result["indexed_in_brain"] is False
        # Marker must be deleted after reading
        assert not marker_path.exists()

    def test_calls_search_sessions_when_indexed(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_start_helpers import _check_compaction_rehydration

        marker_path = self._write_marker(
            tmp_path / ".tapps-mcp", session_id="sess-xyz", indexed=True
        )

        bridge = _FakeBridge(
            search_result={"results": [{"chunk": "compaction_boundary:sess-xyz"}]}
        )

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            result = asyncio.run(_check_compaction_rehydration(tmp_path))

        assert result is not None
        assert result["session_id"] == "sess-xyz"
        assert "compaction_boundary:sess-xyz" in result["prior_chunks"]
        assert result["search_result_count"] == 1
        # Bridge search was called with session_id in query
        assert bridge.search_calls
        assert "sess-xyz" in bridge.search_calls[0][0]

    def test_deletes_marker_even_on_corrupt_json(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_start_helpers import _check_compaction_rehydration

        marker_dir = tmp_path / ".tapps-mcp"
        marker_dir.mkdir()
        marker_path = marker_dir / "compaction-marker.json"
        marker_path.write_text("{{not-valid-json")

        result = asyncio.run(_check_compaction_rehydration(tmp_path))

        assert result is None  # corrupt marker → None
        assert not marker_path.exists()  # marker must still be deleted
