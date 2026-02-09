"""Impact analysis - AST-based blast-radius detection for file changes.

Given a changed file, builds an import graph and identifies:
- Direct dependents (files that import the changed file)
- Transitive dependents (files that import direct dependents)
- Test files that should be re-run
"""

from __future__ import annotations

import ast
from pathlib import Path

import structlog

from tapps_mcp.project.models import FileImpact, ImpactReport

logger = structlog.get_logger(__name__)

_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", "dist", "build",
    ".tox", ".eggs", "htmlcov", ".mypy_cache",
    ".tapps-agents", ".tapps-mcp-cache", "site-packages",
})

# Severity thresholds
_SEVERITY_CRITICAL = 10
_SEVERITY_HIGH = 5


# ---------------------------------------------------------------------------
# Import graph builder
# ---------------------------------------------------------------------------


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.parts)


def _extract_imports(file_path: Path) -> list[str]:
    """Return top-level module names imported by *file_path*."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _module_for_file(file_path: Path, project_root: Path) -> str | None:
    """Convert a file path to a dotted module name relative to *project_root*."""
    try:
        rel = file_path.relative_to(project_root)
    except ValueError:
        return None
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def _build_import_graph(
    project_root: Path,
    *,
    max_files: int = 2000,
) -> dict[str, set[str]]:
    """Build ``module -> set[files that import it]``."""
    graph: dict[str, set[str]] = {}
    for i, py in enumerate(project_root.rglob("*.py")):
        if _should_skip(py) or i >= max_files:
            break
        imports = _extract_imports(py)
        for mod in imports:
            graph.setdefault(mod, set()).add(str(py))
    return graph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_impact(
    file_path: Path,
    project_root: Path,
    change_type: str = "modified",
    *,
    max_depth: int = 3,
) -> ImpactReport:
    """Analyse the blast radius of changing *file_path*.

    Args:
        file_path: The file being changed.
        project_root: Root of the project tree.
        change_type: ``"added"``, ``"modified"``, or ``"removed"``.
        max_depth: Maximum transitive depth to follow.

    Returns:
        An :class:`ImpactReport` with affected files.
    """
    logger.info(
        "impact_analysis_start",
        file=str(file_path),
        change_type=change_type,
    )

    graph = _build_import_graph(project_root)
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
    for mod, importers in graph.items():
        if mod == changed_module or mod.startswith(changed_module + "."):
            direct_files.update(importers)
    direct_files.discard(str(file_path))

    for fp in sorted(direct_files):
        reason = f"imports {changed_module}"
        if _is_test_file(Path(fp)):
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
            fp_module = _module_for_file(Path(fp), project_root)
            if fp_module is None:
                continue
            for mod, importers in graph.items():
                if mod == fp_module or mod.startswith(fp_module + "."):
                    for imp in importers:
                        if imp not in visited and imp != str(file_path):
                            next_frontier.add(imp)
        visited.update(next_frontier)
        for fp in sorted(next_frontier):
            if _is_test_file(Path(fp)):
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

    total = len(direct) + len(transitive) + len(tests)
    severity = _assess_severity(total, change_type)
    recs = _recommendations(total, change_type, tests)

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


def _is_test_file(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in path.parts
        or "test" in path.parts
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
