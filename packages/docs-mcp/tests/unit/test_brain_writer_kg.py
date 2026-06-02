"""Tests for docs_mcp.integrations.brain_writer KG triple emission (TAP-1948).

The bridge is replaced with a FakeBridge that records upsert_entity /
upsert_edge / add_evidence calls and enforces ADR-012 evidence on edges, so
tests run without a live tapps-brain. The import graph is patched per test
that exercises depends_on edges. asyncio auto-mode means tests need no marker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from docs_mcp import integrations
from docs_mcp.analyzers.dependency import ImportEdge, ImportGraph
from docs_mcp.analyzers.models import ModuleMap, ModuleNode
from docs_mcp.generators.architecture import ArchitectureResult
from docs_mcp.integrations.brain_writer import ArchitectureBrainWriter, BrainWriteResult

# ---------------------------------------------------------------------------
# Stubs / helpers
# ---------------------------------------------------------------------------


class FakeBridge:
    """Records the three KG-shim calls and enforces ADR-012 on edges.

    Returns a stable, readable entity id (``e:<type>:<name>``) so edge wiring
    can be asserted. Set ``degraded=True`` to simulate circuit-open queueing.
    """

    def __init__(self, *, degraded: bool = False) -> None:
        self.entities: list[tuple[str, str, dict[str, Any] | None]] = []
        self.edges: list[tuple[str, str, str, dict[str, Any]]] = []
        self.evidence: list[dict[str, Any]] = []
        self._degraded = degraded

    def _result(self, base: dict[str, Any]) -> dict[str, Any]:
        if self._degraded:
            base = {**base, "degraded": True}
        return base

    async def upsert_entity(
        self,
        canonical_name: str,
        entity_type: str,
        *,
        metadata: dict[str, Any] | None = None,
        project_id: str = "",
    ) -> dict[str, Any]:
        self.entities.append((canonical_name, entity_type, metadata))
        return self._result({"entity_id": f"e:{entity_type}:{canonical_name}"})

    async def upsert_edge(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        *,
        evidence: dict[str, Any],
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        if not evidence or not evidence.get("file_path"):
            raise ValueError("ADR-012: evidence required")
        self.edges.append((subject_id, predicate, object_id, evidence))
        return self._result({"recorded": True})

    async def add_evidence(
        self,
        *,
        file_path: str,
        line_range: str,
        commit_sha: str,
        entity_id: str = "",
        edge_id: str = "",
    ) -> dict[str, Any]:
        self.evidence.append(
            {
                "file_path": file_path,
                "line_range": line_range,
                "commit_sha": commit_sha,
                "entity_id": entity_id,
                "edge_id": edge_id,
            }
        )
        return self._result({"recorded": True})


def _writer(tmp_path: Path, bridge: FakeBridge) -> ArchitectureBrainWriter:
    writer = ArchitectureBrainWriter(tmp_path)
    writer._bridge = bridge
    writer._bridge_resolved = True
    return writer


def _arch_result(**kwargs: Any) -> ArchitectureResult:
    defaults: dict[str, Any] = {
        "content": "<html></html>",
        "package_count": 3,
        "module_count": 12,
        "edge_count": 20,
        "class_count": 8,
    }
    defaults.update(kwargs)
    return ArchitectureResult(**defaults)


def _map(nodes: list[ModuleNode]) -> ModuleMap:
    return ModuleMap(project_root="/r", project_name="proj", module_tree=nodes)


def _patch_graph(graph: ImportGraph) -> Any:
    """Patch ImportGraphBuilder so build() returns *graph*."""
    patcher = patch("docs_mcp.analyzers.dependency.ImportGraphBuilder")
    builder = patcher.start()
    builder.return_value.build.return_value = graph
    return patcher


# ---------------------------------------------------------------------------
# write_from_architecture_result — project-level entity
# ---------------------------------------------------------------------------


class TestArchitectureResult:
    async def test_upserts_single_project_entity(self, tmp_path: Path) -> None:
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        result = await writer.write_from_architecture_result(_arch_result(), "myproject")
        assert result.entities_written == 1
        assert result.failed == 0
        assert bridge.entities == [
            (
                "myproject",
                "project",
                {"packages": 3, "modules": 12, "import_edges": 20, "classes": 8},
            )
        ]

    async def test_project_entity_gets_evidence_row(self, tmp_path: Path) -> None:
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        result = await writer.write_from_architecture_result(_arch_result(), "p")
        assert result.evidence_rows == 1
        assert len(bridge.evidence) == 1
        assert bridge.evidence[0]["entity_id"] == "e:project:p"

    async def test_degraded_when_circuit_open(self, tmp_path: Path) -> None:
        bridge = FakeBridge(degraded=True)
        writer = _writer(tmp_path, bridge)
        result = await writer.write_from_architecture_result(_arch_result(), "p")
        assert result.degraded is True


# ---------------------------------------------------------------------------
# write_from_module_map — entities, symbols, exports edges
# ---------------------------------------------------------------------------


class TestModuleMapStructure:
    async def test_emits_package_and_module_entities(self, tmp_path: Path) -> None:
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        node = ModuleNode(
            name="pkg",
            path="src/pkg",
            is_package=True,
            submodules=[ModuleNode(name="pkg.mod", path="src/pkg/mod.py", is_package=False)],
        )
        patcher = _patch_graph(ImportGraph())
        try:
            result = await writer.write_from_module_map(_map([node]))
        finally:
            patcher.stop()
        types = {(name, etype) for name, etype, _ in bridge.entities}
        assert ("pkg", "package") in types
        assert ("pkg.mod", "module") in types
        assert result.entities_written == 2

    async def test_symbols_become_entities_and_exports_edges(self, tmp_path: Path) -> None:
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        node = ModuleNode(
            name="pkg.mod", path="src/pkg/mod.py", is_package=False, all_exports=["foo", "Bar"]
        )
        patcher = _patch_graph(ImportGraph())
        try:
            result = await writer.write_from_module_map(_map([node]))
        finally:
            patcher.stop()
        names = {name for name, _, _ in bridge.entities}
        assert names == {"pkg.mod", "pkg.mod.foo", "pkg.mod.Bar"}
        exports = [(s, o) for s, p, o, _ in bridge.edges if p == "exports"]
        assert ("e:module:pkg.mod", "e:symbol:pkg.mod.foo") in exports
        assert ("e:module:pkg.mod", "e:symbol:pkg.mod.Bar") in exports
        assert result.entities_written == 3
        assert result.edges_written == 2

    async def test_every_entity_and_edge_has_grounding_evidence(self, tmp_path: Path) -> None:
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        node = ModuleNode(
            name="pkg.mod", path="src/pkg/mod.py", is_package=False, all_exports=["foo"]
        )
        patcher = _patch_graph(ImportGraph())
        try:
            result = await writer.write_from_module_map(_map([node]))
        finally:
            patcher.stop()
        # 2 entity evidence rows (module + symbol) recorded via add_evidence,
        # 1 edge-embedded evidence row (the exports edge) — 3 total.
        assert len(bridge.evidence) == 2
        assert result.evidence_rows == 3
        assert all(e["file_path"] == "src/pkg/mod.py" for e in bridge.evidence)

    async def test_entity_metadata_from_node(self, tmp_path: Path) -> None:
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        node = ModuleNode(
            name="pkg.mod",
            path="src/pkg/mod.py",
            is_package=False,
            module_docstring="Does the thing.\nMore detail.",
            public_api_count=5,
            class_count=2,
            function_count=3,
        )
        patcher = _patch_graph(ImportGraph())
        try:
            await writer.write_from_module_map(_map([node]))
        finally:
            patcher.stop()
        _name, _etype, metadata = bridge.entities[0]
        assert metadata == {
            "summary": "Does the thing",
            "public_api_count": 5,
            "class_count": 2,
            "function_count": 3,
        }

    async def test_symbols_capped(self, tmp_path: Path) -> None:
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        node = ModuleNode(
            name="big",
            path="big.py",
            is_package=False,
            all_exports=[f"sym{i}" for i in range(120)],
        )
        patcher = _patch_graph(ImportGraph())
        try:
            await writer.write_from_module_map(_map([node]))
        finally:
            patcher.stop()
        symbol_entities = [n for n, t, _ in bridge.entities if t == "symbol"]
        assert len(symbol_entities) == 50  # _MAX_SYMBOLS_PER_NODE


# ---------------------------------------------------------------------------
# write_from_module_map — depends_on import edges
# ---------------------------------------------------------------------------


class TestImportEdges:
    async def test_imports_become_depends_on_edges_with_line_evidence(
        self, tmp_path: Path
    ) -> None:
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        graph = ImportGraph(edges=[ImportEdge(source="pkg.a", target="pkg.b", line=12)])
        patcher = _patch_graph(graph)
        try:
            result = await writer.write_from_module_map(_map([]))
        finally:
            patcher.stop()
        deps = [(s, o, ev) for s, p, o, ev in bridge.edges if p == "depends_on"]
        assert len(deps) == 1
        subject, obj, evidence = deps[0]
        assert subject == "e:module:pkg.a"
        assert obj == "e:module:pkg.b"
        assert evidence["line_range"] == "12"
        assert result.edges_written == 1

    async def test_import_graph_failure_is_non_fatal(self, tmp_path: Path) -> None:
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        patcher = patch("docs_mcp.analyzers.dependency.ImportGraphBuilder")
        builder = patcher.start()
        builder.return_value.build.side_effect = RuntimeError("boom")
        try:
            result = await writer.write_from_module_map(_map([]))
        finally:
            patcher.stop()
        assert result.available is True
        assert not any(p == "depends_on" for _, p, _, _ in bridge.edges)


# ---------------------------------------------------------------------------
# Availability + flat-path removal guards
# ---------------------------------------------------------------------------


class TestAvailability:
    async def test_unavailable_when_bridge_none(self, tmp_path: Path) -> None:
        writer = ArchitectureBrainWriter(tmp_path)
        with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=None):
            result = await writer.write_from_module_map(_map([]))
        assert result.available is False

    async def test_unavailable_when_factory_raises(self, tmp_path: Path) -> None:
        writer = ArchitectureBrainWriter(tmp_path)
        with patch(
            "tapps_core.brain_bridge.create_brain_bridge",
            side_effect=RuntimeError("dsn invalid"),
        ):
            result = await writer.write_from_architecture_result(_arch_result(), "p")
        assert result.available is False


class TestFailureHandling:
    async def test_entity_upsert_exception_counts_failed(self, tmp_path: Path) -> None:
        bridge = FakeBridge()

        async def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
            raise RuntimeError("brain down")

        bridge.upsert_entity = _boom  # type: ignore[method-assign]
        writer = _writer(tmp_path, bridge)
        result = await writer.write_from_architecture_result(_arch_result(), "p")
        assert result.failed == 1
        assert result.entities_written == 0

    async def test_edge_without_file_path_is_rejected_not_raised(self, tmp_path: Path) -> None:
        """A path-less node cannot ground its exports edge — it is dropped
        (failed++) via the ADR-012 guard rather than crashing the write."""
        bridge = FakeBridge()
        writer = _writer(tmp_path, bridge)
        node = ModuleNode(name="mod", path="", is_package=False, all_exports=["foo"])
        patcher = _patch_graph(ImportGraph())
        try:
            result = await writer.write_from_module_map(_map([node]))
        finally:
            patcher.stop()
        assert not any(p == "exports" for _, p, _, _ in bridge.edges)
        assert result.failed >= 1


class TestNoFlatWritePath:
    def test_no_flat_save_or_tier_remains(self) -> None:
        """Regression guard: TAP-1948 removed the flat memory write path."""
        src = Path(integrations.brain_writer.__file__).read_text(encoding="utf-8")
        assert "bridge.save(" not in src
        assert "bridge.supersede(" not in src
        assert "_MEMORY_TIER" not in src
        assert "_BASE_TAGS" not in src

    def test_result_to_dict_reports_triple_counts(self) -> None:
        result = BrainWriteResult(
            entities_written=2, edges_written=1, evidence_rows=3, degraded=True
        )
        payload = result.to_dict()["brain_write"]
        assert payload["entities_written"] == 2
        assert payload["edges_written"] == 1
        assert payload["evidence_rows"] == 3
        assert payload["degraded"] is True
        assert result.total == 6
