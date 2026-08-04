"""TAP-1333 / TAP-3927: per-loop MCP-call telemetry — read/aggregate/auto-promote.

Companion module to Stop hooks in
``packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py``,
which append one JSONL line per loop to ``.tapps-mcp/loop-metrics.jsonl``.

Split under TAP-5606 — heavy lifting lives in sibling modules:

* :mod:`tapps_mcp.tools.loop_metrics_scope` — gate-scope + row reliability
* :mod:`tapps_mcp.tools.loop_metrics_parse` — transcript parse
* :mod:`tapps_mcp.tools.loop_metrics_io` — JSONL path helpers + append/read
* :mod:`tapps_mcp.tools.loop_metrics_record` — stop-hook recorder + gate mode
* :mod:`tapps_mcp.tools.loop_metrics_aggregate` — rolling / skill aggregates
* :mod:`tapps_mcp.tools.loop_metrics_promote` — auto-promote + gate rates

This facade re-exports the public (and doctor-private) API so existing imports
of ``tapps_mcp.tools.loop_metrics`` stay stable.
"""

from __future__ import annotations

from tapps_mcp.tools.loop_metrics_aggregate import (
    _DAY_SECONDS as _DAY_SECONDS,
)
from tapps_mcp.tools.loop_metrics_aggregate import (
    _PROMOTE_WINDOW_DAYS as _PROMOTE_WINDOW_DAYS,
)
from tapps_mcp.tools.loop_metrics_aggregate import (
    aggregate_skills_used,
    compute_recent_edit_loop_stats,
    compute_rolling_stats,
)
from tapps_mcp.tools.loop_metrics_io import (
    append_completion_gate_violations,
    append_loop_metrics_row,
    read_loop_metrics,
    resolve_cursor_transcript_path,
)
from tapps_mcp.tools.loop_metrics_parse import parse_transcript_loop_metrics
from tapps_mcp.tools.loop_metrics_promote import (
    compute_gate_pass_rate_7d,
    count_session_start_gate_violations,
    should_auto_promote_cache_gate,
    should_auto_promote_session_start_gate,
)
from tapps_mcp.tools.loop_metrics_record import (
    count_consecutive_gate_skips as count_consecutive_gate_skips,
)
from tapps_mcp.tools.loop_metrics_record import (
    record_loop_metrics_from_hook_payload,
    resolve_project_root_from_payload,
    resolve_transcript_from_payload,
)
from tapps_mcp.tools.loop_metrics_record import (
    resolve_completion_gate_mode as resolve_completion_gate_mode,
)
from tapps_mcp.tools.loop_metrics_scope import (
    _legacy_cursor_unparsed_callmcptool as _legacy_cursor_unparsed_callmcptool,
)
from tapps_mcp.tools.loop_metrics_scope import (
    extract_skill_name,
    is_reliable_edit_loop_row,
    is_scoped_gate_edit,
    loop_row_gate_skipped,
    scoped_source_edits,
)
from tapps_mcp.tools.pipeline_tool_sets import is_gate_tool

__all__ = [
    "aggregate_skills_used",
    "append_completion_gate_violations",
    "append_loop_metrics_row",
    "compute_gate_pass_rate_7d",
    "compute_recent_edit_loop_stats",
    "compute_rolling_stats",
    "count_session_start_gate_violations",
    "extract_skill_name",
    "is_gate_tool",
    "is_reliable_edit_loop_row",
    "is_scoped_gate_edit",
    "loop_row_gate_skipped",
    "parse_transcript_loop_metrics",
    "read_loop_metrics",
    "record_loop_metrics_from_hook_payload",
    "resolve_cursor_transcript_path",
    "resolve_project_root_from_payload",
    "resolve_transcript_from_payload",
    "scoped_source_edits",
    "should_auto_promote_cache_gate",
    "should_auto_promote_session_start_gate",
]
