"""Stem coverage + smoke tests for loop_metrics_scope (TAP-5606)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.tools.loop_metrics_scope import (
    extract_skill_name,
    is_reliable_edit_loop_row,
    is_scoped_gate_edit,
    loop_row_gate_skipped,
    scoped_source_edits,
)


def test_extract_skill_name_from_skill_tool() -> None:
    assert extract_skill_name("Skill", {"skill": "/tapps-finish-task"}) == "tapps-finish-task"


def test_extract_skill_name_from_skill_md_read() -> None:
    path = "/repo/.cursor/skills/tapps-memory/SKILL.md"
    assert extract_skill_name("Read", {"path": path}) == "tapps-memory"


def test_is_scoped_gate_edit_inside_project(tmp_path: Path) -> None:
    target = tmp_path / "src" / "a.py"
    target.parent.mkdir()
    target.write_text("x=1\n", encoding="utf-8")
    assert is_scoped_gate_edit(str(target), tmp_path) is True


def test_scoped_source_edits_filters_non_source(tmp_path: Path) -> None:
    py = tmp_path / "a.py"
    md = tmp_path / "a.md"
    py.write_text("x=1\n", encoding="utf-8")
    md.write_text("#\n", encoding="utf-8")
    assert scoped_source_edits([str(py), str(md)], tmp_path) == [str(py)]


def test_loop_row_gate_skipped_requires_reliable_edit(tmp_path: Path) -> None:
    row = {
        "files_edited": [str(tmp_path / "a.py")],
        "tools_used": ["Write"],
        "gate_skipped_files": [str(tmp_path / "a.py")],
    }
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    assert is_reliable_edit_loop_row(row, tmp_path) is True
    assert loop_row_gate_skipped(row, tmp_path) is True
