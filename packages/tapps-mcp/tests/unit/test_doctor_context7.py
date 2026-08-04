"""Smoke tests for tapps_mcp.distribution.doctor_context7 (TAP-5606 split)."""

from __future__ import annotations

import os
from pathlib import Path

from tapps_mcp.distribution.doctor_context7 import (
    _env_file_get_value,
    _env_file_sets_key,
    _mcp_configs_set_context7,
    check_consumer_context7_env,
    check_context7_live,
    check_mcp_operator_secrets,
)


def test_env_file_get_value_missing_file_returns_none(tmp_path: Path) -> None:
    assert _env_file_get_value(tmp_path / "missing.env", "KEY") is None


def test_env_file_get_value_reads_defined_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_KEY=abc123\n", encoding="utf-8")
    assert _env_file_get_value(env_file, "SOME_KEY") == "abc123"


def test_env_file_sets_key_false_when_missing(tmp_path: Path) -> None:
    assert _env_file_sets_key(tmp_path / "missing.env", "KEY") is False


def test_mcp_configs_set_context7_no_configs_returns_empty(tmp_path: Path) -> None:
    assert _mcp_configs_set_context7(tmp_path) == []


def test_check_context7_live_quick_mode_skips(tmp_path: Path) -> None:
    result = check_context7_live(tmp_path, quick=True)
    assert result.ok is True
    assert "Skipped" in result.message


def test_check_consumer_context7_env_no_configs_passes(tmp_path: Path) -> None:
    os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    result = check_consumer_context7_env(tmp_path)
    assert result.ok is True


def test_check_mcp_operator_secrets_no_configs_passes(tmp_path: Path) -> None:
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    result = check_mcp_operator_secrets(tmp_path)
    assert result.ok is True
