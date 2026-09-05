"""Best-effort ``tapps_session_start`` data-enrichment blocks (TAP-6881).

Each function wraps one of ``tapps_session_start``'s optional enrichment
phases (search-first hints, repo orientation, call-graph readiness, usage
gaps, recommended workflows) in its own small function instead of one
large inline function body -- extracted to keep ``server_pipeline_tools.py``
within the maintainability gate. Every function is best-effort: on any
internal failure it degrades in place rather than raising, matching the
original inline ``try/except`` behavior.

``enrich_search_first`` takes ``build_search_first_fn`` as a parameter
(rather than importing ``_build_search_first`` itself) because that name
is patched by tests via ``patch("tapps_mcp.server_pipeline_tools._build_search_first")``
-- the caller in ``server_pipeline_tools.py`` passes its own module-level
(patchable) reference through, so the patch keeps taking effect regardless
of which module runs the surrounding logic.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

_logger = structlog.get_logger(__name__)


def enrich_search_first(
    data: dict[str, Any],
    project_root: Any,
    build_search_first_fn: Callable[[Any], dict[str, Any] | None],
) -> None:
    """TAP-475: proactive lookup hints from pyproject.toml, plus TAP-1331's
    background lookup_docs cache warm (ADR-0029 / TAP-4561 warmer)."""
    search_first = build_search_first_fn(project_root)
    if search_first is None:
        return
    data["search_first"] = search_first
    try:
        from tapps_mcp.tools.session_start_helpers import schedule_session_warm

        data["cache_warm"] = schedule_session_warm(
            project_root, covered=search_first.get("covered", [])
        )["docs"]
    except Exception:
        data["cache_warm"] = {"scheduled": False, "skipped": "exception"}


def enrich_repo_orientation(data: dict[str, Any], project_root: Any) -> None:
    try:
        from tapps_mcp.tools.session_start_helpers import _build_repo_orientation

        repo_orientation = _build_repo_orientation(project_root)
        if repo_orientation is not None:
            data["repo_orientation"] = repo_orientation
    except Exception:
        _logger.debug("repo_orientation_session_start_failed", exc_info=True)


def enrich_call_graph(data: dict[str, Any], project_root: Any) -> None:
    """Epic 114: surface call-graph cache readiness for symbol-level refactors.

    Rebuild scheduling routes through the single warmer (ADR-0029 / TAP-4561).
    """
    try:
        from tapps_mcp.project.call_graph_cache import summarize_call_graph_cache
        from tapps_mcp.tools.session_start_helpers import schedule_session_warm

        call_graph_summary = summarize_call_graph_cache(Path(project_root))
        rebuild = schedule_session_warm(
            Path(project_root), call_graph_summary=call_graph_summary
        )["call_graph"]
        if rebuild.get("scheduled"):
            call_graph_summary["rebuild_scheduled"] = True
        data["call_graph"] = call_graph_summary
    except Exception:
        _logger.debug("call_graph_session_start_failed", exc_info=True)


def enrich_usage_gaps(data: dict[str, Any], project_root: Any) -> None:
    """TAP-3578: surface prior-session usage gaps from disk telemetry."""
    try:
        from tapps_mcp.tools.usage import compute_gaps, format_session_start_gap_hint

        gap_hint = format_session_start_gap_hint(project_root)
        usage = compute_gaps(project_root, called_tools=set())
        data["usage_gaps"] = {
            "gaps": usage.get("gaps", []),
            "recommendations": usage.get("recommendations", []),
            "session_start_hint": gap_hint,
            "rolling_gate_skip_rate": usage.get("rolling_stats", {}).get("gate_skip_rate", 0.0),
            "rolling_loops": usage.get("rolling_stats", {}).get("loops", 0),
        }
    except Exception:
        _logger.debug("usage_gaps_session_start_failed", exc_info=True)


def enrich_recommended_workflows(data: dict[str, Any], settings: Any) -> None:
    """TAP-3929: slash-command workflow catalog for the active bundle + engagement."""
    try:
        from tapps_mcp.tools.session_start_helpers import build_recommended_workflows

        data["recommended_workflows"] = build_recommended_workflows(
            settings.project_root,
            engagement_level=settings.llm_engagement_level,
        )
    except Exception:
        _logger.debug("recommended_workflows_session_start_failed", exc_info=True)


__all__ = [
    "enrich_call_graph",
    "enrich_recommended_workflows",
    "enrich_repo_orientation",
    "enrich_search_first",
    "enrich_usage_gaps",
]
