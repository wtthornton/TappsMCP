"""CLI entry point for tapps-mcp."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import click

from tapps_mcp import __version__

if TYPE_CHECKING:
    from tapps_core.brain_bridge import BrainBridge


@click.group()
@click.version_option(package_name="tapps-mcp", version=__version__)
def main() -> None:
    """TappsMCP: MCP server providing code quality tools."""
    from tapps_mcp.distribution.exe_manager import cleanup_stale_old_exes

    cleanup_stale_old_exes()


@main.group("mcp-bundle")
def mcp_bundle_group() -> None:
    """Show or set the NLT MCP server bundle (``.tapps-mcp.yaml`` + host configs)."""


@mcp_bundle_group.command("show")
@click.option(
    "--project-root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Project root containing .tapps-mcp.yaml / host MCP configs.",
)
def mcp_bundle_show(project_root: Path) -> None:
    """Print yaml ``mcp_bundle``, on-disk ``nlt-*`` servers, and resolved name."""
    from tapps_mcp.distribution.mcp_bundle_cli import show_mcp_bundle

    info = show_mcp_bundle(project_root.resolve())
    click.echo(f"project_root: {info['project_root']}")
    click.echo(f"yaml mcp_bundle: {info['yaml_mcp_bundle'] or '(unset)'}")
    enabled = info["on_disk_servers"]
    click.echo("on-disk nlt-* servers: " + (", ".join(enabled) if enabled else "(none)"))
    click.echo(f"on-disk matches bundle: {info['on_disk_matches_bundle'] or '(custom/none)'}")
    click.echo(f"resolved: {info['resolved']}")
    click.echo("Flip with: tapps-mcp mcp-bundle set developer|minimal|full|… then reload MCP.")


@mcp_bundle_group.command("set")
@click.argument(
    "bundle",
    type=click.Choice(
        [
            "developer",
            "minimal",
            "memory",
            "planning",
            "docs",
            "release",
            "security",
            "audit",
            "full",
        ]
    ),
)
@click.option(
    "--project-root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Project root to update.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would change without writing files.",
)
def mcp_bundle_set(bundle: str, project_root: Path, dry_run: bool) -> None:
    """Write ``mcp_bundle`` to yaml and rewrite host MCP configs to that set.

    Opt down (e.g. ``developer``) or opt up (``full``) in one command, then
    reload MCP in the IDE. Upgrade will no longer re-expand a matching yaml.
    """
    from tapps_mcp.distribution.mcp_bundle_cli import set_mcp_bundle

    try:
        result = set_mcp_bundle(project_root.resolve(), bundle, dry_run=dry_run)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    prefix = "Would set" if dry_run else "Set"
    click.echo(
        click.style(
            f"{prefix} mcp_bundle={result['bundle']!r} ({len(result['enabled_servers'])} servers)",
            fg="green",
        )
    )
    click.echo("servers: " + ", ".join(result["enabled_servers"]))
    if result.get("yaml_written") or result.get("yaml_would_write"):
        click.echo("yaml: .tapps-mcp.yaml")
    if result["hosts_updated"]:
        click.echo("hosts: " + ", ".join(result["hosts_updated"]))
    if result["hosts_skipped"]:
        click.echo("skipped: " + ", ".join(result["hosts_skipped"]))
    click.echo(click.style(result["reload_hint"], fg="yellow"))


@main.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    help="Transport mode: stdio (local) or http (remote/container).",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind HTTP transport to.",
)
@click.option(
    "--port",
    default=8000,
    type=int,
    help="Port to bind HTTP transport to.",
)
@click.option(
    "--mode",
    type=click.Choice(["quality", "admin", "all"]),
    default="all",
    help=(
        "Tool mode: quality (coding session tools, ~14 tools), "
        "admin (setup/troubleshooting tools, ~12 tools), "
        "all (default, all tools — backward compatible)."
    ),
)
@click.option(
    "--profile",
    "tool_profile",
    type=click.Choice(
        [
            "nlt-build",
            "nlt-memory",
            "nlt-setup",
            "nlt-code-quality",
            "nlt-platform-admin",
            "core",
            "pipeline",
            "reviewer",
            "planner",
            "frontend",
            "developer",
            "quality",
            "admin",
            "full",
        ]
    ),
    default=None,
    help=(
        "Tool profile preset (Epic 109 / ADR-0016). Overrides --mode when set. "
        "Use nlt-build for daily coding (~20 tools, 9 eager)."
    ),
)
def serve(
    transport: str,
    host: str,
    port: int,
    mode: str,
    tool_profile: str | None,
) -> None:
    """Start the TappsMCP MCP server."""
    # Profile takes precedence over legacy --mode (TAP-485 / Epic 109).
    if tool_profile is not None:
        os.environ["TAPPS_MCP_TOOL_PRESET"] = tool_profile
    elif mode != "all":
        os.environ["TAPPS_MCP_TOOL_PRESET"] = mode

    from tapps_mcp.server import run_server

    run_server(transport=transport, host=host, port=port)


@main.command()
@click.option(
    "--host",
    "mcp_host",
    type=click.Choice(["claude-code", "cursor", "vscode", "auto"]),
    default="auto",
    help="Target MCP host to configure.",
)
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
@click.option(
    "--check",
    is_flag=True,
    help="Verify existing config instead of generating.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing tapps-mcp entries without prompting (non-interactive).",
)
@click.option(
    "--scope",
    type=click.Choice(["user", "project"]),
    default="project",
    help="Config scope: 'project' (.mcp.json in project root, default) or 'user' (~/.claude.json).",
)
@click.option(
    "--rules/--no-rules",
    default=True,
    help="Generate platform rule files (CLAUDE.md, .cursor/rules/).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be written without making changes.",
)
@click.option(
    "--engagement-level",
    type=click.Choice(["high", "medium", "low"]),
    default=None,
    help=(
        "LLM engagement level for generated rules "
        "(high=mandatory, medium=balanced, low=optional). "
        "Writes to .tapps-mcp.yaml."
    ),
)
@click.option(
    "--overwrite-tech-stack",
    is_flag=True,
    default=False,
    help="Overwrite existing TECH_STACK.md with auto-detected content (default: preserve).",
)
@click.option(
    "--allow-package-init",
    is_flag=True,
    default=False,
    help="Allow init when --project-root is the tapps-mcp package dir (.../packages/tapps-mcp).",
)
@click.option(
    "--with-docs-mcp",
    is_flag=True,
    default=False,
    help="Legacy monolith: also register docs-mcp (ignored with default NLT plugin).",
)
@click.option(
    "--bundle",
    "mcp_bundle",
    type=click.Choice(
        [
            "developer",
            "minimal",
            "memory",
            "planning",
            "docs",
            "release",
            "security",
            "audit",
            "full",
        ]
    ),
    default="full",
    help=(
        "NLT MCP plugin bundle to enable (default: full = all six nlt-* servers; "
        "ADR-0018). Later opt-down: tapps-mcp mcp-bundle set <bundle>."
    ),
)
@click.option(
    "--legacy-monolith/--no-legacy-monolith",
    "legacy_monolith",
    default=False,
    help="Write legacy tapps-mcp + docs-mcp entries instead of NLT nlt-* servers.",
)
@click.option(
    "--uv/--no-uv",
    "uv_flag",
    default=None,
    help=(
        "Force (or disable) 'uv run --extra ... tapps-mcp serve' style MCP config. "
        "Default: auto-detect uv.lock + pyproject.toml extras."
    ),
)
@click.option(
    "--uv-extra",
    default=None,
    help="Optional-dependency group for 'uv run --extra <name>' (default: auto).",
)
@click.option(
    "--with-context7",
    default=None,
    metavar="KEY",
    help=(
        "Set TAPPS_MCP_CONTEXT7_API_KEY in the MCP env block for live docs "
        "via Context7. Pass the key value, or 'prompt' to be asked interactively."
    ),
)
@click.option(
    "--mcp-transport",
    type=click.Choice(["stdio", "http"]),
    default=None,
    help=(
        "MCP transport for host config (ADR-0024). "
        "'http' writes streamableHttp URLs to the shared localhost fleet."
    ),
)
def init(
    mcp_host: str,
    project_root: str,
    check: bool,
    force: bool,
    scope: str,
    rules: bool,
    dry_run: bool,
    engagement_level: str | None,
    overwrite_tech_stack: bool,
    allow_package_init: bool,
    with_docs_mcp: bool,
    mcp_bundle: str,
    legacy_monolith: bool,
    uv_flag: bool | None,
    uv_extra: str | None,
    with_context7: str | None,
    mcp_transport: str | None,
) -> None:
    """Bootstrap TappsMCP in a project (MCP config, AGENTS.md, hooks, agents, skills, rules).

    Creates or merges `.tapps-mcp.yaml` (including `memory_hooks` when engagement implies it).
    Memory pipeline defaults (auto-save, recurring quick_check, architectural supersede, hooks)
    come from shipped `default.yaml` unless your YAML overrides them — see docs/MEMORY_REFERENCE.md.
    """
    from tapps_mcp.distribution.setup_generator import run_init

    uv_mode: str | None
    if uv_flag is None:
        uv_mode = None
    elif uv_flag:
        uv_mode = "on"
    else:
        uv_mode = "off"

    # Issue #79: resolve --with-context7 (interactive prompt or literal key).
    context7_key: str | None = None
    if with_context7 is not None:
        if with_context7.lower() == "prompt":
            context7_key = (
                click.prompt(
                    "TAPPS_MCP_CONTEXT7_API_KEY",
                    hide_input=True,
                    default="",
                ).strip()
                or None
            )
        else:
            context7_key = with_context7.strip() or None

    success = run_init(
        mcp_host=mcp_host,
        project_root=project_root,
        check=check,
        force=force,
        scope=scope,
        rules=rules,
        dry_run=dry_run,
        engagement_level=engagement_level,
        allow_package_init=allow_package_init,
        with_docs_mcp=with_docs_mcp,
        uv_mode=uv_mode,
        uv_extra=uv_extra,
        context7_api_key=context7_key,
        overwrite_tech_stack=overwrite_tech_stack,
        mcp_bundle=mcp_bundle,
        use_nlt_plugin=not legacy_monolith,
        mcp_transport=mcp_transport,
    )
    if not success:
        raise SystemExit(1)


@main.command()
@click.option(
    "--host",
    "mcp_host",
    type=click.Choice(["claude-code", "cursor", "vscode", "auto"]),
    default="auto",
    help="Target MCP host to upgrade.",
)
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite all generated files without prompting.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes.",
)
@click.option(
    "--scope",
    type=click.Choice(["user", "project"]),
    default="project",
    help="Config scope: 'project' (.mcp.json in project root, default) or 'user' (~/.claude.json).",
)
@click.option(
    "--json",
    "emit_json",
    is_flag=True,
    help=(
        "Emit the structured upgrade result as JSON instead of the text summary. "
        "With --dry-run, includes dry_run_summary.verdict plus per-component "
        "managed_files / preserved_files lists."
    ),
)
def upgrade(
    mcp_host: str,
    project_root: str,
    force: bool,
    dry_run: bool,
    scope: str,
    emit_json: bool,
) -> None:
    """Refresh generated files after upgrading the `tapps-mcp` package.

    Re-merges AGENTS.md, platform rules, hooks, agents, skills, and Claude/Cursor settings.
    Creates a timestamped backup under `.tapps-mcp/backups/` before overwriting.
    Preserves custom MCP command paths. Review `.tapps-mcp.yaml` after major upgrades if you
    relied on older default flags (memory pipeline, hooks). See docs/UPGRADE_FOR_CONSUMERS.md.

    v3.11.0 surfaces: refreshed `tapps-stop.sh` (warn-mode completion-gate telemetry on every
    project), new `tapps-upgrade` skill in `.claude/skills/` and `.cursor/skills/`,
    and DEPRECATED notices on wrapper skills (tapps-score, tapps-gate, tapps-validate, tapps-report)
    scheduled for removal in v3.12.0.
    """
    from tapps_mcp.distribution.setup_generator import run_upgrade

    success = run_upgrade(
        mcp_host=mcp_host,
        project_root=project_root,
        force=force,
        dry_run=dry_run,
        scope=scope,
        emit_json=emit_json,
    )
    if not success:
        raise SystemExit(1)


@main.command("session-end")
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root (for handoff-derived session_search query).",
)
def session_end_cmd(project_root: str) -> None:
    """Close the TAPPS session lifecycle (flywheel + session search).

    Best-effort mirror of ``tapps_session_end`` for hosts without MCP wiring.
    Always exits 0 — brain outages are reported in the output, not as errors.
    """
    import json
    from pathlib import Path

    from tapps_mcp.tools.session_end_helpers import run_session_end_sync

    root = _get_project_root() if project_root == "." else Path(project_root).resolve()
    data = run_session_end_sync(project_root=root)
    click.echo(json.dumps(data, indent=2))
    # Best-effort: degrade gracefully when brain is offline (TAP-3174).


# ---------------------------------------------------------------------------
# Handoff CLI group (TAP-3792)
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
@click.option(
    "--quick",
    is_flag=True,
    default=False,
    help="Quick mode: skip tool version checks for faster results.",
)
@click.option(
    "--json",
    "emit_json",
    is_flag=True,
    default=False,
    help=(
        "Emit the structured check results as JSON instead of the text report. "
        "Each check row carries `category` ('release-health' or "
        "'consumer-staleness'), which callers like blue/green post-flip smoke "
        "testing (TAP-6965) key on instead of the text report's PASS/WARN/FAIL lines."
    ),
)
def doctor(project_root: str, quick: bool, emit_json: bool) -> None:
    """Diagnose MCP config, bootstrap files, hooks, checkers, tapps-brain, and memory flags.

    Includes an informational **Memory pipeline (effective config)** row (resolved settings).
    Since v3.11.0 also reports `completion_gate_hook` (warns when ``.claude/hooks/tapps-stop.sh``
    is missing so warn-mode telemetry to ``.completion-gate-violations.jsonl`` is inactive)
    and a `usage_gaps` summary (gap count + top recommendation from ``tapps_usage``).

    Use `--quick` to skip per-tool version probes. Use `--json` for a structured
    report instead of the human-readable text one.
    """
    if emit_json:
        import json as _json

        from tapps_core.common.logging import bootstrap_logging_from_env
        from tapps_mcp.distribution.doctor import run_doctor_structured

        # Structlog is unconfigured on the bare CLI entry point and defaults
        # to printing to stdout, which would interleave log lines into the
        # JSON payload below. Route it to stderr first so stdout carries only
        # the JSON report -- callers like blue/green post-flip smoke testing
        # (TAP-6965) parse this stdout as a single JSON document.
        bootstrap_logging_from_env()
        data = run_doctor_structured(project_root=project_root, quick=quick)
        click.echo(_json.dumps(data))
        if not data["all_passed"]:
            raise SystemExit(1)
        return

    from tapps_mcp.distribution.doctor import run_doctor

    success = run_doctor(project_root=project_root, quick=quick)
    if not success:
        raise SystemExit(1)


@main.command("lane-evidence")
@click.argument(
    "log_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def lane_evidence_cmd(log_path: Path) -> None:
    """Parse a claude -p lane-log transcript for its final LINEAR EVIDENCE block (TAP-6614).

    Pure parser (zero LLM tokens): reads the JSONL transcript already on disk and prints
    structured JSON with the final assistant message, the ``--- LINEAR EVIDENCE ---`` block
    (if any), and ``evidence_found``. On a resumed session, uses the LAST completed turn.
    A log with no completed turn (lane killed mid-run) reports ``evidence_found: false``.
    """
    import json as _json

    from tapps_mcp.tools.lane_evidence import parse_lane_evidence

    data = parse_lane_evidence(log_path)
    click.echo(_json.dumps(data))


def _get_project_root() -> Path:
    """Resolve project root from TAPPS_MCP_PROJECT_ROOT env var or cwd."""
    from pathlib import Path

    root = os.environ.get("TAPPS_MCP_PROJECT_ROOT", ".")
    return Path(root).resolve()


def _brain_bridge_unavailable_message() -> str:
    return (
        "BrainBridge unavailable — configure memory.brain_http_url / "
        "TAPPS_MCP_MEMORY_BRAIN_HTTP_URL (and TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN "
        "for HTTP auth) or TAPPS_BRAIN_DATABASE_URL in .tapps-mcp.yaml "
        "(or environment) before using memory save/get. "
        "See docs/operations/CONSUMER-REPO-BRAIN-WIRING.md § CLI from shell."
    )


def _create_cli_brain_bridge() -> BrainBridge | None:
    """Create a BrainBridge for CLI memory save/get (HTTP or in-process DSN)."""
    from tapps_core.brain_bridge import BRAIN_PROFILE_SERVER, create_brain_bridge
    from tapps_core.config.settings import load_settings

    settings = load_settings(project_root=_get_project_root())
    return create_brain_bridge(settings, default_profile=BRAIN_PROFILE_SERVER)


# ---------------------------------------------------------------------------
# Knowledge & Expert CLI commands (Stories 53.2-53.4)
# ---------------------------------------------------------------------------


def _register_handoff_group() -> None:
    """Lazily register the handoff subcommand group."""
    from tapps_mcp.cli_handoff import handoff_group

    main.add_command(handoff_group)


def _register_deploy_commands() -> None:
    """Lazily register deployment commands."""
    from tapps_mcp.cli_deploy import deploy_local_cmd, upgrade_fleet_cmd

    main.add_command(deploy_local_cmd)
    main.add_command(upgrade_fleet_cmd)


def _register_ops_commands() -> None:
    """Lazily register operational CLI commands."""
    from tapps_mcp.cli_ops import (
        audit_fleet_cmd,
        auto_capture,
        build_cursor_plugin,
        build_plugin,
        bump_stamps,
        check_agents_md_stamp,
        cleanup_hook_backups,
        compact_index_cmd,
        lookup_docs_cmd,
        loop_metrics_record_cmd,
        migrate_memory_cmd,
        pipeline_mark_cmd,
        release_update_cmd,
        replace_exe_cmd,
        rollback,
        show_config,
        tool_usage_fleet_cmd,
        usage_gaps_hint_cmd,
        validate_skills_cmd,
    )

    for command in (
        build_plugin,
        build_cursor_plugin,
        validate_skills_cmd,
        cleanup_hook_backups,
        bump_stamps,
        rollback,
        show_config,
        check_agents_md_stamp,
        auto_capture,
        compact_index_cmd,
        replace_exe_cmd,
        pipeline_mark_cmd,
        lookup_docs_cmd,
        migrate_memory_cmd,
        release_update_cmd,
        usage_gaps_hint_cmd,
        audit_fleet_cmd,
        loop_metrics_record_cmd,
        tool_usage_fleet_cmd,
    ):
        main.add_command(command)


def _register_fleet_group() -> None:
    """Lazily register the fleet subcommand group."""
    from tapps_mcp.cli_fleet import fleet_group

    main.add_command(fleet_group)


def _register_memory_group() -> None:
    """Lazily register the memory subcommand group."""
    from tapps_mcp.cli_memory import memory_group

    main.add_command(memory_group)


def _register_validation_commands() -> None:
    """Lazily register standalone validation commands."""
    from tapps_mcp.cli_validation import quick_check_cmd, session_budget_cmd, validate_changed_cmd

    main.add_command(validate_changed_cmd)
    main.add_command(quick_check_cmd)
    main.add_command(session_budget_cmd)


def _register_benchmark_group() -> None:
    """Lazily register the benchmark subcommand group."""
    from tapps_mcp.benchmark.cli_commands import benchmark_group

    main.add_command(benchmark_group)


def _register_template_group() -> None:
    """Lazily register the template optimization subcommand group."""
    from tapps_mcp.benchmark.cli_commands import template_group

    main.add_command(template_group)


_register_handoff_group()
_register_deploy_commands()
_register_ops_commands()
_register_fleet_group()
_register_memory_group()
_register_validation_commands()
_register_benchmark_group()
_register_template_group()


if __name__ == "__main__":
    main()
