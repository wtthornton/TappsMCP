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
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


async def _get_git_context(commit_sha: str = "") -> dict[str, Any] | None:
    """Retrieve current git context (branch, HEAD SHA, dirty status).

    Returns None if git is unavailable or not in a git repo.
    If *commit_sha* is provided, it overrides the auto-detected HEAD SHA.
    """
    from tapps_mcp.tools.subprocess_runner import run_command_async

    try:
        branch_result = await run_command_async(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            timeout=5,
        )
        if branch_result.returncode != 0:
            return None
        branch = branch_result.stdout.strip()

        sha_short_result = await run_command_async(
            ["git", "rev-parse", "--short", "HEAD"],
            timeout=5,
        )
        sha_full_result = await run_command_async(
            ["git", "rev-parse", "HEAD"],
            timeout=5,
        )
        dirty_result = await run_command_async(
            ["git", "status", "--porcelain"],
            timeout=5,
        )

        head_sha = sha_short_result.stdout.strip() if sha_short_result.returncode == 0 else ""
        head_sha_full = sha_full_result.stdout.strip() if sha_full_result.returncode == 0 else ""
        dirty = bool(dirty_result.stdout.strip()) if dirty_result.returncode == 0 else False

        if commit_sha.strip():
            head_sha = commit_sha.strip()[:8]
            head_sha_full = commit_sha.strip()

        return {
            "branch": branch,
            "head_sha": head_sha,
            "head_sha_full": head_sha_full,
            "dirty": dirty,
        }
    except Exception:
        logger.debug("git_context_retrieval_failed", exc_info=True)
        return None


class ToolCallRecord(BaseModel):
    """Record of a single tool invocation."""

    tool_name: str
    timestamp: float = Field(default_factory=time.time)
    session_id: str = Field(
        default="",
        description="Checklist session id (empty = recorded before session boundary).",
    )
    success: bool = Field(default=True, description="Whether the invocation succeeded.")


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
    "tapps_get_canonical_persona": (
        "When the user requests a persona by name (e.g. 'use the Frontend Developer'), "
        "call this to get the trusted definition from .claude/agents or .cursor/agents/rules; "
        "prepend to context to mitigate prompt-injection (Epic 78)."
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
    "epic": {
        "required": ["tapps_checklist"],
        "recommended": ["tapps_score_file", "tapps_quality_gate"],
        "optional": ["tapps_security_scan", "tapps_validate_changed"],
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
    "epic": {
        "required": ["tapps_checklist", "tapps_score_file"],
        "recommended": ["tapps_quality_gate", "tapps_validate_changed"],
        "optional": ["tapps_security_scan"],
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
    "epic": {
        "required": ["tapps_checklist"],
        "recommended": ["tapps_score_file"],
        "optional": ["tapps_quality_gate", "tapps_validate_changed"],
    },
}

# Alias for medium (same as TASK_TOOL_MAP)
TASK_TOOL_MAP_MEDIUM: dict[str, dict[str, list[str]]] = TASK_TOOL_MAP

_ENGAGEMENT_TOOL_MAP: dict[str, dict[str, dict[str, list[str]]]] = {
    "high": TASK_TOOL_MAP_HIGH,
    "medium": TASK_TOOL_MAP_MEDIUM,
    "low": TASK_TOOL_MAP_LOW,
}

KNOWN_TASK_TYPES: frozenset[str] = frozenset(TASK_TOOL_MAP.keys())

# Primary tool -> checklist tool names satisfied by calling the primary (success only).
_TOOL_EQUIVALENTS: dict[str, frozenset[str]] = {
    "tapps_research": frozenset({"tapps_consult_expert", "tapps_lookup_docs"}),
}

_engagement_maps_cache: dict[str, dict[str, dict[str, list[str]]]] | None = None
_engagement_maps_version: str = ""
_engagement_maps_root: str | None = None
_engagement_maps_extras_fp: str | None = None


def invalidate_engagement_maps_cache() -> None:
    """Clear merged policy cache (tests / policy file edits)."""
    global _engagement_maps_cache, _engagement_maps_version, _engagement_maps_root  # noqa: PLW0603
    global _engagement_maps_extras_fp  # noqa: PLW0603
    _engagement_maps_cache = None
    _engagement_maps_version = ""
    _engagement_maps_root = None
    _engagement_maps_extras_fp = None


def _get_merged_engagement_maps(
    project_root: Path | None,
) -> tuple[dict[str, dict[str, dict[str, list[str]]]], str]:
    from tapps_mcp.tools.checklist_policy import (
        compute_policy_version,
        load_checklist_policy_extras,
        merge_engagement_maps,
    )

    global _engagement_maps_cache, _engagement_maps_version, _engagement_maps_root  # noqa: PLW0603
    global _engagement_maps_extras_fp  # noqa: PLW0603
    root = (project_root or Path.cwd()).resolve()
    extras = load_checklist_policy_extras(root)
    fp = extras.content_fingerprint if extras else ""
    key = str(root)
    if (
        _engagement_maps_cache is not None
        and _engagement_maps_root == key
        and _engagement_maps_extras_fp == fp
    ):
        return _engagement_maps_cache, _engagement_maps_version
    merged = merge_engagement_maps(_ENGAGEMENT_TOOL_MAP, extras)
    ver = compute_policy_version(merged, extras)
    _engagement_maps_cache = merged
    _engagement_maps_version = ver
    _engagement_maps_root = key
    _engagement_maps_extras_fp = fp
    return merged, ver


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
    complete: bool = Field(default=False, description="All required tools have been called.")
    total_calls: int = Field(default=0, description="Total tool calls this session.")


# ---------------------------------------------------------------------------
# Checklist helpers (extracted for CC reduction)
# ---------------------------------------------------------------------------


def _resolve_task_tool_map(
    task_type: str,
    engagement_level: str | None,
    project_root: Path | None,
    *,
    strict_unknown_task_type: bool,
) -> tuple[dict[str, Any], str, str, str, bool]:
    """Return tool_map, engagement_level, policy_version, resolved_key, policy_fallback."""
    merged, ver = _get_merged_engagement_maps(project_root)
    if engagement_level is None:
        from tapps_core.config.settings import load_settings

        engagement_level = load_settings().llm_engagement_level
    if engagement_level not in merged:
        engagement_level = "medium"
    task_maps = merged[engagement_level]
    policy_fallback = False
    resolved_key = task_type
    if task_type not in KNOWN_TASK_TYPES:
        if strict_unknown_task_type:
            msg = (
                f"Unknown task_type {task_type!r}; "
                f"expected one of {sorted(KNOWN_TASK_TYPES)}"
            )
            raise ValueError(msg)
        resolved_key = "review"
        policy_fallback = True
    tool_map = task_maps.get(resolved_key, task_maps["review"])
    if not isinstance(tool_map, dict):
        tool_map = task_maps["review"]
    return tool_map, engagement_level, ver, resolved_key, policy_fallback


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


def _call_states_ordered(calls: list[ToolCallRecord]) -> dict[str, bool]:
    """Latest success flag per tool name (chronological order)."""
    last_success: dict[str, bool] = {}
    for c in sorted(calls, key=lambda x: x.timestamp):
        last_success[c.tool_name] = c.success
    return last_success


def _base_successful_tools(states: dict[str, bool], *, require_success: bool) -> set[str]:
    if require_success:
        return {t for t, ok in states.items() if ok}
    return set(states.keys())


def _compute_effective_tools(base_successful: set[str]) -> set[str]:
    """Expand successful tools with composite / equivalent coverage."""
    effective = set(base_successful)
    if "tapps_quick_check" in base_successful or "tapps_validate_changed" in base_successful:
        effective.update({"tapps_score_file", "tapps_quality_gate", "tapps_security_scan"})
    for primary, implied in _TOOL_EQUIVALENTS.items():
        if primary in base_successful:
            effective.update(implied)
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
    _active_session_id: ClassVar[str | None] = None

    @classmethod
    def _lock_file_path(cls) -> Path | None:
        if cls._persist_path is None:
            return None
        return cls._persist_path.with_name(cls._persist_path.name + ".lock")

    @classmethod
    def _active_session_marker(cls) -> Path | None:
        if cls._persist_path is None:
            return None
        return cls._persist_path.parent / "checklist_active_session"

    @classmethod
    def set_persist_path(cls, path: Path) -> None:
        """Configure persistence file and load existing records."""
        with cls._lock:
            cls._persist_path = Path(path)
            cls._load_active_session_id()
            cls._load_persisted()

    @classmethod
    def _load_active_session_id(cls) -> None:
        marker = cls._active_session_marker()
        if marker is None or not marker.is_file():
            cls._active_session_id = None
            return
        try:
            text = marker.read_text(encoding="utf-8").strip()
            cls._active_session_id = text or None
        except OSError:
            cls._active_session_id = None

    @classmethod
    def _persist_active_session(cls) -> None:
        marker = cls._active_session_marker()
        if marker is None or cls._active_session_id is None:
            return
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(cls._active_session_id, encoding="utf-8")
        except OSError:
            logger.debug("checklist_active_session_write_failed", exc_info=True)

    @classmethod
    def begin_session(cls, session_id: str | None = None) -> str:
        """Start a new checklist session boundary (call from tapps_session_start)."""
        sid = session_id or uuid.uuid4().hex[:16]
        with cls._lock:
            cls._active_session_id = sid
            cls._persist_active_session()
        return sid

    @classmethod
    def get_active_checklist_session_id(cls) -> str | None:
        with cls._lock:
            return cls._active_session_id

    @classmethod
    def _filtered_calls(cls) -> list[ToolCallRecord]:
        if cls._active_session_id is None:
            return list(cls._calls)
        return [c for c in cls._calls if c.session_id == cls._active_session_id]

    @classmethod
    def _load_persisted(cls) -> None:
        """Load previously persisted records (called under lock)."""
        if cls._persist_path is None or not cls._persist_path.exists():
            return
        from filelock import FileLock

        lock_p = cls._lock_file_path()
        if lock_p is None:
            return
        try:
            with FileLock(str(lock_p), timeout=10):
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
                            session_id=data.get("session_id", ""),
                            success=data.get("success", True),
                        )
                    )
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
        except Exception:
            logger.debug("checklist_persist_load_failed", exc_info=True)

    @classmethod
    def _persist_record(cls, record: ToolCallRecord) -> None:
        """Append a single record to the persist file (called under lock)."""
        if cls._persist_path is None:
            return
        from filelock import FileLock

        lock_p = cls._lock_file_path()
        if lock_p is None:
            return
        try:
            cls._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(str(lock_p), timeout=10):
                payload = {
                    "tool_name": record.tool_name,
                    "timestamp": record.timestamp,
                    "session_id": record.session_id,
                    "success": record.success,
                }
                with cls._persist_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(payload) + "\n")
        except Exception:
            logger.debug("checklist_persist_write_failed", exc_info=True)

    @classmethod
    def record(cls, tool_name: str, *, success: bool = True) -> None:
        """Record a tool invocation."""
        with cls._lock:
            sid = cls._active_session_id or ""
            rec = ToolCallRecord(tool_name=tool_name, session_id=sid, success=success)
            cls._calls.append(rec)
            cls._persist_record(rec)

    @classmethod
    def get_called_tools(cls) -> set[str]:
        """Return the set of unique tool names called (active checklist session)."""
        with cls._lock:
            return {c.tool_name for c in cls._filtered_calls()}

    @classmethod
    def total_calls(cls) -> int:
        """Return total number of calls (active checklist session)."""
        with cls._lock:
            return len(cls._filtered_calls())

    @classmethod
    def reset(cls) -> None:
        """Reset the call log (for testing)."""
        invalidate_engagement_maps_cache()
        with cls._lock:
            cls._calls.clear()
            cls._active_session_id = None
            if cls._persist_path is not None:
                if cls._persist_path.exists():
                    with contextlib.suppress(OSError):
                        cls._persist_path.unlink()
                lf = cls._lock_file_path()
                if lf is not None and lf.exists():
                    with contextlib.suppress(OSError):
                        lf.unlink()
                marker = cls._active_session_marker()
                if marker is not None and marker.exists():
                    with contextlib.suppress(OSError):
                        marker.unlink()

    @classmethod
    def evaluate(
        cls,
        task_type: str = "review",
        engagement_level: str | None = None,
        *,
        require_success: bool = False,
        strict_unknown_task_type: bool = False,
        project_root: Path | None = None,
    ) -> ChecklistResult:
        """Evaluate the checklist for a given task type and engagement level.

        When *engagement_level* is None, it is read from
        ``load_settings().llm_engagement_level`` (high/medium/low).
        """
        tool_map, _elvl, policy_version, resolved_key, policy_fallback = _resolve_task_tool_map(
            task_type,
            engagement_level,
            project_root,
            strict_unknown_task_type=strict_unknown_task_type,
        )
        required, recommended, optional = _get_tool_lists(tool_map)

        with cls._lock:
            sub = cls._filtered_calls()
            call_count = len(sub)
        states = _call_states_ordered(sub)
        base_ok = _base_successful_tools(states, require_success=require_success)
        called_sorted = sorted(states.keys())
        effective = _compute_effective_tools(base_ok)
        missing_required = [t for t in required if t not in effective]
        missing_recommended = [t for t in recommended if t not in effective]
        missing_optional = [t for t in optional if t not in effective]
        sat_req = [t for t in required if t in effective]
        sat_rec = [t for t in recommended if t in effective]
        sat_opt = [t for t in optional if t in effective]

        return ChecklistResult(
            task_type=task_type,
            resolved_policy_task_type=resolved_key,
            policy_fallback=policy_fallback,
            checklist_policy_version=policy_version,
            called=called_sorted,
            missing_required=missing_required,
            missing_recommended=missing_recommended,
            missing_optional=missing_optional,
            missing_required_hints=_build_hints(missing_required),
            missing_recommended_hints=_build_hints(missing_recommended),
            missing_optional_hints=_build_hints(missing_optional),
            required_tool_names=list(required),
            satisfied_required_tools=sat_req,
            recommended_tool_names=list(recommended),
            satisfied_recommended_tools=sat_rec,
            optional_tool_names=list(optional),
            satisfied_optional_tools=sat_opt,
            complete=len(missing_required) == 0,
            total_calls=call_count,
        )

    @classmethod
    def evaluate_epic(
        cls,
        file_path: str | None = None,
        engagement_level: str | None = None,
        **eval_kwargs: Any,  # noqa: ANN401
    ) -> EpicChecklistResult:
        """Evaluate the epic checklist, optionally validating an epic file.

        When *file_path* is provided, the markdown file is parsed and
        structural validation is performed. When not provided, only the
        checklist template items are returned.
        """
        project_root = eval_kwargs.get("project_root")
        base = cls.evaluate(
            "epic",
            engagement_level=engagement_level,
            **eval_kwargs,
        )
        validation: EpicValidation | None = None
        if file_path is not None:
            resolved = Path(file_path)
            if not resolved.is_absolute() and project_root:
                resolved = Path(project_root) / resolved
            if not resolved.exists():
                msg = (
                    f"Epic file not found: {resolved}"
                    f" (resolved from {file_path})"
                )
                raise FileNotFoundError(msg)
            content = resolved.read_text(encoding="utf-8")
            validation = validate_epic_markdown(content, epic_file_path=resolved)
        payload = base.model_dump()
        payload["epic_validation"] = validation
        return EpicChecklistResult(**payload)


# ---------------------------------------------------------------------------
# Epic validation models
# ---------------------------------------------------------------------------

# Valid point ranges per size label
_SIZE_POINT_RANGES: dict[str, tuple[int, int]] = {
    "S": (1, 2),
    "M": (3, 5),
    "L": (8, 13),
}


class EpicStoryInfo(BaseModel):
    """Parsed information about a single story in an epic."""

    story_id: str = Field(description="Story identifier (e.g. '1.1').")
    title: str = Field(default="", description="Story title text.")
    points: int | None = Field(default=None, description="Story points.")
    size: str | None = Field(default=None, description="Size label (S/M/L).")
    priority: str | None = Field(default=None, description="Priority (P0-P4).")
    files: list[str] = Field(default_factory=list, description="Files listed.")
    has_acceptance_criteria: bool = Field(
        default=False, description="Whether AC section exists."
    )
    has_tasks: bool = Field(default=False, description="Whether Tasks section exists.")
    linked_file: str | None = Field(
        default=None, description="File path from a markdown link in the heading or table row."
    )


class EpicFinding(BaseModel):
    """A single validation finding for an epic document."""

    severity: str = Field(description="'error' or 'warning'.")
    message: str = Field(description="Human-readable finding description.")
    story_id: str | None = Field(
        default=None, description="Story ID if finding is story-specific."
    )


class CrossFileSummary(BaseModel):
    """Aggregate completeness metrics from linked story files."""

    total_stories: int = Field(default=0, description="Stories with linked files.")
    stories_with_files: int = Field(default=0, description="Stories that have linked files.")
    files_found: int = Field(default=0, description="Linked files that exist on disk.")
    files_missing: int = Field(default=0, description="Linked files not found.")
    with_acceptance_criteria: int = Field(
        default=0, description="Stories whose linked file has an AC section."
    )
    with_tasks: int = Field(
        default=0, description="Stories whose linked file has a Tasks section."
    )
    with_definition_of_done: int = Field(
        default=0, description="Stories whose linked file has a DoD section."
    )
    summary: str = Field(default="", description="Human-readable summary line.")


class EpicValidation(BaseModel):
    """Result of structural validation of an epic markdown file."""

    sections_found: list[str] = Field(
        default_factory=list, description="Top-level sections found."
    )
    stories: list[EpicStoryInfo] = Field(
        default_factory=list, description="Parsed stories."
    )
    files_affected_entries: list[str] = Field(
        default_factory=list,
        description="Files listed in a files-affected table.",
    )
    findings: list[EpicFinding] = Field(
        default_factory=list, description="Validation findings."
    )
    valid: bool = Field(
        default=True,
        description="True when no error-severity findings exist.",
    )
    cross_file_summary: CrossFileSummary | None = Field(
        default=None,
        description="Cross-file story completeness metrics (when linked files are validated).",
    )


class EpicChecklistResult(ChecklistResult):
    """Extended checklist result with epic-specific validation."""

    epic_validation: EpicValidation | None = Field(
        default=None,
        description="Epic structural validation (present when file_path provided).",
    )


# ---------------------------------------------------------------------------
# Epic markdown parsing
# ---------------------------------------------------------------------------

# Regex for story headings: "### Story X.Y: Title" or "### X.Y — Title"
_STORY_HEADING_RE = re.compile(
    r"^###\s+(?:Story\s+)?(\d+\.\d+)\s*[:\u2014-]\s*(.*)",
    re.MULTILINE,
)

# Linked heading: "### [X.Y](path) -- Title"
_LINKED_HEADING_RE = re.compile(
    r"^###\s+\[(\d+\.\d+)\]\(([^)]+)\)\s*[:\u2014-]+\s*(.*)",
    re.MULTILINE,
)

# Table-linked story: "| ID | [Title](file.md) | ... |"
_TABLE_STORY_RE = re.compile(
    r"^\|\s*(\S+)\s*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|(.*)$",
    re.MULTILINE,
)

# Points pattern: "**Points:** N" or "Points: N"
_POINTS_RE = re.compile(r"\*{0,2}Points:?\*{0,2}:?\s*(\d+)", re.IGNORECASE)

# Size pattern: "**Size:** S" or "Size: M"
_SIZE_RE = re.compile(r"\*{0,2}Size:?\*{0,2}:?\s*([SML])\b", re.IGNORECASE)

# Priority pattern: "**Priority:** P1" or "Priority: P2"
_PRIORITY_RE = re.compile(r"\*{0,2}Priority:?\*{0,2}:?\s*(P\d)\b", re.IGNORECASE)

# Files pattern: lines starting with "- `path`" in a Files section
_FILE_ENTRY_RE = re.compile(r"^-\s+`([^`]+)`", re.MULTILINE)

# Table row for files-affected: "| `path` | ..."
_FILES_TABLE_ROW_RE = re.compile(r"^\|\s*`([^`]+)`", re.MULTILINE)


def _parse_table_size_priority(remaining_cols: str) -> tuple[str | None, str | None]:
    """Extract size and priority from remaining table columns.

    Args:
        remaining_cols: The portion of the table row after the link column.

    Returns:
        Tuple of (size, priority) — each may be None.
    """
    cells = [c.strip() for c in remaining_cols.split("|") if c.strip()]
    size: str | None = None
    priority: str | None = None
    size_re = re.compile(r"^(XS|XL|S|M|L)$", re.IGNORECASE)
    prio_re = re.compile(r"^(P[0-4])$", re.IGNORECASE)
    for cell in cells:
        if not size and size_re.match(cell):
            size = cell.upper()
        elif not priority and prio_re.match(cell):
            priority = cell.upper()
    return size, priority


def _parse_epic_markdown(content: str) -> tuple[
    list[str],
    list[EpicStoryInfo],
    list[str],
]:
    """Parse an epic markdown file and extract structural information.

    Returns:
        Tuple of (section_headings, stories, files_affected_entries).
    """
    # Extract top-level (##) section headings
    sections = re.findall(r"^##\s+(.+)", content, re.MULTILINE)
    section_names = [s.strip() for s in sections]

    # --- 1. Try classic story headings ---
    story_matches = list(_STORY_HEADING_RE.finditer(content))
    stories: list[EpicStoryInfo] = []

    for i, match in enumerate(story_matches):
        story_id = match.group(1)
        title = match.group(2).strip()

        start = match.end()
        end = story_matches[i + 1].start() if i + 1 < len(story_matches) else len(content)
        block = content[start:end]

        points_m = _POINTS_RE.search(block)
        size_m = _SIZE_RE.search(block)
        priority_m = _PRIORITY_RE.search(block)
        files = _extract_story_files(block)
        has_ac = _has_subsection(block, "acceptance criteria")
        has_tasks = _has_subsection(block, "tasks")

        stories.append(
            EpicStoryInfo(
                story_id=story_id,
                title=title,
                points=int(points_m.group(1)) if points_m else None,
                size=size_m.group(1).upper() if size_m else None,
                priority=priority_m.group(1).upper() if priority_m else None,
                files=files,
                has_acceptance_criteria=has_ac,
                has_tasks=has_tasks,
            )
        )

    # --- 2. Try linked headings: ### [X.Y](path) -- Title ---
    linked_matches = list(_LINKED_HEADING_RE.finditer(content))
    # Avoid duplicates — only add if story_id not already captured
    existing_ids = {s.story_id for s in stories}

    for i, match in enumerate(linked_matches):
        story_id = match.group(1)
        if story_id in existing_ids:
            continue
        linked_file = match.group(2).strip()
        title = match.group(3).strip()

        start = match.end()
        end = (
            linked_matches[i + 1].start()
            if i + 1 < len(linked_matches)
            else len(content)
        )
        block = content[start:end]

        points_m = _POINTS_RE.search(block)
        size_m = _SIZE_RE.search(block)
        priority_m = _PRIORITY_RE.search(block)
        files = _extract_story_files(block)
        has_ac = _has_subsection(block, "acceptance criteria")
        has_tasks = _has_subsection(block, "tasks")

        stories.append(
            EpicStoryInfo(
                story_id=story_id,
                title=title,
                linked_file=linked_file,
                points=int(points_m.group(1)) if points_m else None,
                size=size_m.group(1).upper() if size_m else None,
                priority=priority_m.group(1).upper() if priority_m else None,
                files=files,
                has_acceptance_criteria=has_ac,
                has_tasks=has_tasks,
            )
        )
        existing_ids.add(story_id)

    # --- 3. Try table-linked stories if no stories found yet ---
    if not stories:
        table_matches = list(_TABLE_STORY_RE.finditer(content))
        for match in table_matches:
            story_id = match.group(1)
            title = match.group(2).strip()
            linked_file = match.group(3).strip()
            remaining = match.group(4)

            size, priority = _parse_table_size_priority(remaining)

            stories.append(
                EpicStoryInfo(
                    story_id=story_id,
                    title=title,
                    linked_file=linked_file,
                    size=size,
                    priority=priority,
                )
            )

    # Extract files-affected table entries
    files_affected = _extract_files_affected(content)

    return section_names, stories, files_affected


def _extract_story_files(block: str) -> list[str]:
    """Extract file paths from a story block's Files section."""
    # Find "**Files:**" or "#### Files" section
    files_match = re.search(
        r"(?:\*\*Files:?\*\*|####\s+Files)\s*\n((?:\s*-\s+`[^`]+`.*\n?)+)",
        block,
        re.IGNORECASE,
    )
    if not files_match:
        return []
    files_text = files_match.group(1)
    return _FILE_ENTRY_RE.findall(files_text)


def _has_subsection(block: str, name: str) -> bool:
    """Check whether a block contains a sub-section with the given name."""
    pattern = re.compile(
        rf"(?:^####?\s+{re.escape(name)}|^\*\*{re.escape(name)}:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )
    return bool(pattern.search(block))


def _extract_files_affected(content: str) -> list[str]:
    """Extract file paths from a files-affected table."""
    # Look for a "Files Affected" or "Files-Affected" section
    section_match = re.search(
        r"(?:^##\s+Files[- ]Affected|^\*\*Files[- ]Affected:?\*\*)",
        content,
        re.IGNORECASE | re.MULTILINE,
    )
    if not section_match:
        return []
    start = section_match.end()
    # Find next section heading
    next_section = re.search(r"^##\s+", content[start:], re.MULTILINE)
    end = start + next_section.start() if next_section else len(content)
    table_text = content[start:end]
    return _FILES_TABLE_ROW_RE.findall(table_text)


# ---------------------------------------------------------------------------
# Epic structural validation
# ---------------------------------------------------------------------------

_REQUIRED_SECTIONS = {"Goal", "Acceptance Criteria", "Stories"}


def _check_required_sections(
    section_names: list[str],
    findings: list[EpicFinding],
) -> None:
    """Check that required top-level sections exist."""
    normalized = {s.lower().strip() for s in section_names}
    for req in _REQUIRED_SECTIONS:
        if req.lower() not in normalized:
            findings.append(
                EpicFinding(
                    severity="error",
                    message=f"Missing required section: '{req}'",
                )
            )


def _check_story_completeness(
    stories: list[EpicStoryInfo],
    findings: list[EpicFinding],
) -> None:
    """Check each story for required sub-fields."""
    for story in stories:
        if story.points is None:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Points",
                    story_id=story.story_id,
                )
            )
        if story.size is None:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Size",
                    story_id=story.story_id,
                )
            )
        if story.priority is None:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Priority",
                    story_id=story.story_id,
                )
            )
        if not story.files:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Files list",
                    story_id=story.story_id,
                )
            )
        if not story.has_acceptance_criteria:
            findings.append(
                EpicFinding(
                    severity="error",
                    message=f"Story {story.story_id} missing Acceptance Criteria",
                    story_id=story.story_id,
                )
            )
        if not story.has_tasks:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} missing Tasks",
                    story_id=story.story_id,
                )
            )


def _check_point_size_consistency(
    stories: list[EpicStoryInfo],
    findings: list[EpicFinding],
) -> None:
    """Flag stories where points don't match the expected range for the size."""
    for story in stories:
        if story.points is None or story.size is None:
            continue
        expected = _SIZE_POINT_RANGES.get(story.size)
        if expected is None:
            continue
        lo, hi = expected
        if not (lo <= story.points <= hi):
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=(
                        f"Story {story.story_id} size {story.size} "
                        f"expects {lo}-{hi} points but has {story.points}"
                    ),
                    story_id=story.story_id,
                )
            )


def _check_dependency_cycles(
    content: str,
    findings: list[EpicFinding],
) -> None:
    """Check for cycles in story dependency references.

    Looks for patterns like "Dependencies: Story X.Y" and builds
    a simple DAG to detect cycles.
    """
    dep_re = re.compile(
        r"(?:depends\s+on|dependencies?:?|requires)\s+(?:story\s+)?(\d+\.\d+)",
        re.IGNORECASE,
    )
    # Build adjacency from story blocks
    story_blocks = list(_STORY_HEADING_RE.finditer(content))
    graph: dict[str, list[str]] = {}

    for i, match in enumerate(story_blocks):
        story_id = match.group(1)
        start = match.end()
        end = story_blocks[i + 1].start() if i + 1 < len(story_blocks) else len(content)
        block = content[start:end]
        deps = dep_re.findall(block)
        if deps:
            graph[story_id] = deps

    # Simple cycle detection via DFS
    visited: set[str] = set()
    in_stack: set[str] = set()

    def _dfs(node: str) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for dep in graph.get(node, []):
            if _dfs(dep):
                return True
        in_stack.discard(node)
        return False

    for node in graph:
        if _dfs(node):
            findings.append(
                EpicFinding(
                    severity="error",
                    message=f"Dependency cycle detected involving story {node}",
                    story_id=node,
                )
            )
            break  # One cycle finding is sufficient


def _check_files_table_coverage(
    stories: list[EpicStoryInfo],
    files_affected: list[str],
    findings: list[EpicFinding],
) -> None:
    """Check that files in stories appear in the files-affected table."""
    if not files_affected:
        return  # No table present, skip check
    table_set = set(files_affected)
    for story in stories:
        for f in story.files:
            if f not in table_set:
                findings.append(
                    EpicFinding(
                        severity="warning",
                        message=(
                            f"Story {story.story_id} references '{f}' "
                            f"not found in files-affected table"
                        ),
                        story_id=story.story_id,
                    )
                )


def _check_story_file_structure(
    content: str,
) -> tuple[bool, bool, bool, int | None, str | None]:
    """Check a story file for structural sections.

    Returns:
        Tuple of (has_ac, has_tasks, has_dod, points, size).
    """
    ac_re = re.compile(
        r"(?:^##?\s+Acceptance\s+Criteria|^\*\*Acceptance\s+Criteria:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )
    tasks_re = re.compile(
        r"(?:^##?\s+Tasks?\b|^\*\*Tasks?:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )
    dod_re = re.compile(
        r"(?:^##?\s+Definition\s+of\s+Done|^\*\*Definition\s+of\s+Done:?\*\*)",
        re.IGNORECASE | re.MULTILINE,
    )

    has_ac = bool(ac_re.search(content))
    has_tasks = bool(tasks_re.search(content))
    has_dod = bool(dod_re.search(content))

    pm = _POINTS_RE.search(content)
    points = int(pm.group(1)) if pm else None

    sm = _SIZE_RE.search(content)
    size = sm.group(1).upper() if sm else None

    return has_ac, has_tasks, has_dod, points, size


def _validate_linked_stories(
    stories: list[EpicStoryInfo],
    findings: list[EpicFinding],
    epic_file_path: Path,
) -> CrossFileSummary | None:
    """Follow linked story files and validate their structure.

    Args:
        stories: Parsed stories (may have ``linked_file`` set).
        findings: Findings list to append to.
        epic_file_path: Path to the epic file (links are resolved relative to its parent).

    Returns:
        A ``CrossFileSummary`` or ``None`` if no stories have linked files.
    """
    epic_dir = epic_file_path.parent
    stories_with_files = [s for s in stories if s.linked_file]

    if not stories_with_files:
        return None

    files_found = 0
    files_missing = 0
    with_ac = 0
    with_tasks = 0
    with_dod = 0
    seen_paths: set[str] = set()

    for story in stories_with_files:
        linked = story.linked_file
        if linked is None:  # pragma: no cover — filtered above
            continue

        resolved = (epic_dir / linked).resolve()
        canonical = str(resolved)

        # Guard against circular/self references
        if canonical in seen_paths:
            continue
        seen_paths.add(canonical)
        if resolved == epic_file_path.resolve():
            continue

        if not resolved.is_file():
            files_missing += 1
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} linked file not found: {linked}",
                    story_id=story.story_id,
                )
            )
            continue

        files_found += 1
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            findings.append(
                EpicFinding(
                    severity="warning",
                    message=f"Story {story.story_id} cannot read linked file: {linked}",
                    story_id=story.story_id,
                )
            )
            continue

        has_ac, has_tasks_sec, has_dod, points, size = _check_story_file_structure(content)

        # Merge with inline metadata (linked file wins if present)
        if has_ac:
            story.has_acceptance_criteria = True
            with_ac += 1
        elif not story.has_acceptance_criteria:
            findings.append(
                EpicFinding(
                    severity="info",
                    message=(
                        f"Story {story.story_id} linked file missing Acceptance Criteria"
                    ),
                    story_id=story.story_id,
                )
            )

        if has_tasks_sec:
            story.has_tasks = True
            with_tasks += 1
        elif not story.has_tasks:
            findings.append(
                EpicFinding(
                    severity="info",
                    message=f"Story {story.story_id} linked file missing Tasks section",
                    story_id=story.story_id,
                )
            )

        if has_dod:
            with_dod += 1

        if points is not None and story.points is None:
            story.points = points
        if size is not None and story.size is None:
            story.size = size

    total = len(stories_with_files)
    parts = [
        f"{total} stories",
        f"{files_found}/{total} files found",
        f"{with_ac}/{total} have AC",
        f"{with_tasks}/{total} have tasks",
    ]
    return CrossFileSummary(
        total_stories=total,
        stories_with_files=total,
        files_found=files_found,
        files_missing=files_missing,
        with_acceptance_criteria=with_ac,
        with_tasks=with_tasks,
        with_definition_of_done=with_dod,
        summary=", ".join(parts),
    )


def validate_epic_markdown(
    content: str,
    *,
    epic_file_path: Path | None = None,
    validate_linked_stories: bool = True,
) -> EpicValidation:
    """Validate an epic markdown document for structural completeness.

    Args:
        content: The epic markdown content.
        epic_file_path: Path to the epic file on disk.  Required for
            cross-file story validation (resolving linked story files).
        validate_linked_stories: When True and ``epic_file_path`` is given,
            follow linked story files and validate their structure.

    Returns an ``EpicValidation`` with all findings.
    """
    section_names, stories, files_affected = _parse_epic_markdown(content)
    findings: list[EpicFinding] = []

    _check_required_sections(section_names, findings)

    cross_file_summary: CrossFileSummary | None = None

    if not stories:
        findings.append(
            EpicFinding(
                severity="error",
                message=(
                    "No stories found (expected '### Story X.Y:', "
                    "'### [X.Y](path) --', or table-linked rows)"
                ),
            )
        )
    else:
        _check_story_completeness(stories, findings)
        _check_point_size_consistency(stories, findings)
        _check_files_table_coverage(stories, files_affected, findings)

        # Cross-file story validation
        if validate_linked_stories and epic_file_path is not None:
            cross_file_summary = _validate_linked_stories(
                stories, findings, epic_file_path,
            )

    _check_dependency_cycles(content, findings)

    has_errors = any(f.severity == "error" for f in findings)

    return EpicValidation(
        sections_found=section_names,
        stories=stories,
        files_affected_entries=files_affected,
        findings=findings,
        valid=not has_errors,
        cross_file_summary=cross_file_summary,
    )
