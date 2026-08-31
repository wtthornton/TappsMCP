"""Checklist tool handler for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.

This module contains:
- tapps_checklist: per-task TAPPS pipeline verification

``tapps_checklist`` itself is a thin orchestrator; each of its response-building
steps (auto-run, git context, tdd stages, usage gaps, structured output, state
marker) is factored into its own ``_gather_*`` / ``_apply_*`` / ``_attach_*``
helper so the handler's cyclomatic complexity stays low even as the response
payload grows.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

import structlog
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server_helpers import error_response, success_response
from tapps_mcp.tools.nothing_to_gate import attach_nothing_to_gate

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from mcp.server.fastmcp import FastMCP

    from tapps_mcp.tools.checklist import ChecklistResult

logger = structlog.get_logger(__name__)

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_FINISH_TASK_TIP_INCOMPLETE = (
    "Run /tapps-finish-task to bundle validate + checklist + optional memory "
    "save into one call instead of fixing the missing tools by hand."
)
_FINISH_TASK_TIP_COMPLETE = (
    "TIP: Next time, invoke /tapps-finish-task to run validate + checklist + "
    "optional memory save in one shot."
)
_AUTO_RUNNABLE_TOOLS = frozenset(
    {
        "tapps_score_file",
        "tapps_quality_gate",
        "tapps_security_scan",
        "tapps_validate_changed",
        "tapps_quick_check",
    }
)
_BLOCKING_USAGE_GAPS = frozenset({"contract_assertions_unverified", "creator_verifier_skipped"})


# ===== Response formatting helpers =====


def _finish_task_tip(result: ChecklistResult) -> str:
    """TAP-983: Surface /tapps-finish-task suggestion in non-markdown formats."""
    return _FINISH_TASK_TIP_INCOMPLETE if not result.complete else _FINISH_TASK_TIP_COMPLETE


def _checklist_json_format(
    result: ChecklistResult,
    auto_run_results: dict[str, Any],
    *,
    checklist_session_id: str | None,
    trace_hint: dict[str, str] | None,
) -> dict[str, Any]:
    """Build structured JSON output with computed counts and next_steps for checklist."""
    next_steps: list[str] = [h.reason for h in result.missing_required_hints]
    next_steps.extend(h.reason for h in result.missing_recommended_hints)
    next_steps.append(_finish_task_tip(result))

    data: dict[str, Any] = {
        "task_type": result.task_type,
        "resolved_policy_task_type": result.resolved_policy_task_type,
        "policy_fallback": result.policy_fallback,
        "checklist_policy_version": result.checklist_policy_version,
        "checklist_session_id": checklist_session_id,
        "otel_trace_hint": trace_hint,
        "complete": result.complete,
        "total_calls": result.total_calls,
        "required": {
            "total": (
                len(result.required_tool_names)
                if result.required_tool_names
                else len(result.missing_required) + len(result.satisfied_required_tools)
            ),
            "satisfied": result.satisfied_required_tools,
            "missing": result.missing_required,
        },
        "recommended": {
            "total": (
                len(result.recommended_tool_names)
                if result.recommended_tool_names
                else len(result.missing_recommended) + len(result.satisfied_recommended_tools)
            ),
            "satisfied": result.satisfied_recommended_tools,
            "missing": result.missing_recommended,
        },
        "optional": {
            "total": (
                len(result.optional_tool_names)
                if result.optional_tool_names
                else len(result.missing_optional) + len(result.satisfied_optional_tools)
            ),
            "satisfied": result.satisfied_optional_tools,
            "missing": result.missing_optional,
        },
        "priority_actions": result.missing_required[:3] if result.missing_required else [],
        "next_steps": next_steps,
        "full": result.model_dump(),
    }
    attach_nothing_to_gate(data, result)
    if auto_run_results:
        data["auto_run_results"] = auto_run_results
    return data


def _checklist_compact_format(
    result: ChecklistResult,
    auto_run_results: dict[str, Any],
    *,
    checklist_session_id: str | None,
    trace_hint: dict[str, str] | None,
) -> dict[str, Any]:
    """Build a short 1-2 line compact summary for checklist."""
    req_tot = len(result.required_tool_names)
    if req_tot == 0:
        req_tot = len(result.missing_required) + len(result.satisfied_required_tools)
    req_sat = len(result.satisfied_required_tools)
    parts = [
        f"complete={result.complete}",
        f"required {req_sat}/{req_tot} satisfied",
    ]
    if result.missing_required:
        missing_names = ", ".join(result.missing_required)
        parts.append(f"{len(result.missing_required)} required missing ({missing_names})")
    if result.missing_recommended:
        missing_names = ", ".join(result.missing_recommended)
        parts.append(f"{len(result.missing_recommended)} recommended missing ({missing_names})")
    summary = f"Checklist {result.task_type}: {', '.join(parts)}"

    next_steps: list[str] = [h.reason for h in result.missing_required_hints]
    next_steps.extend(h.reason for h in result.missing_recommended_hints)
    next_steps.append(_finish_task_tip(result))

    data: dict[str, Any] = {
        "summary": summary,
        "complete": result.complete,
        "task_type": result.task_type,
        "resolved_policy_task_type": result.resolved_policy_task_type,
        "checklist_policy_version": result.checklist_policy_version,
        "checklist_session_id": checklist_session_id,
        "otel_trace_hint": trace_hint,
        "total_calls": result.total_calls,
        "next_steps": next_steps,
        "full": result.model_dump(),
    }
    attach_nothing_to_gate(data, result)
    if auto_run_results:
        data["auto_run_results"] = auto_run_results
    return data


def _format_checklist_response(
    output_format: str,
    result: ChecklistResult,
    auto_run_results: dict[str, Any],
    *,
    session_id: str | None,
    trace_hint: dict[str, str] | None,
) -> dict[str, Any]:
    """Dispatch to the json/compact/markdown response builder."""
    if output_format == "json":
        return _checklist_json_format(
            result, auto_run_results, checklist_session_id=session_id, trace_hint=trace_hint
        )
    if output_format == "compact":
        return _checklist_compact_format(
            result, auto_run_results, checklist_session_id=session_id, trace_hint=trace_hint
        )
    resp_data = result.model_dump()
    if auto_run_results:
        resp_data["auto_run_results"] = auto_run_results
    return resp_data


def _optional_otel_trace_hint() -> dict[str, str] | None:
    tid = (os.environ.get("TAPPS_OTEL_TRACE_ID") or "").strip()
    sid = (os.environ.get("TAPPS_OTEL_SPAN_ID") or "").strip()
    if not tid and not sid:
        return None
    return {"trace_id": tid, "span_id": sid}


# ===== tapps_checklist step helpers =====


def _revoke_uncredited_autorun(result: ChecklistResult, candidates: set[str]) -> list[str]:
    """Un-satisfy the tools an evidence-free auto-run would otherwise pay for.

    ``tapps_validate_changed`` records its own call whether or not it found a
    file to gate, and ``tapps_score_file`` / ``tapps_quality_gate`` ride along as
    equivalents. When the run validated 0 files that credit is a bookkeeping
    artifact — nothing was checked — so the checklist must not read as complete
    off it (TAP-6586).

    Tools TAP-6606 already moved into ``not_applicable_tools`` are left alone:
    there, 0 files is the honest terminal answer rather than a gap.
    """
    from tapps_mcp.tools.checklist import _build_hints

    not_applicable = set(result.not_applicable_tools or [])
    revoked = sorted(t for t in candidates if t not in not_applicable)
    if not revoked:
        return []
    missing = list(result.missing_required)
    missing.extend(t for t in revoked if t not in missing)
    result.missing_required = missing
    result.missing_required_hints = _build_hints(missing)
    revoked_set = set(revoked)
    result.satisfied_required_tools = [
        t for t in result.satisfied_required_tools if t not in revoked_set
    ]
    result.complete = False
    return revoked


async def _run_auto_run(
    auto_run: bool,
    result: ChecklistResult,
    eval_checklist: Callable[[], ChecklistResult],
    settings: Any,
    file_paths: str = "",
) -> tuple[ChecklistResult, dict[str, Any]]:
    """Run the missing validation here and re-evaluate.

    On by default (TAP-6586). A remediation the agent has to remember to switch
    on is the same skippable step the completion gate has been recording as a
    miss; running it from the checklist deletes the step instead of reminding
    about it.

    ``file_paths`` scopes the auto-run ``tapps_validate_changed`` call to the
    caller's known changed files (e.g. ``tapps_pipeline``, which already has
    them). Empty (default) falls back to the unscoped git-wide auto-detect —
    the same behavior direct ``tapps_checklist`` callers had before TAP-6738.
    """
    auto_run_results: dict[str, Any] = {}
    if not (auto_run and result.missing_required):
        return result, auto_run_results

    needs_validate = set(result.missing_required) & _AUTO_RUNNABLE_TOOLS
    files_validated = 0
    if needs_validate:
        try:
            from tapps_mcp.server_pipeline_tools import tapps_validate_changed

            vc_result = await tapps_validate_changed(
                file_paths=file_paths, preset=settings.quality_preset
            )
            vc_data = vc_result.get("data", {})
            files_validated = int(vc_data.get("files_validated", 0) or 0)
            auto_run_results["validate_changed"] = {
                "success": vc_result.get("success", False),
                "files_validated": files_validated,
                "all_gates_passed": vc_data.get("all_gates_passed", False),
            }
            # Epic 66.2: Add validation_note when 0 files validated
            if files_validated == 0:
                auto_run_results["validate_changed"]["validation_note"] = (
                    "Validation ran but 0 files validated. "
                    "Consider tapps_quick_check on changed files."
                )
        except Exception as exc:
            # A run that threw produced no evidence either — same zero-file path.
            files_validated = 0
            auto_run_results["validate_changed"] = {
                "success": False,
                "error": str(exc),
            }

    # Re-evaluate after auto-running
    result = eval_checklist()
    if needs_validate and files_validated == 0:
        revoked = _revoke_uncredited_autorun(result, needs_validate)
        if revoked:
            entry = auto_run_results.setdefault("validate_changed", {})
            entry["credited"] = False
            entry["uncredited_tools"] = revoked
    return result, auto_run_results


async def _gather_git_context(commit_sha: str, project_root: Path) -> dict[str, Any] | None:
    try:
        from tapps_mcp.tools.checklist import _get_git_context

        return await _get_git_context(commit_sha=commit_sha, project_root=project_root)
    except Exception:
        return None


async def _gather_tdd_results(tdd: bool, settings: Any) -> dict[str, Any] | None:
    """TDD stage validation (TAP-476)."""
    if not tdd:
        return None
    try:
        from tapps_mcp.tools.checklist import check_tdd_stages

        tdd_result = await check_tdd_stages(repo_root=settings.project_root)
        return tdd_result.model_dump()
    except Exception as exc:
        return {"error": str(exc), "passed": False, "checks": []}


def _apply_usage_gaps(
    resp_data: dict[str, Any], result: ChecklistResult, settings: Any, task_type: str
) -> None:
    """Inline the usage gap-report and hard-block feature/review on blocking gaps.

    TAP-5543/5548: feature/review cannot complete with contract/verifier gaps.
    """
    try:
        from pathlib import Path as _Path

        from tapps_mcp.tools.usage import compute_gaps

        usage = compute_gaps(_Path(settings.project_root).expanduser().resolve())
        usage_gaps_list = list(usage.get("gaps", []))
        resp_data["usage_gaps"] = {
            "gaps": usage_gaps_list,
            "recommendations": usage.get("recommendations", []),
            "libraries_without_lookup": usage.get("libraries_without_lookup", []),
            "rolling_gate_skip_rate": usage.get("rolling_stats", {}).get("gate_skip_rate", 0.0),
            "rolling_loops": usage.get("rolling_stats", {}).get("loops", 0),
        }
        if task_type in {"feature", "review"} and _BLOCKING_USAGE_GAPS.intersection(
            usage_gaps_list
        ):
            resp_data["complete"] = False
            missing = list(resp_data.get("missing_required") or [])
            for gap in sorted(_BLOCKING_USAGE_GAPS.intersection(usage_gaps_list)):
                if gap not in missing:
                    missing.append(gap)
            resp_data["missing_required"] = missing
            # Keep result in sync for structuredContent + checklist state marker.
            result.complete = False
            result.missing_required = missing
    except Exception:
        logger.debug("usage_gaps_inline_failed", exc_info=True)


def _apply_validation_note(resp_data: dict[str, Any], auto_run_results: dict[str, Any]) -> None:
    """Epic 66.2: Surface validation_note in next_steps."""
    if not auto_run_results.get("validate_changed", {}).get("validation_note"):
        return
    next_steps = resp_data.get("next_steps", [])
    if not isinstance(next_steps, list):
        next_steps = []
    next_steps.append(
        "tapps_validate_changed ran but validated 0 files. "
        "Use tapps_quick_check on individual changed files as fallback."
    )
    resp_data["next_steps"] = next_steps


async def _gather_prior_outcome(settings: Any) -> dict[str, Any] | None:
    """TAP-2000: best-effort prior outcome from brain."""
    try:
        from tapps_mcp.server_helpers import fetch_prior_checklist_outcome

        return await fetch_prior_checklist_outcome(settings.project_root)
    except Exception:
        logger.debug("prior_checklist_outcome_failed", exc_info=True)
        return None


def _attach_checklist_structured_output(
    resp: dict[str, Any],
    result: ChecklistResult,
    session_id: str | None,
    auto_run_results: dict[str, Any],
    output_format: str,
) -> None:
    """Attach structured output (markdown/json only - compact is already minimal)."""
    if output_format == "compact":
        return
    try:
        from tapps_mcp.common.output_schemas import ChecklistOutput

        structured = ChecklistOutput(
            task_type=result.task_type,
            complete=result.complete,
            called=result.called,
            missing_required=result.missing_required,
            missing_recommended=result.missing_recommended,
            total_calls=result.total_calls,
            checklist_policy_version=result.checklist_policy_version or None,
            resolved_policy_task_type=result.resolved_policy_task_type or None,
            checklist_session_id=session_id,
            auto_run_results=auto_run_results or None,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.debug("structured_output_failed: tapps_checklist", exc_info=True)


def _write_checklist_marker(settings: Any, result: ChecklistResult) -> None:
    """TAP-2000: emit checklist_outcome brain event (advisory; hook reads dropped)."""
    try:
        from tapps_mcp.server_helpers import write_checklist_state_marker

        write_checklist_state_marker(
            settings.project_root,
            complete=result.complete,
            missing_required=list(result.missing_required),
        )
    except Exception:
        logger.debug("checklist_state_marker_write_failed", exc_info=True)


def _checklist_fallback_response(task_type: str, start: int) -> dict[str, Any]:
    """Response used when tapps_mcp.tools.checklist is unavailable."""
    from tapps_mcp.server import _record_execution, _with_nudges

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_checklist", start)
    fallback_data = {
        "task_type": task_type,
        "called": [],
        "missing_required": [],
        "missing_recommended": [],
        "missing_optional": [],
        "missing_required_hints": [],
        "missing_recommended_hints": [],
        "missing_optional_hints": [],
        "complete": False,
        "total_calls": 0,
        "checklist_unavailable": True,
        "message": (
            "Module tapps_mcp.tools.checklist is not available. "
            "Use tapps_quality_gate and tapps_security_scan for verification."
        ),
    }
    resp = success_response("tapps_checklist", elapsed_ms, fallback_data)
    return _with_nudges("tapps_checklist", resp, {"complete": False})


# ===== Tool handler =====


async def tapps_checklist(
    task_type: str = "review",
    auto_run: bool = True,
    output_format: str = "markdown",
    commit_sha: str = "",
    epic_file_path: str = "",
    reset_checklist_session: bool = False,
    tdd: bool = False,
    file_paths: str = "",
) -> dict[str, Any]:
    """Verifies the per-task TAPPS pipeline ran end-to-end and returns a
    markdown/JSON/compact report of which required tools fired vs were
    skipped, with remediation hints.

    Call this as the very last step before declaring work complete —
    after ``tapps_validate_changed`` has passed but before announcing
    the task done. By default the checklist runs any missing required
    validation itself and re-evaluates, so you do not have to backfill
    by hand; an auto-run that validates 0 files credits nothing. For
    epic-level validation against a markdown epic file, set
    ``task_type='epic'`` and pass ``epic_file_path``.

    Args:
        task_type: One of ``"feature"``, ``"bugfix"``, ``"refactor"``,
            ``"security"``, ``"review"`` (default), ``"document"``, or
            ``"epic"``. Each type has its own required-tools matrix; e.g.
            ``security`` requires a security scan, ``document`` requires
            ``validate_changed`` with judges for PDF/HTML output work,
            ``epic`` requires the markdown structural check.
        auto_run: When ``True`` (default, TAP-6586), the checklist runs
            any missing required tools itself
            (``tapps_validate_changed``, etc.) and re-evaluates rather
            than returning a fail the caller has to remember to fix. The
            gap is not papered over: a run that validates 0 files leaves
            those tools missing and the checklist incomplete. Pass
            ``False`` to see the raw pre-remediation verdict.
        output_format: ``"markdown"`` (default, full table for human
            review), ``"json"`` (machine-readable counts and per-tool
            status), or ``"compact"`` (one or two lines suitable for
            commit-message context).
        commit_sha: Git SHA to embed in the report. Empty (default)
            auto-detects ``HEAD``.
        epic_file_path: Optional path to a local ``EPIC-N.md`` file (legacy).
            When set, the checklist runs epic-template structural
            validation in addition to tool-coverage checks. Pair with
            ``task_type='epic'``. Prefer Linear (TAP-####) as the epic source of record.
        reset_checklist_session: Rotate the session id and start a
            fresh checklist window before evaluating. Use only from
            long-lived server processes that span multiple tasks.
        tdd: Add TDD stage checks (RED/GREEN/REFACTOR commit pattern +
            coverage delta). Default ``False``; enable when the task
            is supposed to follow strict TDD.
        file_paths: Comma-separated paths to scope the auto-run
            ``tapps_validate_changed`` call to (TAP-6738), when
            ``auto_run`` triggers it. Empty (default) auto-detects via
            ``git diff`` — the slower, unscoped path. Callers that
            already know their changed files (``tapps_pipeline``)
            should always pass this.
    """
    from tapps_mcp.server import (
        _record_call,
        _record_execution,
        _with_nudges,
    )

    start = time.perf_counter_ns()

    valid_formats = {"markdown", "json", "compact"}
    if output_format not in valid_formats:
        return error_response(
            "tapps_checklist",
            "invalid_format",
            f"output_format must be one of {sorted(valid_formats)}, got '{output_format}'",
        )

    try:
        from tapps_mcp.tools.checklist import CallTracker

        if reset_checklist_session:
            CallTracker.begin_session()
        _record_call("tapps_checklist")

        settings = load_settings()
        eval_kw: dict[str, Any] = {
            "require_success": settings.checklist_require_success,
            "strict_unknown_task_type": settings.checklist_strict_unknown_task_types,
            "project_root": settings.project_root,
        }

        def _eval_checklist() -> ChecklistResult:
            epic = epic_file_path.strip()
            if epic:
                return CallTracker.evaluate_epic(file_path=epic, **eval_kw)
            return CallTracker.evaluate(task_type, **eval_kw)

        try:
            result = _eval_checklist()
        except ValueError as exc:
            return error_response(
                "tapps_checklist",
                "invalid_task_type",
                str(exc),
            )

        result, auto_run_results = await _run_auto_run(
            auto_run, result, _eval_checklist, settings, file_paths
        )

        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_checklist", start)
        trace_hint = _optional_otel_trace_hint()
        session_id = CallTracker.get_active_checklist_session_id()

        git_context = await _gather_git_context(commit_sha, settings.project_root)
        tdd_results = await _gather_tdd_results(tdd, settings)

        resp_data = _format_checklist_response(
            output_format,
            result,
            auto_run_results,
            session_id=session_id,
            trace_hint=trace_hint,
        )

        resp_data["git_context"] = git_context
        if tdd_results is not None:
            resp_data["tdd_stages"] = tdd_results
        resp_data["checklist_session_id"] = session_id
        resp_data["otel_trace_hint"] = trace_hint
        if result.checklist_policy_version:
            resp_data["checklist_policy_version"] = result.checklist_policy_version

        _apply_usage_gaps(resp_data, result, settings, task_type)
        _apply_validation_note(resp_data, auto_run_results)

        # Surface epic_validation on markdown path when present
        ev = getattr(result, "epic_validation", None)
        if ev is not None:
            resp_data["epic_validation"] = ev.model_dump()

        prior = await _gather_prior_outcome(settings)
        if prior is not None:
            resp_data["prior_checklist_outcome"] = prior

        resp = success_response("tapps_checklist", elapsed_ms, resp_data)

        _attach_checklist_structured_output(
            resp, result, session_id, auto_run_results, output_format
        )
        _write_checklist_marker(settings, result)

        return _with_nudges("tapps_checklist", resp, {"complete": result.complete})
    except ImportError:
        return _checklist_fallback_response(task_type, start)


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register the checklist tool on the shared *mcp_instance* (Epic 79.1: conditional)."""
    if "tapps_checklist" in allowed_tools:
        register_tool(mcp_instance, tapps_checklist, annotations=_ANNOTATIONS_READ_ONLY)
