"""Stem coverage + smoke tests for loop_metrics_aggregate (TAP-5606)."""

from __future__ import annotations

import time
from pathlib import Path

from tapps_mcp.tools.loop_metrics_aggregate import (
    aggregate_skills_used,
    compute_recent_edit_loop_stats,
    compute_rolling_stats,
)
from tapps_mcp.tools.loop_metrics_io import append_loop_metrics_row


def test_compute_rolling_stats_empty(tmp_path: Path) -> None:
    stats = compute_rolling_stats(tmp_path)
    assert stats["loops"] == 0
    assert stats["gate_skip_rate"] == 0.0


def test_aggregate_skills_used_counts(tmp_path: Path) -> None:
    append_loop_metrics_row(
        tmp_path,
        {
            "ts": int(time.time()),
            "skills_used": ["tapps-finish-task"],
            "tools_used": [],
            "mcp_calls": 0,
        },
    )
    agg = aggregate_skills_used(tmp_path, window_days=7)
    assert agg["loops"] == 1
    assert agg["skill_orchestrated_closes"] == 1


def test_compute_recent_edit_loop_stats_empty(tmp_path: Path) -> None:
    stats = compute_recent_edit_loop_stats(tmp_path)
    assert stats["loops"] == 0
