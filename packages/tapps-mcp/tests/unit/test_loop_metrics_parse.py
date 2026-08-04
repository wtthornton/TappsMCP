"""Stem coverage + smoke tests for loop_metrics_parse (TAP-5606)."""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.tools.loop_metrics_parse import parse_transcript_loop_metrics


def _write_transcript(path: Path, tool_blocks: list[dict[str, object]]) -> None:
    row = {
        "message": {
            "content": [{"type": "tool_use", **blk} for blk in tool_blocks],
        }
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_parse_transcript_empty_path() -> None:
    row = parse_transcript_loop_metrics(None)
    assert row["mcp_calls"] == 0
    assert row["files_edited"] == []


def test_parse_transcript_counts_edit_and_gate(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    target = tmp_path / "mod.py"
    target.write_text("x=1\n", encoding="utf-8")
    _write_transcript(
        transcript,
        [
            {"name": "Write", "input": {"file_path": str(target), "contents": "x=1\n"}},
            {"name": "mcp__nlt-build__tapps_quick_check", "input": {"file_path": str(target)}},
        ],
    )
    row = parse_transcript_loop_metrics(transcript, project_root=tmp_path)
    assert str(target) in row["files_edited"]
    assert row["gate_skipped_files"] == []
    assert row["mcp_calls"] >= 1
