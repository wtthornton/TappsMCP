"""Unit tests for the shared cache substrate (TAP-4556, ADR-0029).

Covers the atomic JSON primitive and the three pluggable staleness strategies
that the call-graph cache pilot-migrates onto.
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_core.cache import (
    AtomicJsonCache,
    FingerprintStaleness,
    TTLStaleness,
    VersionStaleness,
    collect_cache_stats,
    register_cache_stats,
    unregister_cache_stats,
)


class TestAtomicJsonCache:
    def test_write_text_round_trips(self, tmp_path: Path) -> None:
        target = tmp_path / "note.txt"
        AtomicJsonCache.write_text(target, "hello")
        assert target.read_text(encoding="utf-8") == "hello"

    def test_write_json_byte_layout_matches_json_dumps(self, tmp_path: Path) -> None:
        # The pilot's byte-equivalence contract: write_json must produce exactly
        # what json.dumps(indent=2, sort_keys=True) would, so an on-disk cache is
        # unchanged after migration.
        obj = {"b": 2, "a": [1, 2, 3], "c": {"z": 1, "y": 2}}
        target = tmp_path / "index.json"
        AtomicJsonCache.write_json(target, obj, indent=2, sort_keys=True)
        assert target.read_text(encoding="utf-8") == json.dumps(obj, indent=2, sort_keys=True)

    def test_read_json_returns_parsed_object(self, tmp_path: Path) -> None:
        target = tmp_path / "index.json"
        AtomicJsonCache.write_json(target, {"k": "v"})
        assert AtomicJsonCache.read_json(target) == {"k": "v"}

    def test_read_json_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert AtomicJsonCache.read_json(tmp_path / "absent.json") is None

    def test_read_json_malformed_returns_none(self, tmp_path: Path) -> None:
        target = tmp_path / "broken.json"
        target.write_text("{not valid json", encoding="utf-8")
        assert AtomicJsonCache.read_json(target) is None

    def test_write_atomic_leaves_original_on_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "index.json"
        AtomicJsonCache.write_json(target, {"good": True})
        # A non-serializable payload raises inside the temp write; the original
        # file must be untouched and no .tmp_ debris left behind.
        try:
            AtomicJsonCache.write_json(target, {"bad": object()})
        except TypeError:
            pass
        else:  # pragma: no cover - defensive
            raise AssertionError("expected TypeError on non-serializable payload")
        assert AtomicJsonCache.read_json(target) == {"good": True}
        assert not list(tmp_path.glob(".tmp_*"))


class TestStalenessStrategies:
    def test_version_staleness(self) -> None:
        strat = VersionStaleness(current=5)
        assert strat.is_stale(4) is True
        assert strat.is_stale(5) is False

    def test_fingerprint_staleness(self) -> None:
        strat = FingerprintStaleness(current="abc123")
        assert strat.is_stale("stale-hash") is True
        assert strat.is_stale("abc123") is False

    def test_ttl_staleness_uses_injected_clock(self) -> None:
        clock = {"now": 1000.0}
        strat = TTLStaleness(ttl_seconds=60.0, now_fn=lambda: clock["now"])
        # cached at t=1000, now=1000 -> fresh; advance past the TTL -> stale.
        assert strat.is_stale(1000.0) is False
        clock["now"] = 1061.0
        assert strat.is_stale(1000.0) is True

    def test_ttl_staleness_boundary_is_stale_at_exactly_ttl(self) -> None:
        strat = TTLStaleness(ttl_seconds=60.0, now_fn=lambda: 1060.0)
        # >= ttl is stale (matches the KBCache/dep-scan expire-at semantics).
        assert strat.is_stale(1000.0) is True


class TestCacheStatsRegistry:
    def test_register_and_collect(self) -> None:
        register_cache_stats("_test_cache_a", lambda: {"hits": 3, "misses": 1})
        try:
            collected = collect_cache_stats()
            assert collected["_test_cache_a"] == {"hits": 3, "misses": 1}
        finally:
            unregister_cache_stats("_test_cache_a")

    def test_register_is_idempotent_replace(self) -> None:
        register_cache_stats("_test_cache_b", lambda: {"hits": 0})
        register_cache_stats("_test_cache_b", lambda: {"hits": 9})
        try:
            assert collect_cache_stats()["_test_cache_b"] == {"hits": 9}
        finally:
            unregister_cache_stats("_test_cache_b")

    def test_provider_error_is_isolated(self) -> None:
        def _boom() -> dict[str, int]:
            raise RuntimeError("provider exploded")

        register_cache_stats("_test_cache_boom", _boom)
        register_cache_stats("_test_cache_ok", lambda: {"hits": 1})
        try:
            collected = collect_cache_stats()
            # The broken provider reports an error entry; the healthy one is intact.
            assert collected["_test_cache_boom"] == {"error": "provider exploded"}
            assert collected["_test_cache_ok"] == {"hits": 1}
        finally:
            unregister_cache_stats("_test_cache_boom")
            unregister_cache_stats("_test_cache_ok")

    def test_unregister_removes_provider(self) -> None:
        register_cache_stats("_test_cache_gone", lambda: {"hits": 1})
        unregister_cache_stats("_test_cache_gone")
        assert "_test_cache_gone" not in collect_cache_stats()
