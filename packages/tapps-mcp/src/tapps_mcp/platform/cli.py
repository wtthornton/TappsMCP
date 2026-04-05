"""TappsPlatform CLI -- serve combined or individual MCP servers.

Usage::

    tapps-platform serve          # combined (default)
    tapps-platform serve-tapps    # TappsMCP only
    tapps-platform serve-docs     # DocsMCP only
    tapps-platform doctor         # check availability of sub-servers
"""

from __future__ import annotations

from typing import Any

import click
import structlog

logger: Any = structlog.get_logger(__name__)


def _get_version() -> str:
    """Build a version string from available packages."""
    from tapps_mcp import __version__ as tapps_version

    parts = [f"tapps-mcp {tapps_version}"]
    try:
        from docs_mcp import __version__ as docs_version

        parts.append(f"docs-mcp {docs_version}")
    except ImportError:
        parts.append("docs-mcp (not installed)")
    return " | ".join(parts)


@click.group()
@click.option(
    "--version",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=lambda ctx, _param, value: (
        (click.echo(_get_version()), ctx.exit()) if value else None
    ),
    help="Show platform version.",
)
def cli() -> None:
    """TappsPlatform -- combined MCP server CLI."""


@cli.command()
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "http"]))
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8000, type=int)
def serve(transport: str, host: str, port: int) -> None:
    """Start the combined TappsPlatform server (TappsMCP + DocsMCP)."""
    from tapps_mcp.platform.combined_server import run_combined_server

    run_combined_server(transport=transport, host=host, port=port)


@cli.command("serve-tapps")
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "http"]))
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8000, type=int)
def serve_tapps(transport: str, host: str, port: int) -> None:
    """Start TappsMCP only (code quality tools)."""
    from tapps_mcp.server import run_server

    run_server(transport=transport, host=host, port=port)


@cli.command("serve-docs")
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "http"]))
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8000, type=int)
def serve_docs(transport: str, host: str, port: int) -> None:
    """Start DocsMCP only (documentation tools)."""
    try:
        from docs_mcp.server import run_server

        run_server(transport=transport, host=host, port=port)
    except ImportError:
        click.echo("Error: docs-mcp is not installed.", err=True)
        raise SystemExit(1) from None


@cli.command()
def doctor() -> None:
    """Check TappsMCP and DocsMCP availability and tool counts."""
    from tapps_mcp.platform.combined_server import health_check

    info = health_check()

    click.echo("TappsPlatform Doctor")
    click.echo("=" * 40)

    # TappsMCP
    tapps = info["tapps_mcp"]
    status = "OK" if tapps["available"] else "MISSING"
    click.echo(f"  TappsMCP:  {status} (v{tapps.get('version', '?')})")
    click.echo(f"    Tools:   {tapps.get('tool_count', '?')}")

    # DocsMCP
    docs = info["docs_mcp"]
    if docs["available"]:
        status = "OK"
        version = f" (v{docs.get('version', '?')})"
    else:
        status = "NOT INSTALLED"
        version = ""
    click.echo(f"  DocsMCP:   {status}{version}")
    click.echo(f"    Tools:   {docs.get('tool_count', 0)}")

    click.echo("-" * 40)
    click.echo(f"  Total:     {info.get('total_tool_count', '?')} tools")

    if not docs["available"]:
        click.echo()
        click.echo("Tip: Install docs-mcp for documentation tools:")
        click.echo("  uv pip install docs-mcp")
