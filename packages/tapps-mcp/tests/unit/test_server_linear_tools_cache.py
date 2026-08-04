"""Stem coverage + smoke tests for server_linear_tools_cache (TAP-5606)."""

from __future__ import annotations

import time
from pathlib import Path

from tapps_mcp import server_linear_tools_cache as cache


def test_cache_write_then_read_roundtrip(tmp_path: Path) -> None:
    cache_dir = cache._cache_dir(tmp_path)
    cache._cache_write(
        cache_dir,
        "k",
        {"issues": [{"id": "x"}], "expires_at": time.time() + 600},
    )
    got = cache._cache_read(cache_dir, "k")
    assert got is not None
    assert got["issues"] == [{"id": "x"}]


def test_cache_read_missing_file_returns_none(tmp_path: Path) -> None:
    cache_dir = cache._cache_dir(tmp_path)
    assert cache._cache_read(cache_dir, "missing") is None


def test_cache_invalidate_glob_removes_matches(tmp_path: Path) -> None:
    cache_dir = cache._cache_dir(tmp_path)
    cache._cache_write(cache_dir, "T__P__a", {"issues": [], "expires_at": time.time() + 600})
    cache._cache_write(cache_dir, "T__P__b", {"issues": [], "expires_at": time.time() + 600})
    removed = cache._cache_invalidate_glob(cache_dir, "T__P__*")
    assert removed == 2


def test_linear_snapshot_stats_reports_counters() -> None:
    cache._snapshot_last_write_ts = 0.0
    stats = cache._linear_snapshot_stats()
    assert stats["age_seconds"] is None
    assert stats["stale"] is None
    cache._snapshot_last_write_ts = 0.0
