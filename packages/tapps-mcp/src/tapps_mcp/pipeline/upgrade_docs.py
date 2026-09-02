"""Root-document refreshes for the upgrade pipeline.

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913). Covers the
platform-independent markdown artifacts: ``AGENTS.md``, the ``CLAUDE.md``
dry-run verdict, the Karpathy guidelines block, and the version stamps that get
bumped on skip-listed files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.upgrade_report import skipped
from tapps_mcp.pipeline.upgrade_signals import agents_md_opt_out

log = get_logger(__name__)

_KARPATHY_HOMES = ("AGENTS.md", "CLAUDE.md")


def _write_agents_md_atomically(agents_path: Path, template_content: str) -> None:
    """Write the fresh template through a temp file so a crash can't truncate."""
    tmp = agents_path.with_name(agents_path.name + ".tmp")
    try:
        tmp.write_text(template_content, encoding="utf-8")
        tmp.replace(agents_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _agents_md_merge_detail(validation: Any, *, force_merge: bool) -> str:
    """Human-readable reason the existing AGENTS.md needs a merge."""
    issues: list[str] = []
    if validation.sections_missing:
        issues.append(f"missing sections: {', '.join(validation.sections_missing)}")
    if validation.tools_missing:
        issues.append(f"missing tools: {', '.join(validation.tools_missing)}")
    return "; ".join(issues) or ("force merge" if force_merge else "version mismatch")


def upgrade_agents_md(
    project_root: Path,
    *,
    dry_run: bool = False,
    create_agents_md: bool = True,
    force_merge: bool = False,
) -> dict[str, Any]:
    """Validate and update AGENTS.md to the latest template.

    If ``AGENTS.md`` does not exist, creation is gated:
    - ``create_agents_md=False`` skips creation entirely.
    - A ``<!-- tapps:agents-md-disabled -->`` sentinel inside ``CLAUDE.md``
      also skips creation (for repos where CLAUDE.md is the single source of
      truth).

    Existing ``AGENTS.md`` files always get the section-aware smart merge —
    opting out of creation does not regress upgrades for users who already
    have the file.

    Returns a result dict with ``action`` and optional ``detail``.
    """
    from tapps_mcp.pipeline.agents_md import AgentsValidation, update_agents_md
    from tapps_mcp.prompts.prompt_loader import load_agents_template

    agents_path = project_root / "AGENTS.md"
    template_content = load_agents_template()

    if not agents_path.exists():
        reason = agents_md_opt_out(project_root, create_flag=create_agents_md)
        if reason is not None:
            return {"action": "skipped", "detail": reason}
        if not dry_run:
            _write_agents_md_atomically(agents_path, template_content)
        return {"action": "created"}

    validation = AgentsValidation(agents_path.read_text(encoding="utf-8"))
    if validation.is_up_to_date and not force_merge:
        return {"action": "up-to-date", "detail": validation.to_dict()}

    detail = _agents_md_merge_detail(validation, force_merge=force_merge)
    if dry_run:
        return {"action": "needs-update", "detail": detail}
    action, merge_detail = update_agents_md(agents_path, template_content, force_merge=force_merge)
    return {"action": action, "detail": merge_detail or detail}


def dry_run_claude_md_status(project_root: Path, *, force: bool) -> str:
    """Report the would-do verdict for CLAUDE.md based on the version stamp.

    TAP-2334: parallel to the AGENTS.md stamp check. The verdict drives
    whether the dry-run summary flags CLAUDE.md as ``review-recommended``.
    """
    from tapps_mcp import __version__
    from tapps_mcp.pipeline.claude_md import ClaudeValidation

    claude_md = project_root / "CLAUDE.md"
    if not claude_md.exists():
        return "would-create"
    if force:
        return "would-refresh (force)"
    try:
        validation = ClaudeValidation(claude_md.read_text(encoding="utf-8"))
    except OSError as exc:
        return f"check-needed: {exc}"
    if validation.is_up_to_date:
        return "up-to-date"
    if validation.needs_stamp:
        return "would-add-stamp (legacy CLAUDE.md, no version marker)"
    return f"would-merge (stamp {validation.existing_version or '<none>'} != {__version__})"


def _karpathy_primary_action(target: Path, *, opted_out: bool, dry_run: bool) -> str:
    """Install/refresh verdict for the file that owns the block."""
    from tapps_mcp.pipeline import karpathy_block

    if opted_out and not karpathy_block.has_block(target):
        return "skipped (opt-out)"
    return karpathy_block.install_or_refresh(target, dry_run=dry_run)


def _karpathy_secondary_action(target: Path, *, opted_out: bool, force: bool, dry_run: bool) -> str:
    """Verdict for a non-primary home: strip a dual install, or warn about it."""
    from tapps_mcp.pipeline import karpathy_block

    if not karpathy_block.has_block(target):
        return "skipped (single-home)"
    if not (force and not opted_out):
        return "WARN dual-home (use upgrade --force to strip)"
    action = karpathy_block.remove_block(target, dry_run=dry_run)
    return "would_remove (dual-home)" if dry_run else f"removed (dual-home): {action}"


def _karpathy_file_actions(
    project_root: Path,
    primary: str | None,
    *,
    opted_out: bool,
    force: bool,
    dry_run: bool,
) -> dict[str, str]:
    """Per-file Karpathy verdicts for ``AGENTS.md`` and ``CLAUDE.md``."""
    per_file: dict[str, str] = {}
    for rel in _KARPATHY_HOMES:
        target = project_root / rel
        if not target.exists():
            per_file[rel] = "skipped_file_missing"
            continue
        try:
            if primary is not None and rel == primary:
                per_file[rel] = _karpathy_primary_action(
                    target, opted_out=opted_out, dry_run=dry_run
                )
            else:
                per_file[rel] = _karpathy_secondary_action(
                    target, opted_out=opted_out, force=force, dry_run=dry_run
                )
        except (OSError, ValueError) as exc:
            log.exception("karpathy_block_failed", file=rel)
            per_file[rel] = f"error: {exc}"
    return per_file


def _karpathy_cursor_action(
    project_root: Path, *, opted_out: bool, force: bool, dry_run: bool
) -> str:
    """Verdict for the Cursor ``.mdc`` mirror of the Karpathy rule."""
    from tapps_mcp.pipeline import karpathy_block

    try:
        has_cursor = karpathy_block.cursor_rule_path(project_root).is_file()
        if not opted_out:
            return karpathy_block.install_or_refresh_cursor_rule(project_root, dry_run=dry_run)
        if has_cursor and force:
            return karpathy_block.remove_cursor_rule(project_root, dry_run=dry_run)
        return "unchanged (opt-out keeps existing)" if has_cursor else "skipped (opt-out)"
    except (OSError, ValueError) as exc:
        log.exception("karpathy_cursor_rule_failed")
        return f"error: {exc}"


def refresh_karpathy_blocks(
    project_root: Path,
    *,
    dry_run: bool = False,
    include_karpathy: bool = True,
    skip_files: set[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Install or refresh Karpathy guidelines into a single primary home.

    Prefers ``AGENTS.md`` when present, otherwise ``CLAUDE.md``. Dual installs
    are reported; the secondary copy is removed only when ``force=True`` and
    ``karpathy`` is not in ``upgrade_skip_files``.

    When ``.cursor/rules/`` exists, also refreshes the Cursor ``.mdc`` rule
    (or removes it when opted out and ``force=True``).
    """
    from tapps_mcp.pipeline import karpathy_block
    from tapps_mcp.pipeline.init import _karpathy_primary_home

    skip = skip_files or set()
    opted_out = (not include_karpathy) or skipped("karpathy", skip)
    primary = _karpathy_primary_home(project_root)

    per_file = _karpathy_file_actions(
        project_root, primary, opted_out=opted_out, force=force, dry_run=dry_run
    )
    cursor_rule = _karpathy_cursor_action(
        project_root, opted_out=opted_out, force=force, dry_run=dry_run
    )

    # TAP-5361: report on-disk homes *after* install/strip, not the pre-pass
    # snapshot (installing into an empty preferred home used to yield
    # dual_homes=[] while files.* still said WARN dual-home).
    on_disk_homes = [
        name for name in _KARPATHY_HOMES if karpathy_block.has_block(project_root / name)
    ]
    payload: dict[str, Any] = {
        "source_sha": karpathy_block.KARPATHY_GUIDELINES_SOURCE_SHA,
        "files": per_file,
        "cursor_rule": cursor_rule,
        "opted_out": opted_out,
        "primary": primary,
        "dual_homes": on_disk_homes if len(on_disk_homes) >= 2 else [],
    }
    if any(str(v).startswith("WARN dual-home") for v in per_file.values()):
        payload["dual_home_note"] = (
            "Secondary Karpathy copy retained on disk; "
            "non-force upgrade will not strip it — pass --force to remove."
        )
    return payload


def bump_skipped_version_stamps(
    project_root: Path,
    skip_files: set[str],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Refresh version markers on skip-listed AGENTS.md / CLAUDE.md only."""
    from tapps_mcp import __version__
    from tapps_mcp.pipeline.version_stamps import bump_stamp_if_stale

    results: dict[str, Any] = {}
    for name, marker in (
        ("AGENTS.md", "tapps-agents-version"),
        ("CLAUDE.md", "tapps-claude-version"),
    ):
        if name in skip_files:
            results[name] = bump_stamp_if_stale(
                project_root / name,
                marker,
                __version__,
                dry_run=dry_run,
            )
    return results
