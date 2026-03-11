"""Resolve persona name to allowlisted agent/rule file path (Epic 78).

Lookup order: project .claude/agents, .cursor/agents, .cursor/rules;
then optional user ~/.claude/agents. All paths validated; no reads outside allowlist.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog

from tapps_core.common.exceptions import PathValidationError
from tapps_core.security.path_validator import PathValidator

__all__ = ["persona_name_to_slug", "read_persona_content", "resolve_canonical_persona_path"]

logger = structlog.get_logger(__name__)

# Allowlisted relative dirs under project root (story 78.1)
_PROJECT_AGENT_DIRS = (".claude/agents", ".cursor/agents", ".cursor/rules")
_EXTENSIONS = (".md", ".mdc")
_USER_AGENTS_DIR = ".claude/agents"


def persona_name_to_slug(persona_name: str) -> str:
    """Normalize persona name to a filename slug.

    Lowercase, replace spaces/special chars with single hyphen,
    strip leading/trailing hyphens. E.g. "Frontend Developer" -> "frontend-developer".
    """
    if not persona_name or not isinstance(persona_name, str):
        return ""
    s = persona_name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "-", s)
    return s.strip("-")


def _candidate_paths(project_root: Path, slug: str, include_user_home: bool = True) -> list[Path]:
    """Return list of candidate file paths in lookup order (story 78.1)."""
    candidates: list[Path] = []
    proj = project_root.resolve()
    for rel_dir in _PROJECT_AGENT_DIRS:
        for ext in _EXTENSIONS:
            candidates.append(proj / rel_dir / f"{slug}{ext}")
    if include_user_home:
        try:
            home = Path.home()
            agents_dir = home / _USER_AGENTS_DIR
            for ext in _EXTENSIONS:
                candidates.append(agents_dir / f"{slug}{ext}")
        except RuntimeError:
            pass
    return candidates


def _is_under_home_agents(resolved: Path) -> bool:
    """Return True if path is strictly under Path.home()/.claude/agents (no traversal)."""
    try:
        home = Path.home()
        allowed = (home / _USER_AGENTS_DIR).resolve()
        resolved = resolved.resolve()
        resolved.relative_to(allowed)
        return True
    except (ValueError, RuntimeError):
        return False


def resolve_canonical_persona_path(
    persona_name: str,
    project_root: Path,
    *,
    include_user_home: bool = True,
    path_validator: PathValidator | None = None,
) -> tuple[Path, str]:
    """Resolve persona name to first existing allowlisted file path.

    Args:
        persona_name: User-facing name (e.g. "Frontend Developer", "tapps-reviewer").
        project_root: Project root for project-scoped lookups.
        include_user_home: If True, also look in ~/.claude/agents.
        path_validator: Validator for project paths; uses PathValidator(project_root) if None.

    Returns:
        (resolved_path, slug) of the first existing file in lookup order.

    Raises:
        FileNotFoundError: No matching file in allowlisted dirs.
        PathValidationError: If a candidate path fails validation (e.g. traversal).
    """
    slug = persona_name_to_slug(persona_name)
    if not slug:
        raise FileNotFoundError("Persona name is empty or invalid.")

    validator = path_validator or PathValidator(project_root)
    candidates = _candidate_paths(project_root, slug, include_user_home=include_user_home)

    for path in candidates:
        if not path.exists():
            continue
        resolved = path.resolve()

        # Project paths: use PathValidator
        try:
            proj = project_root.resolve()
            try:
                resolved.relative_to(proj)
                validator.validate_path(resolved, must_exist=True)
                return resolved, slug
            except ValueError:
                pass
        except (PathValidationError, FileNotFoundError):
            continue

        # User home path: must be under ~/.claude/agents
        if _is_under_home_agents(resolved):
            return resolved, slug

    raise FileNotFoundError(
        f"Persona '{persona_name}' (slug: {slug}) not found in "
        ".claude/agents, .cursor/agents, or .cursor/rules."
    )


def read_persona_content(path: Path, max_size: int = 512 * 1024) -> str:
    """Read file content as UTF-8 text. Enforces max size (default 512 KiB)."""
    size = path.stat().st_size
    if size > max_size:
        raise PathValidationError(f"Persona file too large: {size} bytes (max {max_size})")
    return path.read_text(encoding="utf-8", errors="replace")
