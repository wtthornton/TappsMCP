"""DocsMCP CLI - documentation MCP server management."""

from __future__ import annotations

import click

from docs_mcp import __version__


@click.group()
@click.version_option(package_name="docs-mcp", version=__version__)
def cli() -> None:
    """DocsMCP: Documentation generation and maintenance MCP server."""


@cli.command()
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
    """Start the DocsMCP MCP server."""
    from docs_mcp.server import run_server

    run_server(transport=transport, host=host, port=port)


@cli.command()
def doctor() -> None:
    """Check DocsMCP configuration and dependencies."""
    click.echo(f"DocsMCP v{__version__}")
    click.echo("Checking configuration...")

    # Check tapps_core import
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        click.echo(f"  Project root: {settings.project_root}")
        click.echo("  tapps-core: OK")
    except Exception as e:
        click.echo(f"  tapps-core: FAILED ({e})")

    # Check docs-mcp config
    try:
        from docs_mcp.config.settings import load_docs_settings

        docs_settings = load_docs_settings()
        click.echo(f"  Output dir: {docs_settings.output_dir}")
        click.echo(f"  Style: {docs_settings.default_style}")
        click.echo("  docs-mcp config: OK")
    except Exception as e:
        click.echo(f"  docs-mcp config: FAILED ({e})")

    # Check MCP SDK
    try:
        import mcp  # noqa: F401

        click.echo("  mcp SDK: OK")
    except ImportError:
        click.echo("  mcp SDK: FAILED (not installed)")

    # Check Jinja2
    try:
        import jinja2  # noqa: F401

        click.echo("  jinja2: OK")
    except ImportError:
        click.echo("  jinja2: FAILED (not installed)")

    # Check GitPython
    try:
        import git  # noqa: F401

        click.echo("  gitpython: OK")
    except ImportError:
        click.echo("  gitpython: FAILED (not installed)")

    click.echo("Done.")


@cli.command()
def generate() -> None:
    """Pointer: documentation is generated via MCP tools, not this CLI subcommand.

    DocsMCP ships 18+ generators (README, CHANGELOG, release notes, API docs,
    ADRs, onboarding, contributing, PRDs, diagrams, architecture, epics,
    stories, purpose, doc index, llms.txt, frontmatter, interactive diagrams).
    They are invoked via MCP from your AI assistant — not as CLI commands.
    """
    click.echo(
        "Documentation generation runs via MCP tools, not this CLI.\n"
        "\n"
        "From your AI assistant session, call any of:\n"
        "  docs_generate_readme, docs_generate_changelog, docs_generate_release_notes,\n"
        "  docs_generate_api, docs_generate_adr, docs_generate_onboarding,\n"
        "  docs_generate_contributing, docs_generate_prd, docs_generate_diagram,\n"
        "  docs_generate_architecture, docs_generate_epic, docs_generate_story,\n"
        "  docs_generate_purpose, docs_generate_doc_index, docs_generate_llms_txt,\n"
        "  docs_generate_frontmatter, docs_generate_interactive_diagrams,\n"
        "  docs_generate_prompt.\n"
        "\n"
        "Start the server with:  docsmcp serve  (stdio)\n"
        "                       docsmcp serve --transport http --port 8000\n"
    )


@cli.command()
def scan() -> None:
    """Scan project for documentation inventory."""
    click.echo("Scanning project for documentation files...")

    try:
        from docs_mcp.config.settings import load_docs_settings
        from docs_mcp.server import _scan_doc_files

        settings = load_docs_settings()
        docs = _scan_doc_files(settings.project_root)

        if not docs:
            click.echo("No documentation files found.")
            return

        click.echo(f"Found {len(docs)} documentation file(s):\n")
        for doc in docs:
            category = doc.get("category", "other")
            size = doc.get("size_bytes", 0)
            click.echo(f"  [{category:>15}] {doc['path']} ({size:,} bytes)")

    except Exception as e:
        click.echo(f"Scan failed: {e}", err=True)
        raise SystemExit(1) from None


@cli.command()
def version() -> None:
    """Print DocsMCP version."""
    click.echo(f"docsmcp {__version__}")


if __name__ == "__main__":
    cli()
