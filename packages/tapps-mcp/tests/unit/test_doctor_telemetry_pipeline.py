"""Smoke tests for tapps_mcp.distribution.doctor_telemetry_pipeline (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_telemetry_pipeline import (
    _cache_gate_promote_hint,
    _hook_install_hint,
    _lookup_ratio_hint,
    check_pipeline_enforce_recommendations,
)


def test_hook_install_hint_none_below_min_loops() -> None:
    assert _hook_install_hint(Path("/tmp"), None, "high", loops=1, skip_rate=0.9, skip_pct=90) is None


def test_lookup_ratio_hint_none_when_ratio_meets_threshold() -> None:
    assert (
        _lookup_ratio_hint(loops=10, lookup_ratio=0.5, lookup_pct=50, engagement="high") is None
    )


def test_cache_gate_promote_hint_none_when_already_block() -> None:
    snippet, hint = _cache_gate_promote_hint(Path("/tmp"), None, "block", viol_24h=100)
    assert snippet is None
    assert hint is None


def test_check_pipeline_enforce_recommendations_no_metrics(tmp_path: Path) -> None:
    result = check_pipeline_enforce_recommendations(tmp_path)
    assert result.ok is True
    assert "no enforcement changes suggested" in result.message
