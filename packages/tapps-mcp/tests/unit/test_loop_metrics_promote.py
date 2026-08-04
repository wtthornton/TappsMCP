"""Stem coverage + smoke tests for loop_metrics_promote (TAP-5606)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.tools.loop_metrics_promote import (
    compute_gate_pass_rate_7d,
    count_session_start_gate_violations,
    should_auto_promote_cache_gate,
)


def test_should_auto_promote_disabled(tmp_path: Path) -> None:
    promote, telemetry = should_auto_promote_cache_gate(
        tmp_path, current_mode="warn", auto_promote_enabled=False
    )
    assert promote is False
    assert telemetry["reason"] == "auto_promote_disabled"


def test_count_session_start_gate_violations_missing(tmp_path: Path) -> None:
    assert count_session_start_gate_violations(tmp_path) == 0


def test_compute_gate_pass_rate_7d_no_metrics_dir(tmp_path: Path) -> None:
    assert compute_gate_pass_rate_7d(tmp_path) is None
