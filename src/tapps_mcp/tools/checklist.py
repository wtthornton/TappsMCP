"""Session-level tool call tracking for ``tapps_checklist``.

Tracks which TappsMCP tools have been called during the current server
session so that ``tapps_checklist`` can report what's been done and what's
still missing for a given task type.
"""

from __future__ import annotations

import threading
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
# Short reasons for checklist hints (so the LLM knows what to do)
# ---------------------------------------------------------------------------

TOOL_REASONS: dict[str, str] = {
    "tapps_server_info": "Call at session start to discover server version and installed checkers.",
    "tapps_session_start": (
        "Call as the FIRST action in every session (combines server_info + project_profile)."
    ),
    "tapps_score_file": (
        "Score the file for quality; use quick=True during edits, full before done."
    ),
    "tapps_security_scan": "Run a dedicated security scan (bandit + secrets) on the file.",
    "tapps_quality_gate": (
        "Call before declaring work complete to ensure the file passes the quality preset."
    ),
    "tapps_lookup_docs": "Look up library docs before using an API to avoid hallucinated usage.",
    "tapps_validate_config": (
        "Validate Dockerfile, docker-compose, or infra config against best practices."
    ),
    "tapps_consult_expert": (
        "Ask a domain expert when making security, testing, or architecture decisions."
    ),
    "tapps_list_experts": "List available expert domains before consulting one.",
    "tapps_checklist": (
        "Call before declaring work complete to verify no required steps were skipped."
    ),
    "tapps_validate_changed": (
        "Batch-validate all changed Python files (score + gate + security) before declaring done."
    ),
    "tapps_quick_check": (
        "Quick score + gate + security in one call. Minimum check after editing any Python file."
    ),
}


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


class ChecklistHint(BaseModel):
    """A missing tool with a short reason for the LLM."""

    tool: str = Field(description="Tool name to call.")
    reason: str = Field(description="Why to call it / what to do next.")


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
    complete: bool = Field(default=False, description="All required tools have been called.")
    total_calls: int = Field(default=0, description="Total tool calls this session.")


class CallTracker:
    """Server-side call log for the current session."""

    _calls: ClassVar[list[ToolCallRecord]] = []
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def record(cls, tool_name: str) -> None:
        """Record a tool invocation."""
        with cls._lock:
            cls._calls.append(ToolCallRecord(tool_name=tool_name))

    @classmethod
    def get_called_tools(cls) -> set[str]:
        """Return the set of unique tool names called."""
        with cls._lock:
            return {c.tool_name for c in cls._calls}

    @classmethod
    def total_calls(cls) -> int:
        """Return total number of calls."""
        with cls._lock:
            return len(cls._calls)

    @classmethod
    def reset(cls) -> None:
        """Reset the call log (for testing)."""
        with cls._lock:
            cls._calls.clear()

    @classmethod
    def evaluate(cls, task_type: str = "review") -> ChecklistResult:
        """Evaluate the checklist for a given task type."""
        tool_map = TASK_TOOL_MAP.get(task_type, TASK_TOOL_MAP["review"])
        if not isinstance(tool_map, dict):
            tool_map = TASK_TOOL_MAP["review"]
        with cls._lock:
            called = {c.tool_name for c in cls._calls}
            call_count = len(cls._calls)
        required = tool_map.get("required", [])
        recommended = tool_map.get("recommended", [])
        optional = tool_map.get("optional", [])
        if not isinstance(required, list):
            required = []
        if not isinstance(recommended, list):
            recommended = []
        if not isinstance(optional, list):
            optional = []

        # Composite tools satisfy individual requirements
        effective = set(called)
        if "tapps_quick_check" in called or "tapps_validate_changed" in called:
            effective.update({"tapps_score_file", "tapps_quality_gate", "tapps_security_scan"})

        missing_required = [t for t in required if t not in effective]
        missing_recommended = [t for t in recommended if t not in effective]
        missing_optional = [t for t in optional if t not in effective]

        def hints(tools: list[str]) -> list[ChecklistHint]:
            return [ChecklistHint(tool=t, reason=TOOL_REASONS.get(t, f"Call {t}.")) for t in tools]

        return ChecklistResult(
            task_type=task_type,
            called=sorted(called),
            missing_required=missing_required,
            missing_recommended=missing_recommended,
            missing_optional=missing_optional,
            missing_required_hints=hints(missing_required),
            missing_recommended_hints=hints(missing_recommended),
            missing_optional_hints=hints(missing_optional),
            complete=len(missing_required) == 0,
            total_calls=call_count,
        )
