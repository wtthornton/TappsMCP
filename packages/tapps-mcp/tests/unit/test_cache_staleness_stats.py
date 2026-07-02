"""Real-cache staleness telemetry in the unified stats surface (TAP-4558).

The unified ``tapps_stats.caches`` surface (TAP-4561) reported raw hit/miss
counters only. TAP-4558 adds ``age_seconds`` + ``stale`` for the dependency-scan
and Linear-snapshot caches so hit-rate *and* staleness health are visible.

These tests drive the **real** cache modules (not synthetic registry providers)
and assert the staleness fields surface through ``collect_cache_stats`` for at
least two distinct caches — the AC4 requirement the prior synthetic tests missed.
"""

from __future__ import annotations

from pathlib import Path

from tapps_core.cache import collect_cache_stats
from tapps_mcp import server_linear_tools
from tapps_mcp.tools import dependency_scan_cache
from tapps_mcp.tools.dependency_scan_cache import (
    clear_dependency_cache,
    set_dependency_findings,
)


class TestDependencyScanStaleness:
    def test_empty_cache_reports_null_age_and_staleness(self) -> None:
        clear_dependency_cache()
        stats = dependency_scan_cache._dependency_scan_stats()
        assert stats["size"] == 0
        assert stats["age_seconds"] is None
        assert stats["stale"] is None

    def test_fresh_entry_reports_age_and_not_stale(self) -> None:
        clear_dependency_cache()
        set_dependency_findings("/proj-fresh", [])
        stats = dependency_scan_cache._dependency_scan_stats()
        assert stats["size"] == 1
        assert isinstance(stats["age_seconds"], float)
        assert stats["age_seconds"] >= 0
        # Just-written entry is well within the 300 s TTL.
        assert stats["stale"] is False
        clear_dependency_cache()

    def test_old_entry_reports_stale(self) -> None:
        clear_dependency_cache()
        # Plant an entry timestamped far in the past (ts=0.0 is past any TTL).
        dependency_scan_cache._cache["/proj-old"] = ([], 0.0)
        stats = dependency_scan_cache._dependency_scan_stats()
        assert stats["stale"] is True
        assert isinstance(stats["age_seconds"], float)
        clear_dependency_cache()


class TestLinearSnapshotStaleness:
    def _reset(self) -> None:
        server_linear_tools._snapshot_last_write_ts = 0.0

    def test_no_write_reports_null_age_and_staleness(self) -> None:
        self._reset()
        stats = server_linear_tools._linear_snapshot_stats()
        assert stats["age_seconds"] is None
        assert stats["stale"] is None

    def test_write_records_age_and_freshness(self, tmp_path: Path) -> None:
        self._reset()
        cache_dir = tmp_path / "linear-snapshots"
        cache_dir.mkdir(parents=True, exist_ok=True)
        server_linear_tools._cache_write(
            cache_dir, "team__proj__any__abc123", {"issues": [], "expires_at": 0}
        )
        stats = server_linear_tools._linear_snapshot_stats()
        assert stats["writes"] >= 1
        assert isinstance(stats["age_seconds"], float)
        assert stats["age_seconds"] >= 0
        # Freshest write is within the default 300 s open-bucket TTL.
        assert stats["stale"] is False
        self._reset()


def test_staleness_fields_surface_for_at_least_two_real_caches(tmp_path: Path) -> None:
    """AC4: unified surface reports age/staleness for >=2 distinct real caches."""
    clear_dependency_cache()
    server_linear_tools._snapshot_last_write_ts = 0.0

    # Drive both real caches so each has a populated entry / recorded write.
    set_dependency_findings("/proj-ac4", [])
    cache_dir = tmp_path / "linear-snapshots"
    cache_dir.mkdir(parents=True, exist_ok=True)
    server_linear_tools._cache_write(
        cache_dir, "team__proj__any__ac4", {"issues": [], "expires_at": 0}
    )

    caches = collect_cache_stats()

    for name in ("dependency_scan", "linear_snapshot"):
        assert name in caches, f"{name} missing from unified surface"
        entry = caches[name]
        assert "age_seconds" in entry, f"{name} lacks age_seconds"
        assert "stale" in entry, f"{name} lacks stale"
        assert entry["age_seconds"] is not None
        assert entry["stale"] is False

    clear_dependency_cache()
    server_linear_tools._snapshot_last_write_ts = 0.0
