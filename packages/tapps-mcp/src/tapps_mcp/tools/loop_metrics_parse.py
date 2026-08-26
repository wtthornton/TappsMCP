"""Transcript parsing for loop metrics (TAP-5606)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from tapps_mcp.tools.loop_metrics_scope import (
    _edit_counts_for_gate,
    extract_skill_name,
)
from tapps_mcp.tools.pipeline_tool_sets import (
    EDIT_TOOL_NAMES,
    SOURCE_FILE_SUFFIXES,
    TRANSCRIPT_WRAPPER_TOOL_NAMES,
    is_checklist_tool,
    is_gate_tool,
    is_lookup_tool,
    is_tapps_mcp_server,
    resolve_transcript_tool_name,
)


def _as_tool_use_pair(blk: object) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(blk, dict) or blk.get("type") != "tool_use":
        return None
    name = str(blk.get("name") or "")
    tool_input = blk.get("input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    return name, tool_input


def _tool_blocks_from_row(row: object) -> list[tuple[str, dict[str, Any]]]:
    """Extract tool_use blocks from one transcript JSONL row."""
    if not isinstance(row, dict):
        return []
    msg = row.get("message") or {}
    if not isinstance(msg, dict):
        return []
    pairs: list[tuple[str, dict[str, Any]]] = []
    for blk in msg.get("content") or []:
        pair = _as_tool_use_pair(blk)
        if pair is not None:
            pairs.append(pair)
    return pairs


def _iter_transcript_tool_blocks(transcript_path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Yield ``(tool_name, input_dict)`` pairs from a Claude/Cursor JSONL transcript."""
    blocks: list[tuple[str, dict[str, Any]]] = []
    try:
        with transcript_path.open(encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                blocks.extend(_tool_blocks_from_row(row))
    except OSError:
        return []
    return blocks


def _mcp_call_from_tool_use(name: str, tool_input: dict[str, Any], resolved_name: str) -> bool:
    if name.startswith("mcp__"):
        return True
    if name not in TRANSCRIPT_WRAPPER_TOOL_NAMES:
        return False
    identifier = str(tool_input.get("server") or tool_input.get("namespace") or "")
    return is_tapps_mcp_server(identifier) or resolved_name.startswith("tapps_")


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


def _unique_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _consume_tool_use(
    name: str,
    tool_input: dict[str, Any],
    *,
    project_root: Path | None,
    tools_used: set[str],
    skills_used: set[str],
    edited: list[str],
) -> tuple[int, bool, bool, bool]:
    """Apply one tool_use block; return mcp delta and gate/checklist/lookup flags."""
    resolved = resolve_transcript_tool_name(name, tool_input)
    tools_used.add(resolved)
    mcp_delta = 1 if _mcp_call_from_tool_use(name, tool_input, resolved) else 0
    edit_path = _edit_path_from_tool_use(name, tool_input, project_root)
    if edit_path is not None:
        edited.append(edit_path)
    skill = extract_skill_name(name, tool_input)
    if skill:
        skills_used.add(skill)
    return (
        mcp_delta,
        is_gate_tool(resolved),
        is_checklist_tool(resolved),
        is_lookup_tool(resolved),
    )


def _violations_for_edits(
    edits: list[str],
    *,
    gate_called: bool,
    checklist_called: bool,
) -> tuple[list[str], list[str]]:
    needs_gate = any(p.endswith(SOURCE_FILE_SUFFIXES) for p in edits)
    gate_skipped: list[str] = []
    violations: list[str] = []
    if needs_gate and not gate_called:
        violations.append("QUALITY_GATE_SKIP:" + ",".join(edits[:8]))
        gate_skipped = edits
    if needs_gate and not checklist_called:
        violations.append("CHECKLIST_MISSING")
    return gate_skipped, violations


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
            mcp_delta, gate, checklist, lookup = _consume_tool_use(
                name,
                tool_input,
                project_root=project_root,
                tools_used=tools_used,
                skills_used=skills_used,
                edited=edited_from_transcript,
            )
            mcp_calls += mcp_delta
            gate_called = gate_called or gate
            checklist_called = checklist_called or checklist
            lookup_called = lookup_called or lookup

    edits = _unique_paths(edited_from_transcript)
    gate_skipped, violations = _violations_for_edits(
        edits, gate_called=gate_called, checklist_called=checklist_called
    )
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
