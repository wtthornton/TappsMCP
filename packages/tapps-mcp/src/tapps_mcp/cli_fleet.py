"""Fleet CLI command group."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import click


@click.group("fleet")
def fleet_group() -> None:
    """Manage the host-level shared HTTP MCP fleet (ADR-0024)."""


@fleet_group.command("start")
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


@fleet_group.command("stop")
def fleet_stop() -> None:
    """Stop all HTTP fleet servers."""
    from tapps_mcp.distribution.fleet_control import stop_fleet

    result = stop_fleet()
    if result["stopped"]:
        click.echo(click.style("Stopped: " + ", ".join(result["stopped"]), fg="green"))
    if result["missing"]:
        click.echo("Not running: " + ", ".join(result["missing"]))


@fleet_group.command("status")
def fleet_status_cmd() -> None:
    """Show HTTP fleet process and reachability status."""
    from tapps_mcp.distribution.fleet_control import fleet_status

    result = fleet_status()
    click.echo(f"Running {result['running']}/{result['total']} on {result['host']}")
    click.echo(f"Code root: {result['code_root']}")
    click.echo(f"Env: {result['env_file']}")
    for server_id, row in result["servers"].items():
        # A reachable port is not proof the fleet's own server answered it —
        # report the orphan case rather than calling it ok (TAP-5630).
        if row["orphaned"]:
            state, color = "orphan", "yellow"
        elif row["reachable"]:
            state, color = "ok", "green"
        elif row["alive"]:
            state, color = "pid", "yellow"
        else:
            state, color = "down", "red"
        detail = f"  {server_id}: {state} pid={row['pid']}"
        if row["orphaned"]:
            detail += f" owner={row['owner_pid']}"
        if row["release"]:
            detail += f" release={row['release']}"
        click.echo(click.style(f"{detail} url={row['url']}", fg=color))


@fleet_group.command("restart")
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
def fleet_restart(skip_smoke: bool, project_root: str) -> None:
    """Stop then start the HTTP fleet and verify MCP handshakes.

    Restart always stops the fleet first, so a fresh start is implied —
    the old ``--force`` flag was a no-op and has been removed.
    """
    _run_fleet_restart(skip_smoke, Path(project_root).resolve())


def _run_fleet_restart(skip_smoke: bool, root: Path) -> None:
    """Restart the fleet and render its smoke report."""
    from tapps_mcp.distribution.fleet_control import (
        restart_fleet_with_smoke,
        start_fleet,
        stop_fleet,
    )

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


@fleet_group.command("smoke")
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


@fleet_group.command("ensure")
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


@fleet_group.command("install-systemd")
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


@fleet_group.command("audit-consumers")
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


@fleet_group.command("repair-consumers")
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
    click.echo(f"repaired={result['repaired_count']} unchanged={result['unchanged_count']}")
    for row in result["repaired"]:
        click.echo(click.style(f"  {row['project']}: {', '.join(row['changes'])}", fg="green"))
    if not audit:
        return
    _run_fleet_consumer_post_audit(audit_consumers, parent, root_list)


def _run_fleet_consumer_post_audit(
    audit_consumers: Callable[..., dict[str, Any]],
    parent: Path | None,
    root_list: list[Path] | None,
) -> None:
    """Render post-repair audit results and preserve its exit status."""
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
