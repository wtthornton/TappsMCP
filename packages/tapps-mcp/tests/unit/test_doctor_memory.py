"""Smoke tests for tapps_mcp.distribution.doctor_memory (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_memory import (
    check_dual_memory_server,
    check_memory_cli_http_mode,
    check_memory_pipeline_config,
    check_memory_profile_resolvable,
    check_quality_tools,
    check_session_sentinel,
)


def test_check_session_sentinel_absent_passes(tmp_path: Path) -> None:
    result = check_session_sentinel(tmp_path)
    assert result.ok is True
    assert "absent" in result.message


def test_check_memory_pipeline_config_always_passes(tmp_path: Path) -> None:
    result = check_memory_pipeline_config(tmp_path)
    assert result.ok is True


def test_check_memory_profile_resolvable_unset_passes(tmp_path: Path) -> None:
    result = check_memory_profile_resolvable(tmp_path)
    assert result.ok is True
    assert "unset" in result.message


def test_check_memory_cli_http_mode_not_http_only_passes(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
    result = check_memory_cli_http_mode(tmp_path)
    assert result.ok is True
    assert "Not in HTTP-only mode" in result.message


def test_check_dual_memory_server_none_configured_passes(tmp_path: Path) -> None:
    result = check_dual_memory_server(tmp_path)
    assert result.ok is True
    assert "No direct tapps-brain" in result.message


def test_check_quality_tools_returns_results() -> None:
    results = check_quality_tools()
    assert isinstance(results, list)
    assert len(results) > 0
