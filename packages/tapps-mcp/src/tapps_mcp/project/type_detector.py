"""Project-type detection - detects archetype (api-service, web-app, etc.).

Adapted from TappsCodingAgents ``core/project_type_detector.py``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------


def _exists_any(root: Path, paths: list[str]) -> bool:
    return any((root / p).exists() for p in paths)


def _has_api_indicators(root: Path) -> bool:
    return _exists_any(
        root,
        [
            "api",
            "routes",
            "endpoints",
            "controllers",
            "app.py",
            "main.py",
            "openapi.yaml",
            "openapi.yml",
            "swagger.yaml",
        ],
    )


def _has_openapi_spec(root: Path) -> bool:
    return _exists_any(
        root,
        [
            "openapi.yaml",
            "openapi.yml",
            "swagger.yaml",
            "swagger.yml",
            "api.yaml",
        ],
    )


def _has_graphql_schema(root: Path) -> bool:
    return _exists_any(root, ["schema.graphql", "schema.gql", "graphql"])


def _has_frontend(root: Path) -> bool:
    return _exists_any(
        root,
        [
            "src",
            "public",
            "static",
            "components",
            "pages",
            "app",
            "index.html",
            "package.json",
        ],
    )


def _has_backend(root: Path) -> bool:
    return _exists_any(
        root,
        [
            "server",
            "backend",
            "api",
            "app.py",
            "main.py",
            "requirements.txt",
            "pyproject.toml",
        ],
    )


def _has_ui_components(root: Path) -> bool:
    return _exists_any(root, ["components", "src/components", "app/components", "ui"])


def _has_fullstack(root: Path) -> bool:
    return _has_frontend(root) and _has_backend(root)


def _has_cli_entrypoint(root: Path) -> bool:
    return _exists_any(root, ["cli.py", "main.py", "command.py", "__main__.py"])


def _has_setup_py_cli(root: Path) -> bool:
    setup_py = root / "setup.py"
    if setup_py.exists():
        try:
            content = setup_py.read_text(encoding="utf-8")
            if "console_scripts" in content or "entry_points" in content:
                return True
        except OSError:
            pass

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            if data.get("project", {}).get("scripts"):
                return True
            if data.get("tool", {}).get("poetry", {}).get("scripts"):
                return True
        except (OSError, tomllib.TOMLDecodeError):
            pass

    return False


def _has_click_or_typer(root: Path) -> bool:
    for req in (root / "requirements.txt", root / "pyproject.toml", root / "setup.py"):
        if req.exists():
            try:
                text = req.read_text(encoding="utf-8", errors="ignore").lower()
                if "click" in text or "typer" in text:
                    return True
            except OSError:
                pass
    return False


def _has_package_structure(root: Path) -> bool:
    for item in root.iterdir():
        if item.is_dir() and not item.name.startswith(".") and (item / "__init__.py").exists():
            return True
    return False


def _has_package_manifest(root: Path) -> bool:
    return _exists_any(root, ["setup.py", "pyproject.toml", "setup.cfg"])


def _has_minimal_entrypoints(root: Path) -> bool:
    count = sum(1 for f in ("main.py", "app.py", "cli.py", "__main__.py") if (root / f).exists())
    return count <= 1


def _is_library_focused(root: Path) -> bool:
    return (
        _has_package_structure(root)
        and _has_package_manifest(root)
        and (
            _has_minimal_entrypoints(root)
            or (not _has_frontend(root) and not _has_api_indicators(root))
        )
    )


def _has_service_boundaries(root: Path) -> bool:
    return _exists_any(root, ["services", "src/services", "microservices"])


def _has_container_orchestration(root: Path) -> bool:
    return _exists_any(
        root,
        [
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "kubernetes",
            "k8s",
            "deployment.yaml",
        ],
    )


def _has_service_mesh(root: Path) -> bool:
    return _exists_any(root, ["istio", "linkerd", "consul"])


def _has_heavy_docs(root: Path) -> bool:
    """Return True if the project has a significant number of documentation files."""
    import os

    md_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv")
        ]
        for f in filenames:
            if f.lower().endswith((".md", ".rst")):
                md_count += 1
                if md_count >= 10:
                    return True
    return md_count >= 10


def _has_docs_dir(root: Path) -> bool:
    """Return True if a docs/ directory with content exists."""
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        return False
    return any(docs_dir.glob("**/*.md")) or any(docs_dir.glob("**/*.rst"))


def _has_few_source_files(root: Path) -> bool:
    """Return True if project has very few source code files (< 5)."""
    import os

    code_count = 0
    code_exts = {".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".cs"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv")
        ]
        for f in filenames:
            if any(f.endswith(ext) for ext in code_exts):
                code_count += 1
                if code_count >= 5:
                    return False
    return True


# ---------------------------------------------------------------------------
# Archetype definitions
# ---------------------------------------------------------------------------

_INDICATOR = tuple[str, Any]  # (name, callable)
_MIN_CONFIDENCE_THRESHOLD = 0.3

_PROJECT_TYPES: dict[str, dict[str, Any]] = {
    "api-service": {
        "indicators": [
            ("has_api_routes", _has_api_indicators),
            ("has_openapi", _has_openapi_spec),
            ("has_graphql", _has_graphql_schema),
            ("api_focused_structure", lambda r: _has_api_indicators(r) and not _has_frontend(r)),
        ],
        "weights": [0.3, 0.3, 0.2, 0.2],
    },
    "web-app": {
        "indicators": [
            ("has_frontend", _has_frontend),
            ("has_backend", _has_backend),
            ("has_ui_components", _has_ui_components),
            ("fullstack_structure", _has_fullstack),
        ],
        "weights": [0.3, 0.3, 0.2, 0.2],
    },
    "cli-tool": {
        "indicators": [
            ("has_cli_entrypoint", _has_cli_entrypoint),
            ("has_setup_py_cli", _has_setup_py_cli),
            ("has_click_typer", _has_click_or_typer),
            (
                "cli_focused_structure",
                lambda r: (
                    (_has_cli_entrypoint(r) or _has_setup_py_cli(r))
                    and not _has_frontend(r)
                    and not _has_api_indicators(r)
                ),
            ),
        ],
        "weights": [0.4, 0.2, 0.2, 0.2],
    },
    "library": {
        "indicators": [
            ("has_package_structure", _has_package_structure),
            ("has_package_manifest", _has_package_manifest),
            ("minimal_entrypoints", _has_minimal_entrypoints),
            ("library_focused", _is_library_focused),
        ],
        "weights": [0.3, 0.3, 0.2, 0.2],
    },
    "microservice": {
        "indicators": [
            ("has_service_boundaries", _has_service_boundaries),
            ("has_docker_k8s", _has_container_orchestration),
            ("has_service_mesh", _has_service_mesh),
            (
                "microservice_structure",
                lambda r: _has_service_boundaries(r) and _has_container_orchestration(r),
            ),
        ],
        "weights": [0.3, 0.3, 0.2, 0.2],
    },
    "documentation": {
        "indicators": [
            ("has_heavy_docs", _has_heavy_docs),
            ("has_docs_dir", _has_docs_dir),
            ("has_few_source_files", _has_few_source_files),
            (
                "docs_focused",
                lambda r: _has_heavy_docs(r) and _has_few_source_files(r),
            ),
        ],
        "weights": [0.3, 0.3, 0.2, 0.2],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_project_type(
    project_root: Path,
) -> tuple[str | None, float, str]:
    """Detect project archetype from file-system signals.

    Returns:
        ``(project_type, confidence, reason)`` or ``(None, 0.0, reason)``.
    """
    if not project_root.exists():
        return (None, 0.0, "Project root does not exist")

    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for ptype, cfg in _PROJECT_TYPES.items():
        score = 0.0
        matched: list[str] = []
        weights: list[float] = cfg["weights"]
        for i, (name, check) in enumerate(cfg["indicators"]):
            try:
                if check(project_root):
                    score += weights[i] if i < len(weights) else 0.25
                    matched.append(name)
            except (OSError, ValueError, TypeError) as e:
                logger.debug("indicator_error", indicator=name, project_type=ptype, error=str(e))
        scores[ptype] = score
        reasons[ptype] = matched

    if not scores or max(scores.values()) < _MIN_CONFIDENCE_THRESHOLD:
        return (None, 0.0, "No clear project type detected (confidence too low)")

    best = max(scores, key=lambda k: scores[k])
    conf = min(1.0, scores[best])
    reason = f"Detected {best} based on: {', '.join(reasons[best])}"
    return (best, conf, reason)
