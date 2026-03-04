"""Business expert auto-loading integration.

Called during session start to load and register business experts
from ``.tapps-mcp/experts.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

from tapps_core.config.settings import load_settings
from tapps_core.experts.business_config import load_business_experts
from tapps_core.experts.business_knowledge import (
    KnowledgeValidationResult,
    validate_business_knowledge,
)
from tapps_core.experts.registry import ExpertRegistry

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)  # type: ignore[assignment]


@dataclass
class BusinessExpertLoadResult:
    """Result of loading and registering business experts."""

    loaded: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    expert_ids: list[str] = field(default_factory=list)
    knowledge_status: dict[str, str] = field(default_factory=dict)


def load_and_register_business_experts(
    project_root: Path,
) -> BusinessExpertLoadResult:
    """Load business experts from YAML and register them with the registry.

    Checks ``settings.business_experts_enabled`` before proceeding.
    Gracefully handles missing config files, validation errors, and
    ID collisions.

    Args:
        project_root: Project root directory.

    Returns:
        Structured result with load status and knowledge validation.
    """
    result = BusinessExpertLoadResult()

    settings = load_settings()
    if not settings.business_experts_enabled:
        logger.debug("business_experts.disabled")
        return result

    # Load from YAML
    try:
        experts = load_business_experts(project_root)
    except (ValueError, OSError) as exc:
        result.errors.append(f"Failed to load business experts: {exc}")
        logger.warning("business_experts.load_failed", error=str(exc))
        return result

    if not experts:
        return result

    # Register with the registry
    try:
        ExpertRegistry.register_business_experts(experts)
    except ValueError as exc:
        result.errors.append(f"Failed to register business experts: {exc}")
        logger.warning("business_experts.register_failed", error=str(exc))
        return result

    result.loaded = len(experts)
    result.expert_ids = [e.expert_id for e in experts]

    # Validate knowledge directories
    validation = validate_business_knowledge(project_root, experts)
    _populate_knowledge_status(result, validation)

    logger.info(
        "business_experts.registered",
        count=result.loaded,
        expert_ids=result.expert_ids,
        knowledge_valid=len(validation.valid),
        knowledge_missing=len(validation.missing),
        knowledge_empty=len(validation.empty),
    )

    return result


def _populate_knowledge_status(
    result: BusinessExpertLoadResult,
    validation: KnowledgeValidationResult,
) -> None:
    """Fill knowledge_status and warnings from validation result."""
    for domain in validation.valid:
        result.knowledge_status[domain] = "valid"
    for domain in validation.missing:
        result.knowledge_status[domain] = "missing"
    for domain in validation.empty:
        result.knowledge_status[domain] = "empty"
    result.warnings.extend(validation.warnings)
