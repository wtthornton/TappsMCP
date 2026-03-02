"""Pipeline data models for handoff state and run log tracking."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from tapps_core.common.pipeline_models import STAGE_ORDER as STAGE_ORDER
from tapps_core.common.pipeline_models import STAGE_TOOLS as STAGE_TOOLS

# Re-export from common.pipeline_models for backward compatibility
from tapps_core.common.pipeline_models import PipelineStage as PipelineStage


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
