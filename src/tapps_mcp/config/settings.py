"""TappsMCP configuration system.

Precedence (highest to lowest):
    1. Environment variables (``TAPPS_MCP_*``)
    2. Project-level ``.tapps-mcp.yaml``
    3. Built-in defaults
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)


class ScoringWeights(BaseSettings):
    """Weights for the 7-category scoring system.  Must sum to ~1.0."""

    model_config = SettingsConfigDict(env_prefix="TAPPS_MCP_WEIGHT_")

    complexity: float = Field(default=0.18, ge=0.0, le=1.0)
    security: float = Field(default=0.27, ge=0.0, le=1.0)
    maintainability: float = Field(default=0.24, ge=0.0, le=1.0)
    test_coverage: float = Field(default=0.13, ge=0.0, le=1.0)
    performance: float = Field(default=0.08, ge=0.0, le=1.0)
    structure: float = Field(default=0.05, ge=0.0, le=1.0)
    devex: float = Field(default=0.05, ge=0.0, le=1.0)


class QualityPreset(BaseSettings):
    """Quality gate thresholds."""

    model_config = SettingsConfigDict(env_prefix="TAPPS_MCP_GATE_")

    overall_min: float = Field(default=70.0, ge=0.0, le=100.0)
    security_min: float = Field(default=0.0, ge=0.0, le=100.0)
    maintainability_min: float = Field(default=0.0, ge=0.0, le=100.0)


# Standard presets
PRESETS: dict[str, dict[str, float]] = {
    "standard": {"overall_min": 70.0, "security_min": 0.0, "maintainability_min": 0.0},
    "strict": {"overall_min": 80.0, "security_min": 8.0, "maintainability_min": 7.0},
    "framework": {"overall_min": 75.0, "security_min": 8.5, "maintainability_min": 7.5},
}


class AdaptiveSettings(BaseSettings):
    """Settings for the adaptive learning subsystem."""

    model_config = SettingsConfigDict(env_prefix="TAPPS_MCP_ADAPTIVE_")

    enabled: bool = Field(
        default=False,
        description="Enable adaptive weight adjustment.",
    )
    learning_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Learning rate for weight adjustment (0.0-1.0).",
    )
    min_outcomes: int = Field(
        default=5,
        ge=1,
        description="Minimum outcome records before adaptive adjustment activates.",
    )


class TappsMCPSettings(BaseSettings):
    """Root settings for TappsMCP server."""

    model_config = SettingsConfigDict(
        env_prefix="TAPPS_MCP_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Core
    project_root: Path = Field(
        default_factory=Path.cwd,
        description="Project root boundary — all file paths must be within this directory.",
    )
    host_project_root: str | None = Field(
        default=None,
        description=(
            "Optional host path the client uses for the same project "
            "(e.g. C:\\projects\\myapp). When set, absolute paths under "
            "this are mapped to project_root so Cursor/Docker work together."
        ),
    )
    quality_preset: str = Field(
        default="standard",
        description="Quality gate preset: standard, strict, or framework.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level.",
    )
    log_json: bool = Field(
        default=False,
        description="Output JSON-formatted logs.",
    )

    # API keys
    context7_api_key: SecretStr | None = Field(
        default=None,
        description="Context7 API key (optional).",
    )
    deepcon_api_key: SecretStr | None = Field(
        default=None,
        description="Deepcon API key (optional) for documentation lookup.",
    )
    docfork_api_key: SecretStr | None = Field(
        default=None,
        description="Docfork API key (optional) for documentation lookup.",
    )

    # Scoring
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    quality_gate: QualityPreset = Field(default_factory=QualityPreset)

    # Adaptive learning
    adaptive: AdaptiveSettings = Field(default_factory=AdaptiveSettings)

    # Tool timeouts
    tool_timeout: int = Field(
        default=30,
        ge=5,
        description="Timeout for individual external tool invocations (seconds).",
    )

    # Dead code detection
    dead_code_enabled: bool = Field(
        default=True,
        description="Enable dead code detection via vulture in scoring.",
    )
    dead_code_min_confidence: int = Field(
        default=80,
        ge=0,
        le=100,
        description="Minimum confidence threshold for dead code findings (0-100).",
    )
    dead_code_whitelist_patterns: list[str] = Field(
        default_factory=lambda: ["test_*", "conftest.py"],
        description="File name patterns to exclude from dead code findings (fnmatch).",
    )

    # Dependency vulnerability scanning
    dependency_scan_enabled: bool = Field(
        default=True,
        description="Enable dependency vulnerability scanning via pip-audit.",
    )
    dependency_scan_severity_threshold: str = Field(
        default="medium",
        description="Minimum severity to include: critical, high, medium, low, unknown.",
    )
    dependency_scan_ignore_ids: list[str] = Field(
        default_factory=list,
        description="Vulnerability IDs to exclude (e.g. CVE-2024-12345).",
    )
    dependency_scan_source: str = Field(
        default="auto",
        description="Scan source: auto, environment, requirements, pyproject.",
    )

    # Expert/doc coupling
    expert_auto_fallback: bool = Field(
        default=True,
        description=(
            "Enable automatic Context7 lookup hints/content when expert RAG has no matches."
        ),
    )
    expert_fallback_max_chars: int = Field(
        default=1200,
        ge=200,
        description="Maximum number of characters merged from Context7 fallback content.",
    )


# Settings cache — only the no-arg (default) case is cached.
_cached_settings: TappsMCPSettings | None = None


def _reset_settings_cache() -> None:
    """Reset the cached settings singleton.

    Call in test teardown or when environment/YAML config changes mid-process.
    """
    global _cached_settings  # noqa: PLW0603
    _cached_settings = None


def _load_yaml_config(project_root: Path) -> dict[str, Any]:
    """Load project-level ``.tapps-mcp.yaml`` if it exists."""
    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return {}

    try:
        with config_path.open(encoding="utf-8-sig") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("mcp_config_load_failed", path=str(config_path), reason=str(e))
        return {}


def load_settings(project_root: Path | None = None) -> TappsMCPSettings:
    """Load settings with correct precedence.

    When *project_root* is ``None`` (the default), returns a cached singleton
    created on the first call.  Pass an explicit *project_root* to bypass the
    cache entirely.

    Args:
        project_root: Override for project root.  When ``None``, uses CWD.

    Returns:
        Fully resolved ``TappsMCPSettings``.
    """
    global _cached_settings  # noqa: PLW0603

    if project_root is None and _cached_settings is not None:
        return _cached_settings

    # Determine root: explicit arg > env var > CWD
    if project_root:
        root = Path(project_root)
    else:
        import os

        env_root = os.environ.get("TAPPS_MCP_PROJECT_ROOT")
        root = Path(env_root) if env_root else Path.cwd()

    yaml_data = _load_yaml_config(root)

    # Merge YAML defaults, then let env vars override via pydantic-settings.
    # Only inject project_root if neither YAML nor env var sets it,
    # so the env var takes priority over CWD.
    if "project_root" not in yaml_data:
        yaml_data["project_root"] = str(root)

    result = TappsMCPSettings(**yaml_data)

    if project_root is None:
        _cached_settings = result

    return result
