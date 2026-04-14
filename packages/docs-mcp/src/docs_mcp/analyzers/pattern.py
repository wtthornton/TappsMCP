"""Architectural pattern classifier (STORY-100.1).

Classifies a Python project into one of six archetypes using deterministic
heuristics over the existing ``ModuleMap`` and ``ImportGraph`` analyzers.

Archetypes:
    - ``layered``: presentation/business/data-access/persistence layering
    - ``hexagonal``: ports/adapters organization (onion / clean arch)
    - ``microservice``: multi-service monorepo (multiple ``pyproject.toml``)
    - ``event_driven``: message-broker imports dominate the edge set
    - ``pipeline``: acyclic stage-to-stage flow (ETL / data pipeline)
    - ``monolith``: small single-package default
    - ``unknown``: no signal meets the minimum confidence floor

The classifier never calls an LLM and never hits the network. Every verdict
carries an ``evidence`` list so downstream generators (posters, ADR links)
can explain *why* a pattern was chosen.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal

import structlog
from pydantic import BaseModel

from docs_mcp.analyzers.dependency import ImportGraph
from docs_mcp.analyzers.models import ModuleMap, ModuleNode

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

Archetype = Literal[
    "layered",
    "hexagonal",
    "microservice",
    "event_driven",
    "pipeline",
    "monolith",
    "unknown",
]

_LAYER_KEYWORDS: dict[str, frozenset[str]] = {
    "presentation": frozenset({"api", "web", "ui", "views", "controllers", "routes", "presentation"}),
    "business": frozenset({"services", "business", "domain", "usecases", "use_cases", "application"}),
    "data_access": frozenset({"repositories", "repository", "dao", "data_access"}),
    "persistence": frozenset({"models", "entities", "persistence", "db", "database"}),
}

_HEX_KEYWORDS: frozenset[str] = frozenset({"ports", "adapters", "hexagonal", "core"})

_EVENT_LIBS: frozenset[str] = frozenset(
    {
        "kafka",
        "aiokafka",
        "confluent_kafka",
        "pika",  # rabbitmq
        "aio_pika",
        "celery",
        "nats",
        "redis",  # only counted when paired with pubsub keywords
        "kombu",
        "pulsar",
    }
)


class ArchetypeResult(BaseModel):
    """Outcome of architectural pattern classification."""

    archetype: Archetype
    confidence: float = 0.0
    evidence: list[str] = []
    alternatives: list[tuple[Archetype, float]] = []


class PatternClassifier:
    """Deterministic architectural pattern classifier."""

    MIN_CONFIDENCE: ClassVar[float] = 0.3

    def classify(
        self,
        project_root: Path,
        *,
        module_map: ModuleMap | None = None,
        import_graph: ImportGraph | None = None,
    ) -> ArchetypeResult:
        """Classify the project at ``project_root``.

        Args:
            project_root: Repository root directory.
            module_map: Optional pre-built module map.
            import_graph: Optional pre-built import graph.

        Returns:
            :class:`ArchetypeResult` with archetype, confidence, and evidence.
        """
        scores: dict[Archetype, float] = {}
        evidence: dict[Archetype, list[str]] = {}

        # --- Microservice: multiple pyproject.toml in subdirs ---
        service_roots = self._find_service_roots(project_root)
        if len(service_roots) >= 2:
            scores["microservice"] = min(1.0, 0.4 + 0.1 * len(service_roots))
            evidence["microservice"] = [
                f"{len(service_roots)} pyproject.toml files found: "
                + ", ".join(str(p.relative_to(project_root)) for p in service_roots[:5])
            ]

        package_names = self._collect_package_names(module_map)

        # --- Hexagonal: ports/adapters folders present ---
        hex_hits = package_names & _HEX_KEYWORDS
        if {"ports", "adapters"}.issubset(hex_hits) or len(hex_hits) >= 3:
            scores["hexagonal"] = 0.85 if {"ports", "adapters"}.issubset(hex_hits) else 0.6
            evidence["hexagonal"] = [f"ports/adapters packages present: {sorted(hex_hits)}"]

        # --- Layered: matches across 3+ canonical layer names ---
        layer_hits = [
            layer
            for layer, kws in _LAYER_KEYWORDS.items()
            if package_names & kws
        ]
        if len(layer_hits) >= 3:
            scores["layered"] = 0.5 + 0.15 * len(layer_hits)
            evidence["layered"] = [f"canonical layer packages matched: {layer_hits}"]

        # --- Event-driven: message-broker imports dominate externals ---
        event_score, event_reason = self._score_event_driven(import_graph)
        if event_score > 0:
            scores["event_driven"] = event_score
            evidence["event_driven"] = [event_reason]

        # --- Pipeline: DAG-shaped internal graph with distinct stages ---
        pipeline_score, pipeline_reason = self._score_pipeline(import_graph, package_names)
        if pipeline_score > 0:
            scores["pipeline"] = pipeline_score
            evidence["pipeline"] = [pipeline_reason]

        # --- Monolith: small single-package fallback ---
        if module_map is not None and module_map.total_packages <= 2:
            scores.setdefault("monolith", 0.4)
            evidence.setdefault(
                "monolith",
                [f"only {module_map.total_packages} top-level packages"],
            )

        if not scores:
            return ArchetypeResult(archetype="unknown", confidence=0.0)

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        winner, winner_score = ranked[0]
        if winner_score < self.MIN_CONFIDENCE:
            return ArchetypeResult(
                archetype="unknown",
                confidence=winner_score,
                evidence=evidence.get(winner, []),
                alternatives=ranked,
            )

        return ArchetypeResult(
            archetype=winner,
            confidence=round(winner_score, 2),
            evidence=evidence.get(winner, []),
            alternatives=[(a, round(s, 2)) for a, s in ranked[1:]],
        )

    # ------------------------------------------------------------------
    # Heuristic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_service_roots(project_root: Path) -> list[Path]:
        skip = {".venv", "venv", "node_modules", ".git", "dist", "build"}
        results: list[Path] = []
        for path in project_root.rglob("pyproject.toml"):
            if path.parent == project_root:
                continue
            if any(part in skip for part in path.parts):
                continue
            results.append(path.parent)
        return results

    @staticmethod
    def _collect_package_names(module_map: ModuleMap | None) -> set[str]:
        if module_map is None:
            return set()
        names: set[str] = set()

        def walk(node: ModuleNode) -> None:
            names.add(node.name.lower())
            for child in node.submodules:
                walk(child)

        for root in module_map.module_tree:
            walk(root)
        return names

    @staticmethod
    def _score_event_driven(import_graph: ImportGraph | None) -> tuple[float, str]:
        if import_graph is None:
            return 0.0, ""
        externals = {ext.lower() for ext in import_graph.external_imports}
        hits = externals & _EVENT_LIBS
        if not hits:
            return 0.0, ""
        # Redis alone is too weak — require a second signal.
        if hits == {"redis"}:
            return 0.0, ""
        score = min(0.9, 0.5 + 0.15 * len(hits))
        return score, f"message-broker libraries imported: {sorted(hits)}"

    @staticmethod
    def _score_pipeline(
        import_graph: ImportGraph | None,
        package_names: set[str],
    ) -> tuple[float, str]:
        if import_graph is None or not import_graph.edges:
            return 0.0, ""
        stage_kws = {"extract", "transform", "load", "ingest", "stage", "pipeline", "etl"}
        hits = package_names & stage_kws
        if len(hits) < 2:
            return 0.0, ""
        # Ensure acyclic-ish shape: few back-edges relative to forward edges.
        if not _looks_acyclic(import_graph):
            return 0.0, ""
        return 0.6 + 0.1 * min(3, len(hits)), f"pipeline-stage packages: {sorted(hits)}"


def _looks_acyclic(graph: ImportGraph) -> bool:
    """Cheap acyclicity proxy: fewer than 10% of edges are back-edges.

    Performs a DFS and counts edges going to an ancestor. Not a full SCC
    algorithm — good enough for a classifier heuristic.
    """
    from collections import defaultdict

    adj: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        adj[edge.source].append(edge.target)

    visited: set[str] = set()
    stack: set[str] = set()
    back_edges = 0
    total = len(graph.edges) or 1

    def dfs(node: str) -> None:
        nonlocal back_edges
        if node in stack:
            back_edges += 1
            return
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        for nxt in adj.get(node, []):
            dfs(nxt)
        stack.discard(node)

    for node in list(adj):
        dfs(node)

    return back_edges / total < 0.1
