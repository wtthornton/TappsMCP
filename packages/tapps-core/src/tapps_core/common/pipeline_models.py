"""Pipeline stage definitions shared across Tapps platform modules.

Centralised here to break the circular dependency between
``common.nudges`` and ``pipeline.models``.
"""

from __future__ import annotations

from enum import StrEnum


class PipelineStage(StrEnum):
    """The 5 stages of the TAPPS quality pipeline."""

    DISCOVER = "discover"
    RESEARCH = "research"
    DEVELOP = "develop"
    VALIDATE = "validate"
    VERIFY = "verify"


# Ordered list matching pipeline execution order.
STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.DISCOVER,
    PipelineStage.RESEARCH,
    PipelineStage.DEVELOP,
    PipelineStage.VALIDATE,
    PipelineStage.VERIFY,
]

# Tools allowed per stage.
STAGE_TOOLS: dict[PipelineStage, list[str]] = {
    PipelineStage.DISCOVER: [
        "tapps_server_info",
        "tapps_session_start",
        "tapps_memory",
    ],
    PipelineStage.RESEARCH: ["tapps_lookup_docs"],
    PipelineStage.DEVELOP: ["tapps_score_file"],
    PipelineStage.VALIDATE: [
        "tapps_score_file",
        "tapps_quality_gate",
        "tapps_security_scan",
        "tapps_validate_config",
        "tapps_validate_changed",
        "tapps_quick_check",
    ],
    PipelineStage.VERIFY: ["tapps_checklist", "tapps_memory"],
}
