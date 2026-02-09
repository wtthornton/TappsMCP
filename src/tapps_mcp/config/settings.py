"""TappsMCP configuration system.

Precedence (highest to lowest):
    1. Environment variables (``TAPPS_MCP_*``)
    2. Project-level ``.tapps-mcp.yaml``
    3. Built-in defaults
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        default=10,
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


def _load_yaml_config(project_root: Path) -> dict[str, Any]:
    """Load project-level ``.tapps-mcp.yaml`` if it exists."""
    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return {}

    try:
        with config_path.open(encoding="utf-8-sig") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_settings(project_root: Path | None = None) -> TappsMCPSettings:
    """Load settings with correct precedence.

    Args:
        project_root: Override for project root.  When ``None``, uses CWD.

    Returns:
        Fully resolved ``TappsMCPSettings``.
    """
    root = Path(project_root) if project_root else Path.cwd()
    yaml_data = _load_yaml_config(root)

    # Merge YAML defaults, then let env vars override via pydantic-settings
    if "project_root" not in yaml_data:
        yaml_data["project_root"] = str(root)

    return TappsMCPSettings(**yaml_data)
