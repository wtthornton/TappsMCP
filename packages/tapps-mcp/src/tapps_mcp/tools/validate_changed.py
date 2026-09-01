"""``tapps_validate_changed`` MCP tool handler.

Refactored under TAP-2468 — the heavy lifting is now split across three
sibling modules:

* :mod:`tapps_mcp.tools.validate_changed_collection` — discovering
  changed files, partitioning by cache, writing the post-validation
  marker.
* :mod:`tapps_mcp.tools.validate_changed_orchestrator` — running the
  per-file scorer/gate/security pipeline, progress reporting, and the
  auto-detect wall-clock budget.
* :mod:`tapps_mcp.tools.validate_changed_output` — response payload
  assembly (summary, per-file rows, structured output, no-files
  shortcut, judges, timeout hint).

This module keeps only the public MCP handler plus the first-run wizard
helper, both of which remain re-exported from ``server_pipeline_tools``
for test patchability.

The handler looks several names up on ``server_pipeline_tools`` at call
time (``_discover_changed_files``, ``_validate_single_file``,
``_compute_impact_analysis``, ``_write_validate_ok_marker``,
``load_settings``, ``_AUTO_DETECT_BUDGET_S``) so that tests patching
those names on the host module are honoured even though the function
definitions live in the sibling modules.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog
from mcp.server.fastmcp import Context

from tapps_core.knowledge.kg_keys import entity_spec
from tapps_mcp.server_helpers import success_response

_logger = structlog.get_logger(__name__)

from tapps_mcp.tools.validate_changed_collection import (
    _VALIDATE_OK_MARKER,
    _cache_hit_as_file_result,
    _collect_results,
    _discover_changed_files,
    _partition_by_cache,
    _write_validate_ok_marker,
    count_tracked_scorable_files,
    maybe_write_debt_ok_marker,
)
from tapps_mcp.tools.validate_changed_orchestrator import (
    _VALIDATE_CONCURRENCY,
    _emit_file_info,
    _maybe_warm_dependency_cache,
    _report_initial_progress,
    _run_security_scan,
    _run_tasks_with_budget,
    _start_progress_reporting,
    _TimedOutInfo,
    _validate_single_file,
    _warm_dependency_cache,
)
from tapps_mcp.tools.validate_changed_output import (
    _SEVERITY_RANK,
    _build_per_file_results,
    _build_response_data,
    _build_structured_validation_output,
    _build_validation_summary,
    _compute_blast_radius_caveat,
    _compute_diff_impact,
    _handle_no_changed_files,
    _resolve_security_depth,
    _run_judges,
    apply_judge_payload,
    attach_affected_tests,
    attach_blast_radius_caveat,
    attach_diff_impact,
)
from tapps_mcp.tools.validate_changed_response import (
    append_timeout_hint,
    attach_missing_paths_warning,
    attach_optional_payload,
    attach_report_studio_hint,
    attach_timing_profile,
    batch_budget_s,
)
from tapps_mcp.tools.validation_progress import (
    _PROGRESS_HEARTBEAT_INTERVAL,
    _VALIDATION_PROGRESS_FILE,
    _ProgressTracker,
    _validate_progress_heartbeat,
)

if TYPE_CHECKING:
    from tapps_mcp.common.elicitation import WizardResult


# STORY-101.3 — wall-clock cap on auto-detect tapps_validate_changed runs.
# Large repos can yield hundreds of changed files; without a cap, agents
# can block for minutes. Explicit file_paths mode ignores this budget.
# Kept module-level so STORY-101.6 (perf budget regression test) can tune it.
_AUTO_DETECT_BUDGET_S: float = 30.0

# TAP-5271 — warm explicit-path budget (milliseconds). Cold start (first
# ensure_session_initialized / checker warm) is documented separately and is
# excluded from this warm-path target.
VALIDATE_CHANGED_WARM_BUDGET_MS: int = 15_000


def _missing_file_paths_guard(
    *,
    settings: Any,
    host: Any,
) -> dict[str, Any] | None:
    """Warn or error when file_paths is omitted in a large repo (TAP-5271).

    Returns an error response dict when mode is ``error``, else ``None`` after
    optionally recording a warning payload the caller should attach.
    """
    vc = settings.validate_changed
    mode = str(getattr(vc, "missing_file_paths_mode", "warn") or "off")
    if mode == "off":
        return None
    threshold = int(getattr(vc, "require_explicit_paths_above", 50) or 0)
    tracked = count_tracked_scorable_files(settings.project_root)
    if threshold > 0 and tracked < threshold:
        return None
    message = (
        f"file_paths was omitted in a large repo ({tracked}+ scorable files; "
        f"threshold={threshold or 'always'}). Pass explicit "
        "file_paths='a.py,b.py' — auto-detect via git diff is the #1 cause of "
        "slow validate_changed (p95) and QUALITY_GATE_SKIP."
    )
    if mode == "error":
        return cast(
            "dict[str, Any]",
            host.error_response(
                "tapps_validate_changed",
                "missing_file_paths",
                message,
            ),
        )
    # warn mode: signal via sentinel dict the caller merges into response later
    return {"_missing_file_paths_warning": message, "_tracked_scorable": tracked}


# Re-export for test patchability via ``server_pipeline_tools.X``.
# Symbols imported above are kept reachable here so that
# ``from tapps_mcp.tools.validate_changed import X`` keeps working for
# back-compat consumers.
__all__ = [
    "VALIDATE_CHANGED_WARM_BUDGET_MS",
    "_AUTO_DETECT_BUDGET_S",
    "_PROGRESS_HEARTBEAT_INTERVAL",
    "_SEVERITY_RANK",
    "_VALIDATE_CONCURRENCY",
    "_VALIDATE_OK_MARKER",
    "_VALIDATION_PROGRESS_FILE",
    "_ProgressTracker",
    "_TimedOutInfo",
    "_build_per_file_results",
    "_build_response_data",
    "_build_structured_validation_output",
    "_build_validation_summary",
    "_cache_hit_as_file_result",
    "_collect_results",
    "_discover_changed_files",
    "_emit_file_info",
    "_handle_no_changed_files",
    "_maybe_run_wizard",
    "_maybe_warm_dependency_cache",
    "_partition_by_cache",
    "_report_initial_progress",
    "_resolve_security_depth",
    "_run_judges",
    "_run_security_scan",
    "_run_tasks_with_budget",
    "_start_progress_reporting",
    "_validate_progress_heartbeat",
    "_validate_single_file",
    "_warm_dependency_cache",
    "_write_validate_ok_marker",
    "maybe_write_debt_ok_marker",
    "tapps_validate_changed",
]


async def _maybe_run_wizard(
    ctx: Context[Any, Any, Any],
    *,
    llm_engagement_level: str | None,
    platform: str,
    agent_teams: bool,
) -> WizardResult | None:
    """Run the interactive wizard if this is a true first-run.

    Returns a :class:`WizardResult` when the wizard ran and completed,
    or ``None`` when skipped.
    """
    # Skip if explicit params were provided (not all defaults)
    if llm_engagement_level is not None or platform or agent_teams:
        return None

    # Skip if existing config already present; look up load_settings via the host
    # module so tests can patch tapps_mcp.server_pipeline_tools.load_settings.
    from tapps_mcp import server_pipeline_tools as _host

    settings = _host.load_settings()
    proj = settings.project_root
    has_settings = (proj / ".claude" / "settings.json").exists()
    has_yaml = (proj / ".tapps-mcp.yaml").exists()
    if has_settings or has_yaml:
        return None

    from tapps_mcp.common.elicitation import run_init_wizard

    wizard = await run_init_wizard(ctx)
    if not wizard.completed:
        return None

    # Persist wizard answers in .tapps-mcp.yaml
    yaml_content = (
        f"llm_engagement_level: {wizard.engagement_level}\n"
        f"quality_preset: {wizard.quality_preset}\n"
    )
    yaml_path = proj / ".tapps-mcp.yaml"
    with contextlib.suppress(OSError):
        await asyncio.to_thread(yaml_path.write_text, yaml_content, encoding="utf-8")

    return wizard


@dataclasses.dataclass
class _BatchContext:
    """Inputs and per-run scaffolding for one validate_changed invocation."""

    file_paths: str
    base_ref: str
    preset: str
    include_security: bool
    quick: bool
    security_depth: str
    include_impact: bool
    correlation_id: str
    judges: list[dict[str, Any]] | None
    ctx: Context[Any, Any, Any] | None
    start: int
    settings: Any
    paths: list[Path]
    baseline_ref: str
    capped: bool
    extra_count: int
    tracker: _ProgressTracker
    auto_detect: bool
    cached_results: list[dict[str, Any]]
    uncached_paths: list[Path]


@dataclasses.dataclass
class _BatchOutcome:
    """Aggregate outcome of the per-file validation batch."""

    results: list[dict[str, Any]]
    all_passed: bool
    total_sec: int
    impact_data: dict[str, Any] | None
    affected_tests_data: dict[str, Any] | None
    diff_impact_data: dict[str, Any] | None
    blast_radius_caveat: dict[str, Any] | None
    timeout_info: _TimedOutInfo


def _prepare_batch_context(
    *,
    file_paths: str,
    base_ref: str,
    preset: str,
    include_security: bool,
    quick: bool,
    security_depth: str,
    include_impact: bool,
    correlation_id: str,
    judges: list[dict[str, Any]] | None,
    ctx: Context[Any, Any, Any] | None,
    start: int,
    settings: Any,
    paths: list[Path],
    baseline_ref: str = "",
) -> _BatchContext:
    """Cap paths, init the progress tracker, partition by content cache."""
    from tapps_mcp.tools.batch_validator import MAX_BATCH_FILES

    capped = len(paths) > MAX_BATCH_FILES
    extra_count = len(paths) - MAX_BATCH_FILES if capped else 0
    capped_paths = paths[:MAX_BATCH_FILES]
    tracker = _ProgressTracker(total=len(capped_paths))
    tracker.init_sidecar(settings.project_root)
    cached_results, uncached_paths = _partition_by_cache(capped_paths, preset)
    return _BatchContext(
        file_paths=file_paths,
        base_ref=base_ref,
        preset=preset,
        include_security=include_security,
        quick=quick,
        security_depth=security_depth,
        include_impact=include_impact,
        correlation_id=correlation_id,
        judges=judges,
        ctx=ctx,
        start=start,
        settings=settings,
        paths=capped_paths,
        baseline_ref=baseline_ref,
        capped=capped,
        extra_count=extra_count,
        tracker=tracker,
        auto_detect=not file_paths.strip(),
        cached_results=cached_results,
        uncached_paths=uncached_paths,
    )


async def _execute_validation_batch(
    bc: _BatchContext,
) -> tuple[list[dict[str, Any]], _TimedOutInfo]:
    """Run the per-file validation pipeline for ``bc.uncached_paths``.

    Wraps the semaphore-bounded task construction and budget-aware
    gather. Looks ``_validate_single_file`` up on
    ``server_pipeline_tools`` so test patches are honoured.
    """
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.server_helpers import ensure_session_initialized

    await ensure_session_initialized()
    _maybe_warm_dependency_cache(bc.settings, bc.quick)

    sem = asyncio.Semaphore(_VALIDATE_CONCURRENCY)
    do_security_full = _resolve_security_depth(bc.security_depth, bc.include_security, bc.quick)

    tasks = [
        asyncio.create_task(
            _host._validate_single_file(
                p,
                bc.preset,
                bc.quick,
                do_security_full,
                sem,
                bc.tracker,
                bc.ctx,
                baseline_ref=bc.baseline_ref,
                project_root=bc.settings.project_root,
            )
        )
        for p in bc.uncached_paths
    ]
    return await _run_tasks_with_budget(tasks, bc.uncached_paths, bc.start, bc.auto_detect)


async def _run_with_progress(
    bc: _BatchContext,
) -> tuple[list[dict[str, Any]], _TimedOutInfo]:
    """Run the batch with progress heartbeats and exception bookkeeping."""
    from tapps_mcp.server import _record_call

    stop_progress = asyncio.Event()
    progress_task = _start_progress_reporting(
        bc.ctx, len(bc.paths), bc.start, stop_progress, bc.tracker
    )
    try:
        return await _execute_validation_batch(bc)
    except Exception as exc:
        _record_call("tapps_validate_changed", success=False)
        bc.tracker.finalize_error(str(exc))
        raise
    finally:
        await _stop_progress_task(progress_task, stop_progress)


async def _finalize_outcome(
    bc: _BatchContext,
    task_results: list[dict[str, Any]],
    timeout_info: _TimedOutInfo,
) -> _BatchOutcome:
    """Combine cached + task results and run post-batch bookkeeping."""
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.server import _record_call, _record_execution
    from tapps_mcp.tools.event_loop_guard import heavy_cpu

    results = [*task_results, *bc.cached_results]
    all_passed = all(r.get("gate_passed", False) for r in results) if results else False
    incomplete = timeout_info.timed_out or bc.capped
    if incomplete:
        all_passed = False
    total_sec = sum(r.get("security_issues", 0) for r in results)

    impact_data = None
    affected_tests_data = None
    diff_impact_data = None
    blast_radius_caveat = None
    if bc.include_impact and bc.paths:
        # Impact / call-graph work is sync CPU — must not run on the HTTP
        # event loop (shared nlt-build fleet starves Cursor handshakes).
        async with heavy_cpu():
            impact_data = await asyncio.to_thread(
                _host._compute_impact_analysis, bc.paths, bc.settings.project_root
            )
            affected_tests_data = await asyncio.to_thread(
                _host._compute_affected_tests, bc.paths, bc.settings.project_root
            )
            diff_impact_data = await asyncio.to_thread(
                _compute_diff_impact, bc.paths, bc.settings.project_root
            )
            blast_radius_caveat = await asyncio.to_thread(
                _compute_blast_radius_caveat, bc.paths, bc.settings.project_root
            )

    if not all_passed:
        _record_call("tapps_validate_changed", success=False)
    _record_execution("tapps_validate_changed", bc.start, gate_passed=all_passed)

    await maybe_write_debt_ok_marker(
        _host._write_validate_ok_marker,
        incomplete=incomplete,
        all_passed=all_passed,
        results=results,
        project_root=bc.settings.project_root,
    )
    return _BatchOutcome(
        results=results,
        all_passed=all_passed,
        total_sec=total_sec,
        impact_data=impact_data,
        affected_tests_data=affected_tests_data,
        diff_impact_data=diff_impact_data,
        blast_radius_caveat=blast_radius_caveat,
        timeout_info=timeout_info,
    )


async def _assemble_response(
    bc: _BatchContext,
    outcome: _BatchOutcome,
) -> dict[str, Any]:
    """Build the final response dict from batch context + outcome."""
    from tapps_mcp.server import _with_nudges

    summary = _build_validation_summary(outcome.results, bc.quick, bc.capped, bc.extra_count)
    per_file_results, summary_rows = _build_per_file_results(outcome.results)
    elapsed_ms = (time.perf_counter_ns() - bc.start) // 1_000_000
    bc.tracker.finalize(outcome.all_passed, summary, elapsed_ms)

    resp_data = _build_response_data(
        outcome.results,
        outcome.all_passed,
        outcome.total_sec,
        per_file_results,
        summary_rows,
        summary,
        outcome.impact_data,
    )
    attach_affected_tests(resp_data, outcome.affected_tests_data)
    attach_diff_impact(resp_data, outcome.diff_impact_data)
    attach_blast_radius_caveat(resp_data, outcome.blast_radius_caveat)
    if bc.capped:
        resp_data["capped"] = True
        resp_data["files_not_validated"] = bc.extra_count
    attach_optional_payload(
        resp_data,
        paths=bc.paths,
        settings=bc.settings,
        correlation_id=bc.correlation_id,
        timeout_info=outcome.timeout_info,
        auto_detect=bc.auto_detect,
    )
    overall_passed = outcome.all_passed
    if bc.judges:
        judge_payload = await _run_judges(
            bc.judges,
            bc.settings.project_root,
            changed_paths=None,
            base_ref=bc.base_ref,
        )
        summary = apply_judge_payload(resp_data, judge_payload, summary=summary)
        overall_passed = bool(resp_data.get("all_gates_passed", overall_passed))

    resp = success_response("tapps_validate_changed", elapsed_ms, resp_data)
    _build_structured_validation_output(
        outcome.results,
        overall_passed,
        bc.security_depth,
        outcome.impact_data,
        resp,
    )
    resp = _with_nudges(
        "tapps_validate_changed",
        resp,
        {
            "changed_python_file_count": sum(
                1 for path in bc.paths if path.suffix in {".py", ".pyi"}
            ),
        },
    )
    if outcome.timeout_info.timed_out:
        append_timeout_hint(
            resp,
            outcome.timeout_info.files_remaining,
            budget_s=batch_budget_s(bc.auto_detect),
            auto_detect=bc.auto_detect,
        )
    return resp


# ---------------------------------------------------------------------------
# TAP-1943: KG event helper — validate_changed completion emission
# ---------------------------------------------------------------------------


def _fire_validate_events(
    paths: list[Path],
    outcome: _BatchOutcome,
    elapsed_ms: int,
) -> None:
    """Fire a brain KG event for validate_changed completion (fire-and-forget).

    Emits a ``validate_completed`` event with one file entity per changed
    path and a scalar payload carrying the overall verdict, per-file scores,
    and elapsed time.  Best-effort: a brain outage must never affect the
    verdict response.
    """

    async def _emit() -> None:
        try:
            from tapps_mcp.server_helpers import _get_brain_bridge, brain_kg_events_enabled

            if not brain_kg_events_enabled():
                return
            bridge = _get_brain_bridge()
            if bridge is None or not hasattr(bridge, "record_kg_event"):
                return
            if not outcome.all_passed:
                verdict = "fail"
                utility_score = 0.0
            elif outcome.total_sec > 0:
                verdict = "warn"
                utility_score = 0.5
            else:
                verdict = "pass"
                utility_score = 1.0
            per_file_scores = {
                str(r.get("file_path", "")): r.get("overall_score", 0.0)
                for r in outcome.results
                if r.get("file_path")
            }
            path_strs = [str(p) for p in paths]
            payload_data: dict[str, Any] = {
                "overall_verdict": verdict,
                "per_category_scores": per_file_scores,
                "elapsed_ms": elapsed_ms,
                "utility_score": utility_score,
            }
            if path_strs:
                payload_data["subject_key"] = path_strs[0]
            await bridge.record_kg_event(
                event_type="validate_completed",
                entities=[entity_spec("file", p) for p in path_strs],
                edges=None,
                payload_data=payload_data,
            )
        except Exception:
            _logger.debug("validate_kg_event_emit_failed", exc_info=True)

    try:
        asyncio.create_task(_emit())  # noqa: RUF006
    except Exception:
        _logger.debug("validate_kg_event_task_failed", exc_info=True)


async def tapps_validate_changed(
    file_paths: str = "",
    base_ref: str = "HEAD",
    preset: str = "standard",
    include_security: bool = True,
    quick: bool = True,
    security_depth: str = "basic",
    include_impact: bool = False,
    correlation_id: str = "",
    judges: list[dict[str, Any]] | None = None,
    project_root: str = "",
    baseline_ref: str = "",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Runs the per-file quality gate across multiple changed files in one
    call: score + gate + (optional) security scan + (optional) blast-radius
    impact, with a pass/fail verdict for each file.

    Call this once before declaring multi-file work complete — it batches
    what would otherwise be N separate ``tapps_quick_check`` invocations.
    Always pass ``file_paths`` explicitly for repos > 50 files; auto-detect
    via ``git diff`` works but is slow. For a single file use
    ``tapps_quick_check`` (same per-file pipeline, lighter wrapper);
    when you need the formal pipeline closure use ``tapps_checklist``
    after this returns green.

    Supports Python (``.py``, ``.pyi``), TypeScript/JavaScript (``.ts``,
    ``.tsx``, ``.js``, ``.jsx``, ``.mjs``, ``.cjs``), Go (``.go``), and
    Rust (``.rs``). Default ``quick=True`` runs ruff-only scoring
    (typically < 10s); ``quick=False`` runs the full checker matrix
    (ruff, mypy, bandit, radon, vulture) and can take 1-5+ minutes.

    Args:
        file_paths: Comma-separated paths inside the project root.
            Empty (default) auto-detects via ``git diff`` against
            ``base_ref``. **Pass explicit paths for any repo with more
            than ~50 tracked files** — auto-detect is the #1 cause of
            slow validate-changed calls.
        base_ref: Git ref to diff against when auto-detecting. Default
            ``"HEAD"`` (unstaged + staged). Use ``"main"`` /
            ``"master"`` for "everything on this branch".
        preset: Quality gate threshold. ``"standard"`` (default,
            ≥70/100 overall, security floor 50), ``"strict"`` (≥80),
            ``"framework"`` (relaxed for library projects).
        include_security: Run a security scan on each Python file.
            Ignored when ``quick=True`` and ``security_depth='basic'``.
        quick: When ``True`` (default), ruff-only scoring for speed.
            When ``False``, full validation (typically 1-5+ minutes).
            Reserve ``False`` for pre-release / security audits.
        security_depth: ``"basic"`` (default, ruff-rule subset in
            quick mode) or ``"full"`` (runs bandit even in quick mode).
            Use ``"full"`` when ``quick=True`` but you still want
            real security signal.
        include_impact: Run blast-radius impact analysis on each file
            (direct + transitive dependents, test coverage). Default
            ``False`` for hot-path latency (TAP-5271); pass ``True`` when
            you need affected_tests / diff_impact enrichment.
        correlation_id: Caller-provided ID echoed in the response for
            log correlation. Empty (default) omits the field.
        judges: Optional list of post-gate judges. Each dict has
            ``type`` (``"pytest"``, ``"grep"``, ``"exists"``, ``"shell"``),
            ``target`` (path or selector), ``expect`` (regex for
            ``grep``), ``description``, and ``blocking`` (default
            ``False``, advisory only). Use to layer task-specific
            assertions on top of the standard gate.
        project_root: Override the project root. Empty (default) uses
            the server-configured root. Set when validating files in a
            sibling repo from a long-lived MCP host; ``file_paths`` must
            then be relative to this root.
        baseline_ref: Git ref to ratchet against (TAP-6904). Empty
            (default) disables the ratchet entirely -- behaviour is then
            identical to before this parameter existed. When set, a file
            already below the overall-score threshold at this ref may pass
            by holding or improving instead of failing outright; a file
            that regresses, or is new at this ref, still fails. Never
            relaxes a category minimum or the security floor. Pass the
            PR's base SHA/branch (e.g. the merge target) -- never a
            feature branch, or the ratchet compares against your own
            in-flight work instead of the merge target. See
            ``tapps_mcp.gates.ratchet`` for the three rules.
        ctx: MCP context handle, injected by the host for progress
            notifications during long-running batch validation. Do
            not pass manually.
    """
    # Late imports through the host module so tests can patch these names.
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.tools.project_paths import resolve_effective_project_root

    start = time.perf_counter_ns()
    _record_call("tapps_validate_changed")

    settings = _host.load_settings()
    root_result = resolve_effective_project_root(settings.project_root, project_root)
    if root_result.error_code:
        _record_call("tapps_validate_changed", success=False)
        return _host.error_response(
            "tapps_validate_changed",
            root_result.error_code,
            root_result.error_message or "",
        )
    cross_repo = bool(project_root.strip())
    if cross_repo:
        settings = settings.model_copy(update={"project_root": root_result.root})

    missing_paths_warning: str | None = None
    if not file_paths.strip():
        guard = _missing_file_paths_guard(settings=settings, host=_host)
        if guard is not None and "_missing_file_paths_warning" not in guard:
            _record_call("tapps_validate_changed", success=False)
            return guard
        if guard is not None:
            missing_paths_warning = str(guard["_missing_file_paths_warning"])

    paths = _host._discover_changed_files(
        file_paths,
        base_ref,
        settings.project_root,
        cross_repo_root=root_result.root if cross_repo else None,
    )

    effective_judges: list[dict[str, Any]] | None = None
    preset_judges = settings.validate_changed.judges
    if preset_judges or judges:
        effective_judges = [*preset_judges, *(judges or [])]

    if not paths:
        resp = await _handle_no_changed_files(
            start,
            settings,
            _record_execution,
            _with_nudges,
            explicit_paths=bool(file_paths.strip()),
            base_ref=base_ref,
            correlation_id=correlation_id,
            judges=effective_judges,
            project_root_override=cross_repo,
            file_paths=file_paths,
        )
        data = resp.get("data")
        if isinstance(data, dict) and missing_paths_warning:
            warnings = data.get("warnings")
            if not isinstance(warnings, list):
                warnings = []
                data["warnings"] = warnings
            warnings.append(missing_paths_warning)
        return resp

    bc = _prepare_batch_context(
        file_paths=file_paths,
        base_ref=base_ref,
        preset=preset,
        include_security=include_security,
        quick=quick,
        security_depth=security_depth,
        include_impact=include_impact,
        correlation_id=correlation_id,
        judges=effective_judges,
        ctx=ctx,
        start=start,
        settings=settings,
        paths=paths,
        baseline_ref=baseline_ref,
    )
    task_results, timeout_info = await _run_with_progress(bc)
    outcome = await _finalize_outcome(bc, task_results, timeout_info)
    resp = await _assemble_response(bc, outcome)

    data = resp.get("data")
    if isinstance(data, dict):
        attach_timing_profile(
            data,
            warm_budget_ms=VALIDATE_CHANGED_WARM_BUDGET_MS,
            auto_detect=bc.auto_detect,
            include_impact=include_impact,
            quick=quick,
        )
        if missing_paths_warning:
            attach_missing_paths_warning(data, missing_paths_warning)

    attach_report_studio_hint(
        resp,
        settings.project_root,
        has_judges=bool(effective_judges),
    )

    elapsed_ms = (time.perf_counter_ns() - bc.start) // 1_000_000
    _fire_validate_events(bc.paths, outcome, elapsed_ms)
    return resp


async def _stop_progress_task(
    progress_task: asyncio.Task[None] | None,
    stop_progress: asyncio.Event,
) -> None:
    """Signal and await the progress heartbeat task (best-effort)."""
    if progress_task is None:
        return
    stop_progress.set()
    progress_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await progress_task
