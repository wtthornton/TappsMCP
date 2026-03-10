"""DocsMCP configuration system.

Precedence (highest to lowest):
    1. Environment variables (``DOCS_MCP_*``)
    2. Project-level ``.docsmcp.yaml``
    3. Built-in defaults
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)


class DocsMCPSettings(BaseSettings):
    """Root settings for DocsMCP server."""

    model_config = SettingsConfigDict(
        env_prefix="DOCS_MCP_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Core
    project_root: Path = Field(
        default_factory=Path.cwd,
        description="Project root boundary - all file paths must be within this directory.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level.",
    )
    log_json: bool = Field(
        default=False,
        description="Output JSON-formatted logs.",
    )

    # Documentation generation
    output_dir: str = Field(
        default="docs",
        description="Directory where generated documentation is written.",
    )
    default_style: str = Field(
        default="standard",
        description="README style: minimal, standard, or comprehensive.",
    )
    default_format: Literal["markdown", "rst", "plain"] = Field(
        default="markdown",
        description="Default output format for generated documentation.",
    )
    include_toc: bool = Field(
        default=True,
        description="Include table of contents in generated documents.",
    )
    include_badges: bool = Field(
        default=True,
        description="Include badges in generated README files.",
    )

    # Changelog
    changelog_format: str = Field(
        default="keep-a-changelog",
        description="Changelog format: keep-a-changelog or conventional.",
    )

    # ADR
    adr_format: str = Field(
        default="madr",
        description="ADR template format: madr or nygard.",
    )

    # Diagrams
    diagram_format: str = Field(
        default="mermaid",
        description="Diagram output format: mermaid or plantuml.",
    )

    # Git analysis
    git_log_limit: int = Field(
        default=500,
        ge=1,
        description="Maximum number of git commits to analyze.",
    )


# Settings cache - only the no-arg (default) case is cached.
_cached_settings: DocsMCPSettings | None = None


def _reset_docs_settings_cache() -> None:
    """Reset the cached settings singleton.

    Call in test teardown or when environment/YAML config changes mid-process.
    """
    global _cached_settings  # noqa: PLW0603
    _cached_settings = None


def _load_yaml_config(project_root: Path) -> dict[str, Any]:
    """Load project-level ``.docsmcp.yaml`` if it exists."""
    config_path = project_root / ".docsmcp.yaml"
    if not config_path.exists():
        return {}

    try:
        with config_path.open(encoding="utf-8-sig") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("docs_config_load_failed", path=str(config_path), reason=str(e))
        return {}


def _expand_path(raw: str) -> Path:
    """Expand environment variables and ``~`` in a path string.

    Applies ``os.path.expandvars`` then ``os.path.expanduser`` so that
    values like ``${DOCS_MCP_PROJECT_ROOT}`` or ``~/projects/foo`` resolve
    to absolute filesystem paths.
    """
    import os

    expanded = os.path.expandvars(raw)
    expanded = os.path.expanduser(expanded)
    return Path(expanded)


def load_docs_settings(project_root: Path | None = None) -> DocsMCPSettings:
    """Load settings with correct precedence.

    When *project_root* is ``None`` (the default), returns a cached singleton
    created on the first call.  Pass an explicit *project_root* to bypass the
    cache entirely.

    Args:
        project_root: Override for project root.  When ``None``, uses CWD.

    Returns:
        Fully resolved ``DocsMCPSettings``.
    """
    global _cached_settings  # noqa: PLW0603

    if project_root is None and _cached_settings is not None:
        return _cached_settings

    # Determine root: explicit arg > env var > CWD
    if project_root:
        root = _expand_path(str(project_root))
    else:
        import os

        env_root = os.environ.get("DOCS_MCP_PROJECT_ROOT")
        root = _expand_path(env_root) if env_root else Path.cwd()

    yaml_data = _load_yaml_config(root)

    # Merge YAML defaults, then let env vars override via pydantic-settings.
    if "project_root" not in yaml_data:
        yaml_data["project_root"] = str(root)

    result = DocsMCPSettings(**yaml_data)

    # Expand env vars / ~ in project_root and output_dir after construction
    result.project_root = _expand_path(str(result.project_root))

    expanded_output = _expand_path(result.output_dir)
    result.output_dir = str(expanded_output)

    # Warn if the expanded project_root doesn't exist (it may be created later)
    if not result.project_root.is_dir():
        logger.warning(
            "docs_project_root_missing",
            path=str(result.project_root),
            hint="Directory does not exist yet - it may be created later.",
        )

    if project_root is None:
        _cached_settings = result

    return result
