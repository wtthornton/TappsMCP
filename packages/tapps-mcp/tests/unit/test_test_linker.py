"""Tests for TESTS edge linker (TAP-4052)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.test_linker import build_test_edges, edges_for_symbols, get_tests_for_symbol


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
