"""CLI entry point for tapps-mcp."""

from __future__ import annotations

import click


@click.group()
@click.version_option(package_name="tapps-mcp")
def main() -> None:
    """TappsMCP: MCP server providing code quality tools."""


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
def init(mcp_host: str, project_root: str, check: bool, force: bool) -> None:
    """Generate MCP configuration for Claude Code, Cursor, or VS Code."""
    from tapps_mcp.distribution.setup_generator import run_init

    success = run_init(mcp_host=mcp_host, project_root=project_root, check=check, force=force)
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
