"""DocsMCP MCP server entry point.

Creates the FastMCP server instance, registers tools, and provides
``run_server()`` for the CLI.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, ClassVar

import structlog
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from docs_mcp import __version__
from docs_mcp.server_helpers import error_response, success_response

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Tool annotation presets
# ---------------------------------------------------------------------------

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("DocsMCP")

# ---------------------------------------------------------------------------
# Tool call tracking
# ---------------------------------------------------------------------------

_tool_calls: dict[str, int] = {}


def _record_call(tool_name: str) -> None:
    """Record a tool call for session tracking."""
    _tool_calls[tool_name] = _tool_calls.get(tool_name, 0) + 1


def _reset_tool_calls() -> None:
    """Reset tool call tracking (for testing)."""
    _tool_calls.clear()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Documentation file categories and their typical filenames/patterns.
_CRITICAL_DOCS: ClassVar[list[str]] = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
]

_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})

_RECOMMENDED_DOCS: ClassVar[list[str]] = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "docs/",
]

# Directories to skip when scanning for documentation files.
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".eggs",
    "*.egg-info",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped during scanning."""
    if dirname in _SKIP_DIRS:
        return True
    if dirname.endswith(".egg-info"):
        return True
    return False


def _categorize_doc(path: Path, project_root: Path) -> str:
    """Categorize a documentation file based on its name and location."""
    name_lower = path.name.lower()
    rel = path.relative_to(project_root)
    rel_str = str(rel).replace("\\", "/").lower()

    if name_lower.startswith("readme"):
        return "readme"
    if name_lower.startswith("changelog") or name_lower == "history.md":
        return "changelog"
    if name_lower.startswith("contributing"):
        return "contributing"
    if name_lower.startswith("license") or name_lower.startswith("licence"):
        return "license"
    if name_lower.startswith("security"):
        return "security"
    if name_lower.startswith("code_of_conduct"):
        return "code_of_conduct"

    # ADR detection
    if "adr" in rel_str or "decision" in rel_str:
        return "adr"

    # API docs detection
    if "api" in rel_str:
        return "api_docs"

    # Guide detection
    if "guide" in rel_str or "tutorial" in rel_str or "howto" in rel_str:
        return "guides"

    return "other"


def _detect_doc_format(path: Path) -> str:
    """Detect the format of a documentation file."""
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix == ".rst":
        return "restructuredtext"
    if suffix == ".txt":
        return "plain"
    return "unknown"


def _scan_doc_files(project_root: Path) -> list[dict[str, Any]]:
    """Scan for documentation files under *project_root*.

    Respects skip directories and only includes files with doc extensions.
    """
    docs: list[dict[str, Any]] = []

    if not project_root.is_dir():
        return docs

    for dirpath, dirnames, filenames in os.walk(project_root):
        # Prune skipped directories in-place (os.walk respects this).
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        current = Path(dirpath)
        for fname in filenames:
            fpath = current / fname
            if fpath.suffix.lower() not in _DOC_EXTENSIONS:
                continue

            try:
                stat = fpath.stat()
                rel_path = fpath.relative_to(project_root)
                docs.append({
                    "path": str(rel_path).replace("\\", "/"),
                    "size_bytes": stat.st_size,
                    "last_modified": time.strftime(
                        "%Y-%m-%dT%H:%M:%S",
                        time.localtime(stat.st_mtime),
                    ),
                    "format": _detect_doc_format(fpath),
                    "category": _categorize_doc(fpath, project_root),
                })
            except OSError:
                continue

    return docs


def _detect_project_name(project_root: Path) -> str:
    """Best-effort project name detection from pyproject.toml or directory name."""
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("name") and "=" in stripped:
                    # Parse: name = "my-project"
                    value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
        except OSError:
            pass

    # Fallback to directory name
    return project_root.name


# ---------------------------------------------------------------------------
# Tool: docs_session_start
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def docs_session_start(
    project_root: str = "",
) -> dict[str, Any]:
    """REQUIRED as the FIRST call in every session. Detects project type,
    scans for existing documentation, and returns configuration summary
    with recommendations for missing docs.

    Args:
        project_root: Optional override for project root directory.
    """
    _record_call("docs_session_start")
    start = time.perf_counter_ns()

    from docs_mcp.config.settings import load_docs_settings

    try:
        root_override = Path(project_root) if project_root.strip() else None
        settings = load_docs_settings(root_override)
    except Exception as exc:
        return error_response("docs_session_start", "CONFIG_ERROR", str(exc))

    root = settings.project_root

    # Detect project name
    project_name = _detect_project_name(root)

    # Scan for existing documentation
    existing_docs = _scan_doc_files(root)

    # Build config summary
    docs_config: dict[str, Any] = {
        "output_dir": settings.output_dir,
        "default_style": settings.default_style,
        "default_format": settings.default_format,
        "include_toc": settings.include_toc,
        "include_badges": settings.include_badges,
        "changelog_format": settings.changelog_format,
        "adr_format": settings.adr_format,
        "diagram_format": settings.diagram_format,
        "git_log_limit": settings.git_log_limit,
    }

    # Determine which recommended docs are missing
    existing_names_lower = {d["path"].lower() for d in existing_docs}
    # Also check just filenames for root-level docs
    existing_basenames_lower = {
        d["path"].rsplit("/", 1)[-1].lower() for d in existing_docs
    }

    missing_recommended: list[str] = []
    recommendations: list[str] = []

    for rec in _RECOMMENDED_DOCS:
        if rec.endswith("/"):
            # Check if directory has any docs
            has_docs_in_dir = any(
                d["path"].lower().startswith(rec.lower()) for d in existing_docs
            )
            if not has_docs_in_dir:
                missing_recommended.append(rec.rstrip("/"))
                recommendations.append(f"Consider creating a '{rec.rstrip('/')}/' directory for documentation.")
        else:
            rec_lower = rec.lower()
            # Check both full path and basename (for LICENSE without extension)
            name_without_ext = rec_lower.rsplit(".", 1)[0] if "." in rec_lower else rec_lower
            found = (
                rec_lower in existing_names_lower
                or rec_lower in existing_basenames_lower
                or name_without_ext in existing_basenames_lower
            )
            if not found:
                missing_recommended.append(rec)
                recommendations.append(f"Consider adding a {rec}.")

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "project_name": project_name,
        "project_root": str(root),
        "docs_config": docs_config,
        "existing_docs": existing_docs,
        "missing_recommended": missing_recommended,
        "recommendations": recommendations,
    }

    return success_response("docs_session_start", elapsed_ms, data)


# ---------------------------------------------------------------------------
# Tool: docs_project_scan
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def docs_project_scan(
    project_root: str = "",
) -> dict[str, Any]:
    """Comprehensive documentation state audit. Inventories all documentation
    files, categorizes them, and calculates a completeness score.

    Args:
        project_root: Optional override for project root directory.
    """
    _record_call("docs_project_scan")
    start = time.perf_counter_ns()

    from docs_mcp.config.settings import load_docs_settings

    try:
        root_override = Path(project_root) if project_root.strip() else None
        settings = load_docs_settings(root_override)
    except Exception as exc:
        return error_response("docs_project_scan", "CONFIG_ERROR", str(exc))

    root = settings.project_root

    # Scan all documentation files
    all_docs = _scan_doc_files(root)

    # Categorize documents
    categories: dict[str, list[dict[str, Any]]] = {
        "readme": [],
        "changelog": [],
        "contributing": [],
        "license": [],
        "security": [],
        "code_of_conduct": [],
        "api_docs": [],
        "adr": [],
        "guides": [],
        "other": [],
    }

    total_size = 0
    for doc in all_docs:
        cat = doc.get("category", "other")
        if cat not in categories:
            cat = "other"
        categories[cat].append(doc)
        total_size += doc.get("size_bytes", 0)

    # Check critical docs
    existing_basenames_lower = {
        d["path"].rsplit("/", 1)[-1].lower() for d in all_docs
    }
    existing_names_lower = {d["path"].lower() for d in all_docs}

    critical_docs: dict[str, dict[str, Any]] = {}
    for doc_name in _CRITICAL_DOCS:
        doc_lower = doc_name.lower()
        name_without_ext = doc_lower.rsplit(".", 1)[0] if "." in doc_lower else doc_lower

        found = (
            doc_lower in existing_names_lower
            or doc_lower in existing_basenames_lower
            or name_without_ext in existing_basenames_lower
        )

        if found:
            # Find the matching doc entry for size info
            match = next(
                (
                    d
                    for d in all_docs
                    if d["path"].lower() == doc_lower
                    or d["path"].rsplit("/", 1)[-1].lower() == doc_lower
                    or d["path"].rsplit("/", 1)[-1].lower() == name_without_ext
                ),
                None,
            )
            critical_docs[doc_name] = {
                "exists": True,
                "size_bytes": match["size_bytes"] if match else 0,
            }
        else:
            critical_docs[doc_name] = {"exists": False}

    # Calculate completeness score (0-100)
    completeness_score = _calculate_completeness(categories, critical_docs, all_docs)

    # Build recommendations
    recommendations: list[str] = []
    for doc_name, info in critical_docs.items():
        if not info["exists"]:
            recommendations.append(f"Missing critical document: {doc_name}")
    if not categories["api_docs"]:
        recommendations.append("No API documentation found. Consider adding API docs.")
    if not categories["guides"]:
        recommendations.append("No guides or tutorials found. Consider adding user guides.")
    if len(all_docs) == 0:
        recommendations.append(
            "No documentation files found. Start by creating a README.md."
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "total_docs": len(all_docs),
        "total_size_bytes": total_size,
        "categories": categories,
        "completeness_score": completeness_score,
        "critical_docs": critical_docs,
        "recommendations": recommendations,
    }

    return success_response("docs_project_scan", elapsed_ms, data)


def _calculate_completeness(
    categories: dict[str, list[dict[str, Any]]],
    critical_docs: dict[str, dict[str, Any]],
    all_docs: list[dict[str, Any]],
) -> int:
    """Calculate a documentation completeness score (0-100).

    Scoring breakdown:
    - Critical docs (README, LICENSE, CHANGELOG, CONTRIBUTING): 15 pts each = 60
    - Has API docs: 10 pts
    - Has guides/tutorials: 10 pts
    - Has ADRs: 5 pts
    - Has docs directory with content: 10 pts
    - Has security doc: 5 pts
    """
    score = 0
    max_score = 100

    # Critical docs: 15 points each (60 total)
    critical_weight = 15
    for info in critical_docs.values():
        if info["exists"]:
            score += critical_weight

    # API docs: 10 points
    if categories.get("api_docs"):
        score += 10

    # Guides: 10 points
    if categories.get("guides"):
        score += 10

    # ADRs: 5 points
    if categories.get("adr"):
        score += 5

    # Docs directory with content: 10 points
    has_docs_dir = any(
        "/" in d["path"] and d["path"].split("/")[0].lower() == "docs"
        for d in all_docs
    )
    if has_docs_dir:
        score += 10

    # Security doc: 5 points
    if categories.get("security"):
        score += 5

    return min(score, max_score)


# ---------------------------------------------------------------------------
# Tool: docs_config
# ---------------------------------------------------------------------------

# Valid config keys that can be set via docs_config.
_VALID_CONFIG_KEYS: frozenset[str] = frozenset({
    "output_dir",
    "default_style",
    "default_format",
    "include_toc",
    "include_badges",
    "changelog_format",
    "adr_format",
    "diagram_format",
    "git_log_limit",
    "log_level",
    "log_json",
})

# Keys that accept boolean values.
_BOOL_KEYS: frozenset[str] = frozenset({"include_toc", "include_badges", "log_json"})

# Keys that accept integer values.
_INT_KEYS: frozenset[str] = frozenset({"git_log_limit"})


def _parse_config_value(key: str, value: str) -> str | bool | int:
    """Parse a string value into the appropriate type for the given config key."""
    if key in _BOOL_KEYS:
        return value.lower() in ("true", "1", "yes")
    if key in _INT_KEYS:
        return int(value)
    return value


@mcp.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)
async def docs_config(
    action: str = "view",
    key: str = "",
    value: str = "",
) -> dict[str, Any]:
    """View or update DocsMCP configuration.

    Reads from the current settings (env + .docsmcp.yaml + defaults) for
    ``action="view"``.  Writes to ``.docsmcp.yaml`` for ``action="set"``.

    Args:
        action: "view" to read config, "set" to update a config value.
        key: Config key to set (e.g. "default_style", "output_dir").
            Required when action="set".
        value: Value to set. Required when action="set".
    """
    _record_call("docs_config")
    start = time.perf_counter_ns()

    if action not in ("view", "set"):
        return error_response(
            "docs_config",
            "INVALID_ACTION",
            f"Invalid action {action!r}. Use 'view' or 'set'.",
        )

    from docs_mcp.config.settings import load_docs_settings

    try:
        settings = load_docs_settings()
    except Exception as exc:
        return error_response("docs_config", "CONFIG_ERROR", str(exc))

    if action == "view":
        config_data: dict[str, Any] = {
            "output_dir": settings.output_dir,
            "default_style": settings.default_style,
            "default_format": settings.default_format,
            "include_toc": settings.include_toc,
            "include_badges": settings.include_badges,
            "changelog_format": settings.changelog_format,
            "adr_format": settings.adr_format,
            "diagram_format": settings.diagram_format,
            "git_log_limit": settings.git_log_limit,
            "log_level": settings.log_level,
            "log_json": settings.log_json,
        }

        config_path = settings.project_root / ".docsmcp.yaml"
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

        return success_response(
            "docs_config",
            elapsed_ms,
            {
                "config": config_data,
                "config_file": ".docsmcp.yaml",
                "config_exists": config_path.exists(),
            },
        )

    # action == "set"
    if not key:
        return error_response(
            "docs_config",
            "MISSING_KEY",
            "Parameter 'key' is required when action='set'.",
        )

    if key not in _VALID_CONFIG_KEYS:
        return error_response(
            "docs_config",
            "INVALID_KEY",
            f"Unknown config key {key!r}. Valid keys: {', '.join(sorted(_VALID_CONFIG_KEYS))}",
        )

    if not value and key not in _BOOL_KEYS:
        return error_response(
            "docs_config",
            "MISSING_VALUE",
            "Parameter 'value' is required when action='set'.",
        )

    import yaml

    from tapps_core.security.path_validator import PathValidator

    root = Path(settings.project_root)
    validator = PathValidator(root)

    try:
        config_path = validator.validate_write_path(".docsmcp.yaml")
    except (ValueError, FileNotFoundError) as exc:
        return error_response("docs_config", "PATH_ERROR", str(exc))

    # Read existing YAML data
    existing_data: dict[str, Any] = {}
    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8-sig") as f:
                raw = yaml.safe_load(f)
            if isinstance(raw, dict):
                existing_data = raw
        except Exception as exc:
            return error_response(
                "docs_config",
                "READ_ERROR",
                f"Could not read .docsmcp.yaml: {exc}",
            )

    # Capture old value
    old_value = existing_data.get(key, getattr(settings, key, None))

    # Parse and set new value
    try:
        parsed_value = _parse_config_value(key, value)
    except (ValueError, TypeError) as exc:
        return error_response(
            "docs_config",
            "PARSE_ERROR",
            f"Could not parse value {value!r} for key {key!r}: {exc}",
        )

    existing_data[key] = parsed_value

    # Write back
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as f:
            yaml.dump(existing_data, f, default_flow_style=False, sort_keys=False)
    except OSError as exc:
        return error_response(
            "docs_config",
            "WRITE_ERROR",
            f"Could not write .docsmcp.yaml: {exc}",
        )

    # Reset settings cache so next call picks up the change
    from docs_mcp.config.settings import _reset_docs_settings_cache

    _reset_docs_settings_cache()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return success_response(
        "docs_config",
        elapsed_ms,
        {
            "key": key,
            "old_value": old_value,
            "new_value": parsed_value,
            "config_file": ".docsmcp.yaml",
        },
    )


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------


def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start the DocsMCP MCP server."""
    from tapps_core.common.logging import setup_logging

    from docs_mcp.config.settings import load_docs_settings

    settings = load_docs_settings()
    setup_logging(level=settings.log_level, json_output=settings.log_json)

    logger.info(
        "docs_mcp_starting",
        version=__version__,
        transport=transport,
        project_root=str(settings.project_root),
    )

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "http":
        import uvicorn

        mcp_app = mcp.streamable_http_app()
        uvicorn.run(mcp_app, host=host, port=port)
    else:
        msg = f"Unknown transport: {transport}"
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Import tool modules that register on the shared ``mcp`` instance.
# Must be at the bottom to avoid circular imports.
# ---------------------------------------------------------------------------

import docs_mcp.server_analysis as _server_analysis  # noqa: E402, F401
import docs_mcp.server_gen_tools as _server_gen_tools  # noqa: E402, F401
import docs_mcp.server_git_tools as _server_git_tools  # noqa: E402, F401
import docs_mcp.server_val_tools as _server_val_tools  # noqa: E402, F401
