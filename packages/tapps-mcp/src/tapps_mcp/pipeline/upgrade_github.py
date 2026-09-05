"""Repo-level (host-agnostic) artifact upgrades: ``.github/`` and root scripts.

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913). Each generator is
called independently so one failing artifact records an error instead of
aborting the whole upgrade.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.upgrade_report import enumerate_preserved, skipped

log = get_logger(__name__)


def _plan_ci_workflows(project_root: Path) -> dict[str, Any]:
    """Managed vs preserved workflow files under ``.github/workflows``."""
    from tapps_mcp.pipeline.github_ci import MANAGED_WORKFLOW_FILES

    managed_workflows = frozenset(MANAGED_WORKFLOW_FILES)
    return {
        "action": "would-write-managed-files",
        "managed_files": sorted(managed_workflows),
        "preserved_files": enumerate_preserved(
            project_root / ".github" / "workflows", managed_workflows
        ),
    }


def _would_recreate_deleted(
    project_root: Path, managed_root_files: frozenset[str]
) -> list[dict[str, str]]:
    """TAP-2201: managed root files absent from an *established* project.

    "Established" = ``AGENTS.md`` exists (tapps was previously initialised).
    Fresh installs are excluded so their safe-to-run verdicts stay unchanged.
    """
    if not (project_root / "AGENTS.md").exists():
        return []
    github_root_dir = project_root / ".github"
    return [
        {
            "file": f".github/{fname}",
            "note": (
                "File is absent from repo. If deleted intentionally, "
                f"add '{fname}' to upgrade_skip_files in "
                ".tapps-mcp.yaml to suppress recreation."
            ),
        }
        for fname in managed_root_files
        if not (github_root_dir / fname).exists()
    ]


def _plan_github_templates(project_root: Path) -> dict[str, Any]:
    """Managed vs preserved issue templates and ``.github`` root files."""
    from tapps_mcp.pipeline.github_templates import (
        MANAGED_GITHUB_ROOT_FILES,
        MANAGED_ISSUE_TEMPLATE_FILES,
    )

    issue_template_dir = project_root / ".github" / "ISSUE_TEMPLATE"
    managed_issue_templates = frozenset(MANAGED_ISSUE_TEMPLATE_FILES)
    github_root_dir = project_root / ".github"
    managed_github_root = frozenset(MANAGED_GITHUB_ROOT_FILES)
    # Exclude the subdirectories the upgrade writes into from the "preserved"
    # roll-up at ``.github/`` — they're enumerated separately.
    github_root_managed_for_listing = managed_github_root | {"ISSUE_TEMPLATE", "workflows"}

    return {
        "action": "would-write-managed-files",
        "managed_files": sorted(
            [*(f"ISSUE_TEMPLATE/{n}" for n in managed_issue_templates), *managed_github_root]
        ),
        "preserved_files": sorted(
            [
                *(
                    f"ISSUE_TEMPLATE/{n}"
                    for n in enumerate_preserved(issue_template_dir, managed_issue_templates)
                ),
                *enumerate_preserved(github_root_dir, github_root_managed_for_listing),
            ]
        ),
        "would_recreate_deleted_files": _would_recreate_deleted(
            project_root, frozenset(MANAGED_GITHUB_ROOT_FILES)
        ),
    }


def dry_run_github_artifacts(
    project_root: Path, result: dict[str, Any], *, skip_files: set[str] | None = None
) -> None:
    """Populate dry-run hints for GitHub-hosted artifact generators.

    Mirrors the agents/skills precision pattern for ``ci_workflows`` and
    ``github_templates`` — enumerates managed vs preserved files so consumers
    can see custom workflows / issue forms are safe. ``github_copilot`` and
    ``governance`` stay on the simpler ``would-regenerate`` hint for now;
    their generators span multiple directories with version markers and
    don't benefit from enumeration the way shared directories do. TAP-7054:
    ``github_copilot`` reports the skip marker when pinned.
    """
    result["components"]["ci_workflows"] = _plan_ci_workflows(project_root)
    result["components"]["github_templates"] = _plan_github_templates(project_root)
    result["components"]["github_copilot"] = (
        "skipped (upgrade_skip_files)"
        if skipped("copilot_instructions", skip_files or set())
        else {"action": "would-regenerate"}
    )
    result["components"]["governance"] = {"action": "would-regenerate"}


def _run_generator(
    result: dict[str, Any],
    component: str,
    label: str,
    log_event: str,
    generate: Callable[[], Any],
) -> None:
    """Run one repo-level generator, recording failures instead of raising."""
    try:
        result["components"][component] = generate()
    except Exception as exc:
        log.exception(log_event)
        result["errors"].append(f"{label}: {exc}")


def _generate_ci_workflows(project_root: Path) -> Any:
    from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

    return generate_all_ci_workflows(project_root, upgrade_mode=True)


def _generate_copilot_config(project_root: Path, *, force: bool) -> Any:
    from tapps_mcp.pipeline.github_copilot import generate_all_copilot_config

    return generate_all_copilot_config(project_root, upgrade_mode=True, force=force)


def _generate_github_templates(project_root: Path) -> Any:
    from tapps_mcp.pipeline.github_templates import generate_all_github_templates

    return generate_all_github_templates(project_root)


def _generate_governance(project_root: Path) -> Any:
    from tapps_mcp.pipeline.github_governance import generate_all_governance

    return generate_all_governance(project_root)


def run_github_artifacts(
    project_root: Path,
    result: dict[str, Any],
    *,
    force: bool = False,
    skip_files: set[str] | None = None,
) -> None:
    """Run GitHub-hosted artifact generators (CI, Copilot, templates, governance).

    Each generator is called independently; failures are recorded in
    ``result["errors"]`` rather than aborting the whole upgrade. TAP-7054:
    ``github_copilot`` honors the ``copilot_instructions`` skip token.
    """
    _run_generator(
        result,
        "ci_workflows",
        "CI workflows",
        "ci_workflows_failed",
        lambda: _generate_ci_workflows(project_root),
    )
    if skipped("copilot_instructions", skip_files or set()):
        result["components"]["github_copilot"] = "skipped (upgrade_skip_files)"
    else:
        _run_generator(
            result,
            "github_copilot",
            "Copilot config",
            "copilot_config_failed",
            lambda: _generate_copilot_config(project_root, force=force),
        )
    _run_generator(
        result,
        "github_templates",
        "GitHub templates",
        "github_templates_failed",
        lambda: _generate_github_templates(project_root),
    )
    _run_generator(
        result,
        "governance",
        "Governance",
        "governance_failed",
        lambda: _generate_governance(project_root),
    )


def install_start_program_script(
    project_root: Path,
    result: dict[str, Any],
    *,
    mcp_only: bool,
    skip_files: set[str],
    dry_run: bool,
) -> None:
    """Regenerate ``scripts/start-program.sh`` — platform-agnostic kickoff for a
    MULTI-SESSION program; companion to the orchestration-prompt skill (TAP-6885).
    """
    if mcp_only:
        result["components"]["start_program_script"] = {"action": "skipped (mcp_only)"}
        return
    if skipped("start_program_script", skip_files):
        result["components"]["start_program_script"] = "skipped (upgrade_skip_files)"
        return
    try:
        from tapps_mcp.pipeline.platform_skill_orchestration import (
            generate_start_program_script,
        )

        result["components"]["start_program_script"] = generate_start_program_script(
            project_root, dry_run=dry_run
        )
    except Exception as exc:
        log.exception("start_program_script_failed")
        result["errors"].append(f"start-program.sh: {exc}")
