"""tapps_usage — per-session gap report on agent tool usage.

Composes data from three substrates that already exist:

* ``CallTracker.get_called_tools()`` — in-process set of tools called this
  server session (populated by ``_record_call``).
* ``.tapps-mcp/loop-metrics.jsonl`` — per-Stop-event telemetry written by
  the ``tapps-stop.sh`` hook (files_edited, mcp_calls, gate_skipped,
  lookup_docs_called, checklist_called).
* ``.tapps-mcp/.completion-gate-violations.jsonl`` — warn-mode violation
  log written when a Stop hook detects edits without validation/checklist.

Produces a "what did I miss?" payload — the gaps between what the agent
did and what the TAPPS pipeline recommends. Used both as a standalone tool
and as an inline field on ``tapps_checklist`` responses.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

from tapps_mcp.tools.loop_metrics import compute_rolling_stats, read_loop_metrics
from tapps_mcp.tools.pipeline_tool_sets import (
    GATE_SHORT_NAMES,
    matches_pipeline_tool,
)

_VIOLATIONS_NAME = ".completion-gate-violations.jsonl"
_CHECKLIST_TOOL = "tapps_checklist"
_LOOKUP_TOOL = "tapps_lookup_docs"
_IMPACT_TOOL = "tapps_impact_analysis"
_SESSION_INIT_TOOL = "tapps_session_start"
_PRIORITY_GAPS: tuple[str, ...] = (
    "edits_without_validation",
    "checklist_skipped",
    "lookup_docs_underused",
    "library_uses_without_lookup_docs",
)


def _violations_path(project_root: Path) -> Path:
    return project_root / ".tapps-mcp" / _VIOLATIONS_NAME


def read_recent_violations(project_root: Path, *, limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent completion-gate violations. Best-effort, no raise."""
    path = _violations_path(project_root)
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
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        return []
    return rows[-limit:]


def _session_called_tools() -> set[str]:
    """Return tools called in the current MCP server session. Empty on import failure."""
    try:
        from tapps_mcp.tools.checklist import CallTracker

        return CallTracker.get_called_tools()
    except Exception:  # noqa: BLE001
        return set()


def _strip_mcp_prefix(name: str) -> str:
    """Normalize ``mcp__server__tool`` → ``tool`` for cross-substrate comparison."""
    if not name.startswith("mcp__"):
        return name
    parts = name.split("__", 2)
    return parts[2] if len(parts) >= 3 else name


def _normalize(names: set[str]) -> set[str]:
    return {_strip_mcp_prefix(n) for n in names}


def compute_gaps(
    project_root: Path,
    *,
    called_tools: set[str] | None = None,
    rolling_window_days: int = 7,
) -> dict[str, Any]:
    """Compute the agent's per-session gaps and surface a recommendation list.

    Args:
        project_root: project root path used to locate the telemetry files.
        called_tools: optional override (mainly for tests). Defaults to the
            in-process ``CallTracker`` view.
        rolling_window_days: trailing window for loop-metrics aggregation.

    Returns:
        Dict with ``gaps`` (list of gap-name strings), ``called_tools`` (sorted),
        ``rolling_stats`` (from ``compute_rolling_stats``), ``recent_violations``
        (last 5 violation rows), and ``recommendations`` (human-readable strings).
    """
    called_raw = called_tools if called_tools is not None else _session_called_tools()
    called = _normalize(called_raw)

    rows = read_loop_metrics(project_root, limit=50)
    rolling = compute_rolling_stats(project_root, window_days=rolling_window_days)
    violations = read_recent_violations(project_root, limit=5)

    gaps: list[str] = []
    recs: list[str] = []

    if _SESSION_INIT_TOOL not in called and rows:
        gaps.append("session_start_skipped")
        recs.append(
            "Call tapps_session_start() at the top of every session — checker "
            "matrix and project context are stale otherwise."
        )

    edited_recent = [p for r in rows[-10:] for p in r.get("files_edited", [])]
    has_recent_edits = bool(edited_recent)
    used_gate = any(matches_pipeline_tool(name, GATE_SHORT_NAMES) for name in called)
    if has_recent_edits and not used_gate:
        gaps.append("edits_without_validation")
        sample = ",".join(edited_recent[:3])
        recs.append(
            f"Files were edited (e.g. {sample}) but no quality gate was run. "
            f"Call tapps_validate_changed(file_paths=\"{sample}\") before declaring done."
        )

    if has_recent_edits and _CHECKLIST_TOOL not in called:
        gaps.append("checklist_skipped")
        recs.append(
            "tapps_checklist was not called this session. Invoke "
            "/tapps-finish-task or tapps_checklist(task_type=<feature|bugfix|refactor|security>) "
            "before declaring done."
        )

    if rolling.get("loops", 0) >= 3:
        skip_rate = rolling.get("gate_skip_rate", 0.0)
        if skip_rate >= 0.5:
            gaps.append("recurring_validation_skips")
            pct = int(round(skip_rate * 100))
            recs.append(
                f"Quality gate has been skipped on {pct}% of recent edit loops "
                f"({rolling['loops']} loops, last {rolling_window_days}d). "
                "Consider raising engagement to high so tapps-task-completed.sh blocks instead of warns."
            )
        lookup_ratio = rolling.get("lookup_docs_to_edit_ratio", 0.0)
        if lookup_ratio < 0.2 and any(r.get("files_edited") for r in rows):
            gaps.append("lookup_docs_underused")
            recs.append(
                "tapps_lookup_docs was rarely called before edits. Use it for "
                "any external library API to avoid hallucinated calls."
            )

    if _LOOKUP_TOOL not in called and has_recent_edits:
        if "lookup_docs_underused" not in gaps:
            gaps.append("library_uses_without_lookup_docs")
            recs.append(
                "No tapps_lookup_docs calls this session despite recent edits. "
                "Call it before using any external library API."
            )

    if not gaps:
        recs.append("No gaps detected. Pipeline coverage looks healthy.")

    return {
        "gaps": gaps,
        "called_tools": sorted(called),
        "called_tools_count": len(called),
        "edited_files_recent": edited_recent[:20],
        "rolling_stats": rolling,
        "recent_violations": violations,
        "recommendations": recs,
        "generated_ts": int(time.time()),
    }


def format_session_start_gap_hint(project_root: Path) -> str | None:
    """One-line prior-session pipeline reminder for SessionStart hooks (TAP-3578).

    Uses disk-only telemetry (loop-metrics + completion-gate violations) so hooks
    and CLI invocations work without an active MCP ``CallTracker`` session.
    """
    violations = read_recent_violations(project_root, limit=20)
    violation_tags: list[str] = []
    for row in violations:
        for reason in row.get("reasons", []):
            if isinstance(reason, str):
                violation_tags.append(reason.split(":", 1)[0])

    report = compute_gaps(project_root, called_tools=set())
    gaps = list(report.get("gaps", []))
    recs = [r for r in report.get("recommendations", []) if "No gaps detected" not in r]

    if "CHECKLIST_MISSING" in violation_tags and "checklist_skipped" not in gaps:
        gaps.insert(0, "checklist_skipped")
    if any(t.startswith("QUALITY_GATE_SKIP") for t in violation_tags):
        if "edits_without_validation" not in gaps:
            gaps.insert(0, "edits_without_validation")

    if not gaps:
        return None

    if "CHECKLIST_MISSING" in violation_tags:
        return (
            "Last session ended without tapps_checklist after edits — run "
            "tapps_validate_changed + tapps_checklist before declaring done."
        )
    if recs:
        return f"{', '.join(gaps[:3])}: {recs[0]}"
    return ", ".join(gaps[:3])


def format_stop_gap_followup(
    project_root: Path,
    *,
    called_tools: set[str],
    mode: Literal["off", "warn", "block"],
    fresh_violations: list[str] | None = None,
) -> str | None:
    """Build Cursor stop-hook followup_message from ``compute_gaps`` (TAP-3921)."""
    if mode == "off":
        return None

    report = compute_gaps(project_root, called_tools=called_tools)
    gaps = list(report.get("gaps", []))
    if fresh_violations:
        if any("QUALITY_GATE_SKIP" in reason for reason in fresh_violations):
            if "edits_without_validation" not in gaps:
                gaps.insert(0, "edits_without_validation")
        if "CHECKLIST_MISSING" in fresh_violations and "checklist_skipped" not in gaps:
            gaps.insert(0, "checklist_skipped")

    if not gaps:
        return None

    ordered = [g for key in _PRIORITY_GAPS for g in gaps if g == key]
    ordered.extend(g for g in gaps if g not in ordered)
    headline = ", ".join(ordered[:3])
    recs = [r for r in report.get("recommendations", []) if "No gaps detected" not in r]
    body = recs[0] if recs else "Run /tapps-finish-task before declaring done."

    if mode == "block":
        return f"BLOCKED — pipeline gaps ({headline}). {body}"
    return f"TappsMCP pipeline gaps ({headline}). {body}"


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact markdown summary of a gap report."""
    lines: list[str] = ["## tapps_usage gap report"]
    rolling = report.get("rolling_stats", {})
    lines.append(
        f"- Session calls: {report.get('called_tools_count', 0)} unique tools | "
        f"Window: last {rolling.get('window_days', 7)}d ({rolling.get('loops', 0)} loops)"
    )
    skip_pct = int(round(rolling.get("gate_skip_rate", 0.0) * 100))
    lookup_pct = int(round(rolling.get("lookup_docs_to_edit_ratio", 0.0) * 100))
    lines.append(
        f"- Rolling gate-skip rate: {skip_pct}% | lookup-docs-to-edit ratio: {lookup_pct}%"
    )
    gaps = report.get("gaps", [])
    if gaps:
        lines.append(f"- **Gaps detected ({len(gaps)}):** " + ", ".join(gaps))
    else:
        lines.append("- **Gaps detected:** none")
    if report.get("recommendations"):
        lines.append("")
        lines.append("### Recommendations")
        for rec in report["recommendations"]:
            lines.append(f"- {rec}")
    return "\n".join(lines)


__all__ = [
    "compute_gaps",
    "format_session_start_gap_hint",
    "format_stop_gap_followup",
    "read_recent_violations",
    "render_markdown",
]
