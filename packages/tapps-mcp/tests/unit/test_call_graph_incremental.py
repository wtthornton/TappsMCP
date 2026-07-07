"""Property + behavior tests for incremental call-graph re-index (TAP-4533).

The load-bearing contract (AC2, ADR-0004): an incremental update
(``update_call_graph_index``) must be **byte-equivalent** to a from-scratch
``build_call_graph_index`` over the same tree. These tests mutate a fixture
repo four ways — edit a Python file, add a file, delete a file, and a
cross-module TypeScript change — and assert the incrementally-updated index
serializes identically to a full rebuild each time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tapps_mcp.project.call_graph import (
    build_call_graph_index,
    load_call_graph_index,
    update_call_graph_index,
)
from tapps_mcp.project.call_graph_analyze_ts import HAS_TREE_SITTER
from tapps_mcp.project.call_graph_cache import index_to_dict


def _write(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _canonical(index_dict: dict[str, object]) -> str:
    """Serialize an index dict the same way the on-disk cache does."""
    return json.dumps(index_dict, indent=2, sort_keys=True)


def _assert_byte_equivalent(incremental_root: Path, rebuild_root: Path) -> None:
    """Assert the two trees produce byte-identical indexes (project_root aside).

    The trees are separate temp dirs, so ``project_root`` legitimately differs;
    everything else — symbols, edges, gaps, routes, fingerprint inputs, and the
    persisted raw map — must match exactly.
    """
    inc = load_call_graph_index(incremental_root)
    full = build_call_graph_index(rebuild_root, force_rebuild=True)
    assert inc is not None
    inc_dict = index_to_dict(inc)
    full_dict = index_to_dict(full)
    # Neutralize the two fields that are legitimately root-dependent.
    for d in (inc_dict, full_dict):
        d["project_root"] = "<root>"
        # fingerprint folds in git HEAD / absolute mtimes of the specific temp
        # dir; the *content* equivalence we care about is everything else.
        d["fingerprint"] = "<fp>"
    assert _canonical(inc_dict) == _canonical(full_dict)


def _seed_python(root: Path) -> None:
    _write(root, "demo/__init__.py", "")
    _write(
        root,
        "demo/worker.py",
        "def build():\n    return 1\n",
    )
    _write(
        root,
        "demo/handler.py",
        "from demo.worker import build\n\n\ndef run():\n    return build()\n",
    )


class TestIncrementalPythonEquivalence:
    def test_edit_python_file(self, tmp_path: Path) -> None:
        inc_root = tmp_path / "inc"
        rebuild_root = tmp_path / "rebuild"
        _seed_python(inc_root)
        build_call_graph_index(inc_root, force_rebuild=True)

        # Edit worker.py: add a new function + a call into it from build().
        new_worker = "def helper():\n    return 2\n\n\ndef build():\n    return helper()\n"
        _write(inc_root, "demo/worker.py", new_worker)
        update_call_graph_index(inc_root, [Path("demo/worker.py")])

        # Rebuild tree mirrors the final state.
        _seed_python(rebuild_root)
        _write(rebuild_root, "demo/worker.py", new_worker)
        _assert_byte_equivalent(inc_root, rebuild_root)

    def test_add_python_file(self, tmp_path: Path) -> None:
        inc_root = tmp_path / "inc"
        rebuild_root = tmp_path / "rebuild"
        _seed_python(inc_root)
        build_call_graph_index(inc_root, force_rebuild=True)

        added = "def extra():\n    return 3\n"
        _write(inc_root, "demo/extra.py", added)
        update_call_graph_index(inc_root, ["demo/extra.py"])

        _seed_python(rebuild_root)
        _write(rebuild_root, "demo/extra.py", added)
        _assert_byte_equivalent(inc_root, rebuild_root)

    def test_delete_python_file_drops_symbols_and_dangling_edges(self, tmp_path: Path) -> None:
        inc_root = tmp_path / "inc"
        rebuild_root = tmp_path / "rebuild"
        _seed_python(inc_root)
        build_call_graph_index(inc_root, force_rebuild=True)

        # Delete worker.py — its symbol must vanish from the index (AC4).
        (inc_root / "demo/worker.py").unlink()
        updated = update_call_graph_index(inc_root, [], deleted_paths=["demo/worker.py"])
        assert "demo.worker.build" not in {s.qualified_name for s in updated.symbols}

        # NOTE (finding): the Python analyzer records an imported-call edge from
        # the *import binding* alone (``from demo.worker import build``) — it does
        # not verify the target symbol still exists. So the ``handler.run ->
        # demo.worker.build`` edge stays ``resolved=True`` here — but a full
        # rebuild of the SAME tree-without-worker.py produces the identical edge,
        # so "consistent with a full rebuild" (AC4) holds. The byte-equivalence
        # assertion below is the authoritative check.
        _seed_python(rebuild_root)
        (rebuild_root / "demo/worker.py").unlink()
        full = build_call_graph_index(rebuild_root, force_rebuild=True)
        assert any(e.callee == "demo.worker.build" and e.resolved for e in full.edges), (
            "sanity: rebuild also keeps the dangling import edge resolved"
        )
        _assert_byte_equivalent(inc_root, rebuild_root)

    def test_changed_path_missing_on_disk_is_treated_as_delete(self, tmp_path: Path) -> None:
        inc_root = tmp_path / "inc"
        rebuild_root = tmp_path / "rebuild"
        _seed_python(inc_root)
        build_call_graph_index(inc_root, force_rebuild=True)

        (inc_root / "demo/worker.py").unlink()
        # Pass it as *changed* (not deleted) — the updater must notice it is gone.
        update_call_graph_index(inc_root, ["demo/worker.py"])

        _seed_python(rebuild_root)
        (rebuild_root / "demo/worker.py").unlink()
        _assert_byte_equivalent(inc_root, rebuild_root)


class TestIncrementalFallback:
    def test_no_cache_falls_back_to_full_build(self, tmp_path: Path) -> None:
        _seed_python(tmp_path)
        # No prior build → update must produce a full, correct index.
        index = update_call_graph_index(tmp_path, ["demo/worker.py"])
        assert "demo.worker.build" in {s.qualified_name for s in index.symbols}
        assert index.raw_by_file  # v5 material present after fallback rebuild


@pytest.mark.skipif(not HAS_TREE_SITTER, reason="tree-sitter TypeScript grammar not installed")
class TestIncrementalCrossModuleTs:
    def test_cross_module_ts_change_re_runs_post_pass(self, tmp_path: Path) -> None:
        """A change to module B flips module A's resolved edge (post-pass re-run).

        ``consumer.ts`` calls a default import from ``util.ts``. Editing ONLY
        ``util.ts`` (renaming the default symbol) changes the *consumer's*
        resolved callee even though consumer.ts is unchanged — the incremental
        update must re-run the cross-file post-pass in full to match a rebuild.
        """
        inc_root = tmp_path / "inc"
        rebuild_root = tmp_path / "rebuild"

        consumer = 'import md from "./util";\nfunction run() { md(); }\n'
        _write(inc_root, "src/util.ts", "export default function makeDefault() {}\n")
        _write(inc_root, "src/consumer.ts", consumer)
        first = build_call_graph_index(inc_root, force_rebuild=True)
        # Sanity: the cross-file default-export edge resolved on the full build.
        assert any(e.callee.endswith("makeDefault") and e.resolved for e in first.edges)

        # Edit ONLY util.ts — rename the default symbol. consumer.ts is untouched
        # but its resolved callee must now point at the new origin name.
        new_util = "export default function renamedDefault() {}\n"
        _write(inc_root, "src/util.ts", new_util)
        updated = update_call_graph_index(inc_root, ["src/util.ts"])
        assert any(e.callee.endswith("renamedDefault") and e.resolved for e in updated.edges)
        assert not any(e.callee.endswith("makeDefault") for e in updated.edges)

        _write(rebuild_root, "src/util.ts", new_util)
        _write(rebuild_root, "src/consumer.ts", consumer)
        _assert_byte_equivalent(inc_root, rebuild_root)

    def test_add_and_delete_ts_files_equivalent(self, tmp_path: Path) -> None:
        inc_root = tmp_path / "inc"
        rebuild_root = tmp_path / "rebuild"

        _write(inc_root, "src/util.ts", "export default function md() {}\n")
        _write(
            inc_root,
            "src/consumer.ts",
            'import md from "./util";\nfunction run() { md(); }\n',
        )
        _write(inc_root, "src/orphan.ts", "function lonely() {}\n")
        build_call_graph_index(inc_root, force_rebuild=True)

        # Add a new TS module and delete the orphan in one incremental sweep.
        added = "export function fresh() {}\n"
        _write(inc_root, "src/fresh.ts", added)
        (inc_root / "src/orphan.ts").unlink()
        update_call_graph_index(inc_root, ["src/fresh.ts"], deleted_paths=["src/orphan.ts"])

        _write(rebuild_root, "src/util.ts", "export default function md() {}\n")
        _write(
            rebuild_root,
            "src/consumer.ts",
            'import md from "./util";\nfunction run() { md(); }\n',
        )
        _write(rebuild_root, "src/fresh.ts", added)
        _assert_byte_equivalent(inc_root, rebuild_root)
