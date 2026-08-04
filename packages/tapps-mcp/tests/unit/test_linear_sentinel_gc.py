"""Tests for orphaned Linear snapshot sentinel GC (TAP-5456)."""

from __future__ import annotations

import time
from pathlib import Path

from tapps_mcp.tools.linear_list_gateway import (
    _SENTINEL_GC_MAX_AGE_S,
    gc_stale_linear_sentinels,
)


class TestGcStaleLinearSentinels:
    def test_removes_old_sentinels_keeps_fresh(self, tmp_path: Path) -> None:
        tapps = tmp_path / ".tapps-mcp"
        tapps.mkdir()
        fresh = tapps / ".linear-snapshot-sentinel-fresh"
        stale = tapps / ".linear-snapshot-sentinel-stale"
        fresh.write_text(str(int(time.time())), encoding="utf-8")
        stale.write_text("1", encoding="utf-8")
        old = time.time() - (_SENTINEL_GC_MAX_AGE_S + 10)
        import os

        os.utime(stale, (old, old))
        removed = gc_stale_linear_sentinels(tmp_path)
        assert removed == 1
        assert fresh.exists()
        assert not stale.exists()

    def test_noop_when_tapps_dir_missing(self, tmp_path: Path) -> None:
        assert gc_stale_linear_sentinels(tmp_path) == 0
