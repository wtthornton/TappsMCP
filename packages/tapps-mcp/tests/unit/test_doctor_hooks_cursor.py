"""Smoke tests for tapps_mcp.distribution.doctor_hooks_cursor (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_hooks_cursor import (
    check_claude_settings,
    check_cursor_mcp_zombie_cleanup,
    check_hooks,
    check_managed_json_parseable,
)


def test_check_hooks_none_found_fails(tmp_path: Path) -> None:
    result = check_hooks(tmp_path)
    assert result.ok is False
    assert "No TappsMCP hooks found" in result.message


def test_check_managed_json_parseable_no_files_passes(tmp_path: Path) -> None:
    result = check_managed_json_parseable(tmp_path)
    assert result.ok is True


def test_check_claude_settings_missing_fails(tmp_path: Path) -> None:
    result = check_claude_settings(tmp_path)
    assert result.ok is False
    assert "not found" in result.message


def test_check_cursor_mcp_zombie_cleanup_no_hooks_json_passes(tmp_path: Path) -> None:
    result = check_cursor_mcp_zombie_cleanup(tmp_path)
    assert result.ok is True
    assert "Not applicable" in result.message
