"""Tests for loop_metrics (TAP-1333, TAP-2769)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tapps_mcp.tools.loop_metrics import (
    aggregate_skills_used,
    compute_gate_pass_rate_7d,
    compute_rolling_stats,
    extract_skill_name,
    parse_transcript_loop_metrics,
    read_loop_metrics,
    record_loop_metrics_from_hook_payload,
    should_auto_promote_cache_gate,
)


def _write_metrics(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


class TestReadLoopMetrics:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert read_loop_metrics(tmp_path) == []

    def test_skips_blank_and_invalid_lines(self, tmp_path: Path) -> None:
        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        metrics.parent.mkdir(parents=True, exist_ok=True)
        metrics.write_text(
            '{"ts": 1, "mcp_calls": 2}\n\nnot-json\n{"ts": 2, "mcp_calls": 1}\n',
            encoding="utf-8",
        )
        rows = read_loop_metrics(tmp_path)
        assert len(rows) == 2
        assert rows[0]["mcp_calls"] == 2
        assert rows[1]["mcp_calls"] == 1

    def test_respects_limit(self, tmp_path: Path) -> None:
        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        _write_metrics(metrics, [{"ts": i, "mcp_calls": 1} for i in range(5)])
        rows = read_loop_metrics(tmp_path, limit=2)
        assert len(rows) == 2
        assert rows[-1]["ts"] == 4


class TestComputeRollingStats:
    def test_empty_window(self, tmp_path: Path) -> None:
        stats = compute_rolling_stats(tmp_path, window_days=7)
        assert stats["loops"] == 0
        assert stats["gate_skip_rate"] == 0.0

    def test_aggregates_recent_rows(self, tmp_path: Path) -> None:
        now = int(time.time())
        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        src = str(tmp_path / "packages" / "mod.py")
        _write_metrics(
            metrics,
            [
                {
                    "ts": now - 100,
                    "mcp_calls": 4,
                    "tools_used": ["a"],
                    "files_edited": [src],
                    "gate_skipped_files": [src],
                    "lookup_docs_called": True,
                },
                {
                    "ts": now - 200,
                    "mcp_calls": 2,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                    "files_edited": [src],
                    "gate_skipped_files": [],
                    "lookup_docs_called": False,
                    "checklist_called": True,
                },
            ],
        )
        stats = compute_rolling_stats(tmp_path, window_days=7)
        assert stats["loops"] == 2
        assert stats["gate_skip_rate"] == pytest.approx(0.5)
        assert stats["lookup_docs_to_edit_ratio"] == pytest.approx(0.5)

    def test_comprehension_tool_use_ratio(self, tmp_path: Path) -> None:
        now = int(time.time())
        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        _write_metrics(
            metrics,
            [
                {"ts": now - 100, "tools_used": ["tapps_call_graph"]},
                {"ts": now - 200, "tools_used": ["tapps_validate_changed"]},
                {"ts": now - 300, "tools_used": ["tapps_impact_analysis", "tapps_checklist"]},
                {"ts": now - 400, "tools_used": []},
            ],
        )
        stats = compute_rolling_stats(tmp_path, window_days=7)
        # 2 of 4 loops used a comprehension tool.
        assert stats["comprehension_tool_use_ratio"] == pytest.approx(0.5)

    def test_comprehension_ratio_zero_on_empty(self, tmp_path: Path) -> None:
        stats = compute_rolling_stats(tmp_path, window_days=7)
        assert stats["comprehension_tool_use_ratio"] == 0.0

    def test_excludes_legacy_unparsed_callmcptool_rows(self, tmp_path: Path) -> None:
        now = int(time.time())
        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        pkg = tmp_path / "packages" / "mod.py"
        pkg.parent.mkdir(parents=True)
        pkg.write_text("x = 1\n", encoding="utf-8")
        _write_metrics(
            metrics,
            [
                {
                    "ts": now - 100,
                    "mcp_calls": 0,
                    "tools_used": ["CallMcpTool", "Write"],
                    "files_edited": [str(pkg), "/tmp/snippet.py"],
                    "gate_skipped_files": [str(pkg), "/tmp/snippet.py"],
                    "lookup_docs_called": False,
                },
                {
                    "ts": now - 200,
                    "mcp_calls": 2,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                    "files_edited": [str(pkg)],
                    "gate_skipped_files": [],
                    "lookup_docs_called": True,
                },
            ],
        )
        stats = compute_rolling_stats(tmp_path, window_days=7)
        assert stats["gate_skip_rate"] == pytest.approx(0.0)


class TestShouldAutoPromoteCacheGate:
    def test_disabled_when_flag_off(self, tmp_path: Path) -> None:
        promote, telemetry = should_auto_promote_cache_gate(
            tmp_path, current_mode="warn", auto_promote_enabled=False
        )
        assert promote is False
        assert telemetry["reason"] == "auto_promote_disabled"

    def test_not_ready_when_insufficient_loops(self, tmp_path: Path) -> None:
        now = int(time.time())
        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        _write_metrics(metrics, [{"ts": now, "files_edited": True}])
        promote, telemetry = should_auto_promote_cache_gate(
            tmp_path, current_mode="warn", auto_promote_enabled=True
        )
        assert promote is False
        assert telemetry["reason"] == "insufficient_loops"


class TestComputeGatePassRate7d:
    def test_returns_none_without_metrics(self, tmp_path: Path) -> None:
        assert compute_gate_pass_rate_7d(tmp_path) is None

    def test_computes_from_jsonl(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TAPPS_METRICS_STORAGE", "local")
        from datetime import UTC, date, datetime

        metrics_dir = tmp_path / ".tapps-mcp" / "metrics"
        metrics_dir.mkdir(parents=True)
        day = date.today().isoformat()
        # Timestamps must fall inside the rolling 7-day window (TAP-4571): use
        # today's date rather than a hardcoded past date that rots as the
        # calendar advances.
        now = datetime.now(tz=UTC).replace(microsecond=0)
        ts = now.isoformat()
        rows = [
            {
                "call_id": "1",
                "tool_name": "tapps_quality_gate",
                "status": "success",
                "duration_ms": 1.0,
                "started_at": ts,
                "completed_at": ts,
                "gate_passed": True,
            },
            {
                "call_id": "2",
                "tool_name": "tapps_quality_gate",
                "status": "success",
                "duration_ms": 1.0,
                "started_at": ts,
                "completed_at": ts,
                "gate_passed": False,
            },
        ]
        (metrics_dir / f"tool_calls_{day}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
        rate = compute_gate_pass_rate_7d(tmp_path)
        assert rate == 0.5


class TestTranscriptParsing:
    def test_extract_skill_from_skill_tool(self) -> None:
        assert extract_skill_name("Skill", {"skill": "tapps-finish-task"}) == "tapps-finish-task"

    def test_extract_skill_from_skill_md_read(self) -> None:
        path = "/repo/.cursor/skills/linear-read/SKILL.md"
        assert extract_skill_name("Read", {"path": path}) == "linear-read"

    def test_parse_transcript_row_shape(self, tmp_path: Path) -> None:
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Skill",
                                "input": {"skill": "tapps-finish-task"},
                            },
                            {
                                "type": "tool_use",
                                "name": "mcp__nlt-build__tapps_quick_check",
                                "input": {"file_path": "src/main.py"},
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
        assert row["skills_used"] == ["tapps-finish-task"]
        assert row["mcp_calls"] == 1
        assert "src/main.py" in row["files_edited"]
        assert row["violations"] == ["CHECKLIST_MISSING"]

    def test_callmcptool_unwraps_pipeline_tools(self, tmp_path: Path) -> None:
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "CallMcpTool",
                                "input": {
                                    "server": "project-0-tapps-mcp-nlt-code-quality",
                                    "toolName": "tapps_validate_changed",
                                    "arguments": {"file_paths": "src/main.py"},
                                },
                            },
                            {
                                "type": "tool_use",
                                "name": "CallMcpTool",
                                "input": {
                                    "server": "project-0-tapps-mcp-nlt-code-quality",
                                    "toolName": "tapps_checklist",
                                    "arguments": {"task_type": "feature"},
                                },
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
        row = parse_transcript_loop_metrics(transcript, project_root=tmp_path)
        assert row["violations"] == []
        assert row["checklist_called"] is True
        assert "tapps_validate_changed" in row["tools_used"]
        assert "tapps_checklist" in row["tools_used"]
        assert "CallMcpTool" not in row["tools_used"]
        assert row["mcp_calls"] == 2

    def test_tmp_edits_excluded_from_gate(self, tmp_path: Path) -> None:
        transcript = tmp_path / "session.jsonl"
        pkg_file = tmp_path / "packages" / "mod.py"
        pkg_file.parent.mkdir(parents=True)
        transcript.write_text(
            json.dumps(
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Write",
                                "input": {"path": "/tmp/scratch.py", "contents": "x"},
                            },
                            {
                                "type": "tool_use",
                                "name": "Edit",
                                "input": {"file_path": str(pkg_file)},
                            },
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        row = parse_transcript_loop_metrics(transcript, project_root=tmp_path)
        assert "/tmp/scratch.py" not in row["files_edited"]
        assert str(pkg_file) in row["files_edited"]
        assert any("QUALITY_GATE_SKIP" in v for v in row["violations"])

    def test_out_of_project_edits_excluded(self, tmp_path: Path) -> None:
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Write",
                                "input": {"path": "/other/repo/file.py", "contents": "x"},
                            }
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        row = parse_transcript_loop_metrics(transcript, project_root=tmp_path)
        assert row["files_edited"] == []
        assert row["violations"] == []

    def test_record_from_cursor_payload(self, tmp_path: Path) -> None:
        transcript = tmp_path / "agent-transcripts" / "abc.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(
            json.dumps(
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "mcp__nlt-build__tapps_session_start",
                                "input": {},
                            }
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        payload = {
            "workspace_roots": [str(tmp_path)],
            "transcript_path": str(transcript),
        }
        result = record_loop_metrics_from_hook_payload(payload)
        assert result["recorded"] is True
        rows = read_loop_metrics(tmp_path)
        assert len(rows) == 1
        assert rows[0]["mcp_calls"] == 1


class TestAggregateSkillsUsed:
    def test_top_skills_from_loop_metrics(self, tmp_path: Path) -> None:
        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        now = int(time.time())
        _write_metrics(
            metrics,
            [
                {"ts": now, "skills_used": ["tapps-finish-task", "linear-read"]},
                {"ts": now - 10, "skills_used": ["tapps-finish-task"]},
            ],
        )
        stats = aggregate_skills_used(tmp_path, window_days=7)
        assert stats["loops"] == 2
        assert stats["top_skills"][0]["name"] == "tapps-finish-task"
        assert stats["skill_orchestrated_closes"] == 2
