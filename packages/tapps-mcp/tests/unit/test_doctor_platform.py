"""Smoke tests for tapps_mcp.distribution.doctor_platform (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_platform import (
    check_claude_md,
    check_config_files_rule,
    check_cursor_rules,
    check_pretooluse_matchers,
    check_retired_hooks,
    check_security_rule,
)


def test_check_retired_hooks_clean_project_passes(tmp_path: Path) -> None:
    result = check_retired_hooks(tmp_path)
    assert result.ok is True
    assert "No retired hooks" in result.message


def test_check_claude_md_missing_fails(tmp_path: Path) -> None:
    result = check_claude_md(tmp_path)
    assert result.ok is False
    assert "CLAUDE.md not found" in result.message


def test_check_claude_md_missing_soft_passes_with_cursor_rules(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".cursor" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "tapps-pipeline.md").write_text("rules", encoding="utf-8")
    result = check_claude_md(tmp_path)
    assert result.ok is True


def test_check_cursor_rules_missing_fails(tmp_path: Path) -> None:
    result = check_cursor_rules(tmp_path)
    assert result.ok is False


def test_check_security_rule_no_python_signals_soft_passes(tmp_path: Path) -> None:
    result = check_security_rule(tmp_path)
    assert result.ok is True
    assert "not satisfied" in result.message


def test_check_config_files_rule_no_signals(tmp_path: Path) -> None:
    result = check_config_files_rule(tmp_path)
    assert result.ok is True


def test_check_pretooluse_matchers_missing_settings_passes(tmp_path: Path) -> None:
    result = check_pretooluse_matchers(tmp_path)
    assert result.ok is True
    assert "not present" in result.message
