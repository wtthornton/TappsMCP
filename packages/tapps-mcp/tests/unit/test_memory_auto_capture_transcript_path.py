"""Tests for reading Claude Code's real Stop hook transcript_path shape (TAP-6733)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tapps_mcp.memory.auto_capture import _extract_context_from_payload


def _write_transcript(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


class TestExtractContextFromTranscriptPath:
    """Tests for reading Claude Code's real Stop hook transcript_path shape."""

    def test_reads_last_turns_from_transcript_path(self, tmp_path: Path) -> None:
        transcript = _write_transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "irrelevant chatter"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "We standardized on ruff for linting."}
                        ],
                    },
                },
            ],
        )
        payload = {"transcript_path": str(transcript)}
        context = _extract_context_from_payload(payload)
        assert "ruff for linting" in context

    def test_skips_tool_use_and_tool_result_blocks(self, tmp_path: Path) -> None:
        transcript = _write_transcript(
            tmp_path,
            [
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
                            {"type": "text", "text": "Listed the directory."},
                        ],
                    },
                },
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "tool_result", "content": "huge tool output" * 50}],
                    },
                },
            ],
        )
        payload = {"transcript_path": str(transcript)}
        context = _extract_context_from_payload(payload)
        assert "tool output" not in context
        assert "ls -la" not in context
        assert "Listed the directory." in context

    def test_bounds_by_turn_count(self, tmp_path: Path) -> None:
        rows = [
            {"type": "user", "message": {"role": "user", "content": f"turn {i}"}} for i in range(10)
        ]
        transcript = _write_transcript(tmp_path, rows)
        payload = {"transcript_path": str(transcript)}
        context = _extract_context_from_payload(payload, transcript_turns=3)
        assert "turn 9" in context
        assert "turn 6" not in context

    def test_no_transcript_path_and_no_inline_keys_returns_empty(self) -> None:
        """Never fall back to dumping the raw hook payload as context."""
        payload = {
            "session_id": "abc",
            "cwd": "/tmp",
            "hook_event_name": "Stop",
            "stop_hook_active": False,
        }
        assert _extract_context_from_payload(payload) == ""

    def test_missing_transcript_file_returns_empty(self, tmp_path: Path) -> None:
        payload = {"transcript_path": str(tmp_path / "does-not-exist.jsonl")}
        assert _extract_context_from_payload(payload) == ""

    def test_inline_transcript_still_takes_precedence(self, tmp_path: Path) -> None:
        """Old inline-transcript path still works even when transcript_path is present."""
        transcript = _write_transcript(
            tmp_path,
            [{"type": "user", "message": {"role": "user", "content": "from the file"}}],
        )
        payload = {"transcript": "inline text wins", "transcript_path": str(transcript)}
        context = _extract_context_from_payload(payload)
        assert context == "inline text wins"
