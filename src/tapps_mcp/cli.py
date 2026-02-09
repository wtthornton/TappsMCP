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


if __name__ == "__main__":
    main()
