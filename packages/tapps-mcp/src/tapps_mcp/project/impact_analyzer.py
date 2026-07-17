"""Impact analysis - AST-based blast-radius detection for file changes.

Given a changed file, builds an import graph and identifies:
- Direct dependents (files that import the changed file)
- Transitive dependents (files that import direct dependents)
- Test files that should be re-run

Symbol-level caller/callee analysis lives in ``call_graph.py`` (ADR-0017).
"""

from __future__ import annotations

import ast
from pathlib import Path

import structlog

from tapps_core.common.utils import SKIP_DIRS
from tapps_mcp.project.models import FileImpact, ImpactReport

logger = structlog.get_logger(__name__)

# Severity thresholds
_SEVERITY_CRITICAL = 10
_SEVERITY_HIGH = 5


def _norm_path(path: Path, project_root: Path) -> str:
    """Normalize *path* for stable graph storage and comparison."""
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _path_from_graph(fp: str, project_root: Path) -> Path:
    """Reconstitute a filesystem path from a graph-stored key."""
    p = Path(fp)
    if p.is_absolute():
        return p
    return project_root / p


# ---------------------------------------------------------------------------
# Import graph builder
# ---------------------------------------------------------------------------


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _extract_imports(file_path: Path, source_module: str | None = None) -> list[str]:
    """Return module names imported by *file_path* (absolute + resolved relative)."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    from tapps_mcp.project.import_graph import resolve_relative_import

    is_package = file_path.name == "__init__.py"
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            if level > 0 and source_module:
                base = resolve_relative_import(
                    source_module,
                    node.module,
                    level,
                    is_package=is_package,
                )
                if node.module:
                    if base:
                        modules.append(base)
                else:
                    # from . import util  →  pkg.util (not just pkg)
                    for alias in node.names:
                        if alias.name == "*":
                            if base:
                                modules.append(base)
                            continue
                        modules.append(f"{base}.{alias.name}" if base else alias.name)
            elif node.module:
                modules.append(node.module)
    return modules


def _module_for_file(file_path: Path, project_root: Path) -> str | None:
    """Convert a file path to a dotted module name relative to *project_root*.

    Delegates to :func:`import_graph._file_to_module` so monorepo
    (``packages/*/src``) and ``src/`` layouts match real import paths.
    """
    from tapps_mcp.project.import_graph import _file_to_module

    mod = _file_to_module(file_path, project_root, "")
    return mod or None


def _build_import_graph(
    project_root: Path,
    *,
    max_files: int = 2000,
) -> tuple[dict[str, set[str]], bool]:
    """Build ``module -> set[files that import it]``.

    Returns ``(graph, truncated)`` where ``truncated`` is True when the walk
    stopped early because ``max_files`` was hit.
    """
    graph: dict[str, set[str]] = {}
    count = 0
    truncated = False
    for py in project_root.rglob("*.py"):
        if _should_skip(py):
            continue
        if count >= max_files:
            truncated = True
            break
        count += 1
        source_mod = _module_for_file(py, project_root)
        imports = _extract_imports(py, source_mod)
        for mod in imports:
            graph.setdefault(mod, set()).add(_norm_path(py, project_root))
    return graph, truncated


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_import_graph(
    project_root: Path,
    *,
    max_files: int = 2000,
) -> dict[str, set[str]]:
    """Build and return the project import graph.

    Public wrapper around :func:`_build_import_graph` so callers (e.g.
    ``tapps_validate_changed``) can build the graph once and pass it to
    multiple :func:`analyze_impact` calls.
    """
    graph, _truncated = _build_import_graph(project_root, max_files=max_files)
    return graph


def analyze_impact(
    file_path: Path,
    project_root: Path,
    change_type: str = "modified",
    *,
    max_depth: int = 3,
    graph: dict[str, set[str]] | None = None,
) -> ImpactReport:
    """Analyse the blast radius of changing *file_path*.

    Args:
        file_path: The file being changed.
        project_root: Root of the project tree.
        change_type: ``"added"``, ``"modified"``, or ``"removed"``.
        max_depth: Maximum transitive depth to follow.
        graph: Pre-built import graph (from :func:`build_import_graph`).
            When ``None`` the graph is built on each call — pass a shared
            graph when analysing multiple files to avoid redundant work.

    Returns:
        An :class:`ImpactReport` with affected files.
    """
    logger.info(
        "impact_analysis_start",
        file=str(file_path),
        change_type=change_type,
    )

    graph_truncated = False
    if graph is None:
        graph, graph_truncated = _build_import_graph(project_root)
    changed_module = _module_for_file(file_path, project_root)

    direct: list[FileImpact] = []
    transitive: list[FileImpact] = []
    tests: list[FileImpact] = []

    if changed_module is None:
        return ImpactReport(
            changed_file=str(file_path),
            change_type=change_type,
            severity="low",
            recommendations=[
                "File is outside the project root; no impact detected.",
            ],
        )

    # Direct dependents
    direct_files: set[str] = set()
    changed_norm = _norm_path(file_path, project_root)
    for mod, importers in graph.items():
        if mod == changed_module or mod.startswith(changed_module + "."):
            direct_files.update(importers)
    direct_files.discard(changed_norm)

    for fp in sorted(direct_files):
        reason = f"imports {changed_module}"
        if _is_test_file(_path_from_graph(fp, project_root)):
            tests.append(
                FileImpact(
                    file_path=fp,
                    impact_type="test",
                    reason=f"test file {reason}",
                ),
            )
        else:
            direct.append(
                FileImpact(file_path=fp, impact_type="direct", reason=reason),
            )

    # Transitive dependents (BFS)
    visited = set(direct_files)
    frontier = set(direct_files)
    for _depth in range(1, max_depth):
        next_frontier: set[str] = set()
        for fp in frontier:
            fp_module = _module_for_file(_path_from_graph(fp, project_root), project_root)
            if fp_module is None:
                continue
            for mod, importers in graph.items():
                if mod == fp_module or mod.startswith(fp_module + "."):
                    for imp in importers:
                        if imp not in visited and imp != changed_norm:
                            next_frontier.add(imp)
        visited.update(next_frontier)
        for fp in sorted(next_frontier):
            if _is_test_file(_path_from_graph(fp, project_root)):
                tests.append(
                    FileImpact(
                        file_path=fp,
                        impact_type="test",
                        reason="transitive test dependency",
                    ),
                )
            else:
                transitive.append(
                    FileImpact(
                        file_path=fp,
                        impact_type="transitive",
                        reason="transitive import",
                    ),
                )
        frontier = next_frontier
        if not frontier:
            break

    # Heuristic: discover test files by naming convention
    visited = {changed_norm} | direct_files
    for dep in transitive:
        visited.add(dep.file_path)
    for tf in tests:
        visited.add(tf.file_path)
    heuristic_tests = _find_test_files_by_name(file_path, project_root)
    for test_fp in heuristic_tests:
        if test_fp not in visited:
            tests.append(
                FileImpact(
                    file_path=test_fp,
                    impact_type="test",
                    reason=f"test file matches module name ({file_path.stem})",
                ),
            )
            visited.add(test_fp)

    total = len(direct) + len(transitive) + len(tests)
    severity = _assess_severity(total, change_type)
    recs = _recommendations(total, change_type, tests)
    if graph_truncated:
        recs.append(
            "Import graph was truncated at max_files — blast radius may be incomplete."
        )

    report = ImpactReport(
        changed_file=str(file_path),
        change_type=change_type,
        direct_dependents=direct,
        transitive_dependents=transitive,
        test_files=tests,
        total_affected=total,
        severity=severity,
        recommendations=recs,
    )

    logger.info(
        "impact_analysis_complete",
        total_affected=total,
        severity=severity,
    )
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_test_files_by_name(
    file_path: Path,
    project_root: Path,
) -> list[str]:
    """Find test files matching the module name by naming convention.

    Looks for ``test_<stem>.py`` and ``<stem>_test.py`` patterns anywhere
    under *project_root*.
    """
    stem = file_path.stem
    candidates = {f"test_{stem}", f"{stem}_test"}
    found: list[str] = []
    for py in project_root.rglob("*.py"):
        if _should_skip(py):
            continue
        if py.stem in candidates:
            found.append(_norm_path(py, project_root))
    return sorted(found)


def _is_test_file(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in path.parts
    )


def _assess_severity(total: int, change_type: str) -> str:
    if change_type == "removed":
        return "critical" if total > 0 else "medium"
    if total > _SEVERITY_CRITICAL:
        return "critical"
    if total > _SEVERITY_HIGH:
        return "high"
    if total > 0:
        return "medium"
    return "low"


def _recommendations(
    total: int,
    change_type: str,
    tests: list[FileImpact],
) -> list[str]:
    recs: list[str] = []
    if total == 0:
        recs.append("No downstream dependents detected; change is isolated.")
        return recs
    if change_type == "removed":
        recs.append(
            "File removal may break imports in dependent files - review each.",
        )
    if tests:
        recs.append(
            f"Re-run {len(tests)} test file(s) to verify no regressions.",
        )
    if total > _SEVERITY_HIGH:
        recs.append("Consider incremental rollout due to wide blast radius.")
    return recs


def analyze_symbol_impact(
    symbol: str,
    project_root: Path,
    *,
    max_depth: int = 3,
    token_budget: int = 4000,
) -> dict[str, object]:
    """Symbol-level blast radius via function call graph (TAP-4051)."""
    from tapps_mcp.project.call_graph import build_call_graph_index
    from tapps_mcp.project.call_graph_queries import query_call_graph

    index = build_call_graph_index(project_root)
    query = query_call_graph(
        index,
        symbol,
        mode="all",
        max_depth=max_depth,
        token_budget=token_budget,
    )
    if not query.get("found"):
        return {
            **query,
            "severity": "low",
            "recommendations": [f"Symbol {symbol!r} not found in call graph index."],
        }

    caller_count = len(query.get("callers", []))
    callee_count = len(query.get("callees", []))
    total = caller_count + callee_count
    severity = _assess_severity(total, "modified")
    recs: list[str] = []
    if caller_count:
        recs.append(f"{caller_count} direct/indirect caller edge(s) — review before changing signature.")
    if callee_count:
        recs.append(f"{callee_count} callee edge(s) — changing behavior may affect downstream calls.")
    if query.get("resolution_gaps"):
        recs.append("Unresolved static calls exist; see resolution_gaps (degraded mode).")
    if query.get("truncated"):
        recs.append("Graph output truncated at token budget; narrow symbol or reduce max_depth.")

    return {
        **query,
        "severity": severity,
        "total_affected": total,
        "recommendations": recs,
    }
