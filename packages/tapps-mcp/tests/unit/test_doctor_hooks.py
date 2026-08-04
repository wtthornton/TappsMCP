"""Smoke tests for tapps_mcp.distribution.doctor_hooks (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_hooks import (
    check_agents_md,
    check_scope_recommendation,
    check_tapps_mcp_yaml,
)


def test_check_agents_md_missing_fails(tmp_path: Path) -> None:
    result = check_agents_md(tmp_path)
    assert result.ok is False
    assert "AGENTS.md not found" in result.message


def test_check_tapps_mcp_yaml_not_present_passes(tmp_path: Path) -> None:
    result = check_tapps_mcp_yaml(tmp_path)
    assert result.ok is True
    assert "not present" in result.message


def test_check_tapps_mcp_yaml_invalid_fails(tmp_path: Path) -> None:
    (tmp_path / ".tapps-mcp.yaml").write_text("bad: [unbalanced", encoding="utf-8")
    result = check_tapps_mcp_yaml(tmp_path)
    assert result.ok is False


def test_check_scope_recommendation_no_user_config_passes(tmp_path: Path) -> None:
    result = check_scope_recommendation(tmp_path, home=tmp_path / "home")
    assert result.ok is True
    assert "No user-scoped config" in result.message
