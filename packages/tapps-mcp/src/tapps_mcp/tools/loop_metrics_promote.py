"""Auto-promote and gate-rate helpers for loop metrics (TAP-5606)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tapps_mcp.tools.loop_metrics_aggregate import (
    _PROMOTE_WINDOW_DAYS,
    compute_rolling_stats,
)

_PROMOTE_THRESHOLD = 0.05  # 5% gate-skip rate
_SESSION_START_GATE_VIOLATIONS_NAME = ".session-start-gate-violations.jsonl"


def should_auto_promote_cache_gate(
    project_root: Path,
    *,
    current_mode: str,
    auto_promote_enabled: bool,
) -> tuple[bool, dict[str, Any]]:
    """TAP-1333 AC: warn → block when 7-day gate-skip rate < 5%.

    Returns ``(should_promote, telemetry)``. ``telemetry`` always carries the
    rolling stats and a ``reason`` string explaining the decision so callers
    can log the promotion (or lack thereof).
    """
    stats = compute_rolling_stats(project_root)
    if not auto_promote_enabled:
        return False, {**stats, "reason": "auto_promote_disabled"}
    if current_mode != "warn":
        return False, {**stats, "reason": f"current_mode={current_mode}"}
    if stats["loops"] < _PROMOTE_WINDOW_DAYS:
        return False, {**stats, "reason": "insufficient_loops"}
    if stats["gate_skip_rate"] >= _PROMOTE_THRESHOLD:
        return False, {**stats, "reason": "skip_rate_above_threshold"}
    return True, {**stats, "reason": "ready_to_promote"}


def count_session_start_gate_violations(
    project_root: Path,
    *,
    window_days: int = _PROMOTE_WINDOW_DAYS,
) -> int:
    """Count session-start gate violations logged in the trailing window.

    Reads ``.tapps-mcp/.session-start-gate-violations.jsonl`` and counts entries
    whose ``ts`` is within ``window_days`` of now. Returns 0 when the log is
    missing or unparseable — a telemetry signal, not a gate, so failures degrade
    silently. Each entry is one time the agent reached for a TappsMCP quality
    tool before ``tapps_session_start`` ran that session.
    """
    from datetime import UTC, datetime, timedelta

    log_path = project_root / ".tapps-mcp" / _SESSION_START_GATE_VIOLATIONS_NAME
    if not log_path.exists():
        return 0
    cutoff = datetime.now(tz=UTC) - timedelta(days=window_days)
    count = 0
    try:
        with log_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_raw = entry.get("ts", "")
                if not isinstance(ts_raw, str):
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except ValueError:
                    continue
                if ts >= cutoff:
                    count += 1
    except OSError:
        return 0
    return count


def should_auto_promote_session_start_gate(
    project_root: Path,
    *,
    current_mode: str,
    auto_promote_enabled: bool,
) -> tuple[bool, dict[str, Any]]:
    """warn → block for the session-start gate when the repo is disciplined.

    Mirrors :func:`should_auto_promote_cache_gate` (TAP-1333): promote only from
    ``warn``, only when auto-promote is enabled, only once there is enough
    activity in the window (``loops >= _PROMOTE_WINDOW_DAYS``), and only when the
    session-start skip signal is below threshold. The skip signal is
    ``session_start_gate_violations / loops`` over the trailing 7 days — the
    fraction of agent activity that reached for a quality tool before
    ``tapps_session_start`` ran. Returns ``(should_promote, telemetry)`` with a
    ``reason`` string so callers can log the decision.
    """
    stats = compute_rolling_stats(project_root)
    violations = count_session_start_gate_violations(project_root)
    loops = int(stats.get("loops", 0))
    skip_rate = (violations / loops) if loops else 0.0
    telemetry = {
        **stats,
        "session_start_gate_violations": violations,
        "session_start_skip_rate": skip_rate,
    }
    if not auto_promote_enabled:
        return False, {**telemetry, "reason": "auto_promote_disabled"}
    if current_mode != "warn":
        return False, {**telemetry, "reason": f"current_mode={current_mode}"}
    if loops < _PROMOTE_WINDOW_DAYS:
        return False, {**telemetry, "reason": "insufficient_loops"}
    if skip_rate >= _PROMOTE_THRESHOLD:
        return False, {**telemetry, "reason": "skip_rate_above_threshold"}
    return True, {**telemetry, "reason": "ready_to_promote"}


def compute_gate_pass_rate_7d(project_root: Path) -> float | None:
    """Return 7-day quality gate pass rate from execution metrics JSONL.

    Uses tool-call rows where ``gate_passed`` is set. Returns ``None`` when
    no gated calls were recorded in the window.
    """
    from datetime import UTC, datetime, timedelta

    from tapps_core.metrics.execution_metrics import ToolCallMetricsCollector

    metrics_dir = project_root / ".tapps-mcp" / "metrics"
    if not metrics_dir.is_dir():
        return None
    since = datetime.now(tz=UTC) - timedelta(days=7)
    collector = ToolCallMetricsCollector(metrics_dir)
    summary = collector.get_summary(since=since)
    return summary.gate_pass_rate


# Re-export shared constants for doctor private imports via the facade.
__all__ = [
    "compute_gate_pass_rate_7d",
    "count_session_start_gate_violations",
    "should_auto_promote_cache_gate",
    "should_auto_promote_session_start_gate",
]
