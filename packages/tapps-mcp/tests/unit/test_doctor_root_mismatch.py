"""TAP-7225 / VAL-08: doctor detects a stale ``X-Tapps-Project-Root`` header.

A linked git worktree that inherits its ``.mcp.json`` from the primary
checkout carries the primary's literal, resolved root (baked in at
generation time). ``check_mcp_project_root_mismatch`` must catch that, gate
``tapps-mcp doctor --quick`` (non-zero exit, category ``consumer-staleness``
so a fleet-wide deploy is not blocked by one stale consumer), and clear once
the header is rewritten to the worktree's own root.
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.distribution.doctor_mcp import check_mcp_project_root_mismatch
from tapps_mcp.distribution.doctor_runner import run_doctor_structured
from tapps_mcp.distribution.nlt_http_fleet import build_nlt_http_mcp_entry


def _write_claude_mcp_json(root: Path, header_root: Path) -> None:
    entry = build_nlt_http_mcp_entry("nlt-build", project_root=header_root, host="claude-code")
    (root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"nlt-build": entry}}, indent=2) + "\n", encoding="utf-8"
    )


def test_mismatch_reported_when_header_names_a_different_root(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()
    _write_claude_mcp_json(worktree, primary)

    result = check_mcp_project_root_mismatch(worktree)
    assert result.ok is False
    assert result.category == "consumer-staleness"
    assert "mcp_project_root_mismatch" in result.message


def test_mismatch_absent_after_header_points_at_this_root(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    _write_claude_mcp_json(worktree, worktree)

    result = check_mcp_project_root_mismatch(worktree)
    assert result.ok is True


def test_mismatch_absent_with_no_mcp_json(tmp_path: Path) -> None:
    result = check_mcp_project_root_mismatch(tmp_path)
    assert result.ok is True


def test_doctor_quick_json_gates_on_mismatch(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()
    _write_claude_mcp_json(worktree, primary)

    report = run_doctor_structured(project_root=str(worktree), quick=True)
    assert report["all_passed"] is False
    rows = [c for c in report["checks"] if c["name"] == "MCP project root mismatch"]
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert rows[0]["category"] == "consumer-staleness"


def test_doctor_quick_json_clean_after_repair(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    _write_claude_mcp_json(worktree, worktree)

    report = run_doctor_structured(project_root=str(worktree), quick=True)
    rows = [c for c in report["checks"] if c["name"] == "MCP project root mismatch"]
    assert len(rows) == 1
    assert rows[0]["ok"] is True
