"""Fleet-level TAPPS usage audit across bootstrapped project roots (TAP-3572).

Merges local execution-metrics JSONL with optional brain telemetry and
loop-metrics pipeline compliance signals for operator-server visibility.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tapps_core.metrics.brain_telemetry import (
    brain_metrics_bridge_available,
    sync_load_tool_call_metrics_from_brain,
)
from tapps_core.metrics.execution_metrics import ToolCallMetric, ToolCallMetricsCollector
from tapps_mcp.tools.loop_metrics import aggregate_skills_used, compute_rolling_stats

_PERIOD_DAYS: dict[str, int] = {"1d": 1, "7d": 7, "30d": 30}
_BOOTSTRAP_MARKER = ".tapps-mcp.yaml"
_HANDOFF_PATH = Path(".tapps-mcp") / "session-handoff.md"


def _top_tools(metrics: list[ToolCallMetric], *, limit: int = 10) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter(m.tool_name for m in metrics if m.tool_name)
    return [{"name": name, "count": count} for name, count in counts.most_common(limit)]


def _aggregate_fleet_top_tools(
    projects: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for project in projects:
        for entry in project.get("top_tools", []):
            counts[str(entry.get("name", ""))] += int(entry.get("count", 0))
    return [
        {"name": name, "count": count}
        for name, count in counts.most_common(limit)
        if name
    ]


def _aggregate_fleet_skills(
    projects: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> dict[str, Any]:
    skill_counts: Counter[str] = Counter()
    finish_total = 0
    direct_total = 0
    loops = 0
    for project in projects:
        skills = project.get("pipeline", {}).get("skills", {})
        loops += int(skills.get("loops", 0))
        finish_total += int(skills.get("skill_orchestrated_closes", 0))
        direct_total += int(skills.get("direct_mcp_validate_loops", 0))
        for entry in skills.get("top_skills", []):
            skill_counts[str(entry.get("name", ""))] += int(entry.get("count", 0))
    return {
        "loops": loops,
        "top_skills": [
            {"name": name, "count": count}
            for name, count in skill_counts.most_common(limit)
            if name
        ],
        "skill_orchestrated_closes": finish_total,
        "direct_mcp_validate_loops": direct_total,
    }


def parse_period(period: str) -> int:
    """Return window length in days for a period token."""
    key = period.strip().lower()
    if key not in _PERIOD_DAYS:
        msg = f"Invalid period {period!r}; expected one of {sorted(_PERIOD_DAYS)}"
        raise ValueError(msg)
    return _PERIOD_DAYS[key]


def period_cutoff(period: str) -> datetime:
    """UTC cutoff datetime for the trailing window."""
    days = parse_period(period)
    return datetime.now(tz=UTC) - timedelta(days=days)


def discover_project_roots(
    *,
    explicit_roots: list[Path] | None = None,
    scan_parent: Path | None = None,
) -> list[Path]:
    """Resolve bootstrapped project roots for a fleet audit."""
    if explicit_roots:
        return [_normalize_root(r) for r in explicit_roots if _is_bootstrapped(_normalize_root(r))]

    env_roots = os.environ.get("TAPPS_FLEET_ROOTS", "").strip()
    if env_roots:
        candidates = [Path(p.strip()) for p in env_roots.split(",") if p.strip()]
        return [_normalize_root(r) for r in candidates if _is_bootstrapped(_normalize_root(r))]

    parent = (scan_parent or Path.cwd()).resolve()
    if _is_bootstrapped(parent):
        return [parent]

    discovered: list[Path] = []
    if not parent.is_dir():
        return discovered
    for child in sorted(parent.iterdir()):
        if child.is_dir() and _is_bootstrapped(child):
            discovered.append(child.resolve())
    return discovered


def _normalize_root(root: Path) -> Path:
    return root.expanduser().resolve()


def _is_bootstrapped(root: Path) -> bool:
    return (root / _BOOTSTRAP_MARKER).is_file()


def load_jsonl_metrics(
    metrics_dir: Path,
    *,
    since: datetime,
    until: datetime | None = None,
) -> list[ToolCallMetric]:
    """Load tool-call metrics from daily JSONL files (no brain dependency)."""
    if not metrics_dir.is_dir():
        return []

    metrics: list[ToolCallMetric] = []
    for path in sorted(metrics_dir.glob("tool_calls_*.jsonl")):
        try:
            file_date = datetime.fromisoformat(path.stem.replace("tool_calls_", "")).replace(
                tzinfo=UTC
            )
        except ValueError:
            continue
        if file_date.date() < since.date():
            continue
        if until is not None and file_date.date() > until.date():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                metric = ToolCallMetric.from_dict(data)
            except (json.JSONDecodeError, TypeError):
                continue
            if _metric_in_window(metric, since, until):
                metrics.append(metric)
    return metrics


def merge_metrics(
    local: list[ToolCallMetric],
    brain: list[ToolCallMetric],
) -> list[ToolCallMetric]:
    """Merge local and brain metrics, deduplicating by ``call_id``."""
    merged: dict[str, ToolCallMetric] = {m.call_id: m for m in local}
    for metric in brain:
        merged.setdefault(metric.call_id, metric)
    return list(merged.values())


def _metric_in_window(
    metric: ToolCallMetric,
    since: datetime,
    until: datetime | None,
) -> bool:
    try:
        ts = datetime.fromisoformat(metric.started_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return True
    if ts < since:
        return False
    return not (until is not None and ts > until)


def _pipeline_compliance(project_root: Path, *, window_days: int) -> dict[str, Any]:
    stats = compute_rolling_stats(project_root, window_days=window_days)
    skills = aggregate_skills_used(project_root, window_days=window_days)
    rows_total = stats.get("loops", 0)
    return {
        "loop_samples": rows_total,
        "gate_skip_rate": stats.get("gate_skip_rate", 0.0),
        "lookup_docs_to_edit_ratio": stats.get("lookup_docs_to_edit_ratio", 0.0),
        "mcp_call_ratio": stats.get("mcp_call_ratio", 0.0),
        "skills": skills,
    }


def _session_start_lookup_ratio(metrics: list[ToolCallMetric]) -> float | None:
    session_starts = sum(1 for m in metrics if m.tool_name == "tapps_session_start")
    lookups = sum(1 for m in metrics if m.tool_name == "tapps_lookup_docs")
    if session_starts == 0:
        return None
    return round(lookups / session_starts, 4)


def audit_project_root(
    project_root: Path,
    *,
    since: datetime,
    until: datetime | None = None,
    include_brain: bool = True,
    window_days: int = 1,
) -> dict[str, Any]:
    """Audit a single bootstrapped project root."""
    root = _normalize_root(project_root)
    metrics_dir = root / ".tapps-mcp" / "metrics"
    local = load_jsonl_metrics(metrics_dir, since=since, until=until)

    brain_count = 0
    if include_brain and brain_metrics_bridge_available():
        brain = sync_load_tool_call_metrics_from_brain(since=since, until=until, limit=5000)
        brain_count = len(brain)
        metrics = merge_metrics(local, brain)
    else:
        metrics = local

    collector = ToolCallMetricsCollector(metrics_dir)
    summary = collector._compute_summary(metrics)

    handoff_path = root / _HANDOFF_PATH
    handoff_mtime: str | None = None
    if handoff_path.is_file():
        handoff_mtime = datetime.fromtimestamp(handoff_path.stat().st_mtime, tz=UTC).isoformat()

    return {
        "project_root": str(root),
        "bootstrapped": True,
        "top_tools": _top_tools(metrics),
        "metrics": {
            "total_calls": summary.total_calls,
            "local_jsonl_rows": len(local),
            "brain_rows_merged": brain_count,
            "success_rate": summary.success_rate,
            "gate_pass_rate": summary.gate_pass_rate,
            "avg_score": summary.avg_score,
            "session_start_lookup_ratio": _session_start_lookup_ratio(metrics),
        },
        "pipeline": _pipeline_compliance(root, window_days=window_days),
        "handoff": {
            "path": str(_HANDOFF_PATH),
            "exists": handoff_path.is_file(),
            "updated_at": handoff_mtime,
        },
    }


def run_fleet_audit(
    *,
    period: str = "1d",
    roots: list[Path] | None = None,
    scan_parent: Path | None = None,
    include_brain: bool = True,
) -> dict[str, Any]:
    """Run fleet audit and return structured results."""
    window_days = parse_period(period)
    since = period_cutoff(period)
    project_roots = discover_project_roots(explicit_roots=roots, scan_parent=scan_parent)

    projects: list[dict[str, Any]] = []
    for root in project_roots:
        projects.append(
            audit_project_root(
                root,
                since=since,
                include_brain=include_brain,
                window_days=window_days,
            )
        )

    totals = sum(p["metrics"]["total_calls"] for p in projects)
    return {
        "period": period,
        "since": since.isoformat(),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "project_count": len(projects),
        "total_tool_calls": totals,
        "fleet_top_tools": _aggregate_fleet_top_tools(projects),
        "fleet_skills": _aggregate_fleet_skills(projects),
        "projects": projects,
    }


def format_fleet_audit_markdown(report: dict[str, Any]) -> str:
    """Render fleet audit report as Markdown."""
    lines = [
        "# TAPPS fleet audit",
        "",
        f"- **Period:** {report.get('period', '?')}",
        f"- **Since:** {report.get('since', '?')}",
        f"- **Projects:** {report.get('project_count', 0)}",
        f"- **Total tool calls:** {report.get('total_tool_calls', 0)}",
        "",
        "| Project | Calls | Gate pass | Lookup/session | Handoff |",
        "|---------|------:|----------:|---------------:|---------|",
    ]
    for project in report.get("projects", []):
        metrics = project.get("metrics", {})
        name = Path(project.get("project_root", "?")).name
        gate = metrics.get("gate_pass_rate")
        gate_str = f"{gate:.0%}" if gate is not None else "—"
        ratio = metrics.get("session_start_lookup_ratio")
        ratio_str = f"{ratio:.0%}" if ratio is not None else "—"
        handoff = "yes" if project.get("handoff", {}).get("exists") else "no"
        lines.append(
            f"| {name} | {metrics.get('total_calls', 0)} | {gate_str} | {ratio_str} | {handoff} |"
        )

    fleet_tools = report.get("fleet_top_tools") or []
    if fleet_tools:
        lines.extend(["", "## Fleet top tools", ""])
        for entry in fleet_tools[:10]:
            lines.append(f"- `{entry.get('name', '?')}`: {entry.get('count', 0)}")

    for project in report.get("projects", []):
        top_tools = project.get("top_tools") or []
        if not top_tools:
            continue
        name = Path(project.get("project_root", "?")).name
        lines.extend(["", f"### Top tools — {name}", ""])
        for entry in top_tools[:10]:
            lines.append(f"- `{entry.get('name', '?')}`: {entry.get('count', 0)}")

    fleet_skills = report.get("fleet_skills") or {}
    if fleet_skills.get("top_skills"):
        lines.extend(
            [
                "",
                "## Skill utilization (loop-metrics)",
                "",
                f"- **Loops sampled:** {fleet_skills.get('loops', 0)}",
                (
                    "- **Skill-orchestrated closes:** "
                    f"{fleet_skills.get('skill_orchestrated_closes', 0)}"
                ),
                (
                    "- **Direct MCP validate/checklist loops:** "
                    f"{fleet_skills.get('direct_mcp_validate_loops', 0)}"
                ),
                "",
            ]
        )
        for entry in fleet_skills.get("top_skills", [])[:10]:
            lines.append(f"- `{entry.get('name', '?')}`: {entry.get('count', 0)}")

    return "\n".join(lines) + "\n"


def format_tool_usage_fleet_markdown(report: dict[str, Any]) -> str:
    """Render per-tool usage leaderboard as Markdown."""
    lines = [
        "# TAPPS fleet tool usage",
        "",
        f"- **Period:** {report.get('period', '?')}",
        f"- **Projects:** {report.get('project_count', 0)}",
        f"- **Total tool calls:** {report.get('total_tool_calls', 0)}",
        "",
        "## Fleet leaderboard",
        "",
    ]
    for entry in report.get("fleet_top_tools", []):
        lines.append(f"- `{entry.get('name', '?')}`: {entry.get('count', 0)}")
    for project in report.get("projects", []):
        top_tools = project.get("top_tools") or []
        if not top_tools:
            continue
        name = Path(project.get("project_root", "?")).name
        lines.extend(["", f"## {name}", ""])
        for entry in top_tools:
            lines.append(f"- `{entry.get('name', '?')}`: {entry.get('count', 0)}")
    return "\n".join(lines) + "\n"


def run_tool_usage_fleet(
    *,
    period: str = "1d",
    roots: list[Path] | None = None,
    scan_parent: Path | None = None,
    include_brain: bool = True,
) -> dict[str, Any]:
    """Fleet per-tool leaderboard (TAP-3919) — thin wrapper over audit data."""
    report = run_fleet_audit(
        period=period,
        roots=roots,
        scan_parent=scan_parent,
        include_brain=include_brain,
    )
    return {
        "period": report.get("period"),
        "since": report.get("since"),
        "generated_at": report.get("generated_at"),
        "project_count": report.get("project_count"),
        "total_tool_calls": report.get("total_tool_calls"),
        "fleet_top_tools": report.get("fleet_top_tools", []),
        "projects": [
            {
                "project_root": p.get("project_root"),
                "total_calls": p.get("metrics", {}).get("total_calls", 0),
                "top_tools": p.get("top_tools", []),
            }
            for p in report.get("projects", [])
        ],
    }


__all__ = [
    "audit_project_root",
    "discover_project_roots",
    "format_fleet_audit_markdown",
    "format_tool_usage_fleet_markdown",
    "load_jsonl_metrics",
    "merge_metrics",
    "parse_period",
    "period_cutoff",
    "run_fleet_audit",
    "run_tool_usage_fleet",
]
