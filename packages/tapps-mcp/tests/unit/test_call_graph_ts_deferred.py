"""S4 cross-file TS resolution tests (TAP-4540).

Exercises the ``build_call_graph_index`` post-pass end to end: a default import
resolving to the real default symbol, a ``@/``-alias resolving via a fixture
``tsconfig.json``, and a re-export chain following through to the origin — each
with a negative counterpart (no config / no default / broken chain → honest
gap) per the deterministic contract (ADR-0004).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_analyze_ts import HAS_TREE_SITTER

pytestmark = pytest.mark.skipif(
    not HAS_TREE_SITTER, reason="tree-sitter TypeScript grammar not installed"
)


def _project(tmp_path: Path, files: dict[str, str], tsconfig: str | None = None) -> Path:
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if tsconfig is not None:
        (tmp_path / "tsconfig.json").write_text(tsconfig, encoding="utf-8")
    return tmp_path


def _edge(idx, caller: str, callee: str) -> bool:
    return any(e.caller == caller and e.callee == callee for e in idx.edges)


def _gap(idx, caller: str, expr: str, reason: str) -> bool:
    return any(
        g.caller == caller and g.expr == expr and g.reason == reason
        for g in idx.resolution_gaps
    )


class TestDefaultExportResolution:
    def test_default_import_resolves_to_default_symbol(self, tmp_path: Path) -> None:
        root = _project(
            tmp_path,
            {
                "src/util.ts": "export default function makeDefault() {}\n",
                "src/consumer.ts": (
                    'import makeDefault from "./util";\n'
                    "function run() { makeDefault(); }\n"
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _edge(idx, "consumer.run", "util.makeDefault")
        assert not _gap(idx, "consumer.run", "makeDefault", "unresolved_default_export")

    def test_default_named_export_resolves(self, tmp_path: Path) -> None:
        # `export default foo;` where foo is a local function.
        root = _project(
            tmp_path,
            {
                "src/util.ts": "function foo() {}\nexport default foo;\n",
                "src/consumer.ts": 'import md from "./util";\nfunction run() { md(); }\n',
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _edge(idx, "consumer.run", "util.foo")

    def test_no_default_symbol_stays_gap(self, tmp_path: Path) -> None:
        # NEGATIVE: the target module has no default export at all.
        root = _project(
            tmp_path,
            {
                "src/util.ts": "export const x = 1;\n",
                "src/consumer.ts": (
                    'import makeDefault from "./util";\n'
                    "function run() { makeDefault(); }\n"
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert not _edge(idx, "consumer.run", "util.makeDefault")
        assert _gap(idx, "consumer.run", "makeDefault", "unresolved_default_export")

    def test_anonymous_default_arrow_stays_gap(self, tmp_path: Path) -> None:
        # NEGATIVE: `export default () => {}` has no nameable symbol.
        root = _project(
            tmp_path,
            {
                "src/util.ts": "export default () => {};\n",
                "src/consumer.ts": 'import md from "./util";\nfunction run() { md(); }\n',
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert not any(e.callee_expr == "md" for e in idx.edges)
        assert _gap(idx, "consumer.run", "md", "unresolved_default_export")


class TestPathAliasResolution:
    _TSCONFIG = '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'

    def test_alias_named_import_resolves(self, tmp_path: Path) -> None:
        root = _project(
            tmp_path,
            {
                "src/util.ts": "export function util() {}\n",
                "src/consumer.ts": (
                    'import { util } from "@/util";\nfunction run() { util(); }\n'
                ),
            },
            tsconfig=self._TSCONFIG,
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _edge(idx, "consumer.run", "util.util")
        assert not _gap(idx, "consumer.run", "util", "path_alias_unresolved")

    def test_alias_default_import_resolves(self, tmp_path: Path) -> None:
        root = _project(
            tmp_path,
            {
                "src/util.ts": "export default function md() {}\n",
                "src/consumer.ts": 'import md from "@/util";\nfunction run() { md(); }\n',
            },
            tsconfig=self._TSCONFIG,
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _edge(idx, "consumer.run", "util.md")

    def test_alias_namespace_import_resolves(self, tmp_path: Path) -> None:
        root = _project(
            tmp_path,
            {
                "src/util.ts": "export function greet() {}\n",
                "src/consumer.ts": (
                    'import * as U from "@/util";\nfunction run() { U.greet(); }\n'
                ),
            },
            tsconfig=self._TSCONFIG,
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _edge(idx, "consumer.run", "util.greet")

    def test_no_tsconfig_stays_gap(self, tmp_path: Path) -> None:
        # NEGATIVE: without a tsconfig the alias cannot be resolved.
        root = _project(
            tmp_path,
            {
                "src/util.ts": "export function util() {}\n",
                "src/consumer.ts": (
                    'import { util } from "@/util";\nfunction run() { util(); }\n'
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert not _edge(idx, "consumer.run", "util.util")
        assert _gap(idx, "consumer.run", "util", "path_alias_unresolved")

    def test_non_matching_alias_stays_gap(self, tmp_path: Path) -> None:
        # NEGATIVE: config exists but the specifier matches no alias key.
        root = _project(
            tmp_path,
            {
                "src/util.ts": "export function util() {}\n",
                "src/consumer.ts": (
                    'import { util } from "@/util";\nfunction run() { util(); }\n'
                ),
            },
            tsconfig='{"compilerOptions": {"paths": {"#lib/*": ["lib/*"]}}}',
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _gap(idx, "consumer.run", "util", "path_alias_unresolved")


class TestReexportResolution:
    def test_named_reexport_chain_resolves(self, tmp_path: Path) -> None:
        root = _project(
            tmp_path,
            {
                "src/impl.ts": "export function origin() {}\n",
                "src/barrel.ts": 'export { origin } from "./impl";\n',
                "src/consumer.ts": (
                    'import { origin } from "./barrel";\nfunction run() { origin(); }\n'
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        # Follows through the barrel to the origin symbol.
        assert _edge(idx, "consumer.run", "impl.origin")
        assert not _edge(idx, "consumer.run", "barrel.origin")

    def test_aliased_reexport_resolves(self, tmp_path: Path) -> None:
        root = _project(
            tmp_path,
            {
                "src/impl.ts": "export function realThing() {}\n",
                "src/barrel.ts": 'export { realThing as pub } from "./impl";\n',
                "src/consumer.ts": (
                    'import { pub } from "./barrel";\nfunction run() { pub(); }\n'
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _edge(idx, "consumer.run", "impl.realThing")

    def test_star_reexport_resolves(self, tmp_path: Path) -> None:
        root = _project(
            tmp_path,
            {
                "src/impl.ts": "export function starFn() {}\n",
                "src/barrel.ts": 'export * from "./impl";\n',
                "src/consumer.ts": (
                    'import { starFn } from "./barrel";\nfunction run() { starFn(); }\n'
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _edge(idx, "consumer.run", "impl.starFn")

    def test_transitive_reexport_chain_resolves(self, tmp_path: Path) -> None:
        root = _project(
            tmp_path,
            {
                "src/impl.ts": "export function deep() {}\n",
                "src/mid.ts": 'export { deep } from "./impl";\n',
                "src/barrel.ts": 'export { deep } from "./mid";\n',
                "src/consumer.ts": (
                    'import { deep } from "./barrel";\nfunction run() { deep(); }\n'
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _edge(idx, "consumer.run", "impl.deep")

    def test_broken_reexport_chain_stays_gap(self, tmp_path: Path) -> None:
        # NEGATIVE: the barrel re-exports from a module that doesn't exist.
        root = _project(
            tmp_path,
            {
                "src/barrel.ts": 'export { origin } from "./missing";\n',
                "src/consumer.ts": (
                    'import { origin } from "./barrel";\nfunction run() { origin(); }\n'
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert not _edge(idx, "consumer.run", "barrel.origin")
        assert _gap(idx, "consumer.run", "origin", "reexport_unresolved")

    def test_reexport_cycle_stays_gap(self, tmp_path: Path) -> None:
        # NEGATIVE: a -> b -> a re-export cycle must not loop; keep the gap.
        root = _project(
            tmp_path,
            {
                "src/a.ts": 'export { x } from "./b";\n',
                "src/b.ts": 'export { x } from "./a";\n',
                "src/consumer.ts": (
                    'import { x } from "./a";\nfunction run() { x(); }\n'
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert not any(e.callee_expr == "x" for e in idx.edges)
        assert _gap(idx, "consumer.run", "x", "reexport_unresolved")


class TestNoRegressionOnResolvedCases:
    def test_plain_named_import_still_resolves(self, tmp_path: Path) -> None:
        # A direct (non-re-exported) named import must keep its edge; the
        # post-pass must not demote it.
        root = _project(
            tmp_path,
            {
                "src/util.ts": "export function greet() {}\n",
                "src/consumer.ts": (
                    'import { greet } from "./util";\nfunction run() { greet(); }\n'
                ),
            },
        )
        idx = build_call_graph_index(root, force_rebuild=True)
        assert _edge(idx, "consumer.run", "util.greet")
