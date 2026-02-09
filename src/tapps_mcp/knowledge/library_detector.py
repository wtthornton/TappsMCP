"""Library detector — extract project dependencies from manifest files.

Scans ``pyproject.toml``, ``requirements.txt``, and ``package.json`` to
build a prioritised list of libraries for cache warming.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

# Strip version specifiers to get bare package names
_VERSION_RE = re.compile(r"[<>=!~\[].*$")
# Strip inline comments and extras
_COMMENT_RE = re.compile(r"\s*#.*$")


def detect_libraries(project_root: Path) -> list[str]:
    """Detect libraries used in the project.

    Scans common dependency files and returns a deduplicated, sorted list
    of library names.

    Args:
        project_root: Path to the project root directory.

    Returns:
        List of library names (lowercase, sorted).
    """
    libs: set[str] = set()

    # pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        libs.update(_parse_pyproject(pyproject))

    # requirements.txt (and variants)
    for name in ("requirements.txt", "requirements-dev.txt", "requirements_dev.txt"):
        req_file = project_root / name
        if req_file.exists():
            libs.update(_parse_requirements(req_file))

    # package.json
    pkg_json = project_root / "package.json"
    if pkg_json.exists():
        libs.update(_parse_package_json(pkg_json))

    result = sorted(libs)
    logger.debug("libraries_detected", count=len(result), libraries=result[:20])
    return result


def _parse_pyproject(path: Path) -> list[str]:
    """Extract dependency names from pyproject.toml."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []

    # Simple TOML parsing — extract dependencies array
    # Look for [project] dependencies = [...]
    libs: list[str] = []
    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()

        # Start of dependencies array
        if re.match(r"^dependencies\s*=\s*\[", stripped):
            in_deps = True
            # Check for inline deps on same line
            bracket_content = stripped.split("[", 1)[1]
            libs.extend(_extract_names_from_bracket(bracket_content))
            if "]" in bracket_content:
                in_deps = False
            continue

        if in_deps:
            libs.extend(_extract_names_from_bracket(stripped))
            if "]" in stripped:
                in_deps = False

    return libs


def _extract_names_from_bracket(line: str) -> list[str]:
    """Extract package names from a TOML array line."""
    names: list[str] = []
    # Find quoted strings
    for match in re.finditer(r'"([^"]+)"', line):
        raw = match.group(1).strip()
        name = _clean_package_name(raw)
        if name:
            names.append(name)
    return names


def _parse_requirements(path: Path) -> list[str]:
    """Extract dependency names from requirements.txt."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []

    libs: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        # Skip comments and empty lines
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        name = _clean_package_name(stripped)
        if name:
            libs.append(name)
    return libs


def _parse_package_json(path: Path) -> list[str]:
    """Extract dependency names from package.json."""
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, dict):
        return []

    libs: list[str] = []
    for key in ("dependencies", "devDependencies"):
        deps = data.get(key, {})
        if isinstance(deps, dict):
            libs.extend(deps.keys())
    return [name.lower() for name in libs]


def _clean_package_name(raw: str) -> str:
    """Extract a clean package name from a dependency string."""
    # Remove comments
    cleaned = _COMMENT_RE.sub("", raw).strip()
    # Remove extras like [cli]
    cleaned = re.sub(r"\[.*?\]", "", cleaned)
    # Remove version specifiers
    cleaned = _VERSION_RE.sub("", cleaned).strip()
    # Normalize
    cleaned = cleaned.lower().replace("_", "-")
    # Skip invalid names
    if not cleaned or not re.match(r"^[a-z0-9]", cleaned):
        return ""
    return cleaned
