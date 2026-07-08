"""TAP-1333 / TAP-3927: per-loop MCP-call telemetry — read/aggregate/auto-promote.

Companion module to Stop hooks in
``packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py``,
which append one JSONL line per loop to ``.tapps-mcp/loop-metrics.jsonl``.
This module parses transcripts, records rows, and produces rolling stats for
``tapps_doctor``, ``tapps_dashboard``, fleet audit, and cache-gate auto-promote.
"""

from __future__ import annotations

import json
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from tapps_mcp.tools.pipeline_tool_sets import (
    EDIT_TOOL_NAMES,
    SOURCE_FILE_SUFFIXES,
    is_checklist_tool,
    is_gate_tool,
    is_lookup_tool,
    is_tapps_mcp_server,
    resolve_transcript_tool_name,
)

_METRICS_NAME = "loop-metrics.jsonl"

_FINISH_SKILL_NAMES = frozenset(
    {"tapps-finish-task", "/tapps-finish-task", "finish-task"}
)
_VIOLATIONS_NAME = ".completion-gate-violations.jsonl"
_ROTATE_BYTES = 10 * 1024 * 1024
_DAY_SECONDS = 86_400
_PROMOTE_THRESHOLD = 0.05  # 5% gate-skip rate
_PROMOTE_WINDOW_DAYS = 7


def _metrics_path(project_root: Path) -> Path:
    return project_root / ".tapps-mcp" / _METRICS_NAME


def extract_skill_name(tool_name: str, tool_input: Any) -> str | None:
    """Resolve a slash-skill name from a Skill tool call or SKILL.md Read."""
    if not isinstance(tool_input, dict):
        tool_input = {}
    lowered = tool_name.lower()
    if lowered in {"skill", "skills"}:
        for key in ("skill", "name", "command", "skill_name"):
            raw = tool_input.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip().lstrip("/")
    if tool_name == "Read":
        path_val = tool_input.get("path") or tool_input.get("file_path") or ""
        if isinstance(path_val, str) and "/skills/" in path_val and path_val.endswith("SKILL.md"):
            parts = Path(path_val).parts
            for idx, part in enumerate(parts):
                if part == "skills" and idx + 1 < len(parts):
                    return parts[idx + 1]
    return None


def _iter_transcript_tool_blocks(transcript_path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Yield ``(tool_name, input_dict)`` pairs from a Claude/Cursor JSONL transcript."""
    blocks: list[tuple[str, dict[str, Any]]] = []
    try:
        with transcript_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                msg = row.get("message") or {}
                if not isinstance(msg, dict):
                    continue
                for blk in msg.get("content") or []:
                    if not isinstance(blk, dict):
                        continue
                    if blk.get("type") != "tool_use":
                        continue
                    name = str(blk.get("name") or "")
                    tool_input = blk.get("input")
                    if not isinstance(tool_input, dict):
                        tool_input = {}
                    blocks.append((name, tool_input))
    except OSError:
        return []
    return blocks


def is_scoped_gate_edit(path_str: str, project_root: Path | None) -> bool:
    """True when *path_str* is in-scope for gate-required edit telemetry."""
    if not path_str:
        return False
    if project_root is not None:
        try:
            path = Path(path_str)
            resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
            resolved.relative_to(project_root.resolve())
            return True
        except (ValueError, OSError):
            pass
    normalized = path_str.replace("\\", "/")
    tmp_root = Path(tempfile.gettempdir()).resolve().as_posix()
    if normalized == tmp_root or normalized.startswith(f"{tmp_root}/"):
        return False
    return project_root is None


def _edit_counts_for_gate(path_str: str, project_root: Path | None) -> bool:
    return is_scoped_gate_edit(path_str, project_root)


def scoped_source_edits(paths: list[str], project_root: Path) -> list[str]:
    """In-project source paths that count toward gate-required edit telemetry."""
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


def _legacy_cursor_unparsed_callmcptool(row: dict[str, Any]) -> bool:
    """Pre-TAP-4017 Cursor rows: ``CallMcpTool`` without unwrapped ``tapps_*`` names."""
    tools = [str(t) for t in row.get("tools_used") or []]
    if "CallMcpTool" not in tools:
        return False
    return not any(t.startswith("tapps_") or t.startswith("mcp__") for t in tools)


def is_reliable_edit_loop_row(row: dict[str, Any], project_root: Path) -> bool:
    """False for legacy unparsed Cursor rows or loops with no in-scope source edits."""
    if _legacy_cursor_unparsed_callmcptool(row):
        return False
    files_raw = row.get("files_edited")
    if not files_raw:
        return False
    if isinstance(files_raw, bool):
        return False
    files = files_raw if isinstance(files_raw, list) else []
    return bool(scoped_source_edits([p for p in files if isinstance(p, str)], project_root))


def loop_row_gate_skipped(row: dict[str, Any], project_root: Path) -> bool:
    """True when a reliable edit loop lacks gate/checklist compliance signals."""
    if not is_reliable_edit_loop_row(row, project_root):
        return False
    if row.get("checklist_called"):
        return False
    for tool in row.get("tools_used") or []:
        if is_gate_tool(str(tool)):
            return False
    scoped_skipped = scoped_source_edits(
        [p for p in row.get("gate_skipped_files") or [] if isinstance(p, str)],
        project_root,
    )
    if scoped_skipped:
        return True
    scoped_edited = scoped_source_edits(
        [p for p in row.get("files_edited") or [] if isinstance(p, str)],
        project_root,
    )
    return bool(scoped_edited)


def _mcp_call_from_tool_use(name: str, tool_input: dict[str, Any], resolved_name: str) -> bool:
    if name.startswith("mcp__"):
        return True
    if name != "CallMcpTool":
        return False
    server = str(tool_input.get("server") or "")
    return is_tapps_mcp_server(server) or resolved_name.startswith("tapps_")


def _edit_path_from_tool_use(
    name: str,
    tool_input: dict[str, Any],
    project_root: Path | None,
) -> str | None:
    if name not in EDIT_TOOL_NAMES:
        return None
    fp = tool_input.get("file_path") or tool_input.get("path") or ""
    if not isinstance(fp, str) or not fp or not _edit_counts_for_gate(fp, project_root):
        return None
    return fp


def parse_transcript_loop_metrics(
    transcript_path: Path | None,
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build a loop-metrics row dict from a session transcript path."""
    mcp_calls = 0
    gate_called = False
    checklist_called = False
    lookup_called = False
    tools_used: set[str] = set()
    skills_used: set[str] = set()
    edited_from_transcript: list[str] = []

    if transcript_path is not None and transcript_path.is_file():
        for name, tool_input in _iter_transcript_tool_blocks(transcript_path):
            resolved_name = resolve_transcript_tool_name(name, tool_input)
            tools_used.add(resolved_name)
            if _mcp_call_from_tool_use(name, tool_input, resolved_name):
                mcp_calls += 1
            if is_gate_tool(resolved_name):
                gate_called = True
            if is_checklist_tool(resolved_name):
                checklist_called = True
            if is_lookup_tool(resolved_name):
                lookup_called = True
            edit_path = _edit_path_from_tool_use(name, tool_input, project_root)
            if edit_path is not None:
                edited_from_transcript.append(edit_path)
            skill = extract_skill_name(name, tool_input)
            if skill:
                skills_used.add(skill)

    seen: set[str] = set()
    edits: list[str] = []
    for path in edited_from_transcript:
        if path not in seen:
            seen.add(path)
            edits.append(path)
    needs_gate = any(p.endswith(SOURCE_FILE_SUFFIXES) for p in edits)
    gate_skipped: list[str] = []
    violations: list[str] = []
    if needs_gate and not gate_called:
        violations.append("QUALITY_GATE_SKIP:" + ",".join(edits[:8]))
        gate_skipped = edits
    if needs_gate and not checklist_called:
        violations.append("CHECKLIST_MISSING")

    return {
        "ts": int(time.time()),
        "files_edited": edits,
        "mcp_calls": mcp_calls,
        "gate_skipped_files": gate_skipped,
        "lookup_docs_called": lookup_called,
        "checklist_called": checklist_called,
        "tools_used": sorted(tools_used)[:50],
        "skills_used": sorted(skills_used)[:30],
        "violations": violations,
    }


def _cursor_project_slug(workspace_root: Path) -> str:
    return workspace_root.resolve().as_posix().lstrip("/").replace("/", "-")


def resolve_cursor_transcript_path(
    workspace_root: Path,
    conversation_id: str = "",
) -> Path | None:
    """Best-effort Cursor transcript path from workspace slug + conversation id."""
    base = Path.home() / ".cursor" / "projects" / _cursor_project_slug(workspace_root)
    transcripts = base / "agent-transcripts"
    if not transcripts.is_dir():
        return None
    candidates = list(transcripts.rglob("*.jsonl"))
    if not candidates:
        return None
    if conversation_id:
        matched = [
            p
            for p in candidates
            if conversation_id in p.name or conversation_id in str(p.parent)
        ]
        if matched:
            return max(matched, key=lambda p: p.stat().st_mtime)
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _rotate_if_needed(path: Path) -> None:
    if path.exists() and path.stat().st_size > _ROTATE_BYTES:
        path.replace(path.with_name(path.name + ".1"))


def append_loop_metrics_row(project_root: Path, row: dict[str, Any]) -> None:
    """Append one loop-metrics JSONL row (rotates at 10 MB)."""
    metrics_dir = project_root / ".tapps-mcp"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = _metrics_path(project_root)
    _rotate_if_needed(metrics_path)
    payload = {k: v for k, v in row.items() if k != "violations"}
    with metrics_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def append_completion_gate_violations(
    project_root: Path,
    violations: list[str],
    files_edited: list[str],
) -> None:
    """Warn-mode completion-gate violation log (TAP-1327)."""
    if not violations:
        return
    metrics_dir = project_root / ".tapps-mcp"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    violations_path = metrics_dir / _VIOLATIONS_NAME
    _rotate_if_needed(violations_path)
    with violations_path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "mode": "warn",
                    "reasons": violations,
                    "files_edited": files_edited[:16],
                }
            )
            + "\n"
        )


def resolve_project_root_from_payload(payload: dict[str, Any]) -> Path:
    """Resolve bootstrapped project root from a Cursor/Claude stop-hook payload."""
    env_root = payload.get("project_dir") or payload.get("project_root")
    if isinstance(env_root, str) and env_root.strip():
        return Path(env_root).expanduser().resolve()
    roots = payload.get("workspace_roots") or []
    if roots and isinstance(roots[0], str):
        return Path(roots[0]).expanduser().resolve()
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return Path(cwd).expanduser().resolve()
    return Path.cwd()


def resolve_transcript_from_payload(
    payload: dict[str, Any],
    project_root: Path,
) -> Path | None:
    """Resolve transcript path from hook stdin payload."""
    for key in ("transcript_path", "agent_transcript_path"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            candidate = Path(raw).expanduser()
            if candidate.is_file():
                return candidate
    conv_id = str(payload.get("conversation_id") or "")
    return resolve_cursor_transcript_path(project_root, conv_id)


def record_loop_metrics_from_hook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Record loop-metrics from a Cursor/Claude stop-hook stdin payload."""
    from tapps_core.config.settings import load_settings
    from tapps_mcp.tools.usage import (
        append_call_graph_stop_followup,
        compute_gaps,
        format_stop_gap_followup,
    )

    project_root = resolve_project_root_from_payload(payload)
    transcript = resolve_transcript_from_payload(payload, project_root)
    row = parse_transcript_loop_metrics(transcript, project_root=project_root)
    append_loop_metrics_row(project_root, row)
    violations = list(row.get("violations") or [])
    if violations:
        append_completion_gate_violations(
            project_root,
            violations,
            list(row.get("files_edited") or []),
        )

    settings = load_settings(project_root)
    gate_mode = settings.cursor_stop_completion_gate_resolved()
    called_tools = {str(t) for t in row.get("tools_used", []) if t}
    usage_gaps = compute_gaps(project_root, called_tools=called_tools)
    followup = format_stop_gap_followup(
        project_root,
        called_tools=called_tools,
        mode=gate_mode,
        fresh_violations=violations,
    )
    followup = append_call_graph_stop_followup(
        followup,
        project_root,
        files_edited=[str(f) for f in row.get("files_edited") or []],
        called_tools=called_tools,
    )

    return {
        "recorded": True,
        "project_root": str(project_root),
        "transcript": str(transcript) if transcript else None,
        "violations": violations,
        "completion_gate_mode": gate_mode,
        "usage_gaps": usage_gaps.get("gaps", []),
        "followup_message": followup,
    }


def read_loop_metrics(project_root: Path, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` loop-metrics rows. Best-effort, no raise."""
    path = _metrics_path(project_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-limit:]


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
        if isinstance(tools, list) and any(
            is_gate_tool(str(t)) or is_checklist_tool(str(t)) for t in tools
        ):
            if not skills:
                direct_validate_loops += 1
    top_skills = [
        {"name": name, "count": count}
        for name, count in skill_counts.most_common(10)
    ]
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
    skipped_loops = sum(
        1 for r in reliable_edit_rows if loop_row_gate_skipped(r, project_root)
    )
    lookup_loops = sum(1 for r in reliable_edit_rows if r.get("lookup_docs_called"))
    # Adoption signal: fraction of loops in the window that used a comprehension
    # tool. Watchable over time to confirm the instructions/nudge actually move
    # behavior — an unused-but-correct tool is a failed tool.
    from tapps_mcp.tools.pipeline_tool_sets import COMPREHENSION_SHORT_NAMES

    comprehension_loops = sum(
        1
        for r in rows
        if COMPREHENSION_SHORT_NAMES & {str(t) for t in r.get("tools_used", [])}
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


_RECENT_EDIT_LOOPS_FOR_GAPS = 10


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


__all__ = [
    "aggregate_skills_used",
    "append_completion_gate_violations",
    "append_loop_metrics_row",
    "compute_gate_pass_rate_7d",
    "compute_recent_edit_loop_stats",
    "compute_rolling_stats",
    "extract_skill_name",
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
]
