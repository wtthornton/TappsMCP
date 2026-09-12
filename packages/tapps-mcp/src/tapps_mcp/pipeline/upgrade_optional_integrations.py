"""Opt-in integration refreshers for the upgrade pipeline (TAP-6913 follow-up).

Extracted from :mod:`~tapps_mcp.pipeline.upgrade` to keep the facade under its
line-count ceiling. Each refresher only touches a consumer that has already
opted into the corresponding integration (Linear SDLC templates, document
judges, the Cursor stop gate, the call-graph cache) plus the always-on
runtime-gitignore and backup-untrack maintenance.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any


def _guarded(result: dict[str, Any], component: str, run: Callable[[], None]) -> None:
    """Run one optional refresh, recording a failure under *component*."""
    try:
        run()
    except Exception as exc:
        result["errors"].append(f"{component}: {exc}")
        result["components"][component] = {"action": "error", "detail": str(exc)}


def _refresh_linear_sdlc(project_root: Path, result: dict[str, Any], *, dry_run: bool) -> None:
    """Refresh Linear SDLC templates when previously installed (TAP-417).

    Detection is file-system based: check if the primary template file exists.
    """
    from tapps_mcp.pipeline.linear_sdlc.installer import refresh_linear_sdlc
    from tapps_mcp.pipeline.linear_sdlc.renderer import TEMPLATE_PATHS

    if (project_root / TEMPLATE_PATHS[0]).exists():
        result["components"]["linear_sdlc_refresh"] = refresh_linear_sdlc(
            project_root,
            dry_run=dry_run,
        )


def _refresh_document_judges(project_root: Path, result: dict[str, Any], *, dry_run: bool) -> None:
    """Merge the document-judge config and memory profile into consumer YAML."""
    from tapps_mcp.pipeline.document_judges import (
        is_document_consumer,
        merge_document_judges_into_yaml,
        merge_document_memory_profile,
    )

    if not is_document_consumer(project_root):
        return
    result["components"]["document_judges"] = merge_document_judges_into_yaml(
        project_root,
        dry_run=dry_run,
    )
    result["components"]["document_memory_profile"] = merge_document_memory_profile(
        project_root,
        dry_run=dry_run,
    )


def _refresh_cursor_stop_gate(project_root: Path, result: dict[str, Any], *, dry_run: bool) -> None:
    from tapps_mcp.pipeline.init import _ensure_cursor_stop_completion_gate_config

    result["components"]["cursor_stop_completion_gate"] = {
        "action": _ensure_cursor_stop_completion_gate_config(project_root, dry_run=dry_run)
    }


def _refresh_call_graph_cache(project_root: Path, result: dict[str, Any], *, dry_run: bool) -> None:
    from tapps_mcp.project.call_graph_cache import invalidate_call_graph_cache_if_schema_stale

    result["components"]["call_graph_cache"] = invalidate_call_graph_cache_if_schema_stale(
        project_root,
        dry_run=dry_run,
    )


def refresh_optional_integrations(
    project_root: Path,
    result: dict[str, Any],
    *,
    dry_run: bool,
    mcp_only: bool,
) -> None:
    """Opt-in integrations refreshed only where the consumer already uses them."""
    refreshers: tuple[tuple[str, Callable[..., None]], ...] = (
        ("linear_sdlc_refresh", _refresh_linear_sdlc),
        ("document_judges", _refresh_document_judges),
        ("cursor_stop_completion_gate", _refresh_cursor_stop_gate),
        ("call_graph_cache", _refresh_call_graph_cache),
    )
    for component, refresh in refreshers:
        _guarded(result, component, partial(refresh, project_root, result, dry_run=dry_run))

    if not dry_run and not mcp_only:
        from tapps_mcp.pipeline.platform_hooks import cleanup_legacy_hook_sidecars

        result["components"]["hook_sidecar_cleanup"] = cleanup_legacy_hook_sidecars(
            project_root,
            dry_run=False,
        )

    if not dry_run:
        from tapps_mcp.distribution.setup_generator import ensure_tapps_runtime_gitignore

        added = ensure_tapps_runtime_gitignore(project_root)
        result["components"]["runtime_gitignore"] = {
            "action": "updated" if added else "unchanged",
            "added": added,
        }

    if not dry_run and not mcp_only:
        from tapps_mcp.distribution.setup_generator import (
            backup_untrack_warnings,
            untrack_gitignored_backup_paths,
        )

        untrack_result = untrack_gitignored_backup_paths(project_root)
        result["components"]["backup_untrack"] = untrack_result
        result.setdefault("warnings", []).extend(backup_untrack_warnings(untrack_result))
