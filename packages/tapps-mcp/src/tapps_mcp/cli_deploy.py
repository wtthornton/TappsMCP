"""Deployment CLI commands."""

from __future__ import annotations

from pathlib import Path

import click


@click.command("deploy-local")
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


@click.command("upgrade-fleet")
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
    show_default=True,
    help=(
        "NLT MCP bundle to write per project (default full = all six; "
        "later opt-down: tapps-mcp mcp-bundle set <bundle>)."
    ),
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
    "--skip-deploy-gate",
    is_flag=True,
    default=False,
    help="With --reinstall-clis blue/green, skip the pytest quiescence gate "
    "(default: gate runs — TAP-5157).",
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
    skip_deploy_gate: bool,
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
        skip_deploy_gate=skip_deploy_gate,
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
