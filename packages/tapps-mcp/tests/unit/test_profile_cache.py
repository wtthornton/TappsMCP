"""Tests for project profile disk cache (TAP-3253)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.profile_cache import (
    PROFILE_CACHE_REL,
    load_cached_profile_summary,
    profile_marker_fingerprint,
    save_cached_profile_summary,
)


def test_profile_cache_round_trip(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    fp = profile_marker_fingerprint(tmp_path)
    data = {"project_type": "library", "has_tests": True, "has_docker": False, "has_ci": True}

    assert load_cached_profile_summary(tmp_path, fp) is None
    save_cached_profile_summary(tmp_path, fp, data)
    assert load_cached_profile_summary(tmp_path, fp) == data
    assert (tmp_path / PROFILE_CACHE_REL).is_file()


def test_profile_cache_miss_on_marker_change(tmp_path: Path) -> None:
    marker = tmp_path / "pyproject.toml"
    marker.write_text("v1", encoding="utf-8")
    fp1 = profile_marker_fingerprint(tmp_path)
    save_cached_profile_summary(tmp_path, fp1, {"project_type": "cli-tool"})

    marker.write_text("v2", encoding="utf-8")
    fp2 = profile_marker_fingerprint(tmp_path)
    assert fp1 != fp2
    assert load_cached_profile_summary(tmp_path, fp2) is None
