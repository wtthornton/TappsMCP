"""Rolling aggregation helpers for loop metrics (TAP-5606)."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any

from tapps_mcp.tools.loop_metrics_io import read_loop_metrics
from tapps_mcp.tools.loop_metrics_scope import (
    is_reliable_edit_loop_row,
    loop_row_gate_skipped,
)
from tapps_mcp.tools.pipeline_tool_sets import (
    COMPREHENSION_SHORT_NAMES,
    is_checklist_tool,
    is_gate_tool,
)

_DAY_SECONDS = 86_400
_PROMOTE_WINDOW_DAYS = 7
_FINISH_SKILL_NAMES = frozenset({"tapps-finish-task", "/tapps-finish-task", "finish-task"})
_RECENT_EDIT_LOOPS_FOR_GAPS = 10


def aggregate_skills_used(
    project_root: Path,
    *,
    window_days: int = 7,
) -> dict[str, Any]:
    """Aggregate skill utilization from loop-metrics for fleet/doctor views."""
    cutoff = int(time.time()) - window_days * _DAY_SECONDS
    rows = [r for r in read_loop_metrics(project_root) if int(r.get("ts", 0)) >= cutoff]
    skill_counts: Counter[str] = Counter()
    finish_skill_loops = 0
    direct_validate_loops = 0
    for row in rows:
        skills = row.get("skills_used") or []
        if isinstance(skills, list):
            for skill in skills:
                if isinstance(skill, str) and skill:
                    skill_counts[skill] += 1
                    if skill in _FINISH_SKILL_NAMES or "finish-task" in skill:
                        finish_skill_loops += 1
        tools = row.get("tools_used") or []
        if (
            isinstance(tools, list)
            and any(is_gate_tool(str(t)) or is_checklist_tool(str(t)) for t in tools)
            and not skills
        ):
            direct_validate_loops += 1
    top_skills = [{"name": name, "count": count} for name, count in skill_counts.most_common(10)]
    return {
        "window_days": window_days,
        "loops": len(rows),
        "top_skills": top_skills,
        "skill_orchestrated_closes": finish_skill_loops,
        "direct_mcp_validate_loops": direct_validate_loops,
    }


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
            "comprehension_tool_use_ratio": 0.0,
            "window_days": window_days,
            "window_start_ts": cutoff,
        }
    total_calls = sum(int(r.get("mcp_calls", 0)) + len(r.get("tools_used", [])) for r in rows)
    mcp_calls = sum(int(r.get("mcp_calls", 0)) for r in rows)
    reliable_edit_rows = [r for r in rows if is_reliable_edit_loop_row(r, project_root)]
    edit_loops = len(reliable_edit_rows)
    skipped_loops = sum(1 for r in reliable_edit_rows if loop_row_gate_skipped(r, project_root))
    lookup_loops = sum(1 for r in reliable_edit_rows if r.get("lookup_docs_called"))
    # Adoption signal: fraction of loops in the window that used a comprehension
    # tool. Watchable over time to confirm the instructions/nudge actually move
    # behavior — an unused-but-correct tool is a failed tool.
    comprehension_loops = sum(
        1 for r in rows if COMPREHENSION_SHORT_NAMES & {str(t) for t in r.get("tools_used", [])}
    )
    return {
        "loops": loops,
        "mcp_call_ratio": (mcp_calls / total_calls) if total_calls else 0.0,
        "gate_skip_rate": (skipped_loops / edit_loops) if edit_loops else 0.0,
        "lookup_docs_to_edit_ratio": (lookup_loops / edit_loops) if edit_loops else 0.0,
        "comprehension_tool_use_ratio": comprehension_loops / loops,
        "window_days": window_days,
        "window_start_ts": cutoff,
    }


def compute_recent_edit_loop_stats(
    project_root: Path,
    *,
    window_days: int = _PROMOTE_WINDOW_DAYS,
    last_edit_loops: int = _RECENT_EDIT_LOOPS_FOR_GAPS,
) -> dict[str, Any]:
    """Gate-skip and lookup ratios over the most recent edit loops (TAP-4017).

    Unlike ``compute_rolling_stats``, this ignores no-edit loops so compliant
    sessions improve gap warnings without waiting for the full 7-day window
    to roll off stale false-positive rows.
    """
    cutoff = int(time.time()) - window_days * _DAY_SECONDS
    rows = [r for r in read_loop_metrics(project_root) if int(r.get("ts", 0)) >= cutoff]
    edit_rows = [r for r in rows if is_reliable_edit_loop_row(r, project_root)]
    recent = edit_rows[-last_edit_loops:]
    loops = len(recent)
    if loops == 0:
        return {
            "loops": 0,
            "gate_skip_rate": 0.0,
            "lookup_docs_to_edit_ratio": 0.0,
            "window_days": window_days,
            "last_edit_loops": last_edit_loops,
            "window_start_ts": cutoff,
        }
    skipped_loops = sum(1 for r in recent if loop_row_gate_skipped(r, project_root))
    lookup_loops = sum(1 for r in recent if r.get("lookup_docs_called"))
    return {
        "loops": loops,
        "gate_skip_rate": skipped_loops / loops,
        "lookup_docs_to_edit_ratio": lookup_loops / loops,
        "window_days": window_days,
        "last_edit_loops": last_edit_loops,
        "window_start_ts": cutoff,
    }
