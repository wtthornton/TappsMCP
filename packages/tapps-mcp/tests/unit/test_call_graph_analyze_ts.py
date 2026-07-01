"""Unit tests for the tree-sitter TypeScript call-graph analyzer (TAP-4538).

Covers symbol extraction (function / arrow-const / class method), in-module
edge resolution, non-in-module gaps, the ``const x = f()`` caller-attribution
case, and graceful failure handling (syntax error → ParseFailure).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.project.call_graph_analyze_ts import HAS_TREE_SITTER, analyze_file_ts

pytestmark = pytest.mark.skipif(
    not HAS_TREE_SITTER, reason="tree-sitter TypeScript grammar not installed"
)


def _write(tmp_path: Path, name: str, source: str) -> Path:
    f = tmp_path / name
    f.write_text(source, encoding="utf-8")
    return f


class TestSymbolExtraction:
    def test_function_arrow_and_method_symbols(self, tmp_path: Path) -> None:
        src = """\
function topFn() {}
const arrowFn = () => {};
class Widget {
  render() {}
  update() {}
}
"""
        f = _write(tmp_path, "mod.ts", src)
        symbols, _edges, _gaps, failures = analyze_file_ts(f, "mod", tmp_path)

        assert failures == []
        by_name = {s.qualified_name: s for s in symbols}
        assert "mod.topFn" in by_name
        assert "mod.arrowFn" in by_name
        assert "mod.Widget.render" in by_name
        assert "mod.Widget.update" in by_name

        for s in symbols:
            assert s.language == "typescript"
            assert s.module == "mod"
            assert s.file_path == "mod.ts"

        assert by_name["mod.topFn"].kind == "function"
        assert by_name["mod.arrowFn"].kind == "function"
        assert by_name["mod.Widget.render"].kind == "method"
        # Lines are 1-based.
        assert by_name["mod.topFn"].line == 1
        assert by_name["mod.arrowFn"].line == 2

    def test_exported_declarations_are_extracted(self, tmp_path: Path) -> None:
        src = """\
export function pubFn() {}
export const pubArrow = () => {};
export class Svc { handle() {} }
"""
        f = _write(tmp_path, "svc.ts", src)
        symbols, _e, _g, _f = analyze_file_ts(f, "svc", tmp_path)
        names = {s.qualified_name for s in symbols}
        assert names == {"svc.pubFn", "svc.pubArrow", "svc.Svc.handle"}


class TestEdgeResolution:
    def test_in_module_call_resolves_to_edge(self, tmp_path: Path) -> None:
        src = """\
function helper() {}
function caller() { helper(); }
"""
        f = _write(tmp_path, "mod.ts", src)
        _symbols, edges, gaps, _f = analyze_file_ts(f, "mod", tmp_path)

        assert len(edges) == 1
        edge = edges[0]
        assert edge.caller == "mod.caller"
        assert edge.callee == "mod.helper"
        assert edge.callee_expr == "helper"
        assert edge.resolved is True
        assert not any(g.expr == "helper" for g in gaps)

    def test_arrow_calling_in_module_function_resolves(self, tmp_path: Path) -> None:
        src = """\
function target() {}
const runner = () => { target(); };
"""
        f = _write(tmp_path, "mod.ts", src)
        _symbols, edges, _gaps, _f = analyze_file_ts(f, "mod", tmp_path)
        assert any(
            e.caller == "mod.runner" and e.callee == "mod.target" for e in edges
        )

    def test_this_method_call_resolves(self, tmp_path: Path) -> None:
        src = """\
class C {
  a() { this.b(); }
  b() {}
}
"""
        f = _write(tmp_path, "c.ts", src)
        _symbols, edges, _gaps, _f = analyze_file_ts(f, "c", tmp_path)
        assert any(
            e.caller == "c.C.a" and e.callee == "c.C.b" and e.callee_expr == "this.b"
            for e in edges
        )


class TestResolutionGaps:
    def test_non_in_module_call_becomes_gap(self, tmp_path: Path) -> None:
        src = """\
import { external } from "./other";
function caller() { external(); }
"""
        f = _write(tmp_path, "mod.ts", src)
        _symbols, edges, gaps, _f = analyze_file_ts(f, "mod", tmp_path)

        assert not any(e.callee_expr == "external" for e in edges)
        gap = next(g for g in gaps if g.expr == "external")
        assert gap.caller == "mod.caller"
        assert gap.reason == "import_unresolved"

    def test_member_call_on_object_becomes_gap(self, tmp_path: Path) -> None:
        src = """\
function caller() { console.log("hi"); }
"""
        f = _write(tmp_path, "mod.ts", src)
        _symbols, edges, gaps, _f = analyze_file_ts(f, "mod", tmp_path)
        assert edges == []
        assert any(g.expr == "console.log" and g.caller == "mod.caller" for g in gaps)


class TestCallerAttribution:
    def test_call_inside_const_initializer_attributes_to_enclosing_fn(
        self, tmp_path: Path
    ) -> None:
        # AC3: a call in `const x = f(...)` attributes to the enclosing function,
        # NOT to the variable `x`.
        src = """\
function make() {}
function outer() {
  const built = make();
  return built;
}
"""
        f = _write(tmp_path, "mod.ts", src)
        _symbols, edges, _gaps, _f = analyze_file_ts(f, "mod", tmp_path)

        make_edges = [e for e in edges if e.callee == "mod.make"]
        assert len(make_edges) == 1
        assert make_edges[0].caller == "mod.outer"
        # The variable name must never become a caller.
        assert all("built" not in e.caller for e in edges)

    def test_method_const_initializer_attributes_to_method(self, tmp_path: Path) -> None:
        src = """\
class C {
  helper() {}
  run() {
    const r = this.helper();
    return r;
  }
}
"""
        f = _write(tmp_path, "c.ts", src)
        _symbols, edges, _gaps, _f = analyze_file_ts(f, "c", tmp_path)
        helper_edges = [e for e in edges if e.callee == "c.C.helper"]
        assert len(helper_edges) == 1
        assert helper_edges[0].caller == "c.C.run"


class TestFailureHandling:
    def test_syntax_error_yields_parse_failure(self, tmp_path: Path) -> None:
        src = "function broken( { @#$ !!! garbage"
        f = _write(tmp_path, "bad.ts", src)
        symbols, edges, gaps, failures = analyze_file_ts(f, "bad", tmp_path)
        assert symbols == []
        assert edges == []
        assert gaps == []
        assert len(failures) == 1
        assert failures[0].reason == "syntax_error"
        assert failures[0].file_path == "bad.ts"

    def test_missing_file_yields_io_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.ts"
        symbols, edges, gaps, failures = analyze_file_ts(missing, "nope", tmp_path)
        assert (symbols, edges, gaps) == ([], [], [])
        assert len(failures) == 1
        assert failures[0].reason.startswith("io_error")

    def test_tsx_file_parses(self, tmp_path: Path) -> None:
        src = """\
function Component() {
  return helper();
}
function helper() {}
"""
        f = _write(tmp_path, "App.tsx", src)
        symbols, edges, _gaps, failures = analyze_file_ts(f, "App", tmp_path)
        assert failures == []
        assert any(s.qualified_name == "App.Component" for s in symbols)
        assert any(e.caller == "App.Component" and e.callee == "App.helper" for e in edges)
