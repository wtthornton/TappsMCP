"""Response-tail assembly for ``tapps_validate_changed``.

Split out of :mod:`tapps_mcp.tools.validate_changed` (TAP-5965) so the MCP
handler stays a thin orchestration shell. Everything here mutates an
already-built response payload: optional recall/correlation blocks, the
wall-clock timeout envelope, the timing profile, and the two advisory hints
(missing ``file_paths``, report-studio).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.tools.validate_changed_orchestrator import _TimedOutInfo

_logger = structlog.get_logger(__name__)

_MISSING_PATHS_NEXT_STEP = (
    "WARNING: Pass explicit file_paths= to tapps_validate_changed — "
    "auto-detect in large repos inflates p95 and correlates with "
    "QUALITY_GATE_SKIP."
)

_REPORT_STUDIO_HINT = (
    "Report-studio detected: add validate_changed.judges in .tapps-mcp.yaml "
    "or pass judges=[{type: pytest, target: tests/, description: PDF audit}] "
    "to gate PDF quality after rebuild."
)

_TIMING_PROFILE_NOTE = (
    "Warm budget applies after session/checkers are already initialized. "
    "Cold start (first ensure_session_initialized / checker warm) is "
    "excluded and can dominate first-call latency."
)


def batch_budget_s(auto_detect: bool) -> float:
    """Return the wall-clock ceiling that applied to this batch.

    Both constants are read off their defining module at call time so a test
    patching either one sees it honoured here as well as in the orchestrator.
    """
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.tools import validate_changed_orchestrator as _orch

    budget: float = _host._AUTO_DETECT_BUDGET_S if auto_detect else _orch._EXPLICIT_PATHS_BUDGET_S
    return budget


def attach_timeout_payload(
    resp_data: dict[str, Any],
    timeout_info: _TimedOutInfo,
    auto_detect: bool,
) -> None:
    """Describe a wall-clock breach in machine-readable terms (TAP-5965)."""
    from tapps_mcp import server_pipeline_tools as _host

    resp_data["timed_out"] = True
    # A caller must be able to tell "batch hit its ceiling" from an ordinary
    # gate failure without parsing prose.
    resp_data["code"] = "validate_changed_timeout"
    resp_data["files_remaining"] = len(timeout_info.files_remaining)
    resp_data["files_remaining_paths"] = [str(p) for p in timeout_info.files_remaining]
    resp_data["budget_s"] = batch_budget_s(auto_detect)
    resp_data["auto_detect"] = auto_detect
    # Pre-TAP-5965 key: auto-detect was the only bounded mode. Kept for callers
    # that already read it.
    resp_data["auto_detect_budget_s"] = _host._AUTO_DETECT_BUDGET_S


def attach_optional_payload(
    resp_data: dict[str, Any],
    *,
    paths: list[Path],
    settings: Any,
    correlation_id: str,
    timeout_info: _TimedOutInfo,
    auto_detect: bool,
) -> None:
    """Append correlation id, insight recall, and timeout summary to data."""
    # EPIC-102: auto-recall of relevant insights (opt-in)
    if settings.memory.recall_on_validate:
        from tapps_mcp.tools.insight_recall import recall_insights_for_validate

        resp_data.update(recall_insights_for_validate(paths, settings.project_root))
    if correlation_id.strip():
        resp_data["correlation_id"] = correlation_id.strip()
    if timeout_info.timed_out:
        attach_timeout_payload(resp_data, timeout_info, auto_detect)

    from tapps_mcp.tools.validate_changed_diagnostics import (
        build_multi_file_memory_hint,
        count_src_paths,
    )

    src_count = count_src_paths(paths)
    memory_hint = build_multi_file_memory_hint(src_count)
    if memory_hint:
        resp_data["multi_file_src_count"] = src_count
        existing = list(resp_data.get("next_steps") or [])
        resp_data["next_steps"] = [memory_hint, *existing][:5]


def append_timeout_hint(
    resp: dict[str, Any],
    files_remaining: list[Path],
    *,
    budget_s: float,
    auto_detect: bool,
) -> None:
    """Inject a wall-clock-budget hint into the response's next_steps.

    TAP-5965: explicit ``file_paths`` runs are bounded too, so the hint names
    the mode that actually breached instead of always saying "auto-detect".
    """
    data = resp.get("data", {})
    sample = ",".join(str(p) for p in files_remaining[:10])
    mode = "Auto-detect" if auto_detect else "Explicit file_paths run"
    remedy = (
        f'Finish with explicit paths: tapps_validate_changed(file_paths="{sample}")'
        if auto_detect
        else "Re-run on a smaller file set, or investigate why validation wedged."
    )
    hint = (
        f"{mode} exceeded the {budget_s:.0f}s budget with "
        f"{len(files_remaining)} files unvalidated. {remedy}"
    )
    existing = list(data.get("next_steps") or [])
    data["next_steps"] = [hint, *existing][:5]


def attach_timing_profile(
    data: dict[str, Any],
    *,
    warm_budget_ms: int,
    auto_detect: bool,
    include_impact: bool,
    quick: bool,
) -> None:
    """Record which latency regime this call ran under."""
    data["timing_profile"] = {
        "warm_budget_ms": warm_budget_ms,
        "auto_detect": auto_detect,
        "include_impact": include_impact,
        "quick": quick,
        "note": _TIMING_PROFILE_NOTE,
    }


def attach_missing_paths_warning(data: dict[str, Any], warning: str) -> None:
    """Surface the omitted-``file_paths`` warning as a warning + next step."""
    warnings = data.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
        data["warnings"] = warnings
    warnings.append(warning)
    steps = data.get("next_steps")
    if not isinstance(steps, list):
        steps = []
        data["next_steps"] = steps
    steps.insert(0, _MISSING_PATHS_NEXT_STEP)


def attach_report_studio_hint(
    resp: dict[str, Any],
    project_root: Path,
    *,
    has_judges: bool,
) -> None:
    """Nudge report-studio projects to gate PDF quality with judges."""
    try:
        from tapps_mcp.pipeline.report_studio.installer import check_report_studio

        rs = check_report_studio(project_root)
        if not rs.get("installed") or has_judges:
            return
        data = resp.get("data", {})
        steps = list(data.get("next_steps") or [])
        data["next_steps"] = [_REPORT_STUDIO_HINT, *steps][:5]
        data["report_studio"] = rs
    except Exception:
        _logger.debug("report_studio_hint_failed", exc_info=True)


__all__ = [
    "append_timeout_hint",
    "attach_missing_paths_warning",
    "attach_optional_payload",
    "attach_report_studio_hint",
    "attach_timeout_payload",
    "attach_timing_profile",
    "batch_budget_s",
]
