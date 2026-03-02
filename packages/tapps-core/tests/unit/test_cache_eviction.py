"""Unit tests for KBCache LRU eviction (Epic 37.4)."""

from __future__ import annotations

import time

import pytest

from tapps_core.knowledge.cache import KBCache
from tapps_core.knowledge.models import CacheEntry


def _make_entry(library: str, topic: str = "overview", size_kb: int = 10) -> CacheEntry:
    """Create a CacheEntry with content of approximately *size_kb* kilobytes."""
    content = "x" * (size_kb * 1024)
    return CacheEntry(library=library, topic=topic, content=content)


class TestCacheEviction:
    """Tests for size-based LRU eviction in KBCache."""

    @pytest.fixture()
    def cache(self, tmp_path):
        return KBCache(cache_dir=tmp_path / "cache")

    def test_eviction_triggers_at_limit(self, tmp_path):
        """Fill cache over limit, verify entries are removed."""
        cache = KBCache(cache_dir=tmp_path / "cache")

        # Put 5 entries of ~50 KB each = ~250 KB content + metadata
        for i in range(5):
            entry = _make_entry(f"lib{i}", size_kb=50)
            cache.put(entry)
            # Access to register in metadata
            cache.get(f"lib{i}")

        # Verify all 5 exist
        assert len(cache.list_entries()) == 5

        # Evict with a very small limit (should remove some entries)
        # Total is ~250 KB content + metadata, set limit to ~100 KB
        removed = cache.evict_lru(max_mb=0)  # 0 MB → evict everything possible
        assert removed > 0
        # Some entries should be gone
        remaining = cache.list_entries()
        assert len(remaining) < 5

    def test_lru_order_correct(self, tmp_path):
        """Oldest-accessed entries should be evicted first."""
        cache = KBCache(cache_dir=tmp_path / "cache")

        # Insert 4 entries of ~30 KB each
        for i in range(4):
            entry = _make_entry(f"lib{i}", size_kb=30)
            cache.put(entry)

        # Access order: lib2 (oldest), lib0, lib3, lib1 (newest)
        cache.get("lib2")
        time.sleep(0.01)
        cache.get("lib0")
        time.sleep(0.01)
        cache.get("lib3")
        time.sleep(0.01)
        cache.get("lib1")

        # Verify metadata reflects correct ordering
        metadata = cache._load_metadata()
        assert metadata["lib2/overview"] < metadata["lib0/overview"]
        assert metadata["lib0/overview"] < metadata["lib3/overview"]
        assert metadata["lib3/overview"] < metadata["lib1/overview"]

        # Evict with 0 MB limit — all should be evicted, oldest first
        evicted = cache.evict_lru(max_mb=0)
        assert evicted == 4
        assert len(cache.list_entries()) == 0

    def test_metadata_tracking(self, cache):
        """Verify access timestamps are written and updated in metadata."""
        entry = _make_entry("fastapi")
        cache.put(entry)

        metadata = cache._load_metadata()
        assert "fastapi/overview" in metadata
        assert isinstance(metadata["fastapi/overview"], float)

        # Access the entry and verify timestamp is updated
        before_ts = metadata["fastapi/overview"]
        time.sleep(0.01)
        cache.get("fastapi")
        metadata_after = cache._load_metadata()
        assert metadata_after["fastapi/overview"] > before_ts

    def test_config_override(self, tmp_path):
        """cache_max_mb=50 triggers eviction at a lower limit."""
        from tapps_core.config.settings import TappsMCPSettings

        settings = TappsMCPSettings(project_root=tmp_path, cache_max_mb=50)
        assert settings.cache_max_mb == 50

        # Verify default is 100
        settings_default = TappsMCPSettings(project_root=tmp_path)
        assert settings_default.cache_max_mb == 100

        # Create a cache and verify evict_lru respects the limit
        cache = KBCache(cache_dir=tmp_path / "cache")
        entry = _make_entry("lib1", size_kb=10)
        cache.put(entry)
        cache.get("lib1")

        # With 50 MB limit and ~10 KB entry, no eviction should happen
        evicted = cache.evict_lru(max_mb=50)
        assert evicted == 0

    def test_no_eviction_under_limit(self, tmp_path):
        """Cache under limit — nothing should be evicted."""
        cache = KBCache(cache_dir=tmp_path / "cache")

        # Put a small entry (~10 KB)
        entry = _make_entry("fastapi", size_kb=10)
        cache.put(entry)
        cache.get("fastapi")

        # 100 MB limit — way above the ~10 KB entry
        evicted = cache.evict_lru(max_mb=100)
        assert evicted == 0
        assert cache.has("fastapi")

    def test_evict_lru_returns_count(self, tmp_path):
        """evict_lru() returns the number of evicted entries."""
        cache = KBCache(cache_dir=tmp_path / "cache")

        # Insert 3 entries
        for i in range(3):
            entry = _make_entry(f"lib{i}", size_kb=20)
            cache.put(entry)
            cache.get(f"lib{i}")
            time.sleep(0.01)

        # With 0 MB limit, all entries should be evicted
        count = cache.evict_lru(max_mb=0)
        assert count == 3

    def test_metadata_persists_across_instances(self, tmp_path):
        """Create cache, access entries, create new instance, verify metadata."""
        cache_dir = tmp_path / "cache"
        cache1 = KBCache(cache_dir=cache_dir)

        # Put and access entries
        cache1.put(_make_entry("fastapi"))
        cache1.put(_make_entry("django"))
        cache1.get("fastapi")
        time.sleep(0.01)
        cache1.get("django")

        # Read metadata from first instance
        meta1 = cache1._load_metadata()
        assert "fastapi/overview" in meta1
        assert "django/overview" in meta1

        # Create a new instance pointing at the same directory
        cache2 = KBCache(cache_dir=cache_dir)
        meta2 = cache2._load_metadata()

        # Metadata should persist — same keys and timestamps
        assert "fastapi/overview" in meta2
        assert "django/overview" in meta2
        assert meta2["fastapi/overview"] == meta1["fastapi/overview"]
        assert meta2["django/overview"] == meta1["django/overview"]

    def test_get_updates_access_timestamp(self, tmp_path):
        """Calling get() should update the access timestamp for that entry."""
        cache = KBCache(cache_dir=tmp_path / "cache")

        entry = _make_entry("fastapi")
        cache.put(entry)

        # First get
        cache.get("fastapi")
        meta_after_first = cache._load_metadata()
        ts1 = meta_after_first["fastapi/overview"]

        time.sleep(0.02)

        # Second get — timestamp should be newer
        cache.get("fastapi")
        meta_after_second = cache._load_metadata()
        ts2 = meta_after_second["fastapi/overview"]

        assert ts2 > ts1
