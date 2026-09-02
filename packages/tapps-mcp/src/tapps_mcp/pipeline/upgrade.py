"""Upgrade pipeline for refreshing TappsMCP-generated files.

Provides :func:`upgrade_pipeline` which is called by the
``tapps_upgrade`` MCP tool. Reuses existing generators but operates
in ``upgrade_mode`` so custom command paths are never overwritten.

Module layout (TAP-6913)
========================

This module is the orchestrator and the public surface; the work lives in
focused leaf modules:

- :mod:`~tapps_mcp.pipeline.upgrade_skip_tokens` — the ``upgrade_skip_files``
  vocabulary (imported by ``tapps doctor`` without dragging in the pipeline)
- :mod:`~tapps_mcp.pipeline.upgrade_report` — skip gating, preserved-file
  enumeration, and the dry-run summary
- :mod:`~tapps_mcp.pipeline.upgrade_signals` — project-shape detection
  (Python/infra signals, consent, host detection)
- :mod:`~tapps_mcp.pipeline.upgrade_docs` — AGENTS.md / CLAUDE.md / Karpathy
- :mod:`~tapps_mcp.pipeline.upgrade_mcp_config` — per-host ``.mcp.json``
- :mod:`~tapps_mcp.pipeline.upgrade_hooks_migration` — canonical hook manifest
  and retired-hook rewiring
- :mod:`~tapps_mcp.pipeline.upgrade_hosts` — per-host component resolution
- :mod:`~tapps_mcp.pipeline.upgrade_github` — ``.github/`` and root scripts
- :mod:`~tapps_mcp.pipeline.upgrade_backup` — rollback snapshot
- :mod:`~tapps_mcp.pipeline.upgrade_content_return` — read-only-filesystem mode

The historical private names are re-exported at the bottom of this module, so
``from tapps_mcp.pipeline.upgrade import _skipped`` keeps working.

Design notes — merge over skip
==============================

The upgrade pipeline defaults to *merging* into files that may contain user
content, not overwriting or skipping them. Coverage:

- ``AGENTS.md`` — section-aware smart merge (:mod:`~tapps_mcp.pipeline.agents_md`)
- ``CLAUDE.md`` — H1-section replace (preserves user's non-TAPPS sections)
- ``.mcp.json`` — ``upgrade_mode=True`` preserves custom command paths
- ``.claude/settings.json`` — permissions are merged, not replaced
- Karpathy block — BEGIN/END markers, content-idempotent

Files that are 100% tapps-owned (``.claude/rules/*``, hook scripts, tapps-*
agents and skills) are full overwrites, but are gated per-project so we don't
drop them into repos that don't need them (e.g. Python rules on a bash-only
repo).

Opt-outs — config-first, skip as last resort
============================================

Preferred knobs (in ``.tapps-mcp.yaml``):

- ``upgrade_create_agents_md: false`` — don't create ``AGENTS.md`` if missing;
  existing files still get merged. The HTML comment
  ``<!-- tapps:agents-md-disabled -->`` inside ``CLAUDE.md`` does the same.
- ``include_karpathy_guidelines: false`` — don't install the Karpathy block.
  Already-installed blocks are still refreshed (no silent removal).
- ``force_python_quality_rule: true`` — install the Python rule files even on
  projects with no detected Python signals (override the language gate).

For an MCP-server-only install, call ``tapps_upgrade(mcp_only=True)``.

``upgrade_skip_files`` is the emergency escape hatch — per-artifact tokens
(``AGENTS.md``, ``CLAUDE.md``, ``.mcp.json``,
``.claude/rules/python-quality.md``, ``.claude/rules/agent-scope.md``,
``.claude/rules/tapps-pipeline.md``, ``.claude/settings.json``,
``.claude/hooks``, ``.claude/agents``, ``.claude/skills``, ``karpathy``).
Each token now skips *only* its artifact; in particular ``CLAUDE.md`` no
longer gates hooks/agents/skills/rules. Tokens are honored identically in
dry-run and live mode (TAP-6913).

Dry-run result shape
====================

``upgrade_pipeline(dry_run=True)`` returns structured per-component details
so consumers can audit exactly which paths would change:

- ``components.platforms[].components.agents`` / ``.skills`` / ``.hooks``
  are dicts with ``action``, ``managed_files``/``managed_skills``, and
  ``preserved_files``/``preserved_skills``. The ``managed_*`` lists are the
  ``tapps-*`` files the upgrade would write; ``preserved_*`` lists the
  existing consumer-custom files that stay untouched.
- ``components.settings`` is a string describing the hook-merge behavior.
- ``components.github_templates`` may carry a ``would_recreate_deleted_files``
  list when the project is established (``AGENTS.md`` exists) and one or more
  files from ``MANAGED_GITHUB_ROOT_FILES`` are absent from ``.github/``. Each
  entry is ``{"file": ".github/<name>", "note": "<hint>"}`` describing the
  file and suggesting ``upgrade_skip_files`` if the deletion was intentional.
  Fresh-project dry-runs (no ``AGENTS.md``) never populate this list.
- ``dry_run_summary`` at the top level rolls this up into a ``verdict``
  (``"safe-to-run"`` or ``"review-recommended"``), counts, the full
  preserved-file list, and a ``would_recreate_deleted_files`` rollup —
  enough for an agent to decide whether to proceed without parsing
  per-component details.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from tapps_core.common.file_operations import WriteMode, detect_write_mode
from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.upgrade_backup import collect_upgrade_targets, create_pre_upgrade_backup
from tapps_mcp.pipeline.upgrade_content_return import (
    build_upgrade_manifest,
    upgrade_agents_md_content_return,
    upgrade_content_return,
    upgrade_platform_content_return,
)
from tapps_mcp.pipeline.upgrade_docs import (
    bump_skipped_version_stamps,
    dry_run_claude_md_status,
    refresh_karpathy_blocks,
    upgrade_agents_md,
)
from tapps_mcp.pipeline.upgrade_github import (
    dry_run_github_artifacts,
    install_start_program_script,
    run_github_artifacts,
)
from tapps_mcp.pipeline.upgrade_hooks_migration import (
    CANONICAL_HOOK_MANIFEST,
    is_managed_hook_filename,
    migrate_retired_hooks,
    verify_hook_manifest,
)
from tapps_mcp.pipeline.upgrade_hosts import upgrade_platform
from tapps_mcp.pipeline.upgrade_mcp_config import (
    mcp_json_has_unresolved_workspacefolder,
    upgrade_mcp_config,
)
from tapps_mcp.pipeline.upgrade_report import (
    apply_or_skip,
    build_dry_run_summary,
    dry_run_status,
    enumerate_preserved,
    lift_asset_overwrite_warnings,
    record_applied_skip_tokens,
    record_managed_json_error,
    record_unknown_skip_tokens,
    skipped,
)
from tapps_mcp.pipeline.upgrade_signals import (
    AGENTS_MD_OPT_OUT_SENTINEL,
    CONSENT_HOSTS,
    agents_md_opt_out,
    detect_platform,
    has_infra_signals,
    has_python_signals,
    hosts_for_platform,
    mcp_json_has_tapps_entry,
)
from tapps_mcp.pipeline.upgrade_skip_tokens import ALL_SKIP_TOKENS, SKIP_TOKENS

log = get_logger(__name__)


@dataclass(frozen=True)
class _RunOptions:
    """Per-run configuration resolved once from ``.tapps-mcp.yaml``."""

    settings: Any
    skip_files: set[str]
    mcp_bundle: str | None


def _check_install_drift(result: dict[str, Any]) -> bool:
    """TAP-2200: refuse to upgrade while sibling CLIs lag the in-process version.

    When docsmcp / tapps-brain-mcp are behind, the upgrade plan is not
    trustworthy — templates reference capabilities the lagging binary does not
    yet expose. Returns ``True`` when the run may proceed. Dry-run callers skip
    this gate so operators can still preview the diff while drift is present.
    """
    from tapps_mcp.diagnostics import check_install_drift, format_upgrade_blocked_by_drift

    drift = check_install_drift()
    if not drift.drift_detected:
        return True
    result["errors"].append(format_upgrade_blocked_by_drift(drift))
    result["install_drift"] = drift.model_dump()
    result["success"] = False
    return False


def _resolve_run_options(
    project_root: Path, result: dict[str, Any], *, dry_run: bool
) -> _RunOptions:
    """Load settings, resolve the MCP bundle, and record the skip-token report."""
    from tapps_core.config.settings import load_settings
    from tapps_mcp.distribution.nlt_mcp_config import (
        persist_mcp_bundle_yaml,
        resolve_upgrade_mcp_bundle,
    )

    # Pass the target project_root explicitly so the per-project
    # ``.tapps-mcp.yaml`` (not this process's CWD) drives the upgrade knobs.
    settings = load_settings(project_root=project_root)

    mcp_bundle, bundle_explicit, bundle_note = resolve_upgrade_mcp_bundle(
        project_root,
        settings_bundle=settings.mcp_bundle,
    )
    # Persist inferred named bundles so the next upgrade does not fall through
    # to full and re-expand a trimmed Cursor/Claude set.
    if (
        not dry_run
        and not bundle_explicit
        and mcp_bundle is not None
        and settings.mcp_bundle is None
    ):
        try:
            persist_mcp_bundle_yaml(project_root, mcp_bundle)
            bundle_note = f"{bundle_note}; persisted mcp_bundle={mcp_bundle!r}"
        except Exception:
            log.debug("persist_mcp_bundle_yaml_failed", exc_info=True)
    result["mcp_bundle"] = mcp_bundle if mcp_bundle is not None else "custom"
    result["mcp_bundle_note"] = bundle_note

    # Load skip list from settings (Issue #86)
    skip_files: set[str] = set(settings.upgrade_skip_files)
    if skip_files:
        result["skipped_files"] = sorted(skip_files)
        record_unknown_skip_tokens(result, skip_files)
        record_applied_skip_tokens(result, skip_files)

    stamp_results = bump_skipped_version_stamps(project_root, skip_files, dry_run=dry_run)
    if stamp_results:
        result["components"]["version_stamps"] = stamp_results

    return _RunOptions(settings=settings, skip_files=skip_files, mcp_bundle=mcp_bundle)


def _upgrade_root_documents(
    project_root: Path,
    result: dict[str, Any],
    options: _RunOptions,
    *,
    dry_run: bool,
    force: bool,
    mcp_only: bool,
) -> None:
    """AGENTS.md, TECH_STACK.md, and the bridge-only ``.mcp.json`` strip."""
    # AGENTS.md (platform-independent) — merge-first, with sentinel / config
    # opt-out for greenfield creation only.
    if mcp_only:
        result["components"]["agents_md"] = {"action": "skipped (mcp_only)"}
    elif skipped("agents_md", options.skip_files):
        result["components"]["agents_md"] = {"action": "skipped (upgrade_skip_files)"}
    else:
        try:
            result["components"]["agents_md"] = upgrade_agents_md(
                project_root,
                dry_run=dry_run,
                create_agents_md=options.settings.upgrade_create_agents_md,
                force_merge=force,
            )
        except Exception as exc:
            result["errors"].append(f"AGENTS.md: {exc}")
            result["components"]["agents_md"] = {"action": "error", "detail": str(exc)}

    result["components"]["tech_stack_md"] = _tech_stack_status(
        project_root, options.skip_files, mcp_only=mcp_only
    )

    # TAP-1888: strip direct tapps-brain MCP entries (ADR-0001 bridge-only policy).
    if skipped("mcp_config", options.skip_files):
        result["components"]["brain_mcp_strip"] = "skipped (upgrade_skip_files)"
    else:
        from tapps_mcp.distribution.doctor import strip_brain_mcp_entries

        result["components"]["brain_mcp_strip"] = strip_brain_mcp_entries(
            project_root,
            dry_run=dry_run,
        )


def _tech_stack_status(
    project_root: Path, skip_files: set[str], *, mcp_only: bool
) -> dict[str, Any]:
    """TECH_STACK.md is preserve-only — generated once by ``tapps_init``.

    Never refreshed by upgrade because the content captures user tech choices,
    not tapps-managed scaffolding. Surfaced in the report so consumers see it
    as a known artifact, with a hint when it is missing.
    """
    if mcp_only:
        return {"action": "skipped (mcp_only)"}
    if skipped("tech_stack_md", skip_files):
        return {"action": "skipped (upgrade_skip_files)"}
    if (project_root / "TECH_STACK.md").exists():
        return {"action": "preserved"}
    return {
        "action": "missing",
        "hint": (
            "TECH_STACK.md was not generated. Run `tapps-mcp init` "
            "(or re-run with --create-tech-stack-md) to render it "
            "from the detected stack profile."
        ),
    }


def _upgrade_all_hosts(
    project_root: Path,
    result: dict[str, Any],
    options: _RunOptions,
    *,
    platform: str,
    dry_run: bool,
    force: bool,
    mcp_only: bool,
) -> None:
    """Run the per-host upgrade for each detected platform host."""
    detected = platform or detect_platform(project_root)
    result["detected_platform"] = detected

    settings = options.settings
    skill_tier = settings.skill_tier if settings.skill_tier in {"core", "full"} else "full"

    platform_results: list[dict[str, Any]] = []
    for host in hosts_for_platform(detected):
        try:
            host_result = upgrade_platform(
                host,
                project_root,
                force=force,
                dry_run=dry_run,
                engagement_level=settings.llm_engagement_level,
                skill_tier=skill_tier,
                skip_files=options.skip_files,
                mcp_only=mcp_only,
                force_python_rule=settings.force_python_quality_rule,
                destructive_guard=settings.destructive_guard,
                linear_enforce_gate=settings.linear_enforce_gate_resolved(),
                linear_enforce_cache_gate=settings.linear_enforce_cache_gate_resolved(),
                session_start_gate=settings.session_start_gate_resolved(),
                mcp_bundle=options.mcp_bundle,
            )
            platform_results.append(host_result)
            # Surface isolated managed-JSON component failures (malformed
            # settings.json / hooks.json) at the top level so `success` is
            # False and the CLI prints them — without aborting the scope.
            for component_error in host_result.get("component_errors", []):
                result["errors"].append(f"{host}: {component_error}")
        except Exception as exc:
            result["errors"].append(f"{host}: {exc}")
            platform_results.append({"host": host, "error": str(exc)})

    result["components"]["platforms"] = platform_results
    lift_asset_overwrite_warnings(result, platform_results)


def _upgrade_repo_artifacts(
    project_root: Path,
    result: dict[str, Any],
    options: _RunOptions,
    *,
    dry_run: bool,
    force: bool,
    mcp_only: bool,
) -> None:
    """Karpathy block, GitHub artifacts, and the start-program script."""
    # Refreshed after per-host upgrades have potentially created/updated
    # CLAUDE.md. Opt-out never strips existing blocks.
    if mcp_only:
        result["components"]["karpathy_guidelines"] = {"action": "skipped (mcp_only)"}
    else:
        try:
            result["components"]["karpathy_guidelines"] = refresh_karpathy_blocks(
                project_root,
                dry_run=dry_run,
                include_karpathy=options.settings.include_karpathy_guidelines,
                skip_files=options.skip_files,
                force=force,
            )
        except Exception as exc:
            result["errors"].append(f"Karpathy guidelines: {exc}")
            result["components"]["karpathy_guidelines"] = {"action": "error", "detail": str(exc)}

    if mcp_only:
        for component in ("ci_workflows", "github_copilot", "github_templates", "governance"):
            result["components"][component] = {"action": "skipped (mcp_only)"}
    elif dry_run:
        dry_run_github_artifacts(project_root, result)
    else:
        run_github_artifacts(project_root, result, force=force)

    install_start_program_script(
        project_root, result, mcp_only=mcp_only, skip_files=options.skip_files, dry_run=dry_run
    )


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


def _refresh_optional_integrations(
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


def _finalize_result(result: dict[str, Any], *, dry_run: bool) -> None:
    """Roll up demotions and the dry-run verdict, then stamp ``success``."""
    demoted: list[str] = []
    for key, val in result.get("components", {}).items():
        if isinstance(val, dict) and val.get("alwaysApply_demoted"):
            demoted.append(Path(str(val.get("file", key))).name)
    if demoted:
        result["always_apply_demotions"] = demoted
        result["always_apply_demotion_note"] = (
            f"demoted {len(demoted)} rule(s) from alwaysApply to satisfy the "
            f"context budget: {', '.join(demoted)}"
        )

    if dry_run:
        result["dry_run_summary"] = build_dry_run_summary(result)
        result["errors"].extend(result["dry_run_summary"].get("parse_errors", []))

    result["success"] = len(result["errors"]) == 0
    result["consumer_requirements"] = "docs/TAPPS_MCP_REQUIREMENTS.md"


def upgrade_pipeline(
    project_root: Path,
    *,
    platform: str = "",
    force: bool = False,
    dry_run: bool = False,
    mcp_only: bool = False,
) -> dict[str, Any]:
    """Upgrade all TappsMCP-generated files in a project.

    This is the core function called by the ``tapps_upgrade`` MCP tool.
    It uses ``upgrade_mode=True`` internally so custom command paths
    (e.g. PyInstaller exe) are never overwritten.

    Args:
        project_root: Project root directory.
        platform: ``"claude"``, ``"cursor"``, ``"both"``, or ``""`` for
            auto-detection.
        force: If ``True``, overwrite all generated files.
        dry_run: If ``True``, report what would change without writing.
        mcp_only: If ``True``, perform a narrow install — only the
            ``.mcp.json`` merge (when already opted in) and
            ``.claude/settings.json`` permissions merge. Every other
            artifact (CLAUDE.md, AGENTS.md, hooks, rules, agents, skills,
            Karpathy block, GitHub workflows, governance) is skipped.
            Intended for publisher/non-greenfield consumers who just want
            the MCP server wired in.

    Returns:
        Structured dict with per-component upgrade results.
    """
    from tapps_mcp import __version__

    log.info(
        "upgrade_pipeline",
        project_root=str(project_root),
        platform=platform,
        force=force,
        dry_run=dry_run,
        mcp_only=mcp_only,
    )

    # Epic 87: Detect write mode (content-return for Docker/read-only)
    write_mode = WriteMode.DIRECT_WRITE if dry_run else detect_write_mode(project_root)
    if write_mode == WriteMode.CONTENT_RETURN:
        log.info(
            "content_return_mode",
            project_root=str(project_root),
            reason="read-only filesystem or TAPPS_WRITE_MODE=content",
        )
        return upgrade_content_return(
            project_root,
            platform=platform,
            force=force,
            mcp_only=mcp_only,
        )

    result: dict[str, Any] = {
        "version": __version__,
        "dry_run": dry_run,
        "components": {},
        "errors": [],
    }

    if not dry_run and not _check_install_drift(result):
        return result
    if not dry_run and not create_pre_upgrade_backup(project_root, result):
        return result

    options = _resolve_run_options(project_root, result, dry_run=dry_run)
    _upgrade_root_documents(
        project_root, result, options, dry_run=dry_run, force=force, mcp_only=mcp_only
    )
    _upgrade_all_hosts(
        project_root,
        result,
        options,
        platform=platform,
        dry_run=dry_run,
        force=force,
        mcp_only=mcp_only,
    )
    _upgrade_repo_artifacts(
        project_root, result, options, dry_run=dry_run, force=force, mcp_only=mcp_only
    )
    _refresh_optional_integrations(project_root, result, dry_run=dry_run, mcp_only=mcp_only)
    _finalize_result(result, dry_run=dry_run)
    return result


# ---------------------------------------------------------------------------
# Backwards-compatible private aliases.
#
# The split (TAP-6913) moved these out of this module; call sites and tests
# still import them from here under their historical names.
# ---------------------------------------------------------------------------

_SKIP_TOKENS = SKIP_TOKENS
_ALL_SKIP_TOKENS = ALL_SKIP_TOKENS
_AGENTS_MD_OPT_OUT_SENTINEL = AGENTS_MD_OPT_OUT_SENTINEL
_CONSENT_HOSTS = CONSENT_HOSTS
_CANONICAL_HOOK_MANIFEST = CANONICAL_HOOK_MANIFEST

_agents_md_opt_out = agents_md_opt_out
_apply_or_skip = apply_or_skip
_build_dry_run_summary = build_dry_run_summary
_build_upgrade_manifest = build_upgrade_manifest
_bump_skipped_version_stamps = bump_skipped_version_stamps
_collect_upgrade_targets = collect_upgrade_targets
_detect_platform = detect_platform
_dry_run_claude_md_status = dry_run_claude_md_status
_dry_run_github_artifacts = dry_run_github_artifacts
_dry_run_status = dry_run_status
_enumerate_preserved = enumerate_preserved
_has_infra_signals = has_infra_signals
_has_python_signals = has_python_signals
_install_start_program_script = install_start_program_script
_is_managed_hook_filename = is_managed_hook_filename
_lift_asset_overwrite_warnings = lift_asset_overwrite_warnings
_mcp_json_has_tapps_entry = mcp_json_has_tapps_entry
_mcp_json_has_unresolved_workspacefolder = mcp_json_has_unresolved_workspacefolder
_migrate_retired_hooks = migrate_retired_hooks
_record_applied_skip_tokens = record_applied_skip_tokens
_record_managed_json_error = record_managed_json_error
_record_unknown_skip_tokens = record_unknown_skip_tokens
_refresh_karpathy_blocks = refresh_karpathy_blocks
_run_github_artifacts = run_github_artifacts
_skipped = skipped
_upgrade_agents_md = upgrade_agents_md
_upgrade_agents_md_content_return = upgrade_agents_md_content_return
_upgrade_content_return = upgrade_content_return
_upgrade_mcp_config = upgrade_mcp_config
_upgrade_platform = upgrade_platform
_upgrade_platform_content_return = upgrade_platform_content_return
_verify_hook_manifest = verify_hook_manifest
