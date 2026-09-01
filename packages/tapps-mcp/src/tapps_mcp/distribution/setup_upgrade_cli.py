"""CLI presentation for ``tapps-mcp upgrade``.

``pipeline.upgrade.upgrade_pipeline`` owns the actual work and returns a
structured result; everything here turns that dict into human-readable output.
Keeping the two apart is what lets the MCP tool and the CLI share one
implementation. Split out of ``setup_generator`` (TAP-5733).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from tapps_core.common.logging import get_logger
from tapps_mcp.distribution.setup_guidance import _verify_context7_live

log = get_logger(__name__)

# Component statuses that are not a problem when reported as a bare string.
_OK_COMPONENT_STATUSES = ("ok", "skipped", "up-to-date")
# Karpathy-block per-file actions that are not a problem.
_OK_KARPATHY_ACTIONS = frozenset({"unchanged", "added", "refreshed", "skipped_file_missing"})


def _echo_mcp_bundle_section(result: dict[str, Any]) -> None:
    """Report the resolved MCP bundle and how to opt down from it."""
    mcp_bundle = result.get("mcp_bundle")
    mcp_bundle_note = result.get("mcp_bundle_note")
    if mcp_bundle is None and not mcp_bundle_note:
        return
    click.echo(click.style("--- MCP bundle ---", bold=True))
    if mcp_bundle is not None:
        click.echo(f"  mcp_bundle: {mcp_bundle}")
    if mcp_bundle_note:
        click.echo(f"  note: {mcp_bundle_note}")
    click.echo("  opt-down: tapps-mcp mcp-bundle set developer|minimal|… then reload MCP")
    click.echo("")


def _echo_agents_md_section(result: dict[str, Any]) -> None:
    """Report the AGENTS.md smart-merge outcome."""
    click.echo(click.style("--- AGENTS.md ---", bold=True))
    agents = result.get("components", {}).get("agents_md", {})
    agents_action = agents.get("action", "unknown")
    agents_detail = agents.get("detail", "")
    agents_text = f"{agents_action} ({agents_detail})" if agents_detail else agents_action
    color = "green" if agents_action == "up-to-date" else "yellow"
    click.echo(click.style(f"  AGENTS.md: {agents_text}", fg=color))


def _echo_karpathy_section(result: dict[str, Any]) -> None:
    """Report the pinned Karpathy guidelines block (AGENTS.md + CLAUDE.md)."""
    kp = result.get("components", {}).get("karpathy_guidelines", {})
    if not kp:
        return
    click.echo("")
    click.echo(click.style("--- Karpathy guidelines ---", bold=True))
    sha = (kp.get("source_sha") or "")[:7]
    for rel, action in (kp.get("files") or {}).items():
        fg = "green" if action in _OK_KARPATHY_ACTIONS else "yellow"
        click.echo(click.style(f"  {rel}: {action}", fg=fg))
    if sha:
        click.echo(f"  pinned to: {sha}")


def _echo_component_dict(key: str, value: dict[str, Any]) -> None:
    """Report one structured per-platform component result."""
    created = value.get("scripts_created") or value.get("scripts_refreshed") or []
    if created:
        click.echo(click.style(f"  Generated {key}: {', '.join(created)}", fg="green"))
        return
    if value.get("hooks_action") == "refreshed":
        refreshed = value.get("scripts_refreshed") or []
        label = ", ".join(refreshed) if refreshed else key
        click.echo(click.style(f"  Refreshed {key}: {label}", fg="green"))
        return
    action = value.get("action")
    if action in {"created", "updated"}:
        rel = value.get("file", key)
        click.echo(click.style(f"  {key}: {action} ({rel})", fg="green"))
    elif action:
        click.echo(click.style(f"  {key}: {action}", fg="yellow"))
    else:
        click.echo(f"  {key.capitalize()} already up to date (skipped)")


def _echo_platform_section(platform: dict[str, Any]) -> None:
    """Report every component result for one platform."""
    host = platform.get("host", "unknown")
    click.echo("")
    click.echo(click.style(f"--- {host} ---", bold=True))

    if "error" in platform:
        click.echo(click.style(f"  Error: {platform['error']}", fg="red"))
        return

    for key, value in platform.get("components", {}).items():
        if isinstance(value, dict):
            _echo_component_dict(key, value)
        elif isinstance(value, str):
            fg = "green" if value in _OK_COMPONENT_STATUSES else "yellow"
            click.echo(click.style(f"  {key}: {value}", fg=fg))


def _echo_upgrade_summary(result: dict[str, Any], *, dry_run: bool) -> None:
    """Close out with the overall verdict, any warnings, and collected errors."""
    click.echo("")
    # TAP-6891: a working upgrade_skip_files entry used to be indistinguishable
    # from an unconfigured one — this confirms it was actually applied.
    applied = result.get("applied_skip_tokens", [])
    if applied:
        click.echo(
            click.style(
                f"  upgrade_skip_files: {len(applied)} token(s) applied: {', '.join(applied)}",
                fg="green",
            )
        )
    # TAP-6499: warnings used to be computed and dropped. Render them above the
    # verdict so an inert ``upgrade_skip_files`` entry, or an asset about to be
    # overwritten, is impossible to miss in either dry-run or real output.
    for warning in result.get("warnings", []):
        click.echo(click.style(f"  WARNING: {warning}", fg="yellow"))
    if result.get("warnings"):
        click.echo("")
    errors: list[str] = result.get("errors", [])
    if dry_run:
        click.echo(
            click.style("Dry run complete. Run without --dry-run to apply changes.", fg="cyan")
        )
    elif not errors:
        click.echo(click.style("Upgrade complete!", fg="green"))
        click.echo(
            "\nFor the full consumer requirements checklist, see docs/TAPPS_MCP_REQUIREMENTS.md"
        )
    else:
        for err in errors:
            click.echo(click.style(f"  Error: {err}", fg="red"))
        click.echo(click.style("Upgrade completed with issues. Check output above.", fg="yellow"))


def _format_upgrade_result(result: dict[str, Any], *, dry_run: bool = False) -> None:
    """Format the structured result from :func:`upgrade_pipeline` for CLI output.

    Translates the dict returned by ``upgrade_pipeline()`` into human-readable
    ``click.echo()`` lines, keeping a single source of truth for upgrade logic
    in ``pipeline/upgrade.py``.
    """
    prefix = "[DRY-RUN] " if dry_run else ""
    version = result.get("version", "?")

    click.echo("")
    click.echo(click.style(f"{prefix}=== TappsMCP Upgrade (v{version}) ===", bold=True))
    click.echo("")

    _echo_mcp_bundle_section(result)
    _echo_agents_md_section(result)
    _echo_karpathy_section(result)

    platforms: list[dict[str, Any]] = result.get("components", {}).get("platforms", [])
    for platform in platforms:
        _echo_platform_section(platform)

    _echo_upgrade_summary(result, dry_run=dry_run)


def _quiet_logging_for_json() -> None:
    """Route log output to stderr so ``--json`` keeps stdout pure JSON."""
    import logging

    from tapps_core.common.logging import setup_logging

    setup_logging(level="WARNING")
    # Belt-and-braces: drop stdlib loggers below WARNING as well in case
    # code paths invoked by the pipeline use stdlib logging directly.
    logging.getLogger().setLevel(logging.WARNING)


def _platform_for_host(mcp_host: str) -> str:
    """Map a CLI ``--host`` value onto the pipeline's platform name."""
    if mcp_host == "claude-code":
        return "claude"
    if mcp_host == "cursor":
        return "cursor"
    if mcp_host != "auto":
        return mcp_host
    return ""


def run_upgrade(
    *,
    mcp_host: str = "auto",
    project_root: str = ".",
    force: bool = False,
    dry_run: bool = False,
    scope: str = "project",
    emit_json: bool = False,
) -> bool:
    """Validate and update all TappsMCP-generated files.

    Called from the CLI ``upgrade`` command.  Delegates to
    :func:`~tapps_mcp.pipeline.upgrade.upgrade_pipeline` for the actual
    work and formats the structured result for human-readable CLI output.

    Args:
        mcp_host: Target host or ``"auto"`` for detection.
        project_root: Project root directory as a string path.
        force: If ``True``, overwrite all generated files without prompting.
        dry_run: If ``True``, show what would be updated without making changes.
        scope: ``"project"`` (default) or ``"user"``. Only affects ``claude-code``.
        emit_json: If ``True``, print the structured result dict as JSON to stdout
            instead of the text summary. Surfaces ``dry_run_summary`` and per-
            component ``managed_files`` / ``preserved_files`` so the CLI matches
            the MCP tool's precision (3.2.0/3.2.1).
    """
    import json

    from tapps_mcp.pipeline.upgrade import upgrade_pipeline

    if emit_json:
        _quiet_logging_for_json()

    root = Path(project_root).resolve()
    log.info(
        "upgrade_command",
        host=mcp_host,
        project_root=str(root),
        force=force,
        dry_run=dry_run,
        scope=scope,
    )

    result = upgrade_pipeline(
        root, platform=_platform_for_host(mcp_host), force=force, dry_run=dry_run
    )
    if emit_json:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        _format_upgrade_result(result, dry_run=dry_run)
        # Verify Context7 liveness post-upgrade (warn-only). Skipped for JSON
        # output to keep stdout pure, and for dry runs (nothing changed).
        if not dry_run:
            _verify_context7_live(root)
    return bool(result.get("success", True))
