"""Tests for function-level call graph indexer (TAP-4053)."""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.project.call_graph import (
    CALL_GRAPH_CACHE_REL,
    CallGraphIndex,
    build_call_graph_index,
    load_call_graph_index,
)


def _write_pkg(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _symbol_names(index: CallGraphIndex) -> set[str]:
    return {s.qualified_name for s in index.symbols}


def _resolved_edges(index: CallGraphIndex) -> list[tuple[str, str]]:
    return [(e.caller, e.callee) for e in index.edges if e.resolved]


class TestCallGraphSymbols:
    def test_module_level_functions(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/utils.py",
            """
def alpha():
    pass

def beta():
    pass
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert _symbol_names(index) == {"demo.utils.alpha", "demo.utils.beta"}

    def test_class_methods_and_nested_class(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/service.py",
            """
class Outer:
    def outer_method(self):
        pass

    class Inner:
        def inner_method(self):
            pass
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert _symbol_names(index) == {
            "demo.service.Outer.outer_method",
            "demo.service.Outer.Inner.inner_method",
        }


class TestCallGraphEdges:
    def test_direct_function_call(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/calls.py",
            """
def callee():
    return 1

def caller():
    callee()
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert ("demo.calls.caller", "demo.calls.callee") in _resolved_edges(index)

    def test_self_method_call(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/selfcall.py",
            """
class Worker:
    def helper(self):
        return 0

    def run(self):
        self.helper()
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert (
            "demo.selfcall.Worker.run",
            "demo.selfcall.Worker.helper",
        ) in _resolved_edges(index)

    def test_class_attribute_call(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/attrcall.py",
            """
class Engine:
    @staticmethod
    def spin():
        return 2

def drive():
    Engine.spin()
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert (
            "demo.attrcall.drive",
            "demo.attrcall.Engine.spin",
        ) in _resolved_edges(index)

    def test_nested_class_method_call(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/nested.py",
            """
class Outer:
    class Inner:
        def work(self):
            return 1

    def run(self):
        self.Inner.work()
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert (
            "demo.nested.Outer.run",
            "demo.nested.Outer.Inner.work",
        ) in _resolved_edges(index)

    def test_imported_call_resolves_to_qualified_name(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/helper.py",
            """
def support():
    return 3
""",
        )
        _write_pkg(
            tmp_path,
            "demo/consumer.py",
            """
from demo.helper import support

def main():
    support()
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert ("demo.consumer.main", "demo.helper.support") in _resolved_edges(index)

    def test_unresolved_dynamic_call_records_gap(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/dynamic.py",
            """
def mystery(obj):
    return getattr(obj, "run")()
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert index.edges == []
        assert len(index.resolution_gaps) == 1
        gap = index.resolution_gaps[0]
        assert gap.caller == "demo.dynamic.mystery"
        assert gap.reason == "dynamic_dispatch"


class TestCallGraphParseFailures:
    def test_syntax_error_recorded_in_index(self, tmp_path: Path) -> None:
        path = _write_pkg(
            tmp_path,
            "demo/broken.py",
            """
def ok():
    pass

""",
        )
        path.write_text("def broken(\n", encoding="utf-8")
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        assert len(index.parse_failures) == 1
        assert index.parse_failures[0].reason == "syntax_error"


class TestCallGraphHofAndRoutes:
    def test_lambda_callback_calls_tracked(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/lambda_use.py",
            """
def helper():
    return 1

def runner(items):
    return list(map(lambda x: helper(), items))
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        lambda_callers = [e.caller for e in index.edges if "lambda" in e.caller]
        assert any("lambda" in c for c in lambda_callers)

    def test_click_decorator_route_edge(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/cli.py",
            """
import click

@click.command()
def greet():
    click.echo("hi")
""",
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        route_edges = [e for e in index.edges if e.caller.startswith("route:")]
        assert route_edges
        assert any(e.callee.endswith(".greet") for e in route_edges)


class TestExportTestMap:
    def test_writes_test_map_txt(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/target.py",
            """
def target():
    return 1
""",
        )
        _write_pkg(
            tmp_path,
            "tests/test_target.py",
            """
from demo.target import target

def test_target():
    assert target() == 1
""",
        )
        from tapps_mcp.project.diff_impact import export_test_map

        out = export_test_map(tmp_path, force_rebuild=True)
        assert out.name == "test_map.txt"
        text = out.read_text(encoding="utf-8")
        assert "demo.target.target" in text
        assert "tests/test_target.py" in text


class TestCallGraphCache:
    def test_persists_under_tapps_mcp_and_reuses(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/cache.py",
            """
def one():
    pass
""",
        )
        first = build_call_graph_index(tmp_path, force_rebuild=True)
        cache_path = tmp_path / CALL_GRAPH_CACHE_REL
        assert cache_path.is_file()

        second = build_call_graph_index(tmp_path, force_rebuild=False)
        assert second.fingerprint == first.fingerprint
        assert _symbol_names(second) == _symbol_names(first)

    def test_force_rebuild_after_file_change(self, tmp_path: Path) -> None:
        path = _write_pkg(
            tmp_path,
            "demo/cache2.py",
            """
def one():
    pass
""",
        )
        first = build_call_graph_index(tmp_path, force_rebuild=True)
        path.write_text(
            """
def one():
    pass

def two():
    pass
""",
            encoding="utf-8",
        )
        rebuilt = build_call_graph_index(tmp_path, force_rebuild=False)
        assert "demo.cache2.two" not in _symbol_names(first)
        assert "demo.cache2.two" in _symbol_names(rebuilt)

    def test_load_cached_index_round_trip(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/roundtrip.py",
            """
def fn():
    pass
""",
        )
        built = build_call_graph_index(tmp_path, force_rebuild=True)
        loaded = load_call_graph_index(tmp_path)
        assert loaded is not None
        assert loaded.fingerprint == built.fingerprint

    def test_rejects_stale_index_version(self, tmp_path: Path, monkeypatch) -> None:
        _write_pkg(
            tmp_path,
            "demo/version.py",
            """
def fn():
    pass
""",
        )
        first = build_call_graph_index(tmp_path, force_rebuild=True)
        cache_path = tmp_path / CALL_GRAPH_CACHE_REL
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        raw["version"] = 0
        cache_path.write_text(json.dumps(raw), encoding="utf-8")

        rebuilt = build_call_graph_index(tmp_path, force_rebuild=False)
        assert rebuilt.version != 0
        assert rebuilt is not first


class TestInvalidateCallGraphCache:
    def test_removes_schema_stale_cache(self, tmp_path: Path) -> None:
        from tapps_mcp.project.call_graph_cache import (
            invalidate_call_graph_cache_if_schema_stale,
            save_call_graph_index,
        )
        from tapps_mcp.project.call_graph_types import CallGraphIndex

        save_call_graph_index(
            tmp_path,
            CallGraphIndex(project_root=str(tmp_path), fingerprint="abc", version=1),
        )
        result = invalidate_call_graph_cache_if_schema_stale(tmp_path)
        assert result["action"] == "removed"
        assert result["reason"] == "index_version_mismatch"
        assert not (tmp_path / CALL_GRAPH_CACHE_REL).is_file()

    def test_skips_current_schema(self, tmp_path: Path) -> None:
        from tapps_mcp.project.call_graph_cache import (
            invalidate_call_graph_cache_if_schema_stale,
            save_call_graph_index,
        )
        from tapps_mcp.project.call_graph_types import CallGraphIndex, INDEX_VERSION

        save_call_graph_index(
            tmp_path,
            CallGraphIndex(
                project_root=str(tmp_path),
                fingerprint="abc",
                version=INDEX_VERSION,
            ),
        )
        result = invalidate_call_graph_cache_if_schema_stale(tmp_path)
        assert result["action"] == "skipped"
        assert (tmp_path / CALL_GRAPH_CACHE_REL).is_file()


class TestCallGraphQueries:
    def test_callers_and_callees_helpers(self, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            "demo/graph.py",
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
        assert len(index.callees_of("demo.graph.top")) == 1
        assert index.callees_of("demo.graph.top")[0].callee == "demo.graph.mid"
        assert len(index.callers_of("demo.graph.leaf")) == 1
        assert index.callers_of("demo.graph.leaf")[0].caller == "demo.graph.mid"


class TestSummarizeCallGraphCache:
    def test_stale_hint_mentions_auto_rebuild(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.agent_contract import CALL_GRAPH_STALE_HINT
        from tapps_mcp.project.call_graph_cache import (
            save_call_graph_index,
            summarize_call_graph_cache,
        )
        from tapps_mcp.project.call_graph_types import CallGraphIndex, INDEX_VERSION

        save_call_graph_index(
            tmp_path,
            CallGraphIndex(
                project_root=str(tmp_path),
                fingerprint="stale-fingerprint",
                version=INDEX_VERSION,
            ),
        )
        summary = summarize_call_graph_cache(tmp_path)
        assert summary.get("stale") is True
        assert summary.get("hint") == CALL_GRAPH_STALE_HINT
        assert "automatically" in str(summary.get("hint"))
