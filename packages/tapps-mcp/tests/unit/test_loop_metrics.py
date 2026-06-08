"""Tests for loop_metrics (TAP-1333, TAP-2769)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tapps_mcp.tools.loop_metrics import (
    compute_rolling_stats,
    read_loop_metrics,
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
        _write_metrics(
            metrics,
            [
                {
                    "ts": now - 100,
                    "mcp_calls": 4,
                    "tools_used": ["a"],
                    "files_edited": True,
                    "gate_skipped_files": True,
                    "lookup_docs_called": True,
                },
                {
                    "ts": now - 200,
                    "mcp_calls": 2,
                    "tools_used": [],
                    "files_edited": True,
                    "gate_skipped_files": False,
                    "lookup_docs_called": False,
                },
            ],
        )
        stats = compute_rolling_stats(tmp_path, window_days=7)
        assert stats["loops"] == 2
        assert stats["gate_skip_rate"] == pytest.approx(0.5)
        assert stats["lookup_docs_to_edit_ratio"] == pytest.approx(0.5)


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
