"""Cluster Python files into session-sized audit chunks.

Standalone primitive for the proposed ``tapps_audit_campaign`` tool: takes a
project root + scope, returns groups of related files suitable for a single
review session. Uses the existing :mod:`tapps_mcp.project.import_graph` for
the dependency graph; no MCP wiring, Linear writes, or brain memory.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from tapps_mcp.project.import_graph import build_import_graph

if TYPE_CHECKING:
    from tapps_mcp.project.import_graph import ImportGraph


@dataclass
class AuditChunk:
    """A session-sized review unit."""

    session_index: int
    files: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    rationale: str = ""
    intra_edges: int = 0
    boundary_edges: int = 0

    @property
    def size(self) -> int:
        return len(self.files)


@dataclass
class ChunkPlan:
    """Result of chunking a scope into audit sessions."""

    project_root: str
    scope: str
    total_files: int
    chunks: list[AuditChunk] = field(default_factory=list)
    skipped_trivial: list[str] = field(default_factory=list)

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)


def chunk_scope(
    project_root: Path,
    scope: Path | None = None,
    *,
    graph_root: Path | None = None,
    min_size: int = 4,
    target_size: int = 6,
    max_size: int = 9,
) -> ChunkPlan:
    """Build a chunk plan for ``scope`` under ``project_root``.

    ``project_root`` controls relative paths in the output; ``graph_root``
    (defaulting to ``project_root``) is the directory used to build the
    import graph. For monorepos, set ``graph_root`` to the package's
    source root (e.g. ``packages/foo/src``) so imports like
    ``from foo.bar import baz`` resolve. ``scope`` may be a subdirectory
    under ``graph_root``.

    Sizes are advisory: components inside [min_size, max_size] pass through;
    larger ones split, smaller ones bin-pack by package affinity.
    """
    project_root = project_root.resolve()
    graph_root = (graph_root or project_root).resolve()
    scope = (scope or project_root).resolve()

    graph = build_import_graph(graph_root)

    in_scope_files: dict[str, Path] = {}
    skipped_trivial: list[str] = []
    for py_file in sorted(scope.rglob("*.py")):
        if _should_skip(py_file):
            continue
        mod = _file_to_module(py_file, graph_root)
        if not mod or mod not in graph.modules:
            continue
        if _is_trivial_file(py_file):
            skipped_trivial.append(_rel(py_file, project_root))
            continue
        in_scope_files[mod] = py_file

    if not in_scope_files:
        return ChunkPlan(
            project_root=str(project_root),
            scope=str(scope),
            total_files=0,
            skipped_trivial=skipped_trivial,
        )

    in_scope_modules = set(in_scope_files.keys())
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        src, tgt = edge.source_module, edge.target_module
        if src in in_scope_modules and tgt in in_scope_modules and src != tgt:
            adjacency[src].add(tgt)
            adjacency[tgt].add(src)

    components = _connected_components(in_scope_modules, adjacency)

    chunks_modules: list[list[str]] = []
    stash: list[list[str]] = []
    for comp in components:
        if len(comp) > max_size:
            chunks_modules.extend(
                _split_oversized(comp, adjacency, max_size, target_size)
            )
        elif len(comp) < min_size:
            stash.append(comp)
        else:
            chunks_modules.append(comp)

    chunks_modules.extend(_pack_stash(stash, max_size))
    chunks_modules.sort(key=lambda c: (-len(c), c[0] if c else ""))

    out_chunks: list[AuditChunk] = []
    for i, mods in enumerate(chunks_modules, start=1):
        files = [_rel(in_scope_files[m], project_root) for m in mods]
        intra = _count_intra_edges(mods, graph)
        boundary = _count_boundary_edges(mods, graph, in_scope_modules)
        rationale = _build_rationale(mods, intra, boundary)
        out_chunks.append(
            AuditChunk(
                session_index=i,
                files=files,
                modules=mods,
                rationale=rationale,
                intra_edges=intra,
                boundary_edges=boundary,
            )
        )

    return ChunkPlan(
        project_root=str(project_root),
        scope=str(scope),
        total_files=len(in_scope_files),
        chunks=out_chunks,
        skipped_trivial=skipped_trivial,
    )


def _is_trivial_file(path: Path) -> bool:
    """Skip files with no reviewable content (empty / re-export shims).

    A file is trivial iff every top-level statement is an import or a
    module docstring. Function/class definitions and any other executable
    statement make it reviewable.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable files are not "trivial" — keep them in the audit so
        # permission/encoding failures are visible rather than silently dropped.
        return False
    if not text.strip():
        return True
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        return False
    return True


def _connected_components(
    nodes: set[str],
    adjacency: dict[str, set[str]],
) -> list[list[str]]:
    visited: set[str] = set()
    components: list[list[str]] = []
    for start in sorted(nodes):
        if start in visited:
            continue
        comp: list[str] = []
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            comp.append(cur)
            for neighbor in adjacency.get(cur, ()):
                if neighbor not in visited:
                    stack.append(neighbor)
        components.append(sorted(comp))
    return components


def _split_oversized(
    component: list[str],
    adjacency: dict[str, set[str]],
    max_size: int,
    target_size: int,
) -> list[list[str]]:
    """Peel dense sub-clusters of ``target_size`` from a too-large component."""
    remaining = set(component)
    out: list[list[str]] = []
    while remaining:
        if len(remaining) <= max_size:
            out.append(sorted(remaining))
            break
        seed = max(
            remaining,
            key=lambda m: (len(adjacency.get(m, set()) & remaining), m),
        )
        cluster = {seed}
        while len(cluster) < target_size:
            candidates: set[str] = set()
            for c in cluster:
                candidates |= adjacency.get(c, set()) & remaining
            candidates -= cluster
            if not candidates:
                break
            pick = max(
                candidates,
                key=lambda m: (len(adjacency.get(m, set()) & cluster), m),
            )
            cluster.add(pick)
        out.append(sorted(cluster))
        remaining -= cluster
    return out


def _pack_stash(stash: list[list[str]], max_size: int) -> list[list[str]]:
    """Bin-pack small disconnected pieces into chunks by package affinity."""
    if not stash:
        return []
    items = [(_bin_key(comp), comp) for comp in stash]
    items.sort(key=lambda x: (x[0], x[1]))

    out: list[list[str]] = []
    current: list[str] = []
    current_prefix: str | None = None
    for prefix, comp in items:
        if current and (
            len(current) + len(comp) > max_size or prefix != current_prefix
        ):
            out.append(sorted(current))
            current = []
            current_prefix = None
        current.extend(comp)
        if current_prefix is None:
            current_prefix = prefix
    if current:
        out.append(sorted(current))
    return out


def _bin_key(modules: list[str]) -> str:
    """Binning key for stash packing.

    For a singleton ``pkg.a``, returns the parent package ``pkg`` so it can bin
    with siblings ``pkg.b`` / ``pkg.c``. Top-level modules without dots return
    themselves (so a top-level package bins with its own children).
    """
    if not modules:
        return ""
    if len(modules) == 1:
        m = modules[0]
        return m.rsplit(".", 1)[0] if "." in m else m
    return _common_package_prefix(modules)


def _common_package_prefix(modules: list[str]) -> str:
    if not modules:
        return ""
    parts = [m.split(".") for m in modules]
    common: list[str] = []
    for grouped in zip(*parts, strict=False):
        if len(set(grouped)) == 1:
            common.append(grouped[0])
        else:
            break
    return ".".join(common)


def _count_intra_edges(modules: list[str], graph: ImportGraph) -> int:
    mset = set(modules)
    return sum(
        1
        for e in graph.edges
        if e.source_module in mset and e.target_module in mset
    )


def _count_boundary_edges(
    modules: list[str],
    graph: ImportGraph,
    in_scope: set[str],
) -> int:
    mset = set(modules)
    return sum(
        1
        for e in graph.edges
        if (e.source_module in mset) != (e.target_module in mset)
        and (e.source_module in in_scope or e.target_module in in_scope)
    )


def _build_rationale(modules: list[str], intra: int, boundary: int) -> str:
    prefix = _common_package_prefix(modules)
    if prefix:
        return (
            f"{len(modules)} files under '{prefix}' "
            f"({intra} internal imports, {boundary} boundary imports)"
        )
    return (
        f"{len(modules)} disconnected files "
        f"({intra} internal imports, {boundary} boundary imports)"
    )


_SKIP_PARTS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".eggs",
        "htmlcov",
        ".mypy_cache",
        "worktrees",
        ".tapps-mcp-cache",
        ".tapps-agents",
    }
)


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_PARTS for part in path.parts)


def _file_to_module(file_path: Path, project_root: Path) -> str:
    """Delegate to :func:`tapps_mcp.project.import_graph._file_to_module`."""
    from tapps_mcp.project.import_graph import _file_to_module as _ig_file_to_module

    return _ig_file_to_module(file_path, project_root, "")


def _rel(file_path: Path, project_root: Path) -> str:
    try:
        return str(file_path.relative_to(project_root))
    except ValueError:
        return str(file_path)
