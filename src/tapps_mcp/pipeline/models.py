"""Pipeline data models for handoff state and run log tracking."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel, Field


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
    PipelineStage.DISCOVER: ["tapps_server_info", "tapps_project_profile"],
    PipelineStage.RESEARCH: ["tapps_lookup_docs", "tapps_consult_expert", "tapps_list_experts"],
    PipelineStage.DEVELOP: ["tapps_score_file"],
    PipelineStage.VALIDATE: [
        "tapps_score_file",
        "tapps_quality_gate",
        "tapps_security_scan",
        "tapps_validate_config",
    ],
    PipelineStage.VERIFY: ["tapps_checklist"],
}


class StageResult(BaseModel):
    """Result of completing a single pipeline stage."""

    stage: PipelineStage
    completed_at: datetime
    tools_called: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    files_in_scope: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class HandoffState(BaseModel):
    """Full pipeline handoff state - tracks progress across stages."""

    current_stage: PipelineStage
    objective: str
    stage_results: list[StageResult] = Field(default_factory=list)
    next_stage_instructions: str = ""


class RunlogEntry(BaseModel):
    """A single entry in the pipeline run log."""

    timestamp: datetime
    stage: PipelineStage
    action: str
    details: str
