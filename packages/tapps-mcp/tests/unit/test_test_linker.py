"""Tests for TESTS edge linker (TAP-4052, TAP-4080)."""

from __future__ import annotations

from pathlib import Path

from tapps_core.cache import collect_cache_stats
from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.test_linker import (
    build_test_edges,
    edges_for_symbols,
    get_tests_for_symbol,
    load_or_build_test_edges,
)
from tapps_mcp.project.test_linker_cache import (
    TEST_EDGES_CACHE_REL,
    load_test_edges_cache,
    save_test_edges_cache,
)


def _write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


class TestTestLinker:
    def test_tests_edge_from_test_call(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "demo/helper.py",
            """
def support():
    return 1
""",
        )
        _write(
            tmp_path,
            "tests/test_helper.py",
            """
from demo.helper import support

def test_support():
    assert support() == 1
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        edges = build_test_edges(index, project_root=tmp_path)
        assert len(edges) == 1
        edge = edges[0]
        assert edge.code_symbol == "demo.helper.support"
        assert "tests/test_helper.py" in edge.test_file

        matched = edges_for_symbols(edges, {"demo.helper.support"})
        assert len(matched) == 1

    def test_get_tests_for_symbol(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "demo/helper.py",
            """
def support():
    return 1
""",
        )
        _write(
            tmp_path,
            "tests/test_helper.py",
            """
from demo.helper import support

def test_support():
    assert support() == 1
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        edges = build_test_edges(index, project_root=tmp_path)
        ranked = get_tests_for_symbol(edges, "support", index=index)
        assert len(ranked) == 1
        assert ranked[0]["test_symbol"].endswith("test_support")

    def test_test_edges_cache_save_and_load(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "demo/helper.py",
            """
def support():
    return 1
""",
        )
        _write(
            tmp_path,
            "tests/test_helper.py",
            """
from demo.helper import support

def test_support():
    assert support() == 1
""",
        )
        # Build edges and save to cache keyed by the call-graph fingerprint.
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        edges = build_test_edges(index, project_root=tmp_path)
        save_test_edges_cache(tmp_path, index.fingerprint, edges)

        # Verify cache file exists at the fingerprint-keyed path.
        cache_path = tmp_path / TEST_EDGES_CACHE_REL
        assert cache_path.is_file()

        # Load from cache (same fingerprint) and verify contents match.
        cached_edges = load_test_edges_cache(tmp_path, index.fingerprint)
        assert cached_edges is not None
        assert len(cached_edges) == len(edges)
        assert cached_edges[0].code_symbol == edges[0].code_symbol
        assert cached_edges[0].test_symbol == edges[0].test_symbol

    def test_load_or_build_uses_cache(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "demo/helper.py",
            """
def support():
    return 1
""",
        )
        _write(
            tmp_path,
            "tests/test_helper.py",
            """
from demo.helper import support

def test_support():
    assert support() == 1
""",
        )
        # First call builds and caches.
        edges1 = load_or_build_test_edges(tmp_path)
        assert len(edges1) == 1
        cache_path = tmp_path / TEST_EDGES_CACHE_REL
        assert cache_path.is_file()

        # Second call loads from cache (not rebuilt).
        edges2 = load_or_build_test_edges(tmp_path)
        assert len(edges2) == 1
        assert edges2[0].code_symbol == edges1[0].code_symbol

    def test_load_or_build_force_rebuild_bypasses_cache(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "demo/helper.py",
            """
def support():
    return 1
""",
        )
        _write(
            tmp_path,
            "tests/test_helper.py",
            """
from demo.helper import support

def test_support():
    assert support() == 1
""",
        )
        # First call builds and caches.
        edges1 = load_or_build_test_edges(tmp_path)
        assert len(edges1) == 1

        # force_rebuild=True should rebuild regardless of cache.
        edges2 = load_or_build_test_edges(tmp_path, force_rebuild=True)
        assert len(edges2) == 1
        assert edges2[0].code_symbol == edges1[0].code_symbol

    def test_cache_invalidates_on_fingerprint_change(self, tmp_path: Path) -> None:
        """A cache built from an old call graph is a MISS once the fingerprint changes.

        Same fingerprint => hit; a different (changed call graph) fingerprint =>
        no stale edges served, so the caller rebuilds fresh (TAP-4080).
        """
        _write(
            tmp_path,
            "demo/helper.py",
            """
def support():
    return 1
""",
        )
        _write(
            tmp_path,
            "tests/test_helper.py",
            """
from demo.helper import support

def test_support():
    assert support() == 1
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        edges = build_test_edges(index, project_root=tmp_path)
        assert index.fingerprint  # keyed by a real fingerprint
        save_test_edges_cache(tmp_path, index.fingerprint, edges)

        # Same fingerprint -> cache HIT.
        assert load_test_edges_cache(tmp_path, index.fingerprint) is not None

        # Changed call graph -> different fingerprint -> MISS (no stale serve).
        stale = load_test_edges_cache(tmp_path, index.fingerprint + "-changed")
        assert stale is None

        # A full rebuild path with a genuinely changed graph returns fresh edges
        # and rewrites the cache under the new fingerprint.
        _write(
            tmp_path,
            "demo/helper.py",
            """
def support():
    return 1

def support_two():
    return 2
""",
        )
        _write(
            tmp_path,
            "tests/test_helper.py",
            """
from demo.helper import support, support_two

def test_support():
    assert support() == 1

def test_support_two():
    assert support_two() == 2
""",
        )
        new_index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert new_index.fingerprint != index.fingerprint
        fresh = load_or_build_test_edges(tmp_path)
        assert {e.code_symbol for e in fresh} == {
            "demo.helper.support",
            "demo.helper.support_two",
        }
        # Cache now serves the fresh edges under the NEW fingerprint.
        assert load_test_edges_cache(tmp_path, new_index.fingerprint) is not None

    def test_stats_registered_in_collect_cache_stats(self) -> None:
        """`test_edges` appears in the unified cache-stats surface (tapps_stats.caches)."""
        # Importing test_linker (done at module top) eagerly registers the provider.
        import tapps_mcp.project.test_linker  # noqa: F401

        stats = collect_cache_stats()
        assert "test_edges" in stats
        assert set(stats["test_edges"]) >= {"hits", "misses"}
