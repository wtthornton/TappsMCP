"""Benchmark configuration loading and defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from tapps_mcp.benchmark.models import BenchmarkConfig, ContextMode

__all__ = [
    "DEFAULT_CONFIG",
    "load_benchmark_config",
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = BenchmarkConfig()


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _load_yaml_benchmark_section(project_root: Path) -> dict[str, Any]:
    """Load the ``benchmark`` section from ``.tapps-mcp.yaml`` if present."""
    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return {}

    try:
        with config_path.open(encoding="utf-8-sig") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        logger.debug(
            "benchmark_config_load_failed",
            path=str(config_path),
            reason=str(exc),
        )
        return {}

    if not isinstance(data, dict):
        return {}

    section = data.get("benchmark")
    if not isinstance(section, dict):
        return {}

    return section


def _coerce_context_mode(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize ``context_mode`` string to a ``ContextMode`` enum value."""
    if "context_mode" in raw and isinstance(raw["context_mode"], str):
        raw["context_mode"] = ContextMode(raw["context_mode"].lower())
    return raw


def load_benchmark_config(
    project_root: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> BenchmarkConfig:
    """Load benchmark configuration with correct precedence.

    Precedence (highest to lowest):
        1. Explicit overrides
        2. ``.tapps-mcp.yaml`` ``benchmark:`` section
        3. Built-in defaults

    Args:
        project_root: Project root directory.  Falls back to CWD.
        overrides: Field-level overrides applied on top of YAML values.

    Returns:
        Fully resolved ``BenchmarkConfig``.
    """
    root = Path(project_root) if project_root else Path.cwd()

    yaml_values = _load_yaml_benchmark_section(root)
    yaml_values = _coerce_context_mode(yaml_values)

    effective_overrides = overrides or {}
    merged: dict[str, Any] = {**yaml_values, **effective_overrides}
    merged = _coerce_context_mode(merged)

    try:
        config = BenchmarkConfig(**merged)
    except Exception as exc:
        logger.warning(
            "benchmark_config_validation_failed",
            reason=str(exc),
            falling_back_to="defaults",
        )
        config = DEFAULT_CONFIG

    logger.debug(
        "benchmark_config_loaded",
        dataset=config.dataset_name,
        context_mode=config.context_mode.value,
        subset_size=config.subset_size,
    )

    return config
