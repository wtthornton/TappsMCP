"""Tests for call graph query layer (TAP-4050)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_queries import query_call_graph, resolve_symbol_name


def _write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


class TestCallGraphQueries:
    def test_callers_callees_and_chain(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/graph.py",
            """
def leaf():
    return 0

def mid():
    leaf()

def top():
    mid()
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        result = query_call_graph(index, "pkg.graph.leaf", mode="callers", max_depth=1)
        assert result["found"] is True
        assert len(result["callers"]) == 1
        assert result["callers"][0]["caller"] == "pkg.graph.mid"

        callees = query_call_graph(index, "pkg.graph.top", mode="callees", max_depth=3)
        assert callees["callees"][0]["callee"] == "pkg.graph.mid"

        chain = query_call_graph(index, "pkg.graph.leaf", mode="chain", max_depth=3)
        assert chain["chain"]

    def test_resolution_gaps_surface_as_degraded(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/dynamic.py",
            """
def mystery(obj):
    return getattr(obj, "run")()
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        result = query_call_graph(index, "pkg.dynamic.mystery", mode="all")
        assert result["degraded"] is True
        assert result["resolution_gaps"]

    def test_unknown_symbol(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/empty.py", "def ok():\n    pass\n")
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        result = query_call_graph(index, "missing.fn")
        assert result["found"] is False
        assert resolve_symbol_name(index, "missing.fn") is None

    def test_token_budget_truncates(self, tmp_path: Path) -> None:
        lines = ["def f():\n    pass\n"] + [f"def t{i}():\n    f()\n" for i in range(20)]
        _write(tmp_path, "pkg/big.py", "\n".join(lines))
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        result = query_call_graph(index, "pkg.big.f", mode="callers", max_depth=10, token_budget=50)
        assert result["truncated"] is True
