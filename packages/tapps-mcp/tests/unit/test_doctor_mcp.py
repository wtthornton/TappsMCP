"""Smoke tests for tapps_mcp.distribution.doctor_mcp (TAP-5606 split)."""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.distribution.doctor_mcp import (
    check_brain_mcp_entry,
    check_cursor_config,
    check_json_config,
    check_mcp_config_unresolved_project_root,
    strip_brain_mcp_entries,
)


def test_check_json_config_missing_file_fails(tmp_path: Path) -> None:
    result = check_json_config(tmp_path / "missing.json", "mcpServers", "Cursor")
    assert result.ok is False
    assert "Not found" in result.message


def test_check_cursor_config_valid_entry_passes(tmp_path: Path) -> None:
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    (cursor_dir / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "tapps-mcp": {"command": "uv", "args": ["run", "tapps-mcp", "serve"]},
                }
            }
        ),
        encoding="utf-8",
    )
    result = check_cursor_config(tmp_path)
    assert result.ok is True


def test_check_brain_mcp_entry_no_offenses_passes(tmp_path: Path) -> None:
    result = check_brain_mcp_entry(tmp_path)
    assert result.ok is True
    assert "No direct" in result.message


def test_check_brain_mcp_entry_direct_entry_fails(tmp_path: Path) -> None:
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"tapps-brain": {"command": "tapps-brain"}}}),
        encoding="utf-8",
    )
    result = check_brain_mcp_entry(tmp_path)
    assert result.ok is False
    assert "tapps-brain" in result.message


def test_strip_brain_mcp_entries_removes_offending_key(tmp_path: Path) -> None:
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(
        json.dumps(
            {"mcpServers": {"tapps-brain": {"command": "tapps-brain"}, "tapps-mcp": {}}}
        ),
        encoding="utf-8",
    )
    result = strip_brain_mcp_entries(tmp_path)
    assert result["stripped"] == [".mcp.json"]
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "tapps-brain" not in data["mcpServers"]
    assert "tapps-mcp" in data["mcpServers"]


def test_check_mcp_config_unresolved_project_root_clean(tmp_path: Path) -> None:
    result = check_mcp_config_unresolved_project_root(tmp_path)
    assert result.ok is True
