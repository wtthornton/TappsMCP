"""CLI entry point for tapps-mcp."""

from __future__ import annotations

import os

import click

from tapps_mcp import __version__


@click.group()
@click.version_option(package_name="tapps-mcp", version=__version__)
def main() -> None:
    """TappsMCP: MCP server providing code quality tools."""
    from tapps_mcp.distribution.exe_manager import cleanup_stale_old_exes

    cleanup_stale_old_exes()


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
def serve(transport: str, host: str, port: int) -> None:
    """Start the TappsMCP MCP server."""
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
    default="user",
    help="Config scope: 'user' (~/.claude.json) or 'project' (.mcp.json in project root).",
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
def init(
    mcp_host: str,
    project_root: str,
    check: bool,
    force: bool,
    scope: str,
    rules: bool,
    dry_run: bool,
) -> None:
    """Generate MCP configuration for Claude Code, Cursor, or VS Code."""
    from tapps_mcp.distribution.setup_generator import run_init

    success = run_init(
        mcp_host=mcp_host,
        project_root=project_root,
        check=check,
        force=force,
        scope=scope,
        rules=rules,
        dry_run=dry_run,
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
def upgrade(mcp_host: str, project_root: str, force: bool, dry_run: bool) -> None:
    """Validate and update all TappsMCP-generated files after a version upgrade.

    Checks AGENTS.md, platform rules, hooks, agents, skills, and settings
    against the current TappsMCP version and refreshes outdated files.
    """
    from tapps_mcp.distribution.setup_generator import run_upgrade

    success = run_upgrade(
        mcp_host=mcp_host,
        project_root=project_root,
        force=force,
        dry_run=dry_run,
    )
    if not success:
        raise SystemExit(1)


@main.command()
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
def doctor(project_root: str) -> None:
    """Diagnose TappsMCP configuration and connectivity."""
    from tapps_mcp.distribution.doctor import run_doctor

    success = run_doctor(project_root=project_root)
    if not success:
        raise SystemExit(1)


@main.command("validate-changed")
@click.option(
    "--quick/--full",
    default=True,
    help="Quick (ruff-only) or full validation. Default: quick.",
)
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root (default: current directory).",
)
def validate_changed_cmd(quick: bool, project_root: str) -> None:
    """Validate all changed Python files (same logic as the MCP tool).

    Run this before ending a session to confirm changed files pass quality gates.
    Uses git to detect changed files, then runs quick (ruff-only) or full
    (ruff + mypy + bandit + radon + vulture) checks per file.
    """
    import asyncio

    from tapps_mcp.server_pipeline_tools import tapps_validate_changed

    # So load_settings() and git run in the right project
    if project_root != ".":
        os.chdir(project_root)

    async def _run() -> None:
        result = await tapps_validate_changed(
            file_paths="",
            quick=quick,
            include_security=not quick,
        )
        if not result.get("success"):
            click.echo(result.get("error", "Validation failed."), err=True)
            raise SystemExit(1)
        data = result.get("data", {})
        summary = data.get("summary", "")
        all_passed = data.get("all_gates_passed", False)
        click.echo(summary)
        if not all_passed:
            raise SystemExit(1)

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


if __name__ == "__main__":
    main()
