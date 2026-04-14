"""Tests for the SHA-256 content-hash cache (STORY-101.1)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.tools import content_hash_cache as cache


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


def test_content_hash_is_deterministic(tmp_path: Path) -> None:
    p = tmp_path / "a.py"
    p.write_text("x = 1\n")
    h1 = cache.content_hash(p)
    h2 = cache.content_hash(p)
    assert h1 == h2
    assert len(h1) == 64


def test_content_hash_differs_across_content(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n")
    b.write_text("x = 2\n")
    assert cache.content_hash(a) != cache.content_hash(b)


def test_set_and_get_roundtrip() -> None:
    cache.set(cache.KIND_SCORE, "abc", {"score": 85})
    assert cache.get(cache.KIND_SCORE, "abc") == {"score": 85}
    assert cache.stats()["hits"] == 1
    assert cache.stats()["sets"] == 1


def test_get_miss_returns_none_and_increments_miss_counter() -> None:
    assert cache.get(cache.KIND_SCORE, "nope") is None
    assert cache.stats()["misses"] == 1


def test_different_kinds_are_isolated() -> None:
    cache.set(cache.KIND_SCORE, "h", {"score": 80})
    cache.set(cache.KIND_GATE, "h", {"passed": True})
    assert cache.get(cache.KIND_SCORE, "h") == {"score": 80}
    assert cache.get(cache.KIND_GATE, "h") == {"passed": True}


def test_ttl_expires_entry() -> None:
    cache.set(cache.KIND_SCORE, "h", {"score": 80})
    # Bump monotonic clock forward past ttl via patch.
    real = time.monotonic()
    with patch("tapps_mcp.tools.content_hash_cache.time.monotonic", return_value=real + 10_000):
        assert cache.get(cache.KIND_SCORE, "h", ttl=1.0) is None
    assert cache.size() == 0


def test_eviction_when_over_capacity() -> None:
    with patch("tapps_mcp.tools.content_hash_cache._MAX_ENTRIES", 3):
        cache.set(cache.KIND_SCORE, "a", {"v": 1})
        cache.set(cache.KIND_SCORE, "b", {"v": 2})
        cache.set(cache.KIND_SCORE, "c", {"v": 3})
        cache.set(cache.KIND_SCORE, "d", {"v": 4})  # triggers eviction of "a"
    assert cache.get(cache.KIND_SCORE, "a") is None
    assert cache.get(cache.KIND_SCORE, "d") == {"v": 4}
    assert cache.stats()["evictions"] >= 1


def test_clear_resets_stats_and_entries() -> None:
    cache.set(cache.KIND_SCORE, "h", {"v": 1})
    cache.get(cache.KIND_SCORE, "h")
    cache.clear()
    assert cache.size() == 0
    assert cache.stats() == {"hits": 0, "misses": 0, "sets": 0, "evictions": 0}


def test_cache_key_is_content_not_path(tmp_path: Path) -> None:
    """Same bytes, different filenames → cache hit."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("same\n")
    b.write_text("same\n")
    ha = cache.content_hash(a)
    hb = cache.content_hash(b)
    assert ha == hb
    cache.set(cache.KIND_SCORE, ha, {"score": 90})
    assert cache.get(cache.KIND_SCORE, hb) == {"score": 90}


def test_cache_hit_key_used_by_quick_check_wiring(tmp_path: Path) -> None:
    """Prove the KIND_QUICK_CHECK kind is the one server_scoring_tools uses.

    Integration through tapps_quick_check requires a real project_root for
    path validation; that is covered in test_server_scoring_tools. Here we
    just pin the kind constant so the wiring cannot silently drift.
    """
    assert cache.KIND_QUICK_CHECK == "quick_check"
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    h = cache.content_hash(f)
    cache.set(cache.KIND_QUICK_CHECK, h, {"score": 90})
    assert cache.get(cache.KIND_QUICK_CHECK, h) == {"score": 90}
