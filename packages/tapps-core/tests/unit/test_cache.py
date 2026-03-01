"""Unit tests for knowledge/cache.py — KB cache with TTL and atomic writes."""

from __future__ import annotations

import json
import time

import pytest

from tapps_core.knowledge.cache import KBCache, _safe_name
from tapps_core.knowledge.models import CacheEntry


class TestSafeName:
    def test_simple(self):
        assert _safe_name("fastapi") == "fastapi"

    def test_slashes(self):
        assert _safe_name("vercel/next.js") == "vercel_next.js"

    def test_spaces(self):
        assert _safe_name("my library") == "my_library"

    def test_uppercase(self):
        assert _safe_name("FastAPI") == "fastapi"

    def test_colons(self):
        assert _safe_name("C:path") == "c_path"


class TestKBCacheBasics:
    @pytest.fixture
    def cache(self, tmp_path):
        return KBCache(cache_dir=tmp_path / "cache")

    def test_cache_dir_created(self, cache):
        assert cache.cache_dir.exists()

    def test_put_and_get(self, cache):
        entry = CacheEntry(library="fastapi", topic="overview", content="# FastAPI docs")
        cache.put(entry)

        result = cache.get("fastapi", "overview")
        assert result is not None
        assert result.library == "fastapi"
        assert result.content == "# FastAPI docs"
        assert result.cache_hits == 1

    def test_get_missing(self, cache):
        result = cache.get("nonexistent")
        assert result is None

    def test_has(self, cache):
        assert not cache.has("fastapi")
        cache.put(CacheEntry(library="fastapi", content="docs"))
        assert cache.has("fastapi")

    def test_remove(self, cache):
        cache.put(CacheEntry(library="fastapi", content="docs"))
        assert cache.has("fastapi")
        removed = cache.remove("fastapi")
        assert removed is True
        assert not cache.has("fastapi")

    def test_remove_nonexistent(self, cache):
        assert cache.remove("nonexistent") is False

    def test_list_entries(self, cache):
        cache.put(CacheEntry(library="fastapi", content="a"))
        cache.put(CacheEntry(library="django", content="b"))
        entries = cache.list_entries()
        names = {e.library for e in entries}
        assert "fastapi" in names
        assert "django" in names

    def test_clear(self, cache):
        cache.put(CacheEntry(library="fastapi", content="a"))
        cache.put(CacheEntry(library="django", content="b"))
        count = cache.clear()
        assert count > 0
        assert cache.list_entries() == []

    def test_cache_hit_counter_increments(self, cache):
        cache.put(CacheEntry(library="fastapi", content="docs"))
        r1 = cache.get("fastapi")
        assert r1 is not None
        assert r1.cache_hits == 1
        r2 = cache.get("fastapi")
        assert r2 is not None
        assert r2.cache_hits == 2


class TestKBCacheStaleness:
    @pytest.fixture
    def cache(self, tmp_path):
        return KBCache(cache_dir=tmp_path / "cache", default_ttl=1.0)

    def test_fresh_entry_not_stale(self, cache):
        cache.put(CacheEntry(library="fastapi", content="docs"))
        assert not cache.is_stale("fastapi")

    def test_expired_entry_is_stale(self, cache):
        cache.put(CacheEntry(library="fastapi", content="docs"))
        # Manually backdate the cached_at in the meta file
        meta_path = cache._meta_path("fastapi", "overview")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["cached_at"] = "2020-01-01T00:00:00Z"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        assert cache.is_stale("fastapi")

    def test_missing_entry_is_stale(self, cache):
        assert cache.is_stale("nonexistent")

    def test_staleness_policy_override(self, tmp_path):
        cache = KBCache(
            cache_dir=tmp_path / "cache",
            default_ttl=86400.0,
            staleness_policies={"fast-lib": 0.001},  # Tiny TTL
        )
        cache.put(CacheEntry(library="fast-lib", content="docs"))
        time.sleep(0.01)
        assert cache.is_stale("fast-lib")


class TestKBCacheStats:
    def test_stats(self, tmp_path):
        cache = KBCache(cache_dir=tmp_path / "cache")
        cache.put(CacheEntry(library="fastapi", content="hello world"))
        cache.get("fastapi")
        cache.get("missing")

        stats = cache.stats
        assert stats.total_entries == 1
        assert stats.hits == 1
        assert stats.misses == 1
        assert stats.total_size_bytes > 0


class TestKBCacheAtomicWrites:
    def test_content_written_correctly(self, tmp_path):
        cache = KBCache(cache_dir=tmp_path / "cache")
        content = "# Docs\n\n```python\nprint('hello')\n```\n"
        cache.put(CacheEntry(library="test", content=content))
        result = cache.get("test")
        assert result is not None
        assert result.content == content

    def test_meta_written_as_json(self, tmp_path):
        cache = KBCache(cache_dir=tmp_path / "cache")
        cache.put(CacheEntry(library="test", topic="api", content="docs"))
        meta_path = cache._meta_path("test", "api")
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["library"] == "test"
        assert meta["topic"] == "api"
        assert "cached_at" in meta


class TestKBCacheTopics:
    def test_different_topics(self, tmp_path):
        cache = KBCache(cache_dir=tmp_path / "cache")
        cache.put(CacheEntry(library="fastapi", topic="overview", content="overview"))
        cache.put(CacheEntry(library="fastapi", topic="routing", content="routing"))

        r1 = cache.get("fastapi", "overview")
        r2 = cache.get("fastapi", "routing")
        assert r1 is not None and r1.content == "overview"
        assert r2 is not None and r2.content == "routing"

    def test_remove_specific_topic(self, tmp_path):
        cache = KBCache(cache_dir=tmp_path / "cache")
        cache.put(CacheEntry(library="fastapi", topic="overview", content="a"))
        cache.put(CacheEntry(library="fastapi", topic="routing", content="b"))
        cache.remove("fastapi", "overview")
        assert not cache.has("fastapi", "overview")
        assert cache.has("fastapi", "routing")
