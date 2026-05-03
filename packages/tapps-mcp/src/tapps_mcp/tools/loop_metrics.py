"""TAP-1333: per-loop MCP-call telemetry — read/aggregate/auto-promote.

Companion module to the Stop hook in
``packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py``,
which appends one JSONL line per loop to ``.tapps-mcp/loop-metrics.jsonl``.
This module reads that file and produces the rolling stats consumed by
``tapps_doctor``, ``tapps_dashboard``, and the cache-gate auto-promote logic
in ``tapps_upgrade``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_METRICS_NAME = "loop-metrics.jsonl"
_DAY_SECONDS = 86_400
_PROMOTE_THRESHOLD = 0.05  # 5% gate-skip rate
_PROMOTE_WINDOW_DAYS = 7


def _metrics_path(project_root: Path) -> Path:
    return project_root / ".tapps-mcp" / _METRICS_NAME


def read_loop_metrics(project_root: Path, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` loop-metrics rows. Best-effort, no raise."""
    path = _metrics_path(project_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return rows[-limit:]


def compute_rolling_stats(
    project_root: Path,
    *,
    window_days: int = _PROMOTE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Aggregate metrics over the trailing ``window_days``.

    Returns:
        Dict with ``loops``, ``mcp_call_ratio``, ``gate_skip_rate``,
        ``lookup_docs_to_edit_ratio``, ``window_days``, ``window_start_ts``.
        All ratios are 0.0 when there are no loops in the window.
    """
    cutoff = int(time.time()) - window_days * _DAY_SECONDS
    rows = [r for r in read_loop_metrics(project_root) if int(r.get("ts", 0)) >= cutoff]
    loops = len(rows)
    if loops == 0:
        return {
            "loops": 0,
            "mcp_call_ratio": 0.0,
            "gate_skip_rate": 0.0,
            "lookup_docs_to_edit_ratio": 0.0,
            "window_days": window_days,
            "window_start_ts": cutoff,
        }
    total_calls = sum(int(r.get("mcp_calls", 0)) + len(r.get("tools_used", [])) for r in rows)
    mcp_calls = sum(int(r.get("mcp_calls", 0)) for r in rows)
    edit_loops = sum(1 for r in rows if r.get("files_edited"))
    skipped_loops = sum(1 for r in rows if r.get("gate_skipped_files"))
    lookup_loops = sum(1 for r in rows if r.get("lookup_docs_called"))
    return {
        "loops": loops,
        "mcp_call_ratio": (mcp_calls / total_calls) if total_calls else 0.0,
        "gate_skip_rate": (skipped_loops / edit_loops) if edit_loops else 0.0,
        "lookup_docs_to_edit_ratio": (lookup_loops / edit_loops) if edit_loops else 0.0,
        "window_days": window_days,
        "window_start_ts": cutoff,
    }


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


__all__ = [
    "compute_rolling_stats",
    "read_loop_metrics",
    "should_auto_promote_cache_gate",
]
