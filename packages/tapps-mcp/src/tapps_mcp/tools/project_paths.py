"""Shared project-root and path resolution for cross-repo MCP tool calls.

When an MCP server runs with ``project_root`` pointing at the host workspace
(e.g. tapps-brain) but a tool receives an explicit ``project_root`` override
for a sibling repo, relative paths like ``scope`` or ``file_paths`` must be
resolved under the override — not via ``Path(...).resolve()`` against CWD.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


class ProjectRootResult(NamedTuple):
    """Result of resolving an optional project_root override."""

    root: Path
    error_code: str | None = None
    error_message: str | None = None


def resolve_effective_project_root(
    default_root: Path,
    override: str = "",
) -> ProjectRootResult:
    """Return *override* when set and valid, otherwise *default_root*."""
    if not override.strip():
        return ProjectRootResult(default_root.resolve())
    custom = Path(override).expanduser().resolve()
    if not custom.is_dir():
        return ProjectRootResult(
            default_root,
            "invalid_project_root",
            f"project_root is not an existing directory: {custom}",
        )
    return ProjectRootResult(custom)


def resolve_path_under_root(path_str: str, root: Path) -> Path:
    """Resolve *path_str* under *root* when relative.

    Absolute paths must still lie under *root* after resolution.
    Empty *path_str* returns *root*.
    """
    root = root.resolve()
    raw = path_str.strip()
    if not raw:
        return root
    candidate = Path(raw)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = f"Path escapes project root: {resolved}"
        raise ValueError(msg) from exc
    return resolved


def validate_read_path_under_root(path_str: str, root: Path) -> Path:
    """Validate a repo-relative read path against *root* (PathValidator)."""
    from tapps_core.security.path_validator import PathValidator

    validator = PathValidator(root.resolve())
    return validator.validate_read_path(path_str.strip())


def infer_monorepo_graph_root(project_root: Path, scope: Path) -> Path | None:
    """Infer import-graph root for monorepo nested scopes (TAP-2035 / EPIC-112).

    When *scope* sits under ``packages/<name>/...``, prefer ``packages/<name>/src``
    when present. Otherwise walk upward from *scope* toward *project_root* for a
    ``pyproject.toml`` + ``src/`` layout.
    """
    project_root = project_root.resolve()
    scope = scope.resolve()
    try:
        rel = scope.relative_to(project_root)
    except ValueError:
        return None

    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "packages":
        pkg_dir = project_root / parts[0] / parts[1]
        src_dir = pkg_dir / "src"
        if src_dir.is_dir():
            return src_dir
        if (pkg_dir / "pyproject.toml").is_file():
            return pkg_dir

    current = scope
    while True:
        if (current / "pyproject.toml").is_file():
            src_dir = current / "src"
            if src_dir.is_dir():
                return src_dir.resolve()
            return current.resolve()
        if current == project_root:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
