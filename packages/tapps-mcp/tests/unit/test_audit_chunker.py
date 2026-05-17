"""Tests for the audit-chunker primitive."""

from __future__ import annotations

import textwrap
from pathlib import Path

from tapps_mcp.tools.audit_chunker import (
    _common_package_prefix,
    _connected_components,
    _is_trivial_file,
    _pack_stash,
    _split_oversized,
    chunk_scope,
)


class TestIsTrivialFile:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.py"
        p.write_text("")
        assert _is_trivial_file(p) is True

    def test_whitespace_only(self, tmp_path: Path) -> None:
        p = tmp_path / "ws.py"
        p.write_text("\n   \n\n")
        assert _is_trivial_file(p) is True

    def test_single_import(self, tmp_path: Path) -> None:
        p = tmp_path / "shim.py"
        p.write_text("from foo import bar\n")
        assert _is_trivial_file(p) is True

    def test_two_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "two.py"
        p.write_text("from __future__ import annotations\nfrom foo import bar\n")
        assert _is_trivial_file(p) is True

    def test_real_file(self, tmp_path: Path) -> None:
        p = tmp_path / "real.py"
        p.write_text(
            "from __future__ import annotations\n"
            "\n"
            "def f() -> int:\n"
            "    return 1\n"
        )
        assert _is_trivial_file(p) is False


class TestConnectedComponents:
    def test_empty(self) -> None:
        assert _connected_components(set(), {}) == []

    def test_singletons(self) -> None:
        nodes = {"a", "b", "c"}
        comps = _connected_components(nodes, {})
        assert comps == [["a"], ["b"], ["c"]]

    def test_one_component(self) -> None:
        nodes = {"a", "b", "c"}
        adj = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
        comps = _connected_components(nodes, adj)
        assert comps == [["a", "b", "c"]]

    def test_two_components(self) -> None:
        nodes = {"a", "b", "c", "d"}
        adj = {"a": {"b"}, "b": {"a"}, "c": {"d"}, "d": {"c"}}
        comps = _connected_components(nodes, adj)
        assert comps == [["a", "b"], ["c", "d"]]


class TestSplitOversized:
    def test_returns_one_chunk_when_at_max(self) -> None:
        # 5 fully-connected nodes, max=6 → no split.
        comp = ["a", "b", "c", "d", "e"]
        adj: dict[str, set[str]] = {n: set(comp) - {n} for n in comp}
        result = _split_oversized(comp, adj, max_size=6, target_size=6)
        assert result == [sorted(comp)]

    def test_splits_a_clique_evenly(self) -> None:
        # 12-clique, target=6 → two chunks roughly half.
        comp = [f"m{i}" for i in range(12)]
        adj: dict[str, set[str]] = {n: set(comp) - {n} for n in comp}
        result = _split_oversized(comp, adj, max_size=9, target_size=6)
        assert len(result) == 2
        sizes = sorted(len(c) for c in result)
        assert sizes == [6, 6]
        # No file appears in two chunks.
        flat = [m for chunk in result for m in chunk]
        assert len(flat) == len(set(flat)) == 12

    def test_respects_dense_subclusters(self) -> None:
        # Two dense triangles bridged by one edge — should split on the bridge.
        comp = ["a1", "a2", "a3", "b1", "b2", "b3", "c"]
        adj: dict[str, set[str]] = {
            "a1": {"a2", "a3"},
            "a2": {"a1", "a3"},
            "a3": {"a1", "a2", "c"},
            "b1": {"b2", "b3"},
            "b2": {"b1", "b3"},
            "b3": {"b1", "b2", "c"},
            "c": {"a3", "b3"},
        }
        result = _split_oversized(comp, adj, max_size=4, target_size=4)
        assert len(result) >= 2
        # Each a-triangle node lands with at least one other a-node.
        for chunk in result:
            a_count = sum(1 for n in chunk if n.startswith("a"))
            b_count = sum(1 for n in chunk if n.startswith("b"))
            if a_count > 0:
                assert a_count >= 1
            if b_count > 0:
                assert b_count >= 1


class TestPackStash:
    def test_empty(self) -> None:
        assert _pack_stash([], max_size=6) == []

    def test_same_prefix_packs_together(self) -> None:
        stash = [["pkg.a"], ["pkg.b"], ["pkg.c"]]
        result = _pack_stash(stash, max_size=6)
        assert result == [["pkg.a", "pkg.b", "pkg.c"]]

    def test_different_prefixes_dont_mix(self) -> None:
        stash = [["alpha.a"], ["beta.b"]]
        result = _pack_stash(stash, max_size=6)
        assert sorted(result) == [["alpha.a"], ["beta.b"]]

    def test_respects_max_size(self) -> None:
        stash = [[f"pkg.m{i}"] for i in range(10)]
        result = _pack_stash(stash, max_size=4)
        # 10 items, max_size=4 → three chunks of 4, 4, 2.
        sizes = sorted(len(c) for c in result)
        assert sizes == [2, 4, 4]


class TestCommonPackagePrefix:
    def test_empty(self) -> None:
        assert _common_package_prefix([]) == ""

    def test_identical(self) -> None:
        assert _common_package_prefix(["a.b.c"]) == "a.b.c"

    def test_two_modules(self) -> None:
        assert _common_package_prefix(["pkg.x", "pkg.y"]) == "pkg"

    def test_no_common(self) -> None:
        assert _common_package_prefix(["alpha", "beta"]) == ""


class TestChunkScopeIntegration:
    """End-to-end: build a tiny project tree, chunk it, verify groupings."""

    def _write_project(self, root: Path) -> None:
        # Two clusters and one orphan, all under a single package.
        pkg = root / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")

        # Cluster 1: a imports b, b imports c.
        (pkg / "a.py").write_text(
            textwrap.dedent("""
                from mypkg import b
                from mypkg import c

                def use_bc() -> int:
                    return b.value() + c.value()
            """).lstrip()
        )
        (pkg / "b.py").write_text(
            textwrap.dedent("""
                from mypkg import c

                def value() -> int:
                    return c.value() + 1
            """).lstrip()
        )
        (pkg / "c.py").write_text(
            textwrap.dedent("""
                def value() -> int:
                    return 7
            """).lstrip()
        )

        # Cluster 2: d imports e.
        (pkg / "d.py").write_text(
            textwrap.dedent("""
                from mypkg import e

                def go() -> int:
                    return e.compute()
            """).lstrip()
        )
        (pkg / "e.py").write_text(
            textwrap.dedent("""
                def compute() -> int:
                    return 2
            """).lstrip()
        )

        # Orphan: f imports nothing intra-project, nothing imports it.
        (pkg / "f.py").write_text(
            textwrap.dedent("""
                import os

                def cwd() -> str:
                    return os.getcwd()
            """).lstrip()
        )

    def test_chunks_real_tree(self, tmp_path: Path) -> None:
        self._write_project(tmp_path)
        plan = chunk_scope(
            tmp_path,
            tmp_path / "mypkg",
            min_size=2,
            target_size=3,
            max_size=4,
        )

        # 6 real module files; the empty __init__.py is filtered as trivial.
        assert plan.total_files == 6
        assert plan.total_chunks >= 1
        assert "mypkg/__init__.py" in plan.skipped_trivial

        all_files = sorted(f for chunk in plan.chunks for f in chunk.files)
        # Every file appears exactly once.
        assert len(all_files) == len(set(all_files)) == 6
        assert all(f.startswith("mypkg/") for f in all_files)

        # Cluster 1 (a, b, c) should share a chunk.
        for chunk in plan.chunks:
            if any("a.py" in f for f in chunk.files):
                assert any("b.py" in f for f in chunk.files)
                assert any("c.py" in f for f in chunk.files)

        # Cluster 2 (d, e) should share a chunk.
        for chunk in plan.chunks:
            if any("d.py" in f for f in chunk.files):
                assert any("e.py" in f for f in chunk.files)

        # Rationale should mention the common prefix.
        for chunk in plan.chunks:
            assert chunk.rationale
            assert chunk.size == len(chunk.files) == len(chunk.modules)

    def test_empty_scope_returns_empty_plan(self, tmp_path: Path) -> None:
        plan = chunk_scope(tmp_path, tmp_path)
        assert plan.total_files == 0
        assert plan.total_chunks == 0
        assert plan.chunks == []

    def test_session_indices_are_unique_and_sequential(
        self, tmp_path: Path
    ) -> None:
        self._write_project(tmp_path)
        plan = chunk_scope(
            tmp_path,
            tmp_path / "mypkg",
            min_size=2,
            target_size=3,
            max_size=4,
        )
        indices = [c.session_index for c in plan.chunks]
        assert indices == list(range(1, len(indices) + 1))
