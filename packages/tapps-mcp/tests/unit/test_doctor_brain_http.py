"""Smoke tests for tapps_mcp.distribution.doctor_brain_http (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_brain_http import (
    _parse_histogram_quantiles,
    check_brain_http_auth,
    check_brain_probe_latency,
    check_brain_profile,
    check_stale_exe_backups,
)


def test_check_stale_exe_backups_not_frozen_passes() -> None:
    result = check_stale_exe_backups()
    assert result.ok is True
    assert "not applicable" in result.message


def test_check_brain_http_auth_not_http_mode_passes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
    result = check_brain_http_auth(tmp_path)
    assert result.ok is True
    assert "Not in HTTP mode" in result.message


def test_check_brain_profile_not_http_mode_passes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
    result = check_brain_profile(tmp_path)
    assert result.ok is True
    assert "Not in HTTP mode" in result.message


def test_check_brain_probe_latency_not_http_mode_passes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
    result = check_brain_probe_latency(tmp_path)
    assert result.ok is True
    assert "Not in HTTP mode" in result.message


def test_parse_histogram_quantiles_simple_buckets() -> None:
    metrics_text = (
        'demo_metric_bucket{le="0.1"} 1\n'
        'demo_metric_bucket{le="0.5"} 8\n'
        'demo_metric_bucket{le="+Inf"} 10\n'
    )
    quantiles = _parse_histogram_quantiles(metrics_text, "demo_metric", (0.5, 0.99))
    assert quantiles is not None
    assert 0.1 < quantiles[0.5] <= 0.5


def test_parse_histogram_quantiles_missing_metric_returns_none() -> None:
    assert _parse_histogram_quantiles("no buckets here", "demo_metric", (0.5,)) is None
