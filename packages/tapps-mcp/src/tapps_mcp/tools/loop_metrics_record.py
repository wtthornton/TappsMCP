"""Stop-hook recording and completion-gate mode for loop metrics (TAP-5606)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_mcp.tools.loop_metrics_io import (
    append_completion_gate_violations,
    append_loop_metrics_row,
    read_loop_metrics,
    resolve_cursor_transcript_path,
)
from tapps_mcp.tools.loop_metrics_parse import parse_transcript_loop_metrics


def _row_looks_like_gate_skip(row: dict[str, Any]) -> bool:
    skipped = bool(row.get("gate_skipped_files")) or not bool(row.get("checklist_called"))
    reasons = row.get("violations") or []
    if any(
        isinstance(r, str) and (r.startswith("QUALITY_GATE_SKIP") or r == "CHECKLIST_MISSING")
        for r in reasons
    ):
        return True
    return skipped


def count_consecutive_gate_skips(project_root: Path, *, limit: int = 50) -> int:
    """Count trailing consecutive edit loops that skipped gate or checklist (TAP-5274)."""
    consecutive = 0
    for row in reversed(read_loop_metrics(project_root, limit=limit)):
        if not isinstance(row, dict):
            continue
        if not (row.get("files_edited") or []):
            continue
        if not _row_looks_like_gate_skip(row):
            break
        consecutive += 1
    return consecutive


def resolve_completion_gate_mode(settings: object, project_root: Path) -> str:
    """Resolve effective completion-gate mode, escalating in ralph_mode (TAP-5274)."""
    resolved = "warn"
    resolve = getattr(settings, "cursor_stop_completion_gate_resolved", None)
    if callable(resolve):
        resolved = str(resolve())
    ralph = bool(getattr(settings, "ralph_mode", False))
    if not ralph or resolved == "off":
        return resolved
    threshold = int(getattr(settings, "ralph_consecutive_skip_threshold", 3) or 3)
    if count_consecutive_gate_skips(project_root) >= threshold:
        return "block"
    return resolved


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

    settings = load_settings(project_root)
    gate_mode = resolve_completion_gate_mode(settings, project_root)
    called_tools = {str(t) for t in row.get("tools_used", []) if t}
    usage_gaps = compute_gaps(project_root, called_tools=called_tools)
    if violations:
        append_completion_gate_violations(
            project_root,
            violations,
            list(row.get("files_edited") or []),
            mode=gate_mode if gate_mode in {"warn", "block"} else "warn",
        )
    followup = format_stop_gap_followup(
        project_root,
        called_tools=called_tools,
        mode=gate_mode,  # type: ignore[arg-type]
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
