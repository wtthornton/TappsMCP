"""tapps-brain write path for docs-mcp architecture facts (STORY-102.2).

When ``brain_write_enabled`` is set in ``.docsmcp.yaml``, this module writes
structured architecture facts into tapps-brain after analysis tools run.
Facts are written as MemoryEntry records using the InsightEntry tagging
convention so that :func:`tapps_core.insights.migration.bulk_migrate` can
promote them later.

Writes route through :class:`tapps_core.brain_bridge.BrainBridge` (TAP-1919,
ADR-0001) so every save participates in the bridge's circuit-breaker,
profile filter (TAP-1579), content-safety gate, Hive routing, and
async-native Postgres write path (TAP-1117). Bypassing the bridge — e.g.
importing :class:`tapps_brain.store.MemoryStore` directly — is a violation
of ``.claude/rules/integration-hygiene.md`` and produces silent data loss
into an embedded SQLite shadow.

Profile pinning (TAP-1925)
--------------------------
The bridge factory is called with ``default_profile="agent_brain"`` so
docs-mcp only sees the 10-tool ``brain_*`` facade on the wire
(``brain_remember``, ``brain_recall``, ``brain_record_event``,
``brain_get_neighbors``, ``brain_explain_connection``). Any attempt to call
``memory_*``, ``hive_*``, or ``maintenance_*`` tools surfaces a
:class:`tapps_core.brain_bridge.ToolNotInProfileError` — loud, never silent.
The ``agent_brain`` profile is the minimum surface docs-mcp needs and
reduces the ``/v1/tools/list`` payload from ~40 entries to 10.

KG triple emission (TAP-1948)
-----------------------------
This module emits Knowledge-Graph triples — entities, typed edges, and
grounding evidence — rather than flat ``arch.{project}.*`` memory entries.
All writes go through the ``BrainBridge`` semantic-upsert shims (TAP-1947),
which delegate to ``record_kg_event`` (no second write path):

  - ``package`` / ``module`` entity per node in the module tree
  - ``symbol`` entity per public API name, with an ``exports`` edge from its
    owning module
  - ``depends_on`` edge per internal import (from the import graph)
  - one evidence row per entity and per edge, anchored to ``(file_path,
    line_range, commit_sha)`` per GroundedKG-RAG

Entity IDs are the deterministic UUIDv5 from ``kg_keys.entity_uuid``
(TAP-1949), so re-running an analysis upserts the same rows instead of
duplicating them. The brain scopes entities by the bridge's project
(``X-Project-Id`` header), so the shims are called with the default
``project_id``.

tapps-brain availability
------------------------
tapps-brain is an optional runtime dependency of docs-mcp; the BrainBridge
factory in ``tapps_core.brain_bridge`` returns ``None`` when no transport is
configured (no ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` and no
``TAPPS_BRAIN_DATABASE_URL``). Callers receive ``BrainWriteResult(available=False)``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from docs_mcp.analyzers.models import ModuleMap, ModuleNode
    from docs_mcp.generators.architecture import ArchitectureResult

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Entity types — the closed vocabulary shared with the brain KG schema.
_ENTITY_PROJECT = "project"
_ENTITY_PACKAGE = "package"
_ENTITY_MODULE = "module"
_ENTITY_SYMBOL = "symbol"

# Caps to avoid flooding the graph on large projects (logged when reached).
_MAX_NODES = 200
_MAX_SYMBOLS_PER_NODE = 50
_MAX_IMPORT_EDGES = 400
# Max metadata string length (tapps-brain enforces 4096 chars on values).
_MAX_VALUE_LEN = 4096


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(value: str) -> str:
    """Truncate a metadata string to tapps-brain's max value length."""
    return value[:_MAX_VALUE_LEN]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class BrainWriteResult:
    """Result of a KG triple-write operation.

    Reports entity / edge / evidence counts separately (TAP-1948).
    ``degraded`` is set when any write was queued offline (circuit open).
    """

    entities_written: int = 0
    edges_written: int = 0
    evidence_rows: int = 0
    failed: int = 0
    elapsed_ms: float = 0.0
    available: bool = True
    degraded: bool = False

    @property
    def total(self) -> int:
        return self.entities_written + self.edges_written + self.evidence_rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "brain_write": {
                "available": self.available,
                "degraded": self.degraded,
                "entities_written": self.entities_written,
                "edges_written": self.edges_written,
                "evidence_rows": self.evidence_rows,
                "failed": self.failed,
                "elapsed_ms": round(self.elapsed_ms, 1),
            }
        }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class ArchitectureBrainWriter:
    """Writes architecture facts into tapps-brain via :class:`BrainBridge`.

    Instantiated once per tool call. The bridge is opened lazily and the
    writer falls back to ``BrainWriteResult(available=False)`` when no
    bridge transport is configured (no HTTP URL, no in-process DSN). All
    writes go through the bridge's circuit-breaker, profile filter,
    content-safety gate, and async-native write path.

    Args:
        project_root: Project root path (passed to in-process bridge for
            ``project_dir`` resolution; ignored by the HTTP bridge).
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._bridge: Any = None  # tapps_core.brain_bridge.BrainBridge | None
        self._bridge_resolved: bool = False
        self._sha: str | None = None  # cached HEAD sha for evidence grounding

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def write_from_architecture_result(
        self,
        result: ArchitectureResult,
        project_name: str,
    ) -> BrainWriteResult:
        """Upsert a project-level KG entity summarising the architecture.

        ``ArchitectureResult`` carries only aggregate counts (no per-node
        structure), so this path emits a single ``project`` entity with the
        package / module / edge / class counts as metadata, plus one evidence
        row. The per-package / per-module / per-symbol entities and the
        ``depends_on`` / ``exports`` edges are emitted by
        :meth:`write_from_module_map`, which receives the full module tree.
        """
        t0 = time.perf_counter()
        bridge = self._get_bridge()
        if bridge is None:
            return BrainWriteResult(available=False)

        br = BrainWriteResult()
        sha = self._commit_sha()
        metadata = {
            "packages": result.package_count,
            "modules": result.module_count,
            "import_edges": result.edge_count,
            "classes": result.class_count,
        }
        await self._upsert_entity(
            bridge, br, project_name, _ENTITY_PROJECT, sha, ".", metadata=metadata
        )
        br.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "arch_brain_write_structure",
            project=project_name,
            entities=br.entities_written,
            failed=br.failed,
        )
        return br

    async def write_from_module_map(self, module_map: ModuleMap) -> BrainWriteResult:
        """Emit the KG structure for a project.

        Walks the module tree to upsert ``package`` / ``module`` entities, a
        ``symbol`` entity + ``exports`` edge per public API name, and a
        ``depends_on`` edge per internal import (from the import graph). Every
        entity and edge gets an evidence row anchored to its producing file.
        """
        t0 = time.perf_counter()
        bridge = self._get_bridge()
        if bridge is None:
            return BrainWriteResult(available=False)

        br = BrainWriteResult()
        project = module_map.project_name
        sha = self._commit_sha()
        # (entity_type, canonical_name) -> entity_id, dedups endpoints shared
        # between the tree walk and the import graph within one run.
        seen: dict[tuple[str, str], str] = {}

        budget = _MAX_NODES
        for node in module_map.module_tree:
            if budget <= 0:
                logger.info("kg_nodes_capped", project=project, cap=_MAX_NODES)
                break
            budget = await self._emit_node(bridge, br, seen, node, sha, budget)

        await self._emit_imports(bridge, br, seen, sha)

        br.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "arch_brain_write_module_map",
            project=project,
            entities=br.entities_written,
            edges=br.edges_written,
            evidence=br.evidence_rows,
            failed=br.failed,
        )
        return br

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_bridge(self) -> Any:
        """Return a cached BrainBridge, or None if no transport is configured.

        Delegates to :func:`tapps_core.brain_bridge.create_brain_bridge`. The
        factory selects between HttpBrainBridge (when
        ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` is set) and the in-process
        BrainBridge (when ``TAPPS_BRAIN_DATABASE_URL`` is set), and returns
        None when neither is configured. Result is cached for the lifetime
        of this writer instance.
        """
        if self._bridge_resolved:
            return self._bridge
        self._bridge_resolved = True
        try:
            from tapps_core.brain_bridge import create_brain_bridge

            self._bridge = create_brain_bridge(settings=None, default_profile="agent_brain")
            if self._bridge is None:
                logger.debug("brain_bridge_unavailable", root=str(self._root))
            return self._bridge
        except ImportError:
            logger.debug("tapps_core_not_available", root=str(self._root))
            return None
        except Exception:
            logger.warning(
                "brain_bridge_open_failed",
                root=str(self._root),
                exc_info=True,
            )
            return None

    async def _emit_node(
        self,
        bridge: Any,
        br: BrainWriteResult,
        seen: dict[tuple[str, str], str],
        node: ModuleNode,
        sha: str,
        budget: int,
    ) -> int:
        """Upsert a node's entity, its symbol entities + ``exports`` edges, and
        recurse into submodules. Returns the remaining node budget."""
        if budget <= 0:
            return 0
        entity_type = _ENTITY_PACKAGE if node.is_package else _ENTITY_MODULE
        module_id = await self._get_or_upsert_entity(
            bridge, br, seen, node.name, entity_type, sha, node.path,
            metadata=self._node_metadata(node),
        )
        budget -= 1

        exports = node.all_exports or []
        if len(exports) > _MAX_SYMBOLS_PER_NODE:
            logger.info(
                "kg_symbols_capped", module=node.name, total=len(exports),
                cap=_MAX_SYMBOLS_PER_NODE,
            )
        for symbol in exports[:_MAX_SYMBOLS_PER_NODE]:
            symbol_id = await self._get_or_upsert_entity(
                bridge, br, seen, f"{node.name}.{symbol}", _ENTITY_SYMBOL, sha, node.path,
            )
            if module_id and symbol_id:
                await self._upsert_edge(
                    bridge, br, module_id, "exports", symbol_id, node.path, sha,
                )

        for submodule in node.submodules:
            if budget <= 0:
                break
            budget = await self._emit_node(bridge, br, seen, submodule, sha, budget)
        return budget

    async def _emit_imports(
        self,
        bridge: Any,
        br: BrainWriteResult,
        seen: dict[tuple[str, str], str],
        sha: str,
    ) -> None:
        """Upsert a ``depends_on`` edge per internal import, grounded at the
        import statement's ``file:line``."""
        try:
            from docs_mcp.analyzers.dependency import ImportGraphBuilder

            graph = ImportGraphBuilder().build(self._root)
        except Exception:
            logger.warning("kg_import_graph_failed", root=str(self._root), exc_info=True)
            return

        edges = graph.edges
        if len(edges) > _MAX_IMPORT_EDGES:
            logger.info("kg_import_edges_capped", total=len(edges), cap=_MAX_IMPORT_EDGES)
        for edge in edges[:_MAX_IMPORT_EDGES]:
            if not edge.source or not edge.target:
                continue
            source_id = await self._get_or_upsert_entity(
                bridge, br, seen, edge.source, _ENTITY_MODULE, sha, edge.source,
            )
            target_id = await self._get_or_upsert_entity(
                bridge, br, seen, edge.target, _ENTITY_MODULE, sha, edge.target,
            )
            if source_id and target_id:
                await self._upsert_edge(
                    bridge, br, source_id, "depends_on", target_id, edge.source, sha,
                    line_range=str(edge.line),
                )

    async def _get_or_upsert_entity(
        self,
        bridge: Any,
        br: BrainWriteResult,
        seen: dict[tuple[str, str], str],
        canonical_name: str,
        entity_type: str,
        sha: str,
        file_path: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Upsert an entity once per run; cached by ``(type, name)``."""
        cache_key = (entity_type, canonical_name)
        cached = seen.get(cache_key)
        if cached is not None:
            return cached
        entity_id = await self._upsert_entity(
            bridge, br, canonical_name, entity_type, sha, file_path, metadata=metadata,
        )
        seen[cache_key] = entity_id
        return entity_id

    async def _upsert_entity(
        self,
        bridge: Any,
        br: BrainWriteResult,
        canonical_name: str,
        entity_type: str,
        sha: str,
        file_path: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Upsert one entity and attach its evidence row. Returns the id ("" on
        failure)."""
        try:
            result = await bridge.upsert_entity(
                canonical_name, entity_type, metadata=metadata,
            )
        except Exception:
            logger.warning("kg_entity_upsert_failed", name=canonical_name, exc_info=True)
            br.failed += 1
            return ""
        self._note_degraded(br, result)
        entity_id = str(result.get("entity_id", "")) if isinstance(result, dict) else ""
        br.entities_written += 1
        if entity_id and file_path:
            await self._add_evidence(bridge, br, file_path, sha, entity_id=entity_id)
        return entity_id

    async def _upsert_edge(
        self,
        bridge: Any,
        br: BrainWriteResult,
        subject_id: str,
        predicate: str,
        object_id: str,
        file_path: str,
        sha: str,
        *,
        line_range: str = "",
    ) -> None:
        """Upsert one typed edge with its paired evidence row (ADR-012)."""
        evidence = {"file_path": file_path, "line_range": line_range, "commit_sha": sha}
        try:
            result = await bridge.upsert_edge(
                subject_id, predicate, object_id, evidence=evidence,
            )
        except ValueError:
            # ADR-012 evidence-required — unreachable (file_path always passed),
            # guarded so a future caller omission fails loud, not silent.
            logger.warning("kg_edge_rejected", predicate=predicate)
            br.failed += 1
            return
        except Exception:
            logger.warning("kg_edge_failed", predicate=predicate, exc_info=True)
            br.failed += 1
            return
        self._note_degraded(br, result)
        br.edges_written += 1
        br.evidence_rows += 1  # the edge carries a paired evidence row

    async def _add_evidence(
        self,
        bridge: Any,
        br: BrainWriteResult,
        file_path: str,
        sha: str,
        *,
        entity_id: str = "",
        edge_id: str = "",
        line_range: str = "",
    ) -> None:
        """Attach a standalone evidence row to an entity or edge."""
        try:
            result = await bridge.add_evidence(
                file_path=file_path, line_range=line_range, commit_sha=sha,
                entity_id=entity_id, edge_id=edge_id,
            )
        except Exception:
            logger.warning("kg_evidence_failed", file_path=file_path, exc_info=True)
            br.failed += 1
            return
        self._note_degraded(br, result)
        br.evidence_rows += 1

    @staticmethod
    def _note_degraded(br: BrainWriteResult, result: Any) -> None:
        """Flag the result degraded when a write was queued offline."""
        if isinstance(result, dict) and result.get("degraded"):
            br.degraded = True

    @staticmethod
    def _node_metadata(node: ModuleNode) -> dict[str, Any] | None:
        """Build the metadata dict stored on a module/package entity."""
        metadata: dict[str, Any] = {}
        if node.module_docstring:
            first_line = node.module_docstring.split("\n")[0].strip().rstrip(".")
            if first_line:
                metadata["summary"] = _truncate(first_line)
        if node.public_api_count:
            metadata["public_api_count"] = node.public_api_count
        if node.class_count:
            metadata["class_count"] = node.class_count
        if node.function_count:
            metadata["function_count"] = node.function_count
        return metadata or None

    def _commit_sha(self) -> str:
        """Best-effort short HEAD sha for evidence grounding (cached, "" if no
        repo)."""
        if self._sha is not None:
            return self._sha
        sha = ""
        try:
            import git

            sha = git.Repo(self._root).head.commit.hexsha[:12]
        except Exception:
            logger.debug("kg_commit_sha_unavailable", root=str(self._root))
        self._sha = sha
        return sha
