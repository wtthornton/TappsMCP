"""Smoke tests for tapps_mcp.distribution.doctor_platform (TAP-5606 split)."""

from __future__ import annotations

import json
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


def _install_cache_gate_warn(tmp_path: Path, *, with_matcher: bool = True) -> None:
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "tapps-pre-linear-list.sh").write_text(
        '#!/bin/bash\nMODE="warn"\n',
        encoding="utf-8",
    )
    settings = tmp_path / ".claude" / "settings.json"
    matchers = []
    if with_matcher:
        matchers.append(
            {
                "matcher": (
                    "mcp__plugin_linear_linear__list_issues|"
                    "mcp__claude_ai_Linear__list_issues"
                ),
                "hooks": [{"type": "command", "command": "true"}],
            }
        )
    settings.write_text(
        json.dumps({"hooks": {"PreToolUse": matchers}}),
        encoding="utf-8",
    )


def test_linear_cache_gate_status_blind_when_empty_cache(tmp_path: Path) -> None:
    from tapps_mcp.distribution.doctor_platform import _linear_cache_gate_status

    _install_cache_gate_warn(tmp_path)
    status = _linear_cache_gate_status(
        tmp_path,
        ["mcp__plugin_linear_linear__list_issues|mcp__claude_ai_Linear__list_issues"],
    )
    assert "BLIND" in status
    assert "hook-matcher mismatch" in status
    assert "empty snapshot cache" in status


def test_linear_cache_gate_status_quiet_when_cache_populated(tmp_path: Path) -> None:
    from tapps_mcp.distribution.doctor_platform import _linear_cache_gate_status

    _install_cache_gate_warn(tmp_path)
    snap = tmp_path / ".tapps-mcp-cache" / "linear-snapshots"
    snap.mkdir(parents=True)
    (snap / "abc.json").write_text("{}", encoding="utf-8")
    status = _linear_cache_gate_status(
        tmp_path,
        ["mcp__plugin_linear_linear__list_issues"],
    )
    assert "BLIND" not in status
    assert "0 violations in last 24h" in status
    assert "warn" in status


def test_check_pretooluse_matchers_surfaces_blind_gate(tmp_path: Path) -> None:
    _install_cache_gate_warn(tmp_path)
    result = check_pretooluse_matchers(tmp_path)
    assert result.ok is True
    assert "BLIND" in result.message
    assert "hook-matcher mismatch" in result.message
