"""Session-level tool call tracking for ``tapps_checklist``.

Tracks which TappsMCP tools have been called during the current server
session so that ``tapps_checklist`` can report what's been done and what's
still missing for a given task type.

Call records are persisted to a JSONL file so that state survives
server restarts within the same session.

The task-type tool maps, the shared models, epic markdown validation, and
the TDD stage checks live in sibling ``checklist_*`` modules (TAP-5733) and
are re-exported here — see the re-export block at the bottom of this file.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, ClassVar

import structlog

from tapps_mcp.tools.checklist_epic import (
    CrossFileSummary,
    EpicChecklistResult,
    EpicFinding,
    EpicStoryInfo,
    EpicValidation,
    validate_epic_markdown,
)
from tapps_mcp.tools.checklist_maps import (
    _ENGAGEMENT_TOOL_MAP,
    _TOOL_EQUIVALENTS,
    KNOWN_TASK_TYPES,
    TASK_TOOL_MAP,
    TASK_TOOL_MAP_HIGH,
    TASK_TOOL_MAP_LOW,
    TASK_TOOL_MAP_MEDIUM,
    TASK_TYPE_REASONS,
    TOOL_REASONS,
    _get_merged_engagement_maps,
    invalidate_engagement_maps_cache,
)
from tapps_mcp.tools.checklist_models import (
    ChecklistHint,
    ChecklistResult,
    ToolCallRecord,
)
from tapps_mcp.tools.checklist_tdd import (
    TDDCheckResult,
    TDDStageCheck,
    _check_compile_time_red,
    _check_coverage,
    _check_git_commits,
    check_tdd_stages,
)

logger = structlog.get_logger(__name__)


async def _get_git_context(
    commit_sha: str = "", project_root: Path | None = None
) -> dict[str, Any] | None:
    """Retrieve current git context (branch, HEAD SHA, dirty status).

    Returns None if git is unavailable or not in a git repo.
    If *commit_sha* is provided, it overrides the auto-detected HEAD SHA.
    TAP-6388: *project_root* pins ``cwd`` for every git command so the
    context reflects the TARGET project, not the server process's own cwd.
    """
    from tapps_mcp.tools.subprocess_runner import run_command_async

    cwd = str(project_root) if project_root is not None else None

    try:
        branch_result = await run_command_async(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            timeout=5,
        )
        if branch_result.returncode != 0:
            return None
        branch = branch_result.stdout.strip()

        sha_short_result = await run_command_async(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            timeout=5,
        )
        sha_full_result = await run_command_async(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            timeout=5,
        )
        dirty_result = await run_command_async(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            timeout=5,
        )

        head_sha = sha_short_result.stdout.strip() if sha_short_result.returncode == 0 else ""
        head_sha_full = sha_full_result.stdout.strip() if sha_full_result.returncode == 0 else ""
        dirty = bool(dirty_result.stdout.strip()) if dirty_result.returncode == 0 else False

        if commit_sha.strip():
            head_sha = commit_sha.strip()[:8]
            head_sha_full = commit_sha.strip()
    except Exception:
        logger.debug("git_context_retrieval_failed", exc_info=True)
        return None
    return {
        "branch": branch,
        "head_sha": head_sha,
        "head_sha_full": head_sha_full,
        "dirty": dirty,
    }


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
            msg = f"Unknown task_type {task_type!r}; expected one of {sorted(KNOWN_TASK_TYPES)}"
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
    for primary, implied in _TOOL_EQUIVALENTS.items():
        if primary in base_successful:
            effective.update(implied)
    return effective


def _build_hints(tools: list[str]) -> list[ChecklistHint]:
    """Build hint objects for missing tools."""
    return [ChecklistHint(tool=t, reason=TOOL_REASONS.get(t, f"Call {t}.")) for t in tools]


def _partition_by_effective(
    names: list[str], effective: set[str]
) -> tuple[list[str], list[str]]:
    """Split *names* into (missing, satisfied) against the effective tool set."""
    missing = [t for t in names if t not in effective]
    satisfied = [t for t in names if t in effective]
    return missing, satisfied


def _demote_unavailable_server_tools(
    missing_required: list[str],
    missing_optional: list[str],
    project_root: Path | None,
) -> tuple[list[str], list[str], list[ChecklistHint]]:
    """Move required tools whose NLT server is disabled into optional.

    A tool the caller has no way to invoke is not a checklist failure, so it
    is demoted rather than reported as missing. *missing_optional* is appended
    to in place, matching the pre-split behaviour.

    Returns (still_required, server_unavailable, extra_optional_hints).
    """
    if project_root is None:
        return missing_required, [], []

    from tapps_mcp.distribution.nlt_mcp_config import (
        NLT_TOOL_SERVER,
        _load_enabled_mcp_servers,
        list_nlt_server_ids_in_config,
        tool_unavailable_reason,
        tools_on_enabled_nlt_servers,
    )

    available = tools_on_enabled_nlt_servers(project_root)
    try:
        enabled_servers = frozenset(
            list_nlt_server_ids_in_config(_load_enabled_mcp_servers(project_root))
        )
    except Exception:
        enabled_servers = frozenset({"nlt-build"})

    server_unavailable: list[str] = []
    still_required: list[str] = []
    for tool in missing_required:
        if tool in NLT_TOOL_SERVER and tool not in available:
            server_unavailable.append(tool)
            if tool not in missing_optional:
                missing_optional.append(tool)
        else:
            still_required.append(tool)

    hints = [
        ChecklistHint(
            tool=t,
            reason=tool_unavailable_reason(t, enabled_servers)
            or f"{t} requires another NLT server",
        )
        for t in server_unavailable
    ]
    return still_required, server_unavailable, hints


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
            cls._calls.clear()
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
            # Adopt pre-session records (empty session_id) so early tool calls
            # are not dropped after begin_session.
            for rec in cls._calls:
                if not rec.session_id:
                    rec.session_id = sid
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
        return [c for c in cls._calls if c.session_id == cls._active_session_id or not c.session_id]

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
            # Reload JSONL so tools recorded by other NLT MCP processes
            # (nlt-release-ship, nlt-linear-issues, …) satisfy this checklist.
            if cls._persist_path is not None:
                cls._calls.clear()
                cls._load_persisted()
            sub = cls._filtered_calls()
            call_count = len(sub)
        states = _call_states_ordered(sub)
        base_ok = _base_successful_tools(states, require_success=require_success)
        called_sorted = sorted(states.keys())
        effective = _compute_effective_tools(base_ok)

        missing_required, sat_req = _partition_by_effective(required, effective)
        missing_recommended, sat_rec = _partition_by_effective(recommended, effective)
        missing_optional, sat_opt = _partition_by_effective(optional, effective)

        missing_required, server_unavailable, missing_optional_hints_extra = (
            _demote_unavailable_server_tools(missing_required, missing_optional, project_root)
        )

        return ChecklistResult(
            task_type=task_type,
            task_type_hint=TASK_TYPE_REASONS.get(resolved_key, ""),
            resolved_policy_task_type=resolved_key,
            policy_fallback=policy_fallback,
            checklist_policy_version=policy_version,
            called=called_sorted,
            missing_required=missing_required,
            missing_recommended=missing_recommended,
            missing_optional=missing_optional,
            missing_required_hints=_build_hints(missing_required),
            missing_recommended_hints=_build_hints(missing_recommended),
            missing_optional_hints=_build_hints(missing_optional) + missing_optional_hints_extra,
            server_unavailable_tools=server_unavailable,
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
        **eval_kwargs: Any,
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
                msg = f"Epic file not found: {resolved} (resolved from {file_path})"
                raise FileNotFoundError(msg)
            content = resolved.read_text(encoding="utf-8")
            validation = validate_epic_markdown(content, epic_file_path=resolved)
        payload = base.model_dump()
        payload["epic_validation"] = validation
        return EpicChecklistResult(**payload)


# ---------------------------------------------------------------------------
# Re-exports (TAP-5733)
#
# These names lived here before the split. Tests and callers import them from
# this module, and three of them are monkeypatched by dotted path
# (``tools.checklist.check_tdd_stages``, ``…._get_git_context``,
# ``….CallTracker.evaluate``), so the names must stay bound here.
# ---------------------------------------------------------------------------

__all__ = [
    "KNOWN_TASK_TYPES",
    "TASK_TOOL_MAP",
    "TASK_TOOL_MAP_HIGH",
    "TASK_TOOL_MAP_LOW",
    "TASK_TOOL_MAP_MEDIUM",
    "TASK_TYPE_REASONS",
    "TOOL_REASONS",
    "_ENGAGEMENT_TOOL_MAP",
    "_TOOL_EQUIVALENTS",
    "CallTracker",
    "ChecklistHint",
    "ChecklistResult",
    "CrossFileSummary",
    "EpicChecklistResult",
    "EpicFinding",
    "EpicStoryInfo",
    "EpicValidation",
    "TDDCheckResult",
    "TDDStageCheck",
    "ToolCallRecord",
    "_check_compile_time_red",
    "_check_coverage",
    "_check_git_commits",
    "_get_git_context",
    "_get_merged_engagement_maps",
    "check_tdd_stages",
    "invalidate_engagement_maps_cache",
    "validate_epic_markdown",
]
