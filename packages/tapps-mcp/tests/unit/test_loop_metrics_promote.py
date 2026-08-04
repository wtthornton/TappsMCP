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


def test_should_auto_promote_refuses_without_cache_activity(tmp_path: Path) -> None:
    """TAP-5454: low skip rate alone must not promote on an unmeasured gate."""
    import json
    import time

    metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
    metrics.parent.mkdir(parents=True)
    now = int(time.time())
    rows = [
        {
            "ts": now - i * 60,
            "mcp_calls": 2,
            "tools_used": ["tapps_validate_changed"],
            "files_edited": ["a.py"],
            "gate_skipped_files": [],
            "lookup_docs_called": True,
        }
        for i in range(10)
    ]
    metrics.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    promote, telemetry = should_auto_promote_cache_gate(
        tmp_path, current_mode="warn", auto_promote_enabled=True
    )
    assert promote is False
    assert telemetry["reason"] == "no_cache_activity"
    assert telemetry["snapshot_files"] == 0
    assert telemetry["gate_evaluations"] == 0


def test_should_auto_promote_when_cache_populated_and_clean(tmp_path: Path) -> None:
    import json
    import time

    metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
    metrics.parent.mkdir(parents=True)
    now = int(time.time())
    rows = [
        {
            "ts": now - i * 60,
            "mcp_calls": 2,
            "tools_used": ["tapps_validate_changed"],
            "files_edited": ["a.py"],
            "gate_skipped_files": [],
            "lookup_docs_called": True,
        }
        for i in range(10)
    ]
    metrics.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    snap = tmp_path / ".tapps-mcp-cache" / "linear-snapshots"
    snap.mkdir(parents=True)
    (snap / "hit.json").write_text("{}", encoding="utf-8")
    promote, telemetry = should_auto_promote_cache_gate(
        tmp_path, current_mode="warn", auto_promote_enabled=True
    )
    assert promote is True
    assert telemetry["reason"] == "ready_to_promote"
    assert telemetry["snapshot_files"] == 1


def test_count_session_start_gate_violations_missing(tmp_path: Path) -> None:
    assert count_session_start_gate_violations(tmp_path) == 0


def test_compute_gate_pass_rate_7d_no_metrics_dir(tmp_path: Path) -> None:
    assert compute_gate_pass_rate_7d(tmp_path) is None
