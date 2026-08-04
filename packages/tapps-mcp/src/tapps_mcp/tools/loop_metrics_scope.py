"""Gate-scope and edit-row reliability predicates for loop metrics (TAP-5606)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from tapps_mcp.tools.pipeline_tool_sets import SOURCE_FILE_SUFFIXES, is_gate_tool


def _skill_from_skill_tool(tool_input: dict[str, Any]) -> str | None:
    for key in ("skill", "name", "command", "skill_name"):
        raw = tool_input.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lstrip("/")
    return None


def _skill_from_skill_md_read(tool_input: dict[str, Any]) -> str | None:
    path_val = tool_input.get("path") or tool_input.get("file_path") or ""
    if not isinstance(path_val, str) or "/skills/" not in path_val:
        return None
    if not path_val.endswith("SKILL.md"):
        return None
    parts = Path(path_val).parts
    for idx, part in enumerate(parts):
        if part == "skills" and idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def extract_skill_name(tool_name: str, tool_input: Any) -> str | None:
    """Resolve a slash-skill name from a Skill tool call or SKILL.md Read."""
    if not isinstance(tool_input, dict):
        tool_input = {}
    lowered = tool_name.lower()
    if lowered in {"skill", "skills"}:
        return _skill_from_skill_tool(tool_input)
    if tool_name == "Read":
        return _skill_from_skill_md_read(tool_input)
    return None


def _path_inside_project(path_str: str, project_root: Path) -> bool:
    try:
        path = Path(path_str)
        resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
        resolved.relative_to(project_root.resolve())
    except (ValueError, OSError):
        return False
    return True


def _is_temp_path(path_str: str) -> bool:
    normalized = path_str.replace("\\", "/")
    tmp_root = Path(tempfile.gettempdir()).resolve().as_posix()
    return normalized == tmp_root or normalized.startswith(f"{tmp_root}/")


def is_scoped_gate_edit(path_str: str, project_root: Path | None) -> bool:
    """True when *path_str* is in-scope for gate-required edit telemetry."""
    if not path_str:
        return False
    if project_root is not None and _path_inside_project(path_str, project_root):
        return True
    if _is_temp_path(path_str):
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
    return not any(t.startswith(("tapps_", "mcp__")) for t in tools)


def _files_edited_list(row: dict[str, Any]) -> list[str]:
    files_raw = row.get("files_edited")
    if not files_raw or isinstance(files_raw, bool):
        return []
    if not isinstance(files_raw, list):
        return []
    return [p for p in files_raw if isinstance(p, str)]


def is_reliable_edit_loop_row(row: dict[str, Any], project_root: Path) -> bool:
    """False for legacy unparsed Cursor rows or loops with no in-scope source edits."""
    if _legacy_cursor_unparsed_callmcptool(row):
        return False
    return bool(scoped_source_edits(_files_edited_list(row), project_root))


def loop_row_gate_skipped(row: dict[str, Any], project_root: Path) -> bool:
    """True when a reliable edit loop lacks gate compliance signals.

    Checklist alone does **not** count as gate compliance — agents must call
    ``tapps_quick_check`` / ``tapps_validate_changed`` / ``tapps_quality_gate``.
    """
    if not is_reliable_edit_loop_row(row, project_root):
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
    return bool(scoped_source_edits(_files_edited_list(row), project_root))
