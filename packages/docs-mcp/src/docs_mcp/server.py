"""DocsMCP MCP server entry point.

Creates the FastMCP server instance, registers tools, and provides
``run_server()`` for the CLI.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import structlog
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from docs_mcp import __version__
from docs_mcp.server_helpers import (
    build_style_checker_for_project,
    error_response,
    success_response,
)

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
# Tool curation (Epic 79.2): allowed tool names and presets
# ---------------------------------------------------------------------------

# Canonical list of all DocsMCP tools (32). Used for filtering.
ALL_DOCS_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "docs_session_start",
        "docs_project_scan",
        "docs_config",
        "docs_module_map",
        "docs_api_surface",
        "docs_git_summary",
        "docs_generate_changelog",
        "docs_generate_release_notes",
        "docs_generate_readme",
        "docs_generate_api",
        "docs_generate_adr",
        "docs_generate_onboarding",
        "docs_generate_contributing",
        "docs_generate_prd",
        "docs_generate_diagram",
        "docs_generate_architecture",
        "docs_generate_epic",
        "docs_generate_story",
        "docs_generate_prompt",
        "docs_check_drift",
        "docs_check_completeness",
        "docs_check_links",
        "docs_check_freshness",
        "docs_validate_epic",
        "docs_generate_llms_txt",
        "docs_generate_frontmatter",
        "docs_check_diataxis",
        "docs_generate_interactive_diagrams",
        "docs_generate_purpose",
        "docs_generate_doc_index",
        "docs_check_cross_refs",
        "docs_check_style",
    }
)

# Core preset (Epic 79.2): session start, project scan, drift, readme, completeness, links.
DOCS_TOOL_PRESET_CORE: frozenset[str] = frozenset(
    {
        "docs_session_start",
        "docs_project_scan",
        "docs_check_drift",
        "docs_generate_readme",
        "docs_check_completeness",
        "docs_check_links",
    }
)


def _resolve_allowed_tools(
    enabled_tools: list[str] | None,
    disabled_tools: list[str],
    tool_preset: str | None,
) -> frozenset[str]:
    """Compute the set of tool names to register from config (Epic 79.2).

    Precedence: enabled_tools (if non-empty) > tool_preset > full set; then
    subtract disabled_tools. Invalid names in enabled_tools are ignored and logged.
    """
    allowed: set[str]
    if enabled_tools:
        allowed = set(enabled_tools) & ALL_DOCS_TOOL_NAMES
        invalid = set(enabled_tools) - ALL_DOCS_TOOL_NAMES
        if invalid:
            logger.debug(
                "docs_enabled_tools_invalid_ignored",
                invalid=sorted(invalid),
                valid_count=len(allowed),
            )
    elif tool_preset == "core":
        allowed = set(DOCS_TOOL_PRESET_CORE)
    elif tool_preset == "full":
        allowed = set(ALL_DOCS_TOOL_NAMES)
    else:
        allowed = set(ALL_DOCS_TOOL_NAMES)
    allowed -= set(disabled_tools)
    return frozenset(allowed)


def _register_core_tools(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register core tools (server.py) when their name is in allowed_tools (Epic 79.2)."""
    if "docs_session_start" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_session_start)
    if "docs_project_scan" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_project_scan)
    if "docs_config" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_config)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Documentation file categories and their typical filenames/patterns.
_CRITICAL_DOCS: list[str] = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
]

_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})

_RECOMMENDED_DOCS: list[str] = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "docs/",
]

# Directories to skip when scanning for documentation files.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
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
    }
)


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
                docs.append(
                    {
                        "path": str(rel_path).replace("\\", "/"),
                        "size_bytes": stat.st_size,
                        "last_modified": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ",
                            time.gmtime(stat.st_mtime),
                        ),
                        "format": _detect_doc_format(fpath),
                        "category": _categorize_doc(fpath, project_root),
                    }
                )
            except OSError:
                continue

    return docs


# Source file extensions for language composition analysis.
_SOURCE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".rb": "Ruby",
    ".cpp": "C++",
    ".c": "C",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
}


def _count_source_files(project_root: Path) -> dict[str, int]:
    """Count source files by language under *project_root*."""
    counts: dict[str, int] = {}
    if not project_root.is_dir():
        return counts

    for _dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        for fname in filenames:
            suffix = Path(fname).suffix.lower()
            lang = _SOURCE_EXTENSIONS.get(suffix)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1

    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


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
# Tool: docs_session_start (registered conditionally in _register_core_tools)
# ---------------------------------------------------------------------------


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
    existing_basenames_lower = {d["path"].rsplit("/", 1)[-1].lower() for d in existing_docs}

    missing_recommended: list[str] = []
    recommendations: list[str] = []

    for rec in _RECOMMENDED_DOCS:
        if rec.endswith("/"):
            # Check if directory has any docs
            has_docs_in_dir = any(d["path"].lower().startswith(rec.lower()) for d in existing_docs)
            if not has_docs_in_dir:
                missing_recommended.append(rec.rstrip("/"))
                recommendations.append(
                    f"Consider creating a '{rec.rstrip('/')}/' directory for documentation."
                )
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
# Tool: docs_project_scan (registered conditionally in _register_core_tools)
# ---------------------------------------------------------------------------


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

    all_docs = _scan_doc_files(root)
    categories, total_size = _categorize_docs(all_docs)
    critical_docs = _check_critical_docs(all_docs)
    doc_file_score = _calculate_completeness(categories, critical_docs, all_docs)
    inline_coverage = _calculate_inline_doc_coverage(root)
    # Composite: 70% doc files + 30% inline coverage
    completeness_score = int(doc_file_score * 0.7 + inline_coverage * 0.3)
    recommendations = _build_project_scan_recommendations(categories, critical_docs, all_docs)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "total_docs": len(all_docs),
        "total_size_bytes": total_size,
        "categories": categories,
        "completeness_score": completeness_score,
        "doc_file_completeness": doc_file_score,
        "inline_doc_coverage": inline_coverage,
        "critical_docs": critical_docs,
        "recommendations": recommendations,
    }

    lang_counts = _count_source_files(root)
    if lang_counts:
        data["language_composition"] = lang_counts

    _add_style_summary(data, root, settings)
    _add_tapps_enrichment(data, root)

    return success_response("docs_project_scan", elapsed_ms, data)


def _categorize_docs(
    all_docs: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Bin documents into category buckets and sum total size."""
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
    return categories, total_size


def _check_critical_docs(
    all_docs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Check which critical docs exist and return their metadata."""
    existing_basenames_lower = {d["path"].rsplit("/", 1)[-1].lower() for d in all_docs}
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
    return critical_docs


def _build_project_scan_recommendations(
    categories: dict[str, list[dict[str, Any]]],
    critical_docs: dict[str, dict[str, Any]],
    all_docs: list[dict[str, Any]],
) -> list[str]:
    """Build actionable recommendations for the project scan response."""
    recommendations: list[str] = []
    for doc_name, info in critical_docs.items():
        if not info["exists"]:
            recommendations.append(f"Missing critical document: {doc_name}")
    if not categories["api_docs"]:
        recommendations.append("No API documentation found. Consider adding API docs.")
    if not categories["guides"]:
        recommendations.append("No guides or tutorials found. Consider adding user guides.")
    if len(all_docs) == 0:
        recommendations.append("No documentation files found. Start by creating a README.md.")
    return recommendations


def _add_style_summary(data: dict[str, Any], root: Any, settings: Any) -> None:
    """Optionally add style summary to project scan data (Epic 84)."""
    if not settings.style_include_in_project_scan:
        return
    try:
        style_checker = build_style_checker_for_project(root, settings)
        style_report = style_checker.check_project(root)
        if style_report.total_files > 0:
            data["style_summary"] = {
                "total_files": style_report.total_files,
                "total_issues": style_report.total_issues,
                "aggregate_score": style_report.aggregate_score,
                "top_issues": style_report.top_issues[:5],
            }
    except Exception:
        pass


def _add_tapps_enrichment(data: dict[str, Any], root: Any) -> None:
    """Optionally add TappsMCP enrichment data to project scan data."""
    try:
        from docs_mcp.integrations.tapps import TappsIntegration

        integration = TappsIntegration(root)
        if integration.is_available:
            profile = integration.load_project_profile()
            if profile:
                data["tapps_enrichment"] = {
                    "available": True,
                    "project_type": profile.project_type,
                    "tech_stack": profile.tech_stack,
                    "has_ci": profile.has_ci,
                    "test_frameworks": profile.test_frameworks,
                    "package_managers": profile.package_managers,
                }
    except Exception:
        pass


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
        "/" in d["path"] and d["path"].split("/")[0].lower() == "docs" for d in all_docs
    )
    if has_docs_dir:
        score += 10

    # Security doc: 5 points
    if categories.get("security"):
        score += 5

    return min(score, max_score)


def _calculate_inline_doc_coverage(project_root: Path) -> int:
    """Calculate inline documentation coverage (docstrings) as a 0-100 score.

    Scans up to 50 Python files and computes the percentage of public
    functions and classes that have docstrings.
    """
    try:
        from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer

        analyzer = APISurfaceAnalyzer()
        py_files = sorted(project_root.rglob("*.py"))

        # Skip test files, venvs, and hidden dirs
        filtered: list[Path] = []
        for f in py_files:
            parts = f.relative_to(project_root).parts
            if any(
                p.startswith(".") or p in ("venv", ".venv", "node_modules", "__pycache__")
                for p in parts
            ):
                continue
            filtered.append(f)
            if len(filtered) >= 50:
                break

        total_public = 0
        total_documented = 0
        for py_file in filtered:
            try:
                surface = analyzer.analyze(py_file, project_root=project_root)
                for func in surface.functions:
                    total_public += 1
                    if func.docstring_present:
                        total_documented += 1
                for cls in surface.classes:
                    total_public += 1
                    if cls.docstring_present:
                        total_documented += 1
            except Exception:
                continue

        if not filtered:
            return 0  # No Python files found
        if total_public == 0:
            return 100  # Has Python files but no public API = nothing to document
        return int((total_documented / total_public) * 100)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Tool: docs_config
# ---------------------------------------------------------------------------

# Valid config keys that can be set via docs_config.
_VALID_CONFIG_KEYS: frozenset[str] = frozenset(
    {
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
    }
)

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


# Registered conditionally in _register_core_tools (Epic 79.2).
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
            raw_text = await asyncio.to_thread(config_path.read_text, encoding="utf-8-sig")
            raw = yaml.safe_load(raw_text)
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

    # Epic 87: content-return mode for Docker/read-only
    from docs_mcp.server_helpers import can_write_to_project

    yaml_content = yaml.dump(existing_data, default_flow_style=False, sort_keys=False)

    if can_write_to_project(root):
        # Write back
        try:
            await asyncio.to_thread(config_path.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(config_path.write_text, yaml_content, encoding="utf-8")
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

    result_data: dict[str, Any] = {
        "key": key,
        "old_value": old_value,
        "new_value": parsed_value,
        "config_file": ".docsmcp.yaml",
    }

    if not can_write_to_project(root):
        from docs_mcp.server_helpers import build_generator_manifest

        result_data["content_return"] = True
        result_data["file_manifest"] = build_generator_manifest(
            "docs_config",
            yaml_content,
            ".docsmcp.yaml",
            description="DocsMCP configuration with updated settings.",
        )

    return success_response(
        "docs_config",
        elapsed_ms,
        result_data,
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
    from docs_mcp.config.settings import load_docs_settings
    from tapps_core.common.logging import setup_logging

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
# Register tools from modules (Epic 79.2: conditional registration)
# Must be at the bottom so handlers above are defined; loads settings and
# registers only tools that pass the enabled_tools / disabled_tools / preset filter.
# ---------------------------------------------------------------------------


def _register_tool_modules() -> None:
    """Load settings, resolve allowed_tools (Epic 79.2), register core tools
    conditionally, then each module's register(mcp, allowed_tools).
    """
    from docs_mcp.config.settings import load_docs_settings

    settings = load_docs_settings()
    allowed_tools = _resolve_allowed_tools(
        settings.enabled_tools,
        settings.disabled_tools,
        settings.tool_preset,
    )

    _register_core_tools(mcp, allowed_tools)

    from docs_mcp import (
        server_analysis,
        server_gen_tools,
        server_git_tools,
        server_val_tools,
    )

    server_analysis.register(mcp, allowed_tools)
    server_git_tools.register(mcp, allowed_tools)
    server_gen_tools.register(mcp, allowed_tools)
    server_val_tools.register(mcp, allowed_tools)

    # Resources and prompts (no tool filtering)
    import docs_mcp.server_resources as _  # noqa: F401  # register resources on mcp


_register_tool_modules()
