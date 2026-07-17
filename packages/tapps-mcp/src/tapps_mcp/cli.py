"""CLI entry point for tapps-mcp."""

from __future__ import annotations

import os
from pathlib import Path

import click

from tapps_mcp import __version__


@click.group()
@click.version_option(package_name="tapps-mcp", version=__version__)
def main() -> None:
    """TappsMCP: MCP server providing code quality tools."""
    from tapps_mcp.distribution.exe_manager import cleanup_stale_old_exes

    cleanup_stale_old_exes()


@main.group()
def fleet() -> None:
    """Manage the host-level shared HTTP MCP fleet (ADR-0024)."""


@fleet.command("start")
@click.option("--force", is_flag=True, help="Restart servers that are already running.")
def fleet_start(force: bool) -> None:
    """Start six long-lived HTTP NLT servers on localhost:8760-8765."""
    from tapps_mcp.distribution.fleet_control import ensure_fleet_env_file, start_fleet

    ensure_fleet_env_file()
    result = start_fleet(force=force)
    click.echo(f"Fleet code root: {result['code_root']}")
    click.echo(f"Fleet host: {result['host']}")
    if result["started"]:
        click.echo(click.style("Started: " + ", ".join(result["started"]), fg="green"))
    if result["skipped"]:
        click.echo("Already running: " + ", ".join(result["skipped"]))
    for err in result["errors"]:
        click.echo(click.style(err, fg="red"))
    if result["errors"]:
        raise SystemExit(1)


@fleet.command("stop")
def fleet_stop() -> None:
    """Stop all HTTP fleet servers."""
    from tapps_mcp.distribution.fleet_control import stop_fleet

    result = stop_fleet()
    if result["stopped"]:
        click.echo(click.style("Stopped: " + ", ".join(result["stopped"]), fg="green"))
    if result["missing"]:
        click.echo("Not running: " + ", ".join(result["missing"]))


@fleet.command("status")
def fleet_status_cmd() -> None:
    """Show HTTP fleet process and reachability status."""
    from tapps_mcp.distribution.fleet_control import fleet_status

    result = fleet_status()
    click.echo(f"Running {result['running']}/{result['total']} on {result['host']}")
    click.echo(f"Code root: {result['code_root']}")
    click.echo(f"Env: {result['env_file']}")
    for server_id, row in result["servers"].items():
        state = "ok" if row["reachable"] else ("pid" if row["alive"] else "down")
        color = "green" if row["reachable"] else ("yellow" if row["alive"] else "red")
        click.echo(
            click.style(
                f"  {server_id}: {state} pid={row['pid']} url={row['url']}",
                fg=color,
            )
        )


@fleet.command("restart")
@click.option("--force", is_flag=True, help="Force restart even when PIDs look healthy.")
@click.option(
    "--skip-smoke",
    is_flag=True,
    default=False,
    help="Skip post-restart MCP handshake smoke (not recommended).",
)
@click.option(
    "--project-root",
    default=".",
    show_default=True,
    help="Project root sent as X-Tapps-Project-Root during smoke probes.",
)
def fleet_restart(force: bool, skip_smoke: bool, project_root: str) -> None:
    """Stop then start the HTTP fleet and verify MCP handshakes."""
    from tapps_mcp.distribution.fleet_control import (
        restart_fleet_with_smoke,
        start_fleet,
        stop_fleet,
    )

    root = Path(project_root).resolve()
    if skip_smoke:
        stop_fleet()
        result = start_fleet(force=True)
        click.echo(click.style("Restarted: " + ", ".join(result["started"]), fg="green"))
        for err in result.get("errors", []):
            click.echo(click.style(err, fg="red"))
        if result.get("errors"):
            raise SystemExit(1)
        return

    report = restart_fleet_with_smoke(project_root=root)
    click.echo(click.style("Restarted: " + ", ".join(report["started"]), fg="green"))
    smoke = report["smoke"]
    for server_id, row in smoke.get("servers", {}).items():
        if row.get("ok"):
            click.echo(
                click.style(
                    f"  smoke {server_id}: ok ({row.get('tool_count', 0)} tools)",
                    fg="green",
                )
            )
        else:
            click.echo(click.style(f"  smoke {server_id}: FAIL ({row.get('stage')})", fg="red"))
    for err in report.get("errors", []):
        click.echo(click.style(err, fg="red"))
    if not report.get("ok"):
        raise SystemExit(1)


@fleet.command("smoke")
@click.option(
    "--project-root",
    default=".",
    show_default=True,
    help="Project root sent as X-Tapps-Project-Root during smoke probes.",
)
def fleet_smoke_cmd(project_root: str) -> None:
    """Verify initialize + tools/list on every HTTP fleet server (Cursor-like)."""
    from tapps_mcp.distribution.fleet_smoke import smoke_test_fleet

    root = Path(project_root).resolve()
    result = smoke_test_fleet(project_root=root)
    for server_id, row in result.get("servers", {}).items():
        if row.get("ok"):
            click.echo(
                click.style(
                    f"PASS {server_id}: {row.get('tool_count', 0)} tools @ {row.get('url')}",
                    fg="green",
                )
            )
        else:
            detail = row.get("error") or f"http={row.get('http_status')}"
            click.echo(
                click.style(
                    f"FAIL {server_id} ({row.get('stage', '?')}): {detail}",
                    fg="red",
                )
            )
    if not result.get("ok"):
        raise SystemExit(1)
    click.echo(click.style(f"All {result['total']} fleet servers passed MCP smoke.", fg="green"))


@fleet.command("ensure")
def fleet_ensure() -> None:
    """Restart the fleet only when it is not fully reachable (watchdog entry)."""
    from tapps_mcp.distribution.fleet_control import ensure_fleet_running

    result = ensure_fleet_running()
    if result["action"] == "none":
        click.echo(click.style("Fleet healthy: all servers reachable", fg="green"))
        return
    unhealthy = ", ".join(result["unhealthy"])
    if result["action"] == "defer":
        # First strike: a single bad poll defers a restart so transient host
        # overload does not sever every client's session (debounce).
        click.echo(
            click.style(
                f"Fleet degraded ({unhealthy}); deferring restart pending "
                "confirmation on the next poll",
                fg="yellow",
            )
        )
        return
    click.echo(
        click.style(
            f"Fleet unhealthy ({unhealthy}); recovered via {result['action']}",
            fg="yellow",
        )
    )


@fleet.command("install-systemd")
def fleet_install_systemd() -> None:
    """Install systemd user units for the fleet + health-aware watchdog timer."""
    from tapps_mcp.distribution.fleet_control import install_systemd_user_unit

    paths = install_systemd_user_unit()
    for path in paths:
        click.echo(click.style(f"Wrote {path}", fg="green"))
    click.echo("Enable with:")
    click.echo("  systemctl --user daemon-reload")
    click.echo("  systemctl --user enable --now tapps-mcp-fleet.service")
    click.echo("  systemctl --user enable --now tapps-mcp-fleet-watch.timer")


@fleet.command("audit-consumers")
@click.option(
    "--scan-parent",
    default="",
    help="Parent directory to scan for consumers (default: ~/code).",
)
@click.option(
    "--roots",
    default="",
    help="Comma-separated project roots (skips scan-parent when set).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def fleet_audit_consumers(scan_parent: str, roots: str, as_json: bool) -> None:
    """Audit Cursor/VS Code/Claude MCP configs against the shared HTTP fleet."""
    import json as json_lib

    from tapps_mcp.distribution.fleet_consumers import audit_consumers

    root_list = [Path(p.strip()) for p in roots.split(",") if p.strip()] or None
    parent = Path(scan_parent).expanduser() if scan_parent.strip() else None
    report = audit_consumers(scan_parent=parent, roots=root_list)
    if as_json:
        click.echo(json_lib.dumps(report, indent=2))
    else:
        click.echo(
            f"package={report['package_version']} projects={report['total']} "
            f"ok={report['ok']} fail={report['fail']}"
        )
        for row in report["projects"]:
            status = "OK" if row["ok"] else f"FAIL({len(row['issues'])})"
            color = "green" if row["ok"] else "red"
            click.echo(click.style(f"  {row['project']:<28} {status}", fg=color))
            for issue in row["issues"]:
                click.echo(f"    - {issue}")
    if report["fail"]:
        raise SystemExit(1)


@fleet.command("repair-consumers")
@click.option(
    "--scan-parent",
    default="",
    help="Parent directory to scan for consumers (default: ~/code).",
)
@click.option(
    "--roots",
    default="",
    help="Comma-separated project roots (skips scan-parent when set).",
)
@click.option(
    "--audit/--no-audit",
    default=True,
    show_default=True,
    help="Re-audit after repair and exit non-zero on remaining failures.",
)
def fleet_repair_consumers(scan_parent: str, roots: str, audit: bool) -> None:
    """Repair consumer MCP configs to match the shared HTTP fleet (ADR-0024)."""
    from tapps_mcp.distribution.fleet_consumers import audit_consumers, repair_consumers

    root_list = [Path(p.strip()) for p in roots.split(",") if p.strip()] or None
    parent = Path(scan_parent).expanduser() if scan_parent.strip() else None
    result = repair_consumers(scan_parent=parent, roots=root_list)
    click.echo(
        f"repaired={result['repaired_count']} unchanged={result['unchanged_count']}"
    )
    for row in result["repaired"]:
        click.echo(click.style(f"  {row['project']}: {', '.join(row['changes'])}", fg="green"))
    if not audit:
        return
    report = audit_consumers(scan_parent=parent, roots=root_list)
    click.echo(f"post-audit ok={report['ok']} fail={report['fail']}")
    for row in report["projects"]:
        if row["ok"]:
            continue
        click.echo(click.style(f"  FAIL {row['project']}", fg="red"))
        for issue in row["issues"]:
            click.echo(f"    - {issue}")
    if report["fail"]:
        raise SystemExit(1)


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
        "Use nlt-build for daily coding (~16 tools, 9 eager)."
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
    type=click.Choice(["developer", "minimal", "planning", "docs", "release", "full"]),
    default="full",
    help="NLT MCP plugin bundle to enable (default: full = all six nlt-* servers; ADR-0018).",
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


@main.group()
def handoff() -> None:
    """Cross-session handoff utilities."""


@handoff.command("write")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="Read handoff markdown from a file (else stdin when piped).",
)
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root directory.",
)
@click.option(
    "--no-brain-mirror",
    is_flag=True,
    help="Skip brain mirror (file only).",
)
@click.option(
    "--session-end",
    "with_session_end",
    is_flag=True,
    help="Also run session-end flywheel after write.",
)
@click.option(
    "--allow-lint-warnings",
    is_flag=True,
    help="Allow advisory lint warnings (still fails on P0/Open errors).",
)
def handoff_write(
    file_path: str | None,
    project_root: str,
    no_brain_mirror: bool,
    with_session_end: bool,
    allow_lint_warnings: bool,
) -> None:
    """Atomically write session handoff file, mirror to brain, and lint schema."""
    import json
    import sys
    from pathlib import Path

    from tapps_mcp.tools.handoff_write import HandoffWriteError, write_handoff_sync

    root = _get_project_root() if project_root == "." else Path(project_root).resolve()
    if file_path:
        markdown = Path(file_path).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        markdown = sys.stdin.read()
    else:
        click.echo("Provide --file or pipe handoff markdown on stdin.", err=True)
        raise SystemExit(2)

    if not markdown.strip():
        click.echo("Handoff markdown is empty.", err=True)
        raise SystemExit(2)

    try:
        result = write_handoff_sync(
            root,
            markdown,
            mirror_brain=not no_brain_mirror,
            run_session_end=with_session_end,
            fail_on_lint_errors=True,
        )
    except HandoffWriteError as exc:
        click.echo("Handoff schema lint failed:", err=True)
        for err in exc.errors:
            click.echo(f"  error: {err}", err=True)
        for warn in exc.warnings:
            click.echo(f"  warning: {warn}", err=True)
        raise SystemExit(1) from exc

    if not allow_lint_warnings and result.lint.warnings:
        click.echo("Handoff lint warnings (use --allow-lint-warnings to persist anyway):", err=True)
        for warn in result.lint.warnings:
            click.echo(f"  warning: {warn}", err=True)
        raise SystemExit(1)

    payload = {
        "file_path": result.file_path,
        "linear_p0": result.doc.linear_p0,
        "metadata": result.metadata,
        "lint": {
            "ok": result.lint.ok,
            "errors": result.lint.errors,
            "warnings": result.lint.warnings,
        },
        "brain_mirror": result.brain_mirror,
        "session_end": result.session_end,
    }
    click.echo(json.dumps(payload, indent=2))


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
def doctor(project_root: str, quick: bool) -> None:
    """Diagnose MCP config, bootstrap files, hooks, checkers, tapps-brain, and memory flags.

    Includes an informational **Memory pipeline (effective config)** row (resolved settings).
    Since v3.11.0 also reports `completion_gate_hook` (warns when ``.claude/hooks/tapps-stop.sh``
    is missing so warn-mode telemetry to ``.completion-gate-violations.jsonl`` is inactive)
    and a `usage_gaps` summary (gap count + top recommendation from ``tapps_usage``).

    Use `--quick` to skip per-tool version probes.
    """
    from tapps_mcp.distribution.doctor import run_doctor

    success = run_doctor(project_root=project_root, quick=quick)
    if not success:
        raise SystemExit(1)


@main.command("usage-gaps-hint")
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
def usage_gaps_hint_cmd(project_root: str) -> None:
    """Print a one-line prior-session pipeline reminder for SessionStart hooks (TAP-3578)."""
    from pathlib import Path

    from tapps_mcp.tools.usage import format_session_start_gap_hint

    hint = format_session_start_gap_hint(Path(project_root).resolve())
    if hint:
        click.echo(hint)


@main.command("audit-fleet")
@click.option(
    "--period",
    type=click.Choice(["1d", "7d", "30d"]),
    default="1d",
    show_default=True,
    help="Trailing window for tool-call and pipeline metrics.",
)
@click.option(
    "--roots",
    default="",
    help="Comma-separated project roots (default: TAPPS_FLEET_ROOTS or scan parent dir).",
)
@click.option(
    "--scan-parent",
    default=".",
    help="When --roots is empty, scan immediate children of this directory.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--no-brain",
    is_flag=True,
    default=False,
    help="Skip brain telemetry merge (local JSONL only).",
)
def audit_fleet_cmd(
    period: str,
    roots: str,
    scan_parent: str,
    output_format: str,
    no_brain: bool,
) -> None:
    """Audit TAPPS usage across bootstrapped projects (local JSONL + brain merge).

    Discovers projects via ``--roots``, ``TAPPS_FLEET_ROOTS``, or by scanning
    ``--scan-parent`` for ``.tapps-mcp.yaml`` markers.
    """
    import json
    from pathlib import Path

    from tapps_mcp.tools.fleet_audit import format_fleet_audit_markdown, run_fleet_audit

    explicit: list[Path] | None = None
    if roots.strip():
        explicit = [Path(p.strip()) for p in roots.split(",") if p.strip()]

    report = run_fleet_audit(
        period=period,
        roots=explicit,
        scan_parent=Path(scan_parent),
        include_brain=not no_brain,
    )
    if output_format == "markdown":
        click.echo(format_fleet_audit_markdown(report))
    else:
        click.echo(json.dumps(report, indent=2))


@main.command("loop-metrics-record")
def loop_metrics_record_cmd() -> None:
    """Record loop-metrics from Cursor/Claude stop-hook stdin (TAP-3918)."""
    import json
    import sys

    from tapps_mcp.tools.loop_metrics import record_loop_metrics_from_hook_payload

    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    result = record_loop_metrics_from_hook_payload(payload)
    followup = result.get("followup_message")
    if followup:
        click.echo(json.dumps({"followup_message": followup}))


@main.command("tool-usage-fleet")
@click.option(
    "--period",
    type=click.Choice(["1d", "7d", "30d"]),
    default="1d",
    show_default=True,
    help="Trailing window for tool-call metrics.",
)
@click.option(
    "--roots",
    default="",
    help="Comma-separated project roots (default: TAPPS_FLEET_ROOTS or scan parent dir).",
)
@click.option(
    "--scan-parent",
    default=".",
    help="When --roots is empty, scan immediate children of this directory.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--no-brain",
    is_flag=True,
    default=False,
    help="Skip brain telemetry merge (local JSONL only).",
)
def tool_usage_fleet_cmd(
    period: str,
    roots: str,
    scan_parent: str,
    output_format: str,
    no_brain: bool,
) -> None:
    """Per-tool fleet usage leaderboard (TAP-3919)."""
    import json
    from pathlib import Path

    from tapps_mcp.tools.fleet_audit import (
        format_tool_usage_fleet_markdown,
        run_tool_usage_fleet,
    )

    explicit: list[Path] | None = None
    if roots.strip():
        explicit = [Path(p.strip()) for p in roots.split(",") if p.strip()]

    report = run_tool_usage_fleet(
        period=period,
        roots=explicit,
        scan_parent=Path(scan_parent),
        include_brain=not no_brain,
    )
    if output_format == "markdown":
        click.echo(format_tool_usage_fleet_markdown(report))
    else:
        click.echo(json.dumps(report, indent=2))


@main.command("deploy-local")
@click.option(
    "--tapps-checkout",
    default=".",
    show_default=True,
    help="Path to tapps-mcp monorepo checkout.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print planned release path and flip without executing.",
)
@click.option(
    "--skip-gate",
    is_flag=True,
    default=False,
    help="Skip quiescence gate (pytest-in-checkout check).",
)
@click.option(
    "--force-build",
    is_flag=True,
    default=False,
    help="Rebuild release even when the version-sha directory already exists.",
)
@click.option(
    "--keep-releases",
    default=3,
    show_default=True,
    type=int,
    help="Number of release dirs to retain after GC.",
)
@click.option(
    "--skip-doctor-smoke",
    is_flag=True,
    default=False,
    help="Skip doctor --quick during smoke test.",
)
def deploy_local_cmd(
    tapps_checkout: str,
    dry_run: bool,
    skip_gate: bool,
    force_build: bool,
    keep_releases: int,
    skip_doctor_smoke: bool,
) -> None:
    """Blue/green deploy dev-monorepo MCP CLIs to ~/.tapps-mcp/current.

    Builds an immutable release venv, smoke-tests it, atomically flips the
    ``current`` symlink, and GCs old releases. Running MCP servers stay pinned
    to their release dir; reload MCP in Cursor to pick up the new build.
    """
    import json
    from pathlib import Path

    from tapps_mcp.distribution.blue_green import deploy_blue_green

    checkout = Path(tapps_checkout).resolve()
    report = deploy_blue_green(
        checkout,
        skip_gate=skip_gate,
        dry_run=dry_run,
        force_build=force_build,
        keep_releases=keep_releases,
        run_doctor_smoke=not skip_doctor_smoke,
    )
    click.echo(json.dumps(report, indent=2))
    if not report.get("ok"):
        raise SystemExit(1)


@main.command("upgrade-fleet")
@click.option(
    "--roots",
    default="",
    help=(
        "Comma-separated project roots. Default: TAPPS_FLEET_ROOTS, scan parent, "
        "or maintainer list (AgentForge, NLTlabsPE, ReportLab, tapps-mcp, ~/NewCompanyIdeas)."
    ),
)
@click.option(
    "--scan-parent",
    default=str(Path.home() / "code"),
    show_default=True,
    help="When --roots is empty, scan immediate children for .tapps-mcp.yaml.",
)
@click.option(
    "--bundle",
    "mcp_bundle",
    type=click.Choice(["developer", "minimal", "planning", "docs", "release", "full"]),
    default="full",
    show_default=True,
    help="NLT MCP bundle to write per project (full = all six nlt-* servers; developer = build+memory+linear).",
)
@click.option(
    "--uv-mode",
    type=click.Choice(["auto", "on", "off"]),
    default="off",
    show_default=True,
    help="MCP launch form: global binaries (off), uv run (on), or auto-detect.",
)
@click.option(
    "--host",
    "mcp_host",
    type=click.Choice(["claude-code", "cursor", "vscode", "auto"]),
    default="auto",
    show_default=True,
    help="MCP host config to refresh.",
)
@click.option(
    "--reinstall-clis",
    is_flag=True,
    default=False,
    help="Reinstall global tapps-mcp + docs-mcp from --tapps-checkout (uv tool install).",
)
@click.option(
    "--blue-green-deploy/--inplace-cli-reinstall",
    default=True,
    show_default=True,
    help="With --reinstall-clis, use immutable deploy-local (default, ADR-0023). "
    "In-place uv tool install mutates the venv under live MCP servers.",
)
@click.option(
    "--force-inplace-cli-reinstall",
    is_flag=True,
    default=False,
    help="Allow in-place uv tool reinstall even when live MCP servers are running "
    "(kills stdio servers — avoid unless MCP is stopped).",
)
@click.option(
    "--tapps-checkout",
    default=".",
    show_default=True,
    help="Path to tapps-mcp monorepo when using --reinstall-clis.",
)
@click.option(
    "--skip-mcp-refresh",
    is_flag=True,
    default=False,
    help="Run upgrade only; skip init MCP bundle refresh.",
)
@click.option(
    "--skip-doctor",
    is_flag=True,
    default=False,
    help="Skip per-project doctor --quick after upgrade.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print planned commands without executing.",
)
@click.option(
    "--force/--no-force",
    default=True,
    show_default=True,
    help="Overwrite generated files (recommended for fleet migrations).",
)
@click.option(
    "--import-legacy-doc-cache",
    is_flag=True,
    default=False,
    help="Import .tapps-mcp-cache into tapps-brain before MCP refresh (ADR-0014).",
)
@click.option(
    "--strip-context7-env",
    is_flag=True,
    default=False,
    help="Regenerate MCP config without consumer Context7 key (ADR-0014).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="markdown",
    show_default=True,
    help="Output format.",
)
def upgrade_fleet_cmd(
    roots: str,
    scan_parent: str,
    mcp_bundle: str,
    uv_mode: str,
    mcp_host: str,
    reinstall_clis: bool,
    blue_green_deploy: bool,
    force_inplace_cli_reinstall: bool,
    tapps_checkout: str,
    skip_mcp_refresh: bool,
    skip_doctor: bool,
    dry_run: bool,
    force: bool,
    import_legacy_doc_cache: bool,
    strip_context7_env: bool,
    output_format: str,
) -> None:
    """Upgrade TAPPS scaffolding + NLT MCP config across bootstrapped projects.

    Discovers repos via ``--roots``, ``TAPPS_FLEET_ROOTS``, ``--scan-parent``,
    or the maintainer default list. Migrates legacy ``tapps-mcp`` + ``docs-mcp``
    monolith entries to NLT ``nlt-*`` servers on ``upgrade --force``.

    Set fleet roots once::

        export TAPPS_FLEET_ROOTS=\\
          ~/code/AgentForge,~/code/NLTlabsPE,~/code/ReportLab,~/code/tapps-mcp

    Then::

        tapps-mcp upgrade-fleet --reinstall-clis --bundle full --uv-mode off

    Opt into blue/green zero-downtime deploy (ADR-0019) with ``--blue-green-deploy``.
    When live MCP ``serve`` processes are detected, in-place reinstall auto-promotes
    to blue/green unless ``--force-inplace-cli-reinstall`` is set.
    """
    import json
    from pathlib import Path

    from tapps_mcp.tools.fleet_upgrade import format_fleet_upgrade_markdown, run_fleet_upgrade

    explicit: list[Path] | None = None
    if roots.strip():
        explicit = [Path(p.strip()) for p in roots.split(",") if p.strip()]

    report = run_fleet_upgrade(
        roots=explicit,
        scan_parent=Path(scan_parent),
        force=force,
        dry_run=dry_run,
        mcp_host=mcp_host,
        mcp_bundle=mcp_bundle,
        refresh_mcp=not skip_mcp_refresh,
        uv_mode=uv_mode,  # type: ignore[arg-type]
        run_doctor=not skip_doctor,
        reinstall_clis=reinstall_clis,
        blue_green_deploy=blue_green_deploy,
        force_inplace_cli_reinstall=force_inplace_cli_reinstall,
        tapps_checkout=Path(tapps_checkout),
        import_legacy_doc_cache=import_legacy_doc_cache,
        strip_context7_env=strip_context7_env,
    )
    if output_format == "markdown":
        click.echo(format_fleet_upgrade_markdown(report))
    else:
        click.echo(json.dumps(report, indent=2))

    if report["summary"]["failed"]:
        raise SystemExit(1)


@main.command("check-agents-md-stamp")
@click.option(
    "--project-root",
    default=".",
    help="Project root directory (defaults to current dir).",
)
def check_agents_md_stamp(project_root: str) -> None:
    """Release gate — exit 1 if AGENTS.md version marker != pyproject version (TAP-982).

    Minimal, single-purpose check suitable for release CI. Faster than a full
    ``doctor`` run and reports only the stamp-vs-package comparison so the
    failure message is unambiguous.
    """
    from pathlib import Path

    from tapps_mcp.distribution.doctor import check_agents_md_stamp_matches_package

    result = check_agents_md_stamp_matches_package(Path(project_root))
    status = "OK" if result.ok else "FAIL"
    click.echo(f"[{status}] {result.name}: {result.message}")
    if result.detail:
        click.echo(f"       {result.detail}")
    if not result.ok:
        raise SystemExit(1)


@main.command("auto-capture")
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root directory (default: CLAUDE_PROJECT_DIR or current).",
)
@click.option(
    "--max-facts",
    default=5,
    type=int,
    help="Maximum facts to extract (default: 5).",
)
def auto_capture(project_root: str, max_facts: int) -> None:
    """Extract durable facts from stdin (Stop hook JSON) and save to memory (Epic 65.5).

    Read JSON from stdin (Claude Code Stop event), extract decision-like facts,
    and save to project memory. Invoked by memory_auto_capture Stop hook.
    """
    import sys
    from pathlib import Path

    project_root_path = Path(
        os.environ.get("CLAUDE_PROJECT_DIR")
        or os.environ.get("TAPPS_MCP_PROJECT_ROOT")
        or project_root
    ).resolve()
    raw = sys.stdin.read()
    from tapps_mcp.memory.auto_capture import run_auto_capture

    run_auto_capture(raw, project_root_path, max_facts=max_facts)


@main.command("compact-index")
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root directory (default: CLAUDE_PROJECT_DIR or current).",
)
def compact_index_cmd(project_root: str) -> None:
    """Index pre-compaction session state in brain (PreCompact hook, TAP-2017).

    Read JSON from stdin (Claude Code PreCompact event), index the session
    context via memory_index_session, and write a compaction marker so
    tapps_session_start can surface prior session context on rehydration.

    Disabled by setting TAPPS_MCP_COMPACTION_REHYDRATE=false.
    """
    import asyncio
    import sys
    from pathlib import Path

    project_root_path = Path(
        os.environ.get("CLAUDE_PROJECT_DIR")
        or os.environ.get("TAPPS_MCP_PROJECT_ROOT")
        or project_root
    ).resolve()
    raw = sys.stdin.read()
    from tapps_mcp.memory.compact_index import run_compact_index

    asyncio.run(run_compact_index(raw, project_root_path))


def _echo_validate_changed_data(data: dict[str, object]) -> None:
    """Print batch validation summary and per-file failure diagnostics."""
    summary = data.get("summary", "")
    if summary:
        click.echo(str(summary))
    for row in data.get("summary_rows") or []:
        click.echo(str(row))
    for entry in data.get("per_file_results") or []:
        if not isinstance(entry, dict) or entry.get("status") != "FAIL":
            continue
        for finding in entry.get("top_findings") or []:
            if not isinstance(finding, dict):
                continue
            code = finding.get("code", "")
            message = finding.get("message", "")
            line = finding.get("line", "?")
            click.echo(f"  {code}: {message} (line {line})")
        for hint in entry.get("improvement_hints") or []:
            click.echo(f"  hint: {hint}")


@main.command("validate-changed")
@click.option(
    "--quick/--full",
    default=True,
    help="Quick (ruff-only) or full validation. Default: quick.",
)
@click.option(
    "--file-paths",
    "--paths",
    default="",
    help="Comma-separated file paths (default: git auto-detect changed files).",
)
@click.option(
    "--security-depth",
    type=click.Choice(["none", "basic", "full"]),
    default=None,
    help="Security scan depth (overrides --quick/--full default).",
)
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root (default: current directory).",
)
def validate_changed_cmd(
    quick: bool, file_paths: str, security_depth: str | None, project_root: str
) -> None:
    """Validate changed Python files (same logic as the MCP tool).

    Run this before ending a session to confirm changed files pass quality gates.
    Without --file-paths, uses git to detect changed files, then runs quick
    (ruff-only) or full (ruff + mypy + bandit + radon + vulture) checks per file.
    """
    import asyncio

    from tapps_mcp.server_pipeline_tools import tapps_validate_changed

    if project_root != ".":
        os.chdir(project_root)

    async def _run() -> None:
        kwargs: dict[str, object] = {
            "file_paths": file_paths,
            "quick": quick,
            "include_security": not quick if security_depth is None else security_depth != "none",
        }
        if security_depth is not None:
            kwargs["security_depth"] = security_depth
        result = await tapps_validate_changed(**kwargs)  # type: ignore[arg-type]
        if not result.get("success"):
            click.echo(result.get("error", "Validation failed."), err=True)
            raise SystemExit(1)
        data = result.get("data", {})
        _echo_validate_changed_data(data)
        if not data.get("all_gates_passed", False) or not data.get("judges_passed", True):
            raise SystemExit(1)

    asyncio.run(_run())


@main.command("quick-check")
@click.option(
    "--file-path",
    required=True,
    help="Path to the Python file to validate.",
)
@click.option(
    "--preset",
    default="standard",
    show_default=True,
    type=click.Choice(["standard", "strict", "framework"]),
    help="Quality gate preset.",
)
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root (default: current directory).",
)
def quick_check_cmd(file_path: str, preset: str, project_root: str) -> None:
    """Quick score + gate + security for one file (MCP tapps_quick_check equivalent)."""
    import asyncio

    from tapps_mcp.server_scoring_tools import tapps_quick_check

    if project_root != ".":
        os.chdir(project_root)

    async def _run() -> None:
        result = await tapps_quick_check(file_path, preset=preset)
        if not result.get("success"):
            click.echo(result.get("error", "Quick check failed."), err=True)
            raise SystemExit(1)
        data = result.get("data", {})
        path = data.get("file_path", file_path)
        score = data.get("overall_score", 0)
        gate = "pass" if data.get("gate_passed") else "fail"
        click.echo(f"{path}: score={score}, gate={gate}")
        for issue in data.get("lint_issues") or []:
            if isinstance(issue, dict):
                click.echo(
                    f"  {issue.get('code', '')}: {issue.get('message', '')} "
                    f"(line {issue.get('line', '?')})"
                )
        if not data.get("gate_passed", False):
            raise SystemExit(1)

    asyncio.run(_run())


@main.command("build-plugin")
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


@main.command("build-cursor-plugin")
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


@main.command("validate-skills")
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


@main.command("cleanup-hook-backups")
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


@main.command("bump-stamps")
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


@main.command()
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


@main.command("show-config")
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


def _create_cli_brain_bridge() -> object | None:
    """Create a BrainBridge for CLI memory save/get (HTTP or in-process DSN)."""
    from tapps_core.brain_bridge import BRAIN_PROFILE_SERVER, create_brain_bridge
    from tapps_core.config.settings import load_settings

    settings = load_settings(project_root=_get_project_root())
    return create_brain_bridge(settings, default_profile=BRAIN_PROFILE_SERVER)


# ---------------------------------------------------------------------------
# Memory CLI group (Story 53.1)
# ---------------------------------------------------------------------------


@main.group()
def memory() -> None:
    """Manage shared project memories (no MCP server required)."""


@memory.command("list")
@click.option(
    "--tier",
    type=click.Choice(["architectural", "pattern", "procedural", "context"]),
    default=None,
)
@click.option("--scope", type=click.Choice(["project", "branch", "session"]), default=None)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def memory_list(tier: str | None, scope: str | None, as_json: bool) -> None:
    """List all memory entries with optional filters (via BrainBridge)."""
    import asyncio
    import json

    async def _list() -> list[dict[str, object]]:
        bridge = _create_cli_brain_bridge()
        if bridge is None:
            raise RuntimeError("bridge_unavailable")
        try:
            # BrainBridge.list_memories filters by tier; scope is client-side.
            entries = await bridge.list_memories(limit=500, tier=tier)  # type: ignore[attr-defined]
            if scope:
                entries = [e for e in entries if e.get("scope") == scope]
            return entries
        finally:
            bridge.close()  # type: ignore[attr-defined]

    try:
        entries = asyncio.run(_list())
    except RuntimeError as exc:
        if str(exc) == "bridge_unavailable":
            click.echo(_brain_bridge_unavailable_message(), err=True)
            raise SystemExit(1) from exc
        raise
    if as_json:
        click.echo(json.dumps(entries, indent=2, default=str))
        return
    if not entries:
        click.echo("No memories found.")
        return
    click.echo(f"{'Key':<30} {'Tier':<15} {'Scope':<10} {'Confidence':<12} Value")
    click.echo("-" * 90)
    for e in entries:
        value = str(e.get("value", ""))
        value_preview = value[:40].replace("\n", " ")
        if len(value) > 40:
            value_preview += "..."
        conf = e.get("confidence", 0.0)
        conf_s = f"{float(conf):.2f}" if isinstance(conf, (int, float)) else str(conf)
        click.echo(
            f"{e.get('key', '')!s:<30} {e.get('tier', '')!s:<15} "
            f"{e.get('scope', '')!s:<10} {conf_s:<12} {value_preview}"
        )


@memory.command("save")
@click.option("--key", required=True, help="Memory key (lowercase slug).")
@click.option("--value", required=True, help="Memory content.")
@click.option(
    "--tier",
    type=click.Choice(["architectural", "pattern", "procedural", "context"]),
    default="pattern",
)
@click.option("--tags", default="", help="Comma-separated tags.")
@click.option(
    "--memory-group",
    "memory_group",
    default=None,
    help="Brain memory_group scope (e.g. insights for validate_changed recall).",
)
def memory_save(key: str, value: str, tier: str, tags: str, memory_group: str | None) -> None:
    """Save a memory entry via BrainBridge (HTTP or in-process DSN)."""
    import asyncio
    import json

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    async def _save() -> dict[str, object]:
        bridge = _create_cli_brain_bridge()
        if bridge is None:
            raise RuntimeError("bridge_unavailable")
        save_kwargs: dict[str, object] = {}
        if memory_group:
            save_kwargs["memory_group"] = memory_group
        try:
            result = await bridge.save(
                key=key, value=value, tier=tier, tags=tag_list, **save_kwargs
            )
            return result if isinstance(result, dict) else {"key": key, "success": True}
        finally:
            bridge.close()

    try:
        result = asyncio.run(_save())
    except RuntimeError as exc:
        if str(exc) == "bridge_unavailable":
            click.echo(_brain_bridge_unavailable_message(), err=True)
            raise SystemExit(2) from None
        raise

    if isinstance(result, dict) and result.get("error"):
        message = result.get("message", result["error"])
        click.echo(f"Error: {message}", err=True)
        raise SystemExit(1)
    if isinstance(result, dict) and result.get("degraded") and not result.get("success", True):
        click.echo(f"Error: {result.get('reason', 'degraded')}", err=True)
        raise SystemExit(1)
    from tapps_mcp.tools.handoff_memory import enrich_memory_save_result

    payload = enrich_memory_save_result(result) if isinstance(result, dict) else result
    click.echo(json.dumps(payload, indent=2))


@memory.command("get")
@click.option("--key", required=True, help="Memory key to retrieve.")
def memory_get(key: str) -> None:
    """Retrieve a memory entry by key via BrainBridge (HTTP or in-process DSN)."""
    import asyncio
    import json

    async def _get() -> dict[str, object] | None:
        bridge = _create_cli_brain_bridge()
        if bridge is None:
            raise RuntimeError("bridge_unavailable")
        try:
            return await bridge.get(key)
        finally:
            bridge.close()

    try:
        entry = asyncio.run(_get())
    except RuntimeError as exc:
        if str(exc) == "bridge_unavailable":
            click.echo(_brain_bridge_unavailable_message(), err=True)
            raise SystemExit(2) from None
        raise

    if entry is None:
        click.echo(f"Memory '{key}' not found.", err=True)
        raise SystemExit(1)
    from tapps_mcp.tools.handoff_memory import enrich_memory_get_entry

    payload = enrich_memory_get_entry(key, entry)
    click.echo(json.dumps(payload, indent=2))


@memory.command("recall")
@click.option("--query", required=True, help="Search query (from prompt or last user message).")
@click.option("--project-root", default=".", type=click.Path(exists=True, path_type=str))
@click.option(
    "--max-results",
    default=5,
    type=int,
    help="Max results (1-10). Default: 5.",
)
@click.option(
    "--min-score",
    default=0.3,
    type=float,
    help="Minimum confidence (0-1). Default: 0.3.",
)
@click.option(
    "--recall-key",
    "recall_keys",
    multiple=True,
    help="Always include these keys before semantic search (repeatable).",
)
def memory_recall(
    query: str,
    project_root: str,
    max_results: int,
    min_score: float,
    recall_keys: tuple[str, ...],
) -> None:
    """Search memories via BrainBridge and output XML for auto-recall injection.

    Used by the memory_auto_recall hook (Epic 65.4 / TAP-414). Outputs
    ``<memory_context>...</memory_context>`` to stdout. When no
    ``TAPPS_BRAIN_DATABASE_URL`` is configured, exits 0 silently (degraded
    mode — auto-recall just injects nothing).
    """
    import asyncio
    import sys
    from pathlib import Path

    from tapps_core.brain_bridge import BRAIN_PROFILE_READONLY, create_brain_bridge
    from tapps_core.config.settings import load_settings

    root = _get_project_root() if project_root == "." else Path(project_root).resolve()
    max_results = max(1, min(max_results, 10))
    min_score = max(0.0, min(min_score, 1.0))

    async def _recall() -> list[dict[str, object]]:
        settings = load_settings(project_root=root)
        # Read-only auto-recall calls only ``memory_search``; ``reviewer`` is
        # the least-privilege profile that exposes it (ADR-0012). ``coder``
        # hides ``memory_search`` and silently returned no hits on v3.20.0+.
        bridge = create_brain_bridge(settings, default_profile=BRAIN_PROFILE_READONLY)
        if bridge is None:
            return [], []
        try:
            pinned: list[dict[str, object]] = []
            for key in recall_keys:
                entry = await bridge.get(key)
                if entry is not None:
                    pinned.append(entry)
            hits = await bridge.search(query, limit=max_results)
            return pinned, hits
        finally:
            bridge.close()

    try:
        pinned, hits = asyncio.run(_recall())
    except Exception:
        import structlog

        structlog.get_logger(__name__).debug("memory_recall_failed", exc_info=True)
        sys.exit(0)

    # Filter search hits by min_score — pinned keys are always included.
    filtered = [h for h in hits if float(h.get("confidence", h.get("score", 1.0))) >= min_score]
    seen_keys: set[str] = set()
    merged: list[dict[str, object]] = []
    for hit in pinned + filtered:
        key = str(hit.get("key", ""))
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(hit)
    if not merged:
        sys.exit(0)

    def _escape_xml_text(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _escape_xml_attr(s: str) -> str:
        return _escape_xml_text(s).replace('"', "&quot;")

    parts: list[str] = []
    for hit in merged:
        key = str(hit.get("key", ""))
        tier = str(hit.get("tier", ""))
        value = str(hit.get("value", ""))
        parts.append(
            f'  <memory key="{_escape_xml_attr(key)}" tier="{_escape_xml_text(tier)}">'
            f"{_escape_xml_text(value)}</memory>"
        )
    xml = "<memory_context>\n" + "\n".join(parts) + "\n</memory_context>"
    click.echo(xml)


def _emit_memory_search_rows(
    hits: list[dict[str, object]],
    *,
    as_json: bool,
) -> None:
    """Render memory search results from BrainBridge dict payloads."""
    import json

    if as_json:
        click.echo(json.dumps(hits, indent=2))
        return
    if not hits:
        click.echo("No results found.")
        return
    click.echo(f"{'Key':<30} {'Tier':<15} {'Confidence':<12} Value")
    click.echo("-" * 80)
    for hit in hits:
        key = str(hit.get("key", ""))
        tier = str(hit.get("tier", ""))
        confidence = float(hit.get("confidence", hit.get("score", 0.0)))
        value = str(hit.get("value", ""))
        value_preview = value[:40].replace("\n", " ")
        if len(value) > 40:
            value_preview += "..."
        click.echo(f"{key:<30} {tier:<15} {confidence:<12.2f} {value_preview}")


@memory.command("search")
@click.option("--query", required=True, help="Search query.")
@click.option("--limit", default=10, type=int, help="Max results.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def memory_search(query: str, limit: int, as_json: bool) -> None:
    """Search memories via BrainBridge (HTTP or DSN) or local MemoryStore fallback."""
    import asyncio
    import json

    from tapps_core.brain_bridge import BRAIN_PROFILE_READONLY, create_brain_bridge
    from tapps_core.config.settings import load_settings

    limit = max(1, limit)

    async def _search_bridge() -> list[dict[str, object]] | None:
        settings = load_settings(project_root=_get_project_root())
        bridge = create_brain_bridge(settings, default_profile=BRAIN_PROFILE_READONLY)
        if bridge is None:
            return None
        try:
            return await bridge.search(query, limit=limit)
        finally:
            bridge.close()

    try:
        bridge_hits = asyncio.run(_search_bridge())
    except Exception:
        bridge_hits = None

    if bridge_hits is not None:
        _emit_memory_search_rows(bridge_hits, as_json=as_json)
        return

    from tapps_brain.store import MemoryStore

    store = MemoryStore(_get_project_root(), store_dir=".tapps-mcp")
    try:
        results = store.search(query)[:limit]
        if as_json:
            click.echo(json.dumps([e.model_dump(mode="json") for e in results], indent=2))
            return
        if not results:
            click.echo("No results found.")
            return
        click.echo(f"{'Key':<30} {'Tier':<15} {'Confidence':<12} Value")
        click.echo("-" * 80)
        for e in results:
            value_preview = e.value[:40].replace("\n", " ")
            if len(e.value) > 40:
                value_preview += "..."
            click.echo(f"{e.key:<30} {e.tier:<15} {e.confidence:<12.2f} {value_preview}")
    finally:
        store.close()


@memory.command("delete")
@click.option("--key", required=True, help="Memory key to delete.")
def memory_delete(key: str) -> None:
    """Delete a memory entry via BrainBridge."""
    import asyncio

    async def _delete() -> bool:
        bridge = _create_cli_brain_bridge()
        if bridge is None:
            raise RuntimeError("bridge_unavailable")
        try:
            return bool(await bridge.delete(key))  # type: ignore[attr-defined]
        finally:
            bridge.close()  # type: ignore[attr-defined]

    try:
        deleted = asyncio.run(_delete())
    except RuntimeError as exc:
        if str(exc) == "bridge_unavailable":
            click.echo(_brain_bridge_unavailable_message(), err=True)
            raise SystemExit(1) from exc
        raise
    if not deleted:
        click.echo(f"Memory '{key}' not found.", err=True)
        raise SystemExit(1)
    click.echo(f"Deleted memory '{key}'.")


@memory.command("import-file")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True))
@click.option("--overwrite", is_flag=True, help="Overwrite existing keys.")
def memory_import(file_path: str, overwrite: bool) -> None:
    """Import memories from a JSON file."""
    from pathlib import Path

    from tapps_brain.io import import_memories
    from tapps_brain.store import MemoryStore

    from tapps_core.security.path_validator import PathValidator

    root = _get_project_root()
    store = MemoryStore(root, store_dir=".tapps-mcp")
    validator = PathValidator(root)
    try:
        result = import_memories(store, Path(file_path), validator, overwrite=overwrite)
        click.echo(
            f"Imported: {result['imported_count']}, "
            f"Skipped: {result['skipped_count']}, "
            f"Errors: {result['error_count']}"
        )
    finally:
        store.close()


@memory.command("export-file")
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(),
    help="Output file path (.json or .md).",
)
@click.option(
    "--format",
    "export_format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    show_default=True,
    help="Export format.",
)
@click.option(
    "--tier",
    type=click.Choice(["architectural", "pattern", "procedural", "context"]),
    default=None,
    help="Filter by memory tier.",
)
@click.option(
    "--scope",
    type=click.Choice(["project", "branch", "session"]),
    default=None,
    help="Filter by memory scope.",
)
@click.option(
    "--min-confidence",
    type=float,
    default=-1.0,
    help="Minimum confidence threshold (0.0-1.0). Default: no filter.",
)
def memory_export(
    file_path: str,
    export_format: str,
    tier: str | None,
    scope: str | None,
    min_confidence: float,
) -> None:
    """Export memories to a JSON or Markdown file."""
    from pathlib import Path

    from tapps_brain.io import export_memories
    from tapps_brain.store import MemoryStore

    from tapps_core.security.path_validator import PathValidator

    root = _get_project_root()
    store = MemoryStore(root, store_dir=".tapps-mcp")
    validator = PathValidator(root)
    try:
        result = export_memories(
            store,
            Path(file_path),
            validator,
            tier=tier,
            scope=scope,
            min_confidence=min_confidence if min_confidence >= 0 else None,
            export_format=export_format,
        )
        click.echo(f"Exported {result['exported_count']} memories to {result['file_path']}")
    finally:
        store.close()


@memory.command("reseed")
@click.option(
    "--confirm",
    is_flag=True,
    required=True,
    help="Confirm re-seeding from the detected project profile.",
)
def memory_reseed(confirm: bool) -> None:
    """Re-seed memories from the project profile (auto-seeded entries only)."""
    if not confirm:
        raise SystemExit("Pass --confirm to re-seed memories.")
    from tapps_brain.seeding import reseed_from_profile
    from tapps_brain.store import MemoryStore

    from tapps_core.config.settings import load_settings
    from tapps_mcp.project.profiler import detect_project_profile

    root = _get_project_root()
    store = MemoryStore(root, store_dir=".tapps-mcp")
    try:
        settings = load_settings(root)
        profile = detect_project_profile(settings.project_root)
        profile.project_type = profile.project_type or ""
        result = reseed_from_profile(store, profile)  # type: ignore[arg-type]
        click.echo(
            f"Re-seeded {result.get('seeded_count', result.get('count', 0))} "
            f"memories from project profile."
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Knowledge & Expert CLI commands (Stories 53.2-53.4)
# ---------------------------------------------------------------------------


@main.command("lookup-docs")
@click.option("--library", required=True, help="Library name (fuzzy-matched).")
@click.option("--topic", default="overview", help="Topic within the library.")
@click.option("--mode", type=click.Choice(["code", "info"]), default="code")
@click.option("--raw", is_flag=True, help="Show full untruncated output.")
def lookup_docs_cmd(library: str, topic: str, mode: str, raw: bool) -> None:
    """Look up library documentation (no MCP server required)."""
    import asyncio

    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.cache import KBCache
    from tapps_core.knowledge.lookup import LookupEngine

    settings = load_settings()
    cache = KBCache(settings.project_root / ".tapps-mcp-cache")

    async def _run() -> None:
        engine = LookupEngine(cache, settings=settings)
        try:
            result = await engine.lookup(library=library, topic=topic, mode=mode)
        finally:
            await engine.close()

        if not result.success:
            click.echo(f"Error: {result.error}", err=True)
            raise SystemExit(1)

        content = result.content or ""
        if not raw and len(content) > 2000:
            content = content[:2000] + "\n\n... (truncated, use --raw for full output)"

        click.echo(f"Library: {result.library} | Topic: {result.topic} | Source: {result.source}")
        if result.warning:
            click.echo(f"Warning: {result.warning}")
        click.echo("---")
        click.echo(content)

        from tapps_mcp.tools.lookup_telemetry import record_lookup_event

        record_lookup_event(
            settings.project_root,
            library=result.library or library,
            topic=result.topic or topic,
            source="cli",
            resolved_library=result.library if result.library != library else None,
        )

    asyncio.run(_run())


@main.command(name="replace-exe")
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


@main.command("migrate-memory")
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
            f"rollback run_id={rollback_run_id} deleted={result['deleted']} "
            f"ok={result['ok']}"
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


@main.command("release-update")
@click.option("--version", required=True, help="New release version, e.g. 1.5.0")
@click.option("--prev-version", required=True, help="Previous version, e.g. 1.4.2")
@click.option("--bump-type", default="", help="patch | minor | major (inferred if blank)")
@click.option("--team", default="", help="Linear team name/ID")
@click.option("--project", default="", help="Linear project name/slug")
@click.option("--dry-run", is_flag=True, default=False, help="Return body without requiring validation pass")
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


def _register_benchmark_group() -> None:
    """Lazily register the benchmark subcommand group."""
    from tapps_mcp.benchmark.cli_commands import benchmark_group

    main.add_command(benchmark_group)


def _register_template_group() -> None:
    """Lazily register the template optimization subcommand group."""
    from tapps_mcp.benchmark.cli_commands import template_group

    main.add_command(template_group)


_register_benchmark_group()
_register_template_group()


if __name__ == "__main__":
    main()
