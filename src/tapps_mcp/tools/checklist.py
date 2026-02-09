"""Session-level tool call tracking for ``tapps_checklist``.

Tracks which TappsMCP tools have been called during the current server
session so that ``tapps_checklist`` can report what's been done and what's
still missing for a given task type.
"""

from __future__ import annotations

import time
from typing import ClassVar

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class ToolCallRecord(BaseModel):
    """Record of a single tool invocation."""

    tool_name: str
    timestamp: float = Field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Recommended tool sets per task type
# ---------------------------------------------------------------------------

TASK_TOOL_MAP: dict[str, dict[str, list[str]]] = {
    "feature": {
        "required": ["tapps_score_file", "tapps_quality_gate"],
        "recommended": ["tapps_security_scan"],
        "optional": ["tapps_checklist"],
    },
    "bugfix": {
        "required": ["tapps_score_file"],
        "recommended": ["tapps_quality_gate", "tapps_security_scan"],
        "optional": ["tapps_checklist"],
    },
    "refactor": {
        "required": ["tapps_score_file", "tapps_quality_gate"],
        "recommended": [],
        "optional": ["tapps_security_scan", "tapps_checklist"],
    },
    "security": {
        "required": ["tapps_security_scan", "tapps_quality_gate"],
        "recommended": ["tapps_score_file"],
        "optional": ["tapps_checklist"],
    },
    "review": {
        "required": ["tapps_score_file", "tapps_security_scan", "tapps_quality_gate"],
        "recommended": ["tapps_checklist"],
        "optional": [],
    },
}


class ChecklistResult(BaseModel):
    """Result of checklist evaluation."""

    task_type: str = Field(description="The task type evaluated.")
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
    complete: bool = Field(default=False, description="All required tools have been called.")
    total_calls: int = Field(default=0, description="Total tool calls this session.")


class CallTracker:
    """Server-side call log for the current session."""

    _calls: ClassVar[list[ToolCallRecord]] = []

    @classmethod
    def record(cls, tool_name: str) -> None:
        """Record a tool invocation."""
        cls._calls.append(ToolCallRecord(tool_name=tool_name))

    @classmethod
    def get_called_tools(cls) -> set[str]:
        """Return the set of unique tool names called."""
        return {c.tool_name for c in cls._calls}

    @classmethod
    def total_calls(cls) -> int:
        """Return total number of calls."""
        return len(cls._calls)

    @classmethod
    def reset(cls) -> None:
        """Reset the call log (for testing)."""
        cls._calls.clear()

    @classmethod
    def evaluate(cls, task_type: str = "review") -> ChecklistResult:
        """Evaluate the checklist for a given task type."""
        tool_map = TASK_TOOL_MAP.get(task_type, TASK_TOOL_MAP["review"])
        called = cls.get_called_tools()
        required = tool_map.get("required", [])
        recommended = tool_map.get("recommended", [])
        optional = tool_map.get("optional", [])

        missing_required = [t for t in required if t not in called]
        missing_recommended = [t for t in recommended if t not in called]
        missing_optional = [t for t in optional if t not in called]

        return ChecklistResult(
            task_type=task_type,
            called=sorted(called),
            missing_required=missing_required,
            missing_recommended=missing_recommended,
            missing_optional=missing_optional,
            complete=len(missing_required) == 0,
            total_calls=cls.total_calls(),
        )
