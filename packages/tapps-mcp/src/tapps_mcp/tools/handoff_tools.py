"""Pipeline/handoff MCP tools: ``tapps_pipeline``, ``tapps_handoff_save``,
``tapps_session_end``.

Extracted from ``server_pipeline_tools.py`` (TAP-6881) to shrink that
module toward the maintainability gate. ``load_settings``, response
builders, and session-start module state (``_session_state``) are looked
up through ``tapps_mcp.server_pipeline_tools`` at call time (not imported
directly here) so that ``patch("tapps_mcp.server_pipeline_tools.load_settings")``
in the existing test suite keeps intercepting these calls regardless of
which module physically defines the tool body -- the same late-binding
pattern already used by ``tools/pipeline_init_helpers.py``.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


async def tapps_pipeline(
    file_paths: str = "",
    task_type: str = "feature",
    preset: str = "standard",
    skip_session_start: bool = False,
) -> dict[str, Any]:
    """Runs the full TAPPS quality pipeline in one shot: session_start →
    score → quality_gate → security_scan → checklist, and returns an
    aggregated pass/fail report.

    Call this at the end of a coding task instead of invoking each
    pipeline stage individually — it short-circuits on the first failing
    gate and surfaces the per-stage timing so you can see where the
    pipeline spent its budget. Prefer the individual tools when you
    need partial output (e.g., scoring without security scan) or when
    iterating tightly on one file.

    Args:
        file_paths: Comma-separated paths to validate. Empty (default)
            auto-detects via ``git diff``. Always pass explicit paths
            for large repos — auto-detect can be very slow.
        task_type: Drives the checklist matrix at the end of the
            pipeline. One of ``"feature"`` (default), ``"bugfix"``,
            ``"refactor"``, ``"security"``, ``"review"``, ``"epic"``.
        preset: Quality gate threshold preset: ``"standard"`` (default,
            ≥70/100 overall), ``"strict"`` (≥80), or ``"framework"``
            (relaxed for library/framework projects).
        skip_session_start: Skip the leading ``tapps_session_start``
            call. Default ``False``. Enable only when you already ran
            ``session_start`` in the same MCP process and want to save
            its <1s cost.
    """
    from tapps_mcp.server import _record_call
    from tapps_mcp.server_helpers import error_response, success_response
    from tapps_mcp.tools import pipeline_orchestrator as _po

    start = time.perf_counter_ns()
    _record_call("tapps_pipeline")

    if not file_paths.strip():
        return error_response(
            "tapps_pipeline",
            "NO_FILE_PATHS",
            "tapps_pipeline requires file_paths — pass comma-separated paths.",
        )

    stages: list[dict[str, Any]] = []
    pipeline_passed = True

    session_stage = await _po.pipeline_session_start_stage(skip_session_start)
    if session_stage is not None:
        stages.append(session_stage)
        if not session_stage["success"]:
            pipeline_passed = False

    qc_stage, qc_passed, short_circuit = await _po.pipeline_quick_check_stage(file_paths, preset)
    stages.append(qc_stage)
    if not qc_passed:
        pipeline_passed = False

    vc_stage, vc_passed = await _po.pipeline_validate_stage(file_paths, preset, short_circuit)
    stages.append(vc_stage)
    if not vc_passed:
        pipeline_passed = False

    cl_stage, cl_passed = await _po.pipeline_checklist_stage(task_type, file_paths)
    stages.append(cl_stage)
    if not cl_passed:
        pipeline_passed = False

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    data: dict[str, Any] = {
        "pipeline_passed": pipeline_passed,
        "short_circuit": short_circuit,
        "stages": stages,
        "task_type": task_type,
        "file_paths": file_paths,
    }
    return success_response("tapps_pipeline", elapsed_ms, data)


def _append_handoff_subresult_warnings(
    mirror_status: str,
    session_end_status: str,
    brain_mirror: dict[str, Any] | None,
    session_end: dict[str, Any] | None,
    file_path: str,
    warnings: list[str],
    next_steps: list[str],
) -> None:
    """Append warnings/next_steps for any failed best-effort sub-result.

    A failed mirror means the handoff file exists but the cross-session copy
    does not; a failed session-end means the feedback loop never closed.
    Callers reading only the top level saw neither (TAP-5656).
    """
    candidates = (
        ("Brain mirror", mirror_status, brain_mirror),
        ("Session end", session_end_status, session_end),
    )
    failed = [(label, payload or {}) for label, status, payload in candidates if status == "failed"]

    for label, payload in failed:
        detail = str(
            next(
                (
                    v
                    for v in (payload.get("detail"), payload.get("error"), payload.get("reason"))
                    if v
                ),
                "unknown error",
            )
        )
        warnings.append(f"{label} failed ({detail})")
        cap = payload.get("max_value_length")
        length = payload.get("value_length")
        if isinstance(cap, int) and isinstance(length, int) and length > cap:
            next_steps.append(
                f"{label}: {length} chars against a {cap}-char cap — shorten it and re-run."
            )

    if failed:
        warnings.append(f"The handoff file at {file_path} is intact.")


async def tapps_handoff_save(
    markdown: str,
    session_end: bool = False,
    mirror_brain: bool = True,
    allow_lint_warnings: bool = False,
    slot: str | None = None,
    owner: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Atomically write session handoff file, mirror to brain, and lint schema.

    Writes ``.tapps-mcp/session-handoff.md``, mirrors the full markdown body to
    brain key ``session-handoff``, and runs TAP-3573 schema lint. Optionally
    closes the session lifecycle when ``session_end`` is true.

    Args:
        slot: Namespace the file *and* the brain row — ``handoffs/<slot>.md``
            and ``session-handoff.<slot>`` — so concurrent programs stop
            overwriting one another. Omit for the unchanged shared default.
        owner: The program that owns this write, when the body's
            ``**Program:**`` header does not state it. Ownership only; it never
            edits the markdown.
        force: Overwrite another program's handoff under
            ``handoff_conflict_mode: block``. The incumbent is archived first,
            as on every other write.
    """
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.server import _record_call, _record_execution
    from tapps_mcp.server_helpers import (
        error_response,
        gateway_refusal_response,
        success_response,
    )
    from tapps_mcp.tools.handoff_guard import HandoffOwnerConflictError
    from tapps_mcp.tools.handoff_schema import InvalidHandoffSlotError
    from tapps_mcp.tools.handoff_write import HandoffWriteError, write_handoff

    start = time.perf_counter_ns()
    _record_call("tapps_handoff_save")

    settings = _host.load_settings()
    root = Path(settings.project_root)

    try:
        result = await write_handoff(
            root,
            markdown,
            slot=slot,
            owner=owner,
            mirror_brain=mirror_brain,
            run_session_end=session_end,
            session_start_iso=_host._session_state.session_start_iso,
            fail_on_lint_errors=True,
            force=force,
        )
    except (InvalidHandoffSlotError, HandoffOwnerConflictError) as exc:
        # Both carry an Agent Gateway refusal envelope: the agent gets the
        # machine-readable code and the exact retry rather than a traceback.
        _record_execution("tapps_handoff_save", start)
        return gateway_refusal_response(
            "tapps_handoff_save",
            exc.envelope,
            (time.perf_counter_ns() - start) // 1_000_000,
        )
    except HandoffWriteError as exc:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_handoff_save", start)
        resp = error_response(
            "tapps_handoff_save",
            "handoff_lint_failed",
            "; ".join(exc.errors),
            extra={"errors": exc.errors, "warnings": exc.warnings},
        )
        resp["elapsed_ms"] = elapsed_ms
        return resp

    if not allow_lint_warnings and result.lint.warnings:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_handoff_save", start)
        resp = error_response(
            "tapps_handoff_save",
            "handoff_lint_warnings",
            "Handoff has advisory lint warnings",
            extra={"warnings": result.lint.warnings, "file_path": result.file_path},
        )
        resp["elapsed_ms"] = elapsed_ms
        return resp

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_handoff_save", start)

    from tapps_mcp.tools.handoff_guard import conflict_advisory
    from tapps_mcp.tools.handoff_schema import handoff_sections_from_doc
    from tapps_mcp.tools.handoff_write import best_effort_status

    mirror_status = best_effort_status(result.brain_mirror)
    session_end_status = best_effort_status(result.session_end)
    # A conflict is not a failed sub-result — the write completed. It is a
    # completed write that displaced somebody else's, which a caller reading
    # only the top level would not know: the same escape as TAP-5656 from a
    # different cause. Only ``overwritten`` speaks up; ``unknown`` is the
    # ordinary pre-TAP-6872 incumbent and must not make every legacy repo's
    # handoff read as a displacement.
    conflict_state, warnings, next_steps = conflict_advisory(result.conflict or {})

    data: dict[str, Any] = {
        "file_path": result.file_path,
        "slot": slot,
        "linear_p0": result.doc.linear_p0,
        "metadata": result.metadata,
        # Under ``warn`` the guard writes and *reports*; absent here the whole
        # conflict signal stops at the Python boundary (spec §2.2). The raw
        # payload is the record; ``conflict_status`` is the classification a
        # caller can branch on without parsing it.
        "conflict": result.conflict,
        "conflict_status": conflict_state,
        "handoff_sections": handoff_sections_from_doc(result.doc),
        "lint": {
            "ok": result.lint.ok,
            "errors": result.lint.errors,
            "warnings": result.lint.warnings,
        },
        "brain_mirror": result.brain_mirror,  # envelope-ok: examined below by _append_handoff_subresult_warnings
        "brain_mirror_status": mirror_status,
        "session_end": result.session_end,  # envelope-ok: examined below by _append_handoff_subresult_warnings
        "session_end_status": session_end_status,
    }

    # Both sub-results are best-effort and both were embedded in a plain
    # success envelope. A failed mirror means the handoff file exists but the
    # cross-session copy does not; a failed session-end means the feedback loop
    # never closed. Callers reading only the top level saw neither (TAP-5656).
    _append_handoff_subresult_warnings(
        mirror_status,
        session_end_status,
        result.brain_mirror,
        result.session_end,
        result.file_path,
        warnings,
        next_steps,
    )

    # Every note is collected before the envelope is chosen: a conflict alone
    # degrades exactly as a failed sub-result alone does, and neither has to
    # know the other exists.
    if not warnings:
        return success_response("tapps_handoff_save", elapsed_ms, data)

    next_steps.insert(0, "; ".join(warnings))
    data["warnings"] = warnings
    return success_response(
        "tapps_handoff_save",
        elapsed_ms,
        data,
        degraded=True,
        next_steps=next_steps,
    )


async def tapps_session_end() -> dict[str, Any]:
    """Close the feedback loop by processing this session's brain events.

    Calls ``flywheel_process(since=<session_start_iso>)`` so brain
    reconciles the session's feedback events into adaptive weight updates.

    TAP-1999: also calls ``memory_search_sessions`` to fetch the live
    brain-native session record written by ``call_memory_index_session_start``
    at session start.

    Both operations are best-effort — a brain outage does not raise an error.
    """
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.server import _record_call, _record_execution
    from tapps_mcp.server_helpers import success_response
    from tapps_mcp.tools.session_end_helpers import run_session_end

    start = time.perf_counter_ns()
    _record_call("tapps_session_end")

    settings = _host.load_settings()
    data = await run_session_end(
        _host._session_state.session_start_iso,
        project_root=settings.project_root,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_session_end", start)

    return success_response("tapps_session_end", elapsed_ms, data)


__all__ = [
    "_append_handoff_subresult_warnings",
    "tapps_handoff_save",
    "tapps_pipeline",
    "tapps_session_end",
]
