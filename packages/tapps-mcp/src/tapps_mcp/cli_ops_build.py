"""Build / plugin / stamp / rollback CLI commands."""

from __future__ import annotations

from pathlib import Path

import click


@click.command("build-plugin")
@click.option(
    "--output-dir",
    default="./tapps-mcp-plugin",
    type=click.Path(path_type=str),
    help="Output directory for the plugin (default: ./tapps-mcp-plugin/).",
)
@click.option(
    "--engagement-level",
    type=click.Choice(["high", "medium", "low"]),
    default="medium",
    help="Engagement level for generated rules.",
)
def build_plugin(output_dir: str, engagement_level: str) -> None:
    """Generate a Claude Code plugin directory from TappsMCP templates.

    Creates a complete plugin with skills, agents, hooks, MCP config,
    and platform rules that can be submitted to the Claude Code marketplace.
    """
    from pathlib import Path

    from tapps_mcp.distribution.plugin_builder import PluginBuilder

    builder = PluginBuilder(
        output_dir=Path(output_dir).resolve(),
        engagement_level=engagement_level,
    )
    plugin_dir = builder.build()
    result = builder.result

    click.echo(f"Plugin built at {plugin_dir}")
    for component, status in result.get("components", {}).items():
        if isinstance(status, list):
            click.echo(f"  {component}: {len(status)} items")
        else:
            click.echo(f"  {component}: {status}")


@click.command("build-cursor-plugin")
@click.option(
    "--output-dir",
    default="./plugin/cursor",
    type=click.Path(path_type=str),
    help="Output directory for the Cursor plugin (default: ./plugin/cursor/).",
)
@click.option(
    "--version",
    "plugin_version",
    default=None,
    help="Plugin version (default: tapps-mcp package version).",
)
def build_cursor_plugin(output_dir: str, plugin_version: str | None) -> None:
    """Generate the Cursor marketplace plugin bundle from TappsMCP templates."""
    from pathlib import Path

    from tapps_mcp.pipeline.platform_generators import generate_cursor_plugin_bundle

    out = Path(output_dir).resolve()
    result = generate_cursor_plugin_bundle(out, version=plugin_version)
    click.echo(f"Cursor plugin built at {out}")
    click.echo(f"  files_created: {len(result.get('files_created', []))}")


@click.command("validate-skills")
@click.option(
    "--path",
    "skills_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Directory containing skills (e.g. .claude/skills or .cursor/skills). Default: project root (checks both).",
)
@click.option(
    "--platform",
    type=click.Choice(["claude", "cursor", "both"]),
    default="both",
    help="Which platform skills to validate (default: both).",
)
def validate_skills_cmd(skills_path: str, platform: str) -> None:
    """Validate SKILL.md frontmatter against Agent Skills spec (Epic 76.4).

    Checks name (1-64 chars, lowercase+hyphens), description (1-1024 chars),
    and allowed-tools format (space-delimited for Claude). Run from project root
    or pass --path to a skills directory.
    """
    from pathlib import Path

    import yaml

    from tapps_mcp.pipeline.skills_validator import validate_skill_frontmatter

    root = Path(skills_path).resolve()
    dirs_to_check: list[Path] = []
    if platform in ("claude", "both") and (root / ".claude" / "skills").exists():
        dirs_to_check.append(root / ".claude" / "skills")
    if platform in ("cursor", "both") and (root / ".cursor" / "skills").exists():
        dirs_to_check.append(root / ".cursor" / "skills")
    if not dirs_to_check and root.name == "skills":
        dirs_to_check = [root]
    if not dirs_to_check:
        click.echo(
            "No skills directories found. Run from project root or pass --path to .claude/skills or .cursor/skills.",
            err=True,
        )
        raise SystemExit(1)

    errors: list[tuple[str, list[str]]] = []
    for skills_dir in dirs_to_check:
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            raw = skill_md.read_text(encoding="utf-8")
            parts = raw.split("---", 2)
            if len(parts) < 3:
                errors.append((f"{skill_dir.relative_to(root)}", ["Missing frontmatter ---"]))
                continue
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except Exception as e:
                errors.append((str(skill_dir.relative_to(root)), [str(e)]))
                continue
            check_allowed_tools = "cursor" not in str(skill_dir).lower()
            errs = validate_skill_frontmatter(
                skill_dir.name, fm, check_allowed_tools_format=check_allowed_tools
            )
            if errs:
                errors.append((str(skill_dir.relative_to(root)), errs))

    if errors:
        for path_str, err_list in errors:
            click.echo(f"{path_str}:", err=True)
            for err_msg in err_list:
                click.echo(f"  - {err_msg}", err=True)
        raise SystemExit(1)
    click.echo("All skills passed spec validation.")


@click.command("cleanup-hook-backups")
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List sidecars and stale storage copies without deleting.",
)
def cleanup_hook_backups(project_root: str, dry_run: bool) -> None:
    """Remove legacy hook ``*.pre-upgrade.*`` sidecars from ``.claude/hooks`` and ``.cursor/hooks``.

    Also prunes excess copies under ``.tapps-mcp/hook-backups/`` (keeps two per hook).
    Runs automatically at the end of ``tapps-mcp upgrade``; use this for one-off cleanup.
    """
    from pathlib import Path

    from tapps_mcp.pipeline.platform_hooks import cleanup_legacy_hook_sidecars

    root = Path(project_root).resolve()
    report = cleanup_legacy_hook_sidecars(root, dry_run=dry_run)
    sidecars = report["removed_sidecar_count"]
    pruned = report["pruned_storage_count"]
    prefix = "Would remove" if dry_run else "Removed"
    click.echo(
        f"{prefix} {sidecars} legacy sidecar(s), "
        f"{'would prune' if dry_run else 'pruned'} {pruned} excess storage backup(s)."
    )
    for rel, names in report.get("removed_sidecars", {}).items():
        if names:
            click.echo(f"  {rel}: {len(names)} sidecar(s)")
    for rel, names in report.get("pruned_storage", {}).items():
        if names:
            click.echo(f"  {rel}: {len(names)} stale storage copy(ies)")


@click.command("bump-stamps")
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show stamp changes without writing files.",
)
def bump_stamps(project_root: str, dry_run: bool) -> None:
    """Bump AGENTS.md / CLAUDE.md version stamps to the installed package version.

    Use when those files are in ``upgrade_skip_files`` and doctor reports a
    stamp mismatch. Does not merge template content — stamps only.
    """
    from pathlib import Path

    from tapps_mcp import __version__
    from tapps_mcp.pipeline.version_stamps import bump_stamp_if_stale

    root = Path(project_root).resolve()
    targets = (
        (root / "AGENTS.md", "tapps-agents-version"),
        (root / "CLAUDE.md", "tapps-claude-version"),
    )
    changed = 0
    for path, key in targets:
        result = bump_stamp_if_stale(path, key, __version__, dry_run=dry_run)
        action = result.get("action", "unknown")
        if action in {"bumped-stamp", "would-bump-stamp"}:
            changed += 1
        click.echo(f"{path.name}: {action} {result}")
    if changed == 0:
        click.echo("No stamps needed updating.")
    elif dry_run:
        click.echo(f"Would update {changed} stamp(s). Re-run without --dry-run to apply.")


@click.command()
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
@click.option(
    "--backup-id",
    default=None,
    help="Restore a specific backup by timestamp.",
)
@click.option(
    "--list",
    "list_backups",
    is_flag=True,
    help="List available backups.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be restored without making changes.",
)
def rollback(project_root: str, backup_id: str | None, list_backups: bool, dry_run: bool) -> None:
    """Restore configuration files from a pre-upgrade backup.

    By default restores from the latest backup.
    Use --backup-id to select a specific one, or --list to see all.
    """
    from pathlib import Path

    from tapps_mcp.distribution.rollback import BackupManager

    root = Path(project_root).resolve()
    mgr = BackupManager(root)

    if list_backups:
        backups = mgr.list_backups()
        if not backups:
            click.echo("No backups found.")
            return
        click.echo(f"{'Timestamp':<22} {'Version':<12} {'Files':<6} Path")
        click.echo("-" * 70)
        for b in backups:
            click.echo(f"{b.timestamp:<22} {b.version:<12} {b.file_count:<6} {b.path}")
        return

    backup_dir = None
    if backup_id:
        backup_path = root / ".tapps-mcp" / "backups" / backup_id
        if not backup_path.exists():
            click.echo(f"Backup '{backup_id}' not found.", err=True)
            raise SystemExit(1)
        backup_dir = backup_path

    restored = mgr.restore_backup(backup_dir, dry_run=dry_run)
    if not restored:
        click.echo("No files to restore (no backups available).", err=True)
        raise SystemExit(1)

    prefix = "[dry-run] Would restore" if dry_run else "Restored"
    click.echo(f"{prefix} {len(restored)} file(s):")
    for f in restored:
        click.echo(f"  {f}")


@click.command("show-config")
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
def show_config(project_root: str) -> None:
    """Dump the current effective TappsMCP configuration as YAML."""
    from pathlib import Path

    import yaml

    from tapps_core.config.settings import load_settings

    root = Path(project_root).resolve()
    settings = load_settings(project_root=root)
    data = settings.model_dump(mode="json")
    # Redact secret values
    if data.get("context7_api_key"):
        data["context7_api_key"] = "***"
    click.echo(yaml.dump(data, default_flow_style=False, sort_keys=False))


@click.command(name="replace-exe")
@click.argument("new_exe_path", type=click.Path(exists=True))
def replace_exe_cmd(new_exe_path: str) -> None:
    """Replace the running exe with a new version (frozen exe only).

    Renames the currently running tapps-mcp.exe to .old, then copies
    NEW_EXE_PATH to the original location. Old processes keep running
    from the renamed file. New sessions pick up the new binary.

    The .old backup is cleaned up automatically on next startup.
    """
    from tapps_mcp.distribution.exe_manager import run_replace_exe

    success = run_replace_exe(new_exe_path)
    if not success:
        raise SystemExit(1)


@click.command("migrate-memory")
@click.option(
    "--project-root",
    default=".",
    help="Project root containing .tapps-mcp/memory/*.db",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Discover entries and print the summary without writing to brain.",
)
@click.option(
    "--validate-only",
    is_flag=True,
    help="Alias of --dry-run that also reports per-db parse failures.",
)
@click.option(
    "--rollback",
    "rollback_run_id",
    metavar="RUN_ID",
    default=None,
    help="Delete entries tagged with migration-run:<RUN_ID> from brain.",
)
def migrate_memory_cmd(
    project_root: str,
    dry_run: bool,
    validate_only: bool,
    rollback_run_id: str | None,
) -> None:
    """Migrate .tapps-mcp/memory/*.db entries into tapps-brain (TAP-415)."""
    from pathlib import Path

    from tapps_core.brain_bridge import create_brain_bridge
    from tapps_core.config.settings import load_settings
    from tapps_mcp.pipeline.migrate_memory import (
        rollback_migration_sync,
        run_migration_sync,
    )

    settings = load_settings()
    bridge = create_brain_bridge(settings, default_profile="operator")
    if bridge is None:
        click.echo(
            click.style(
                "BrainBridge unavailable — configure TAPPS_BRAIN_DATABASE_URL "
                "or TAPPS_MCP_MEMORY_BRAIN_HTTP_URL before running migrate-memory.",
                fg="red",
            )
        )
        raise SystemExit(2)

    if rollback_run_id:
        result = rollback_migration_sync(bridge, rollback_run_id)
        click.echo(
            f"rollback run_id={rollback_run_id} deleted={result['deleted']} ok={result['ok']}"
        )
        if result.get("errors"):
            click.echo(click.style(f"errors: {result['errors']}", fg="yellow"))
        if not result["ok"]:
            raise SystemExit(1)
        return

    report = run_migration_sync(
        Path(project_root).resolve(),
        bridge,
        dry_run=dry_run,
        validate_only=validate_only,
    )
    click.echo(report.summary())
    if report.failures:
        click.echo(click.style(f"failures: {report.failures[:5]}", fg="yellow"))
    if report.failed > 0 and not dry_run and not validate_only:
        raise SystemExit(1)


@click.command("release-update")
@click.option("--version", required=True, help="New release version, e.g. 1.5.0")
@click.option("--prev-version", required=True, help="Previous version, e.g. 1.4.2")
@click.option("--bump-type", default="", help="patch | minor | major (inferred if blank)")
@click.option("--team", default="", help="Linear team name/ID")
@click.option("--project", default="", help="Linear project name/slug")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Return body without requiring validation pass"
)
def release_update_cmd(
    version: str,
    prev_version: str,
    bump_type: str,
    team: str,
    project: str,
    dry_run: bool,
) -> None:
    """Generate and validate a Linear release update document body (TAP-1112)."""
    import asyncio
    import json

    from tapps_mcp.server_release_tools import tapps_release_update

    result = asyncio.run(
        tapps_release_update(
            version=version,
            prev_version=prev_version,
            bump_type=bump_type,
            team=team,
            project=project,
            dry_run=dry_run,
        )
    )
    click.echo(json.dumps(result, indent=2))
