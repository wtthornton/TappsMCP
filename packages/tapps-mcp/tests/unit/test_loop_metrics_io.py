"""Stem coverage + smoke tests for loop_metrics_io (TAP-5606)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.tools.loop_metrics_io import (
    append_loop_metrics_row,
    read_loop_metrics,
)


def test_append_and_read_loop_metrics_roundtrip(tmp_path: Path) -> None:
    append_loop_metrics_row(tmp_path, {"ts": 1, "mcp_calls": 2, "violations": ["x"]})
    rows = read_loop_metrics(tmp_path)
    assert len(rows) == 1
    assert rows[0]["mcp_calls"] == 2
    assert "violations" not in rows[0]


def test_read_loop_metrics_missing_file(tmp_path: Path) -> None:
    assert read_loop_metrics(tmp_path) == []
