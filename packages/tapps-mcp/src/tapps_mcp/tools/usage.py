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

from tapps_mcp.pipeline.agent_contract import (
    CALL_GRAPH_STOP_FOLLOWUP,
    CHECKLIST_SKIPPED_REC,
    SESSION_START_CHECKLIST_GAP_HINT,
    STOP_GAP_FOLLOWUP_DEFAULT,
    lookup_gap_recommendation,
)
from tapps_mcp.tools.loop_metrics import (
    compute_recent_edit_loop_stats,
    compute_rolling_stats,
    is_scoped_gate_edit,
    read_loop_metrics,
)
from tapps_mcp.tools.pipeline_tool_sets import (
    COMPREHENSION_SHORT_NAMES,
    GATE_SHORT_NAMES,
    LOOKUP_SHORT_NAMES,
    SOURCE_FILE_SUFFIXES,
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
                except Exception:
                    continue
    except Exception:
        return []
    return rows[-limit:]


def _session_called_tools() -> set[str]:
    """Return tools called in the current MCP server session. Empty on import failure."""
    try:
        from tapps_mcp.tools.checklist import CallTracker

        return CallTracker.get_called_tools()
    except Exception:
        return set()


def _strip_mcp_prefix(name: str) -> str:
    """Normalize ``mcp__server__tool`` → ``tool`` for cross-substrate comparison."""
    if not name.startswith("mcp__"):
        return name
    parts = name.split("__", 2)
    return parts[2] if len(parts) >= 3 else name


def _normalize(names: set[str]) -> set[str]:
    return {_strip_mcp_prefix(n) for n in names}


def _scoped_source_edits(paths: list[str], project_root: Path) -> list[str]:
    seen: set[str] = set()
    scoped: list[str] = []
    for path in paths:
        if path in seen:
            continue
        if not is_scoped_gate_edit(path, project_root):
            continue
        if not str(path).endswith(SOURCE_FILE_SUFFIXES):
            continue
        seen.add(path)
        scoped.append(path)
    return scoped


def _telemetry_used_gate(rows: list[dict[str, Any]]) -> bool:
    for row in reversed(rows[-5:]):
        for tool in row.get("tools_used") or []:
            if matches_pipeline_tool(str(tool), GATE_SHORT_NAMES):
                return True
    return False


def _telemetry_used_checklist(rows: list[dict[str, Any]]) -> bool:
    return any(bool(row.get("checklist_called")) for row in rows[-5:])


def _telemetry_used_lookup(rows: list[dict[str, Any]], project_root: Path | None = None) -> bool:
    for row in reversed(rows[-5:]):
        if row.get("lookup_docs_called"):
            return True
        for tool in row.get("tools_used") or []:
            if matches_pipeline_tool(str(tool), LOOKUP_SHORT_NAMES):
                return True
    if project_root is not None:
        try:
            from tapps_mcp.tools.lookup_telemetry import lookup_recorded_recently

            if lookup_recorded_recently(project_root):
                return True
        except Exception:
            pass
    return False


def _resolve_edited_path(raw: str, project_root: Path) -> Path | None:
    """Resolve a telemetry file path to an on-disk path under *project_root*."""
    path = Path(raw)
    if path.is_file():
        return path
    candidate = project_root / raw
    if candidate.is_file():
        return candidate
    if path.is_absolute():
        try:
            rel = path.relative_to(project_root)
            under = project_root / rel
            if under.is_file():
                return under
        except ValueError:
            pass
    return None


def _lookup_gap_libraries(project_root: Path, edited_paths: list[str]) -> list[str]:
    """External libraries in edited Python files that lack cached docs.

    Returns an empty list when edits are test-only stdlib/skip-module imports
    (nothing worth a ``tapps_lookup_docs`` call). Non-Python edits are ignored
    here — callers fall back to a generic recommendation.
    """
    try:
        from tapps_mcp.common.cache_paths import resolve_kb_cache_dir
        from tapps_mcp.knowledge.cache import KBCache
        from tapps_mcp.knowledge.import_analyzer import (
            extract_external_imports,
            find_uncached_libraries,
        )
    except ImportError:
        return []

    py_paths = [p for p in edited_paths if str(p).endswith((".py", ".pyi"))]
    if not py_paths:
        return []

    external: set[str] = set()
    for raw in py_paths:
        resolved = _resolve_edited_path(raw, project_root)
        if resolved is None:
            continue
        external.update(extract_external_imports(resolved, project_root))

    if not external:
        return []

    try:
        cache_dir, _ = resolve_kb_cache_dir(project_root)
        cache = KBCache(cache_dir)
        return find_uncached_libraries(sorted(external), cache)
    except Exception:
        return sorted(external)


def _lookup_gap_recommendation(libraries: list[str], *, generic: bool) -> str:
    return lookup_gap_recommendation(libraries, generic=generic)


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
    recent_edits = compute_recent_edit_loop_stats(
        project_root, window_days=rolling_window_days
    )
    violations = read_recent_violations(project_root, limit=5)

    gaps: list[str] = []
    recs: list[str] = []

    if _SESSION_INIT_TOOL not in called:
        gaps.append("session_start_skipped")
        recs.append(
            "Call tapps_session_start() at the top of every session — checker "
            "matrix and project context are stale otherwise."
        )

    edited_recent = _scoped_source_edits(
        [p for r in rows[-10:] for p in r.get("files_edited", []) if isinstance(p, str)],
        project_root,
    )
    has_recent_edits = bool(edited_recent)
    uncached_libs_in_edits = (
        _lookup_gap_libraries(project_root, edited_recent) if has_recent_edits else []
    )
    used_gate = any(matches_pipeline_tool(name, GATE_SHORT_NAMES) for name in called) or (
        _telemetry_used_gate(rows)
    )
    if has_recent_edits and not used_gate:
        gaps.append("edits_without_validation")
        sample = ",".join(edited_recent[:3])
        recs.append(
            f"Files were edited (e.g. {sample}) but no quality gate was run. "
            f'Call tapps_validate_changed(file_paths="{sample}") before declaring done.'
        )

    used_checklist = _CHECKLIST_TOOL in called or _telemetry_used_checklist(rows)
    if has_recent_edits and not used_checklist:
        gaps.append("checklist_skipped")
        recs.append(CHECKLIST_SKIPPED_REC)

    recent_edit_loops = int(recent_edits.get("loops", 0))
    if recent_edit_loops >= 3:
        skip_rate = float(recent_edits.get("gate_skip_rate", 0.0))
        if skip_rate >= 0.5:
            gaps.append("recurring_validation_skips")
            pct = int(round(skip_rate * 100))
            recs.append(
                f"Quality gate has been skipped on {pct}% of recent edit loops "
                f"({recent_edit_loops} loops, last {rolling_window_days}d). "
                "Consider raising engagement to high so tapps-task-completed.sh blocks instead of warns."
            )
        lookup_ratio = float(recent_edits.get("lookup_docs_to_edit_ratio", 0.0))
        if lookup_ratio < 0.2 and uncached_libs_in_edits:
            gaps.append("lookup_docs_underused")
            recs.append(
                "tapps_lookup_docs was rarely called before edits. Use it for "
                "any external library API to avoid hallucinated calls."
            )

    used_lookup = _LOOKUP_TOOL in called or _telemetry_used_lookup(rows, project_root)
    libraries_without_lookup: list[str] = []
    if not used_lookup and has_recent_edits and "lookup_docs_underused" not in gaps:
        libraries_without_lookup = uncached_libs_in_edits
        py_edits = [p for p in edited_recent if str(p).endswith((".py", ".pyi"))]
        non_py_edits = [p for p in edited_recent if not str(p).endswith((".py", ".pyi"))]
        should_gap = bool(libraries_without_lookup) or bool(non_py_edits and not py_edits)
        if should_gap:
            gaps.append("library_uses_without_lookup_docs")
            rec = _lookup_gap_recommendation(
                libraries_without_lookup,
                generic=bool(non_py_edits and not py_edits),
            )
            if rec:
                recs.append(rec)

    # Comprehension-tool underuse: a cross-module edit set with no blast-radius
    # check. Uses per-row ``tools_used`` telemetry (deterministic) plus the live
    # CallTracker view so it fires whether driven from a tool session or a hook.
    recent_tools = {
        t for r in rows[-10:] for t in r.get("tools_used", []) if isinstance(t, str)
    }
    used_comprehension = any(
        matches_pipeline_tool(t, COMPREHENSION_SHORT_NAMES) for t in recent_tools
    ) or any(
        matches_pipeline_tool(t, COMPREHENSION_SHORT_NAMES) for t in called
    )
    if has_recent_edits and not used_comprehension:
        parent_dirs = {str(Path(p).parent) for p in edited_recent}
        if len(edited_recent) >= 3 and len(parent_dirs) >= 2:
            gaps.append("comprehension_tools_underused")
            recs.append(
                f"Edits span {len(parent_dirs)} modules ({len(edited_recent)} files) "
                "but no call-graph / impact analysis was run. Call "
                f'tapps_impact_analysis(file_path="{edited_recent[0]}") or '
                "tapps_call_graph(symbol=...) to check callers and blast radius "
                "before finishing."
            )

    if not gaps:
        recs.append("No gaps detected. Pipeline coverage looks healthy.")

    return {
        "gaps": gaps,
        "called_tools": sorted(called),
        "called_tools_count": len(called),
        "edited_files_recent": edited_recent[:20],
        "libraries_without_lookup": libraries_without_lookup,
        "rolling_stats": rolling,
        "recent_edit_stats": recent_edits,
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
        return SESSION_START_CHECKLIST_GAP_HINT
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
    body = recs[0] if recs else STOP_GAP_FOLLOWUP_DEFAULT
    if ordered and ordered[0] == "library_uses_without_lookup_docs":
        libs = report.get("libraries_without_lookup") or []
        if libs:
            body = _lookup_gap_recommendation(libs, generic=False)
        else:
            for rec in recs:
                if "tapps_lookup_docs" in rec:
                    body = rec
                    break
    elif ordered and recs:
        gap_to_keyword = {
            "edits_without_validation": "quality gate",
            "checklist_skipped": "tapps_checklist",
            "lookup_docs_underused": "tapps_lookup_docs",
        }
        keyword = gap_to_keyword.get(ordered[0])
        if keyword:
            for rec in recs:
                if keyword in rec:
                    body = rec
                    break

    if mode == "block":
        return f"BLOCKED — pipeline gaps ({headline}). {body}"
    return f"TappsMCP pipeline gaps ({headline}). {body}"


def append_call_graph_stop_followup(
    followup: str | None,
    project_root: Path,
    *,
    files_edited: list[str],
    called_tools: set[str],
) -> str | None:
    """Append stale call-graph note when source was edited but graph tools were skipped."""
    if not any(str(path).endswith(SOURCE_FILE_SUFFIXES) for path in files_edited):
        return followup
    # validate_changed does not rebuild/query the call graph by default — only
    # the dedicated graph tools suppress the stale-graph nudge.
    if {"tapps_call_graph", "tapps_diff_impact"} & called_tools:
        return followup
    from tapps_mcp.project.call_graph_cache import summarize_call_graph_cache

    summary = summarize_call_graph_cache(project_root)
    if not summary.get("stale"):
        return followup
    if followup:
        return f"{followup} {CALL_GRAPH_STOP_FOLLOWUP}"
    return f"TappsMCP: {CALL_GRAPH_STOP_FOLLOWUP}"


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
        libs = report.get("libraries_without_lookup") or []
        if libs:
            lines.append(f"- **Libraries without lookup:** {', '.join(libs[:12])}")
    else:
        lines.append("- **Gaps detected:** none")
    if report.get("recommendations"):
        lines.append("")
        lines.append("### Recommendations")
        for rec in report["recommendations"]:
            lines.append(f"- {rec}")
    return "\n".join(lines)


__all__ = [
    "append_call_graph_stop_followup",
    "compute_gaps",
    "format_session_start_gap_hint",
    "format_stop_gap_followup",
    "read_recent_violations",
    "render_markdown",
]
