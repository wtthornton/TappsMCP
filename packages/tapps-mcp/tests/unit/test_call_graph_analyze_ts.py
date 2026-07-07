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
    def test_relative_named_import_resolves_to_edge(self, tmp_path: Path) -> None:
        # S3 (TAP-4539): a named import from an in-repo relative module now
        # resolves to a cross-module edge (S2 deferred this as a gap).
        src = """\
import { external } from "./other";
function caller() { external(); }
"""
        f = _write(tmp_path, "mod.ts", src)
        _symbols, edges, gaps, _f = analyze_file_ts(f, "mod", tmp_path)

        edge = next(e for e in edges if e.callee_expr == "external")
        assert edge.caller == "mod.caller"
        assert edge.callee == "other.external"
        assert edge.resolved is True
        assert not any(g.expr == "external" for g in gaps)

    def test_unknown_bare_identifier_call_becomes_gap(self, tmp_path: Path) -> None:
        # A bare name never imported and not locally defined stays a gap.
        src = """\
function caller() { mysteryGlobal(); }
"""
        f = _write(tmp_path, "mod.ts", src)
        _symbols, edges, gaps, _f = analyze_file_ts(f, "mod", tmp_path)
        assert not any(e.callee_expr == "mysteryGlobal" for e in edges)
        gap = next(g for g in gaps if g.expr == "mysteryGlobal")
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


class TestCrossModuleResolution:
    """S3 (TAP-4539): named / aliased / namespace import resolution."""

    def _edges(self, tmp_path: Path, module: str, src: str, name: str = "consumer.ts"):
        f = _write(tmp_path, name, src)
        _s, edges, gaps, _f = analyze_file_ts(f, module, tmp_path)
        return edges, gaps

    def test_named_import_resolves(self, tmp_path: Path) -> None:
        src = """\
import { greet } from "./util";
function run() { greet(); }
"""
        edges, gaps = self._edges(tmp_path, "consumer", src)
        edge = next(e for e in edges if e.callee_expr == "greet")
        assert edge.caller == "consumer.run"
        assert edge.callee == "util.greet"
        assert edge.resolved is True
        assert not any(g.expr == "greet" for g in gaps)

    def test_aliased_import_de_aliases(self, tmp_path: Path) -> None:
        # `import {shout as loud}` -> loud() resolves to util.shout.
        src = """\
import { shout as loud } from "./util";
function run() { loud(); }
"""
        edges, _gaps = self._edges(tmp_path, "consumer", src)
        edge = next(e for e in edges if e.callee_expr == "loud")
        assert edge.callee == "util.shout"
        assert edge.caller == "consumer.run"

    def test_namespace_import_resolves(self, tmp_path: Path) -> None:
        # `import * as U from "./util"` -> U.greet() resolves to util.greet.
        src = """\
import * as U from "./util";
function run() { U.greet(); }
"""
        edges, _gaps = self._edges(tmp_path, "consumer", src)
        edge = next(e for e in edges if e.callee_expr == "U.greet")
        assert edge.callee == "util.greet"
        assert edge.caller == "consumer.run"

    def test_nested_relative_path_resolves(self, tmp_path: Path) -> None:
        # From a/b/consumer, `./util` -> a/b/util.
        src = """\
import { greet } from "./util";
function run() { greet(); }
"""
        edges, _gaps = self._edges(tmp_path, "a/b/consumer", src)
        edge = next(e for e in edges if e.callee_expr == "greet")
        assert edge.callee == "a/b/util.greet"

    def test_parent_relative_path_resolves(self, tmp_path: Path) -> None:
        # From a/b/consumer, `../shared/util` -> a/shared/util.
        src = """\
import { greet } from "../shared/util";
function run() { greet(); }
"""
        edges, _gaps = self._edges(tmp_path, "a/b/consumer", src)
        edge = next(e for e in edges if e.callee_expr == "greet")
        assert edge.callee == "a/shared/util.greet"

    def test_in_module_and_intra_class_still_resolve(self, tmp_path: Path) -> None:
        # AC1: S2 cases must keep working alongside cross-module resolution.
        src = """\
import { greet } from "./util";
function helper() {}
function run() {
  helper();
  greet();
}
class C {
  a() { this.b(); }
  b() {}
}
"""
        edges, _gaps = self._edges(tmp_path, "consumer", src)
        callees = {e.callee for e in edges}
        assert "consumer.helper" in callees  # in-module
        assert "util.greet" in callees  # cross-module named import
        assert "consumer.C.b" in callees  # intra-class this.method()


class TestDeferredResolutionGaps:
    """S3 (TAP-4539): honest gaps for cases deferred to S4 or external."""

    def _gaps(self, tmp_path: Path, module: str, src: str):
        f = _write(tmp_path, "consumer.ts", src)
        _s, edges, gaps, _f = analyze_file_ts(f, module, tmp_path)
        return edges, gaps

    def test_default_import_is_unresolved_default_export(self, tmp_path: Path) -> None:
        src = """\
import makeDefault from "./util";
function run() { makeDefault(); }
"""
        edges, gaps = self._gaps(tmp_path, "consumer", src)
        assert not any(e.callee_expr == "makeDefault" for e in edges)
        gap = next(g for g in gaps if g.expr == "makeDefault")
        assert gap.reason == "unresolved_default_export"
        assert gap.language == "typescript"

    def test_typed_receiver_method_is_receiver_untyped(self, tmp_path: Path) -> None:
        src = """\
function run(f) { f.format(); }
"""
        edges, gaps = self._gaps(tmp_path, "consumer", src)
        assert not any(e.callee_expr == "f.format" for e in edges)
        gap = next(g for g in gaps if g.expr == "f.format")
        assert gap.reason == "receiver_untyped"

    def test_reexport_is_reexport_unresolved(self, tmp_path: Path) -> None:
        src = """\
export { x } from "./re";
"""
        _edges, gaps = self._gaps(tmp_path, "consumer", src)
        gap = next(g for g in gaps if g.reason == "reexport_unresolved")
        assert gap.caller == "consumer"
        assert gap.language == "typescript"

    def test_path_alias_import_is_path_alias_unresolved(self, tmp_path: Path) -> None:
        src = """\
import { util } from "@/util";
function run() { util(); }
"""
        edges, gaps = self._gaps(tmp_path, "consumer", src)
        assert not any(e.callee_expr == "util" for e in edges)
        gap = next(g for g in gaps if g.expr == "util")
        assert gap.reason == "path_alias_unresolved"

    def test_external_package_import_is_import_unresolved(self, tmp_path: Path) -> None:
        src = """\
import { readFile } from "fs";
import { debounce } from "lodash";
function run() { readFile(); debounce(); }
"""
        edges, gaps = self._gaps(tmp_path, "consumer", src)
        assert edges == []
        for name in ("readFile", "debounce"):
            gap = next(g for g in gaps if g.expr == name)
            assert gap.reason == "import_unresolved"
            assert gap.language == "typescript"

    def test_scoped_npm_package_is_external_not_alias(self, tmp_path: Path) -> None:
        # `@angular/core` starts with `@` but is an npm package, not a path alias.
        src = """\
import { Component } from "@angular/core";
function run() { Component(); }
"""
        _edges, gaps = self._gaps(tmp_path, "consumer", src)
        gap = next(g for g in gaps if g.expr == "Component")
        assert gap.reason == "import_unresolved"


class TestCallbackAttribution:
    """TAP-4552: calls inside anonymous callbacks attribute to the enclosing
    NAMED symbol instead of being dropped.

    Resolution of the recovered call is identical to a direct call: an
    in-module callee produces a resolved edge; an unimported/unknown callee
    produces an honest ``import_unresolved`` gap (ADR-0004 — never guessed).
    """

    def _run(self, tmp_path: Path, module: str, src: str, name: str = "mod.ts"):
        f = _write(tmp_path, name, src)
        _s, edges, gaps, failures = analyze_file_ts(f, module, tmp_path)
        assert failures == []
        return edges, gaps

    def test_foreach_callback_resolved_callee(self, tmp_path: Path) -> None:
        # AC1: `function render() { items.forEach(x => helper()); }`
        # -> edge render -> helper (resolved in-module), NOT dropped.
        src = """\
function helper() {}
function render() {
  items.forEach(x => helper());
}
"""
        edges, _gaps = self._run(tmp_path, "mod", src)
        helper_edges = [e for e in edges if e.callee_expr == "helper"]
        assert len(helper_edges) == 1
        assert helper_edges[0].caller == "mod.render"
        assert helper_edges[0].callee == "mod.helper"
        assert helper_edges[0].resolved is True

    def test_foreach_callback_unresolved_callee_is_honest_gap(
        self, tmp_path: Path
    ) -> None:
        # AC2: an unknown callee inside the callback stays an honest gap.
        src = """\
function render() {
  items.forEach(x => mysteryGlobal());
}
"""
        edges, gaps = self._run(tmp_path, "mod", src)
        assert not any(e.callee_expr == "mysteryGlobal" for e in edges)
        gap = next(g for g in gaps if g.expr == "mysteryGlobal")
        assert gap.caller == "mod.render"
        assert gap.reason == "import_unresolved"

    def test_map_callback_resolved_and_unresolved(self, tmp_path: Path) -> None:
        # `.map` callback, resolved + unresolved callees together.
        src = """\
function transform(x) {}
function build(rows) {
  return rows.map(r => transform(unknownFn()));
}
"""
        edges, gaps = self._run(tmp_path, "mod", src)
        transform_edges = [e for e in edges if e.callee_expr == "transform"]
        assert len(transform_edges) == 1
        assert transform_edges[0].caller == "mod.build"
        assert transform_edges[0].callee == "mod.transform"
        gap = next(g for g in gaps if g.expr == "unknownFn")
        assert gap.caller == "mod.build"
        assert gap.reason == "import_unresolved"

    def test_then_callback_resolved_and_unresolved(self, tmp_path: Path) -> None:
        # A `.then` promise callback (function_expression form) — resolved and
        # unresolved callees both attribute to the enclosing named function.
        src = """\
function onResult(v) {}
function load(p) {
  p.then(function (v) { onResult(missingCb()); });
}
"""
        edges, gaps = self._run(tmp_path, "mod", src)
        res_edges = [e for e in edges if e.callee_expr == "onResult"]
        assert len(res_edges) == 1
        assert res_edges[0].caller == "mod.load"
        assert res_edges[0].callee == "mod.onResult"
        gap = next(g for g in gaps if g.expr == "missingCb")
        assert gap.caller == "mod.load"
        assert gap.reason == "import_unresolved"

    def test_callback_inside_method_attributes_to_method(self, tmp_path: Path) -> None:
        # Inside a class method, a callback's `this.method()` resolves intra-class
        # and its calls attribute to the enclosing method (not dropped).
        src = """\
class C {
  helper() {}
  run(items) {
    items.forEach(x => this.helper());
  }
}
"""
        edges, _gaps = self._run(tmp_path, "c", src)
        helper_edges = [e for e in edges if e.callee_expr == "this.helper"]
        assert len(helper_edges) == 1
        assert helper_edges[0].caller == "c.C.run"
        assert helper_edges[0].callee == "c.C.helper"

    def test_nested_anonymous_callbacks_attribute_to_outermost_named(
        self, tmp_path: Path
    ) -> None:
        # `a.forEach(() => b.map(() => helper()))` -> attribute to the enclosing
        # NAMED symbol, through two anonymous closures.
        src = """\
function helper() {}
function render(a, b) {
  a.forEach(() => b.map(() => helper()));
}
"""
        edges, _gaps = self._run(tmp_path, "mod", src)
        helper_edges = [e for e in edges if e.callee_expr == "helper"]
        assert len(helper_edges) == 1
        assert helper_edges[0].caller == "mod.render"
        assert helper_edges[0].callee == "mod.helper"

    def test_imported_callee_in_callback_resolves_cross_module(
        self, tmp_path: Path
    ) -> None:
        # AC2: recovered call uses the same import resolution as a direct call.
        src = """\
import { greet } from "./util";
function render(items) {
  items.forEach(x => greet());
}
"""
        edges, _gaps = self._run(tmp_path, "consumer", src)
        edge = next(e for e in edges if e.callee_expr == "greet")
        assert edge.caller == "consumer.render"
        assert edge.callee == "util.greet"
        assert edge.resolved is True

    def test_module_top_level_callback_not_fabricated(self, tmp_path: Path) -> None:
        # AC3: a callback at module top level (no enclosing named symbol) is
        # handled sanely — dropped, never a fabricated caller, no crash.
        src = """\
function helper() {}
items.forEach(x => helper());
"""
        edges, gaps = self._run(tmp_path, "mod", src)
        assert not any(e.callee_expr == "helper" for e in edges)
        assert not any(g.expr == "helper" for g in gaps)

    def test_top_level_named_arrow_const_still_own_scope(self, tmp_path: Path) -> None:
        # Regression guard: a TOP-LEVEL named arrow-const remains its own caller
        # scope (must NOT be swallowed by the callback-attribution change).
        src = """\
function target() {}
const runner = () => { target(); };
"""
        edges, _gaps = self._run(tmp_path, "mod", src)
        edge = next(e for e in edges if e.callee_expr == "target")
        assert edge.caller == "mod.runner"
        assert edge.callee == "mod.target"
