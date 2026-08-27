"""Pydantic models shared by the checklist modules.

Split out of ``checklist.py`` so that ``checklist_epic`` can subclass
``ChecklistResult`` without importing ``checklist`` itself, which would be
a cycle (``checklist`` imports the epic validators back).
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    """Record of a single tool invocation."""

    tool_name: str
    timestamp: float = Field(default_factory=time.time)
    session_id: str = Field(
        default="",
        description="Checklist session id (empty = recorded before session boundary).",
    )
    success: bool = Field(default=True, description="Whether the invocation succeeded.")


class ChecklistHint(BaseModel):
    """A missing tool with a short reason for the LLM."""

    tool: str = Field(description="Tool name to call.")
    reason: str = Field(description="Why to call it / what to do next.")


class ChecklistResult(BaseModel):
    """Result of checklist evaluation."""

    task_type: str = Field(description="The task type evaluated.")
    resolved_policy_task_type: str = Field(
        default="",
        description="Task key used to load policy (may differ when falling back to review).",
    )
    policy_fallback: bool = Field(
        default=False,
        description="True when user task_type was unknown and review policy was used.",
    )
    checklist_policy_version: str = Field(
        default="",
        description="Hash of merged built-in + optional checklist-policy.yaml maps.",
    )
    called: list[str] = Field(
        default_factory=list, description="Tools already called this session."
    )
    missing_required: list[str] = Field(
        default_factory=list, description="Required tools not yet called."
    )
    missing_recommended: list[str] = Field(
        default_factory=list, description="Recommended tools not yet called."
    )
    missing_optional: list[str] = Field(
        default_factory=list, description="Optional tools not yet called."
    )
    missing_required_hints: list[ChecklistHint] = Field(
        default_factory=list,
        description="Required tools not yet called, with a short reason for each.",
    )
    missing_recommended_hints: list[ChecklistHint] = Field(
        default_factory=list,
        description="Recommended tools not yet called, with a short reason for each.",
    )
    missing_optional_hints: list[ChecklistHint] = Field(
        default_factory=list,
        description="Optional tools not yet called, with a short reason for each.",
    )
    required_tool_names: list[str] = Field(
        default_factory=list, description="Required tools for this task/engagement."
    )
    satisfied_required_tools: list[str] = Field(
        default_factory=list, description="Required tools satisfied (including equivalents)."
    )
    recommended_tool_names: list[str] = Field(
        default_factory=list, description="Recommended tools for this task/engagement."
    )
    satisfied_recommended_tools: list[str] = Field(
        default_factory=list, description="Recommended tools satisfied (including equivalents)."
    )
    optional_tool_names: list[str] = Field(
        default_factory=list, description="Optional tools for this task/engagement."
    )
    satisfied_optional_tools: list[str] = Field(
        default_factory=list, description="Optional tools satisfied (including equivalents)."
    )
    task_type_hint: str = Field(
        default="",
        description="When set, explains when to use this task_type (document, epic, etc.).",
    )
    complete: bool = Field(default=False, description="All required tools have been called.")
    total_calls: int = Field(default=0, description="Total tool calls this session.")
    server_unavailable_tools: list[str] = Field(
        default_factory=list,
        description="Required tools downgraded because their NLT server is disabled.",
    )
    nothing_to_gate: bool = Field(
        default=False,
        description=(
            "TAP-6606: tapps_validate_changed recorded that this session's changeset "
            "holds no scorable file, and a fresh git census still agrees. File-scoped "
            "required tools have no target and are reported as not_applicable_tools."
        ),
    )
    nothing_to_gate_reason: str = Field(
        default="",
        description=(
            "Honest terminal reason when nothing_to_gate is set. Distinct from the "
            "'no validation was run' state, which never sets this field."
        ),
    )
    not_applicable_tools: list[str] = Field(
        default_factory=list,
        description=(
            "Required tools that need a scorable file the session never touched. "
            "Not missing and not optional — inapplicable."
        ),
    )
