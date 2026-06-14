"""Tests for Cursor stop completion gate followup (TAP-3921)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from tapps_mcp.tools.loop_metrics import (
    append_completion_gate_violations,
    parse_transcript_loop_metrics,
    read_loop_metrics,
    record_loop_metrics_from_hook_payload,
)
from tapps_mcp.tools.usage import format_stop_gap_followup, read_recent_violations


class TestCursorStopCompletionGate:
    def test_violation_row_written_on_skipped_gate(self, tmp_path: Path) -> None:
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Edit",
                                "input": {"file_path": "src/main.py"},
                            }
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        row = parse_transcript_loop_metrics(transcript)
        append_completion_gate_violations(
            tmp_path,
            list(row["violations"]),
            list(row["files_edited"]),
        )
        violations = read_recent_violations(tmp_path)
        assert len(violations) == 1
        assert "QUALITY_GATE_SKIP" in violations[0]["reasons"][0]

    def test_nlt_build_gate_tool_prevents_violation(self, tmp_path: Path) -> None:
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "mcp__nlt-build__tapps_quick_check",
                                "input": {"file_path": "src/main.py"},
                            },
                            {
                                "type": "tool_use",
                                "name": "mcp__nlt-build__tapps_checklist",
                                "input": {"task_type": "feature"},
                            },
                            {
                                "type": "tool_use",
                                "name": "Edit",
                                "input": {"file_path": "src/main.py"},
                            },
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        row = parse_transcript_loop_metrics(transcript)
        assert row["violations"] == []

    def test_format_stop_gap_followup_block_mode(self, tmp_path: Path) -> None:
        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        metrics.parent.mkdir(parents=True)
        metrics.write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": ["src/a.py"],
                    "mcp_calls": 0,
                    "gate_skipped_files": ["src/a.py"],
                    "lookup_docs_called": False,
                    "checklist_called": False,
                    "tools_used": ["Edit"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        followup = format_stop_gap_followup(
            tmp_path,
            called_tools={"Edit"},
            mode="block",
            fresh_violations=["CHECKLIST_MISSING"],
        )
        assert followup is not None
        assert "BLOCKED" in followup
        assert "checklist_skipped" in followup or "validation" in followup.lower()

    def test_record_payload_returns_usage_gaps(self, tmp_path: Path) -> None:
        transcript = tmp_path / "t.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Edit",
                                "input": {"file_path": "pkg/mod.py"},
                            }
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        result = record_loop_metrics_from_hook_payload(
            {"workspace_roots": [str(tmp_path)], "transcript_path": str(transcript)}
        )
        assert result["recorded"] is True
        assert "edits_without_validation" in result["usage_gaps"]
        assert read_loop_metrics(tmp_path)
        assert read_recent_violations(tmp_path)
