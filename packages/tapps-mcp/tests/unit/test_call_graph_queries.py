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

    def test_caller_completeness_complete_when_all_inbound_resolved(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path,
            "pkg/graph.py",
            "def leaf():\n    return 0\n\ndef mid():\n    leaf()\n",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        result = query_call_graph(index, "pkg.graph.leaf", mode="callers")
        signal = result["caller_completeness"]
        assert signal["complete"] is True
        assert signal["unresolved_inbound"] == 0
        assert signal["resolved_callers"] == 1

    def test_caller_completeness_flags_unresolved_inbound(self, tmp_path: Path) -> None:
        # ``caller.py`` calls ``process()`` without importing it: the resolver
        # cannot bind the edge, so it becomes a gap attributed to ``run`` — NOT
        # to ``process``. ``degraded`` (outbound-only) stays False for process,
        # but the callers list is silently missing an edge.
        _write(tmp_path, "pkg/target.py", "def process():\n    return 1\n")
        _write(tmp_path, "pkg/caller.py", "def run():\n    return process()\n")
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        result = query_call_graph(index, "pkg.target.process", mode="callers")

        assert result["degraded"] is False  # outbound-clean, would look complete
        signal = result["caller_completeness"]
        assert signal["complete"] is False
        assert signal["unresolved_inbound"] >= 1
        assert any(c["caller"] == "pkg.caller.run" for c in signal["candidates"])

    def test_caller_completeness_absent_for_callees_only(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/graph.py", "def leaf():\n    return 0\n")
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        result = query_call_graph(index, "pkg.graph.leaf", mode="callees")
        assert "caller_completeness" not in result

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


def test_compact_symbol_impact_budget(tmp_path: Path) -> None:
    from tapps_mcp.project.call_graph_queries import compact_symbol_impact

    _write(
        tmp_path,
        "pkg/target.py",
        """
def target():
    return 1
""",
    )
    _write(
        tmp_path,
        "pkg/caller.py",
        """
from pkg.target import target

def run():
    return target()
""",
    )
    index = build_call_graph_index(tmp_path, force_rebuild=True)
    block = compact_symbol_impact(index, "pkg/target.py", token_budget=500)
    assert block is not None
    assert block["symbols"][0]["callers"] == ["run"]
