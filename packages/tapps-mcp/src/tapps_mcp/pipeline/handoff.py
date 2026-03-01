"""Render and parse TAPPS handoff markdown files."""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

from tapps_mcp.pipeline.models import HandoffState, PipelineStage, RunlogEntry, StageResult


def _render_list_section(lines: list[str], header: str, items: list[str]) -> None:
    """Append a bold-header + bulleted list to *lines* if *items* is non-empty."""
    if items:
        lines.append(f"**{header}:**")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")


def render_handoff(state: HandoffState) -> str:
    """Render a ``HandoffState`` to markdown suitable for ``TAPPS_HANDOFF.md``."""
    lines: list[str] = [
        "# TAPPS Handoff",
        "",
        f"**Objective:** {state.objective}",
        "",
        "---",
        "",
    ]

    for result in state.stage_results:
        lines.append(f"## Stage: {result.stage.value.capitalize()}")
        lines.append("")
        lines.append(f"**Completed:** {result.completed_at.isoformat()}")
        lines.append(f"**Tools called:** {', '.join(result.tools_called) or 'none'}")
        lines.append("")

        _render_list_section(lines, "Findings", result.findings)
        _render_list_section(lines, "Decisions", result.decisions)
        _render_list_section(lines, "Files in scope", result.files_in_scope)
        _render_list_section(lines, "Open questions", result.open_questions)

        lines.append("---")
        lines.append("")

    if state.next_stage_instructions:
        lines.append(f"**Next:** {state.next_stage_instructions}")
        lines.append("")

    return "\n".join(lines)


def render_runlog_entry(entry: RunlogEntry) -> str:
    """Render a single run-log entry as a log line."""
    ts = entry.timestamp.isoformat()
    return f"[{ts}] [{entry.stage.value}] {entry.action} - {entry.details}"


def parse_handoff(content: str) -> HandoffState:
    """Parse a TAPPS_HANDOFF.md file into a ``HandoffState`` (best-effort).

    This parser handles the standard format produced by ``render_handoff``.
    Non-standard content is silently skipped.
    """
    from datetime import datetime as _dt

    objective = ""
    obj_match = re.search(r"\*\*Objective:\*\*\s*(.+)", content)
    if obj_match:
        objective = obj_match.group(1).strip()

    stage_pattern = re.compile(
        r"## Stage:\s*(\w+)\s*\n(.*?)(?=\n## Stage:|\n---\s*$|\Z)",
        re.DOTALL,
    )

    results: list[StageResult] = []
    current_stage = PipelineStage.DISCOVER

    for match in stage_pattern.finditer(content):
        stage_name = match.group(1).strip().lower()
        body = match.group(2)

        try:
            stage = PipelineStage(stage_name)
        except ValueError:
            continue

        current_stage = stage

        completed_at: datetime = _dt.now()
        ts_match = re.search(r"\*\*Completed:\*\*\s*(.+)", body)
        if ts_match:
            ts_str = ts_match.group(1).strip()
            with contextlib.suppress(ValueError):
                completed_at = _dt.fromisoformat(ts_str)

        tools_called: list[str] = []
        tools_match = re.search(r"\*\*Tools called:\*\*\s*(.+)", body)
        if tools_match:
            raw = tools_match.group(1).strip()
            if raw and raw != "none":
                tools_called = [t.strip() for t in raw.split(",") if t.strip()]

        findings = _extract_list(body, "Findings")
        decisions = _extract_list(body, "Decisions")
        files_in_scope = _extract_list(body, "Files in scope")
        open_questions = _extract_list(body, "Open questions")

        results.append(
            StageResult(
                stage=stage,
                completed_at=completed_at,
                tools_called=tools_called,
                findings=findings,
                decisions=decisions,
                files_in_scope=files_in_scope,
                open_questions=open_questions,
            )
        )

    return HandoffState(
        current_stage=current_stage,
        objective=objective,
        stage_results=results,
    )


def _extract_list(body: str, header: str) -> list[str]:
    """Extract a markdown bullet list following a bold header."""
    pattern = re.compile(
        rf"\*\*{re.escape(header)}:\*\*\s*\n((?:\s*-\s*.+\n?)*)",
    )
    match = pattern.search(body)
    if not match:
        return []
    items: list[str] = []
    for raw_line in match.group(1).strip().splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items
