"""Smoke tests for tapps_mcp.distribution.doctor_brain_version (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_brain_version import (
    _parse_version_tuple,
    _read_brain_floor_pin,
    check_brain_health,
    check_brain_version_delta,
    check_brain_version_floor,
)


def test_parse_version_tuple_full() -> None:
    assert _parse_version_tuple("3.18.2") == (3, 18, 2)


def test_parse_version_tuple_partial() -> None:
    assert _parse_version_tuple("3.18") == (3, 18, 0)


def test_parse_version_tuple_invalid_returns_zeros() -> None:
    assert _parse_version_tuple("not-a-version") == (0, 0, 0)


def test_read_brain_floor_pin_resolves_from_tapps_core() -> None:
    floor = _read_brain_floor_pin()
    assert floor is None or isinstance(floor, str)


def test_check_brain_health_not_http_mode_passes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
    result = check_brain_health(tmp_path)
    assert result.ok is True
    assert "Not in HTTP mode" in result.message


def test_check_brain_version_floor_not_http_mode_passes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
    result = check_brain_version_floor(tmp_path)
    assert result.ok is True
    assert "Not in HTTP mode" in result.message


def test_check_brain_version_delta_not_http_mode_passes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
    result = check_brain_version_delta(tmp_path)
    assert result.ok is True
    assert "Not in HTTP mode" in result.message
