"""Session-level tool call tracking for ``tapps_checklist``.

Tracks which TappsMCP tools have been called during the current server
session so that ``tapps_checklist`` can report what's been done and what's
still missing for a given task type.

Call records are persisted to a JSONL file so that state survives
server restarts within the same session.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from pathlib import Path

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
        "Call as the FIRST action in every session (server info only; call tapps_project_profile when you need project context)."
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
    "tapps_research": (
        "Expert + docs in one call. Use instead of consult_expert + lookup_docs when you need both domain guidance and library documentation."
    ),
    "tapps_list_experts": "List available expert domains before consulting one.",
    "tapps_checklist": (
        "Call before declaring work complete to verify no required steps were skipped."
    ),
    "tapps_validate_changed": (
        "Batch-validate all changed Python files (score + gate; security when quick=False or security_depth='full') before declaring done."
    ),
    "tapps_quick_check": (
        "Quick score + gate + security in one call. Minimum check after editing any Python file."
    ),
    "tapps_dead_code": (
        "Scan for unused functions, classes, imports, and variables. Use during refactoring."
    ),
    "tapps_dependency_scan": (
        "Scan dependencies for known vulnerabilities (CVEs). Use before releases."
    ),
    "tapps_dependency_graph": (
        "Analyze import graph for circular dependencies and coupling. Use before major refactoring."
    ),
    "tapps_set_engagement_level": (
        "When the user requests to change enforcement intensity"
        " (e.g. 'set tappsmcp to high' or 'make checks optional')."
    ),
    "tapps_manage_experts": (
        "Manage business experts: list, add, remove, scaffold knowledge dirs, validate."
    ),
}


# ---------------------------------------------------------------------------
# Recommended tool sets per task type (medium = default)
# ---------------------------------------------------------------------------

TASK_TOOL_MAP: dict[str, dict[str, list[str]]] = {
    "feature": {
        "required": ["tapps_score_file", "tapps_quality_gate"],
        "recommended": ["tapps_security_scan", "tapps_memory"],
        "optional": ["tapps_checklist"],
    },
    "bugfix": {
        "required": ["tapps_score_file"],
        "recommended": ["tapps_quality_gate", "tapps_security_scan"],
        "optional": ["tapps_checklist", "tapps_memory"],
    },
    "refactor": {
        "required": ["tapps_score_file", "tapps_quality_gate"],
        "recommended": ["tapps_dead_code", "tapps_dependency_graph", "tapps_memory"],
        "optional": ["tapps_security_scan", "tapps_checklist"],
    },
    "security": {
        "required": ["tapps_security_scan", "tapps_quality_gate"],
        "recommended": ["tapps_score_file", "tapps_dependency_scan"],
        "optional": ["tapps_checklist", "tapps_memory"],
    },
    "review": {
        "required": ["tapps_score_file", "tapps_security_scan", "tapps_quality_gate"],
        "recommended": ["tapps_checklist", "tapps_dead_code"],
        "optional": ["tapps_dependency_scan", "tapps_dependency_graph", "tapps_memory"],
    },
}

# High engagement: more tools required (stricter)
TASK_TOOL_MAP_HIGH: dict[str, dict[str, list[str]]] = {
    "feature": {
        "required": ["tapps_score_file", "tapps_quality_gate", "tapps_security_scan"],
        "recommended": ["tapps_validate_changed", "tapps_checklist"],
        "optional": [],
    },
    "bugfix": {
        "required": ["tapps_score_file", "tapps_quality_gate"],
        "recommended": ["tapps_security_scan", "tapps_checklist"],
        "optional": [],
    },
    "refactor": {
        "required": ["tapps_score_file", "tapps_quality_gate", "tapps_dead_code"],
        "recommended": ["tapps_dependency_graph", "tapps_security_scan", "tapps_checklist"],
        "optional": [],
    },
    "security": {
        "required": ["tapps_security_scan", "tapps_quality_gate", "tapps_score_file"],
        "recommended": ["tapps_dependency_scan", "tapps_checklist"],
        "optional": [],
    },
    "review": {
        "required": [
            "tapps_score_file", "tapps_security_scan",
            "tapps_quality_gate", "tapps_checklist",
        ],
        "recommended": ["tapps_dead_code", "tapps_validate_changed"],
        "optional": ["tapps_dependency_scan", "tapps_dependency_graph"],
    },
}

# Low engagement: fewer tools required (lighter)
TASK_TOOL_MAP_LOW: dict[str, dict[str, list[str]]] = {
    "feature": {
        "required": ["tapps_quality_gate"],
        "recommended": ["tapps_score_file", "tapps_quick_check"],
        "optional": ["tapps_security_scan", "tapps_checklist"],
    },
    "bugfix": {
        "required": [],
        "recommended": ["tapps_score_file", "tapps_quality_gate"],
        "optional": ["tapps_security_scan", "tapps_checklist"],
    },
    "refactor": {
        "required": ["tapps_quality_gate"],
        "recommended": ["tapps_score_file", "tapps_dead_code"],
        "optional": ["tapps_dependency_graph", "tapps_security_scan", "tapps_checklist"],
    },
    "security": {
        "required": ["tapps_security_scan", "tapps_quality_gate"],
        "recommended": ["tapps_score_file"],
        "optional": ["tapps_dependency_scan", "tapps_checklist"],
    },
    "review": {
        "required": ["tapps_quality_gate"],
        "recommended": ["tapps_score_file", "tapps_security_scan", "tapps_checklist"],
        "optional": ["tapps_dead_code", "tapps_dependency_scan", "tapps_dependency_graph"],
    },
}

# Alias for medium (same as TASK_TOOL_MAP)
TASK_TOOL_MAP_MEDIUM: dict[str, dict[str, list[str]]] = TASK_TOOL_MAP

_ENGAGEMENT_TOOL_MAP: dict[str, dict[str, dict[str, list[str]]]] = {
    "high": TASK_TOOL_MAP_HIGH,
    "medium": TASK_TOOL_MAP_MEDIUM,
    "low": TASK_TOOL_MAP_LOW,
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


# ---------------------------------------------------------------------------
# Checklist helpers (extracted for CC reduction)
# ---------------------------------------------------------------------------


def _resolve_task_tool_map(
    task_type: str,
    engagement_level: str | None,
) -> dict[str, Any]:
    """Resolve the task-specific tool map for the given engagement level."""
    if engagement_level is None:
        from tapps_core.config.settings import load_settings

        engagement_level = load_settings().llm_engagement_level
    if engagement_level not in _ENGAGEMENT_TOOL_MAP:
        engagement_level = "medium"
    task_maps = _ENGAGEMENT_TOOL_MAP[engagement_level]
    tool_map = task_maps.get(task_type, task_maps["review"])
    if not isinstance(tool_map, dict):
        tool_map = task_maps["review"]
    return tool_map


def _get_tool_lists(
    tool_map: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """Extract and validate required/recommended/optional lists from a tool map."""
    required = tool_map.get("required", [])
    recommended = tool_map.get("recommended", [])
    optional = tool_map.get("optional", [])
    if not isinstance(required, list):
        required = []
    if not isinstance(recommended, list):
        recommended = []
    if not isinstance(optional, list):
        optional = []
    return required, recommended, optional


def _compute_effective_tools(called: set[str]) -> set[str]:
    """Expand called tools with composite tool coverage."""
    effective = set(called)
    if "tapps_quick_check" in called or "tapps_validate_changed" in called:
        effective.update({"tapps_score_file", "tapps_quality_gate", "tapps_security_scan"})
    return effective


def _build_hints(tools: list[str]) -> list[ChecklistHint]:
    """Build hint objects for missing tools."""
    return [ChecklistHint(tool=t, reason=TOOL_REASONS.get(t, f"Call {t}.")) for t in tools]


class CallTracker:
    """Server-side call log for the current session.

    Call records are persisted to a JSONL file so that state survives
    server restarts within the same session.
    """

    _calls: ClassVar[list[ToolCallRecord]] = []
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _persist_path: ClassVar[Path | None] = None

    @classmethod
    def set_persist_path(cls, path: Path) -> None:
        """Configure persistence file and load existing records."""
        with cls._lock:
            cls._persist_path = path
            cls._load_persisted()

    @classmethod
    def _load_persisted(cls) -> None:
        """Load previously persisted records (called under lock)."""
        if cls._persist_path is None or not cls._persist_path.exists():
            return
        try:
            text = cls._persist_path.read_text(encoding="utf-8")
            for line in text.strip().splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    cls._calls.append(
                        ToolCallRecord(
                            tool_name=data["tool_name"],
                            timestamp=data.get("timestamp", time.time()),
                        )
                    )
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
        except OSError:
            logger.debug("checklist_persist_load_failed", exc_info=True)

    @classmethod
    def _persist_record(cls, record: ToolCallRecord) -> None:
        """Append a single record to the persist file (called under lock)."""
        if cls._persist_path is None:
            return
        try:
            cls._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with cls._persist_path.open("a", encoding="utf-8") as fh:
                payload = {"tool_name": record.tool_name, "timestamp": record.timestamp}
                fh.write(json.dumps(payload) + "\n")
        except OSError:
            logger.debug("checklist_persist_write_failed", exc_info=True)

    @classmethod
    def record(cls, tool_name: str) -> None:
        """Record a tool invocation."""
        with cls._lock:
            rec = ToolCallRecord(tool_name=tool_name)
            cls._calls.append(rec)
            cls._persist_record(rec)

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
            if cls._persist_path is not None and cls._persist_path.exists():
                with contextlib.suppress(OSError):
                    cls._persist_path.unlink()

    @classmethod
    def evaluate(
        cls,
        task_type: str = "review",
        engagement_level: str | None = None,
    ) -> ChecklistResult:
        """Evaluate the checklist for a given task type and engagement level.

        When *engagement_level* is None, it is read from
        ``load_settings().llm_engagement_level`` (high/medium/low).
        """
        tool_map = _resolve_task_tool_map(task_type, engagement_level)
        required, recommended, optional = _get_tool_lists(tool_map)

        with cls._lock:
            called = {c.tool_name for c in cls._calls}
            call_count = len(cls._calls)

        effective = _compute_effective_tools(called)
        missing_required = [t for t in required if t not in effective]
        missing_recommended = [t for t in recommended if t not in effective]
        missing_optional = [t for t in optional if t not in effective]

        return ChecklistResult(
            task_type=task_type,
            called=sorted(called),
            missing_required=missing_required,
            missing_recommended=missing_recommended,
            missing_optional=missing_optional,
            missing_required_hints=_build_hints(missing_required),
            missing_recommended_hints=_build_hints(missing_recommended),
            missing_optional_hints=_build_hints(missing_optional),
            complete=len(missing_required) == 0,
            total_calls=call_count,
        )
