"""DocsMCP CLI - documentation MCP server management."""

from __future__ import annotations

from pathlib import Path

import click

from docs_mcp import __version__


def _load_tapps_settings(project_root: Path) -> object | None:
    """Load tapps-core settings so brain transport resolves from config (TAP-1955).

    The arch-migration CLI commands construct their brain bridge via
    ``create_brain_bridge``, which — when handed ``settings=None`` — resolves
    the HTTP transport and auth from environment variables only. A CLI operator
    who configured ``memory.brain_http_url`` (and ``brain_auth_token``) in
    ``.tapps-mcp.yaml`` would otherwise hit "brain unavailable" unless they also
    exported the env vars. Loading tapps-core settings here closes that gap.
    Returns ``None`` on import/config failure, preserving the env-only path.
    """
    try:
        from tapps_core.config.settings import load_settings

        return load_settings(project_root)
    except Exception:  # pragma: no cover - falls back to env-only resolution
        return None


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


@cli.command(name="migrate-arch-to-kg")
@click.option(
    "--execute/--dry-run",
    "execute",
    default=False,
    help="--execute performs the migration; --dry-run (default) only reports.",
)
def migrate_arch_to_kg(execute: bool) -> None:
    """Migrate flat ``arch.{project}.*`` brain entries to KG triples (TAP-1953).

    Reads pre-TAP-1948 leftover flat architecture entries, re-emits each as a KG
    entity (prose preserved as ``summary`` metadata + a provenance evidence row),
    and tags the flat entry ``migrated_to_kg=true``. Idempotent: already-tagged
    entries are skipped, so a second ``--execute`` is a no-op. Flat entries are
    never deleted (that is the TAP-1954 GC). Exits non-zero on partial failure.
    """
    import asyncio

    from docs_mcp.config.settings import load_docs_settings
    from docs_mcp.integrations.arch_migration import ArchMigrator

    settings = load_docs_settings()
    project_root = Path(str(settings.project_root))
    migrator = ArchMigrator(project_root, settings=_load_tapps_settings(project_root))
    result = asyncio.run(migrator.migrate(execute=execute))

    mode = "EXECUTE" if execute else "DRY-RUN"
    click.echo(f"migrate-arch-to-kg [{mode}]")
    if not result.available:
        click.echo("  brain unavailable: " + "; ".join(result.errors), err=True)
        raise SystemExit(1)

    click.echo(f"  flat arch.* entries found: {result.flat_total}")
    click.echo(f"  already migrated (skipped): {result.already_migrated}")
    click.echo(f"  unparseable (skipped):      {result.unparseable}")
    for planned in result.planned:
        if planned.status == "already_migrated":
            continue
        verb = {"migrated": "migrated", "failed": "FAILED", "planned": "would migrate"}[
            planned.status
        ]
        click.echo(f"  - {verb}: {planned.key} -> {planned.entity_type}:{planned.canonical_name}")
    if execute:
        click.echo(f"  migrated: {result.migrated}  failed: {result.failed}")
    if result.failed:
        for err in result.errors:
            click.echo(f"  error: {err}", err=True)
        raise SystemExit(1)


@cli.command(name="gc-migrated-arch")
@click.option(
    "--execute/--dry-run",
    "execute",
    default=False,
    help="--execute deletes eligible entries; --dry-run (default) only reports.",
)
@click.option(
    "--older-than-days",
    default=14,
    type=int,
    help="Only GC entries migrated more than this many days ago (default 14).",
)
def gc_migrated_arch(execute: bool, older_than_days: int) -> None:
    """Garbage-collect flat ``arch.*`` entries migrated to the KG (TAP-1954).

    Deletes flat entries tagged ``migrated_to_kg=true`` whose ``migrated_to_kg_at``
    date is older than ``--older-than-days`` (default 14) — the retention buffer
    that lets an operator verify the migration before the flat copy is dropped.
    Undated entries are skipped as a safety guard. Exits non-zero on partial
    failure. Run only after ``migrate-arch-to-kg --execute``.
    """
    import asyncio

    from docs_mcp.config.settings import load_docs_settings
    from docs_mcp.integrations.arch_migration import ArchMigrator

    settings = load_docs_settings()
    project_root = Path(str(settings.project_root))
    migrator = ArchMigrator(project_root, settings=_load_tapps_settings(project_root))
    result = asyncio.run(migrator.gc_migrated(older_than_days=older_than_days, execute=execute))

    mode = "EXECUTE" if execute else "DRY-RUN"
    click.echo(f"gc-migrated-arch [{mode}] (older-than {older_than_days}d)")
    if not result.available:
        click.echo("  brain unavailable: " + "; ".join(result.errors), err=True)
        raise SystemExit(1)

    click.echo(f"  migrated entries scanned: {result.scanned}")
    click.echo(f"  skipped (within window):  {result.skipped_recent}")
    click.echo(f"  skipped (no date tag):    {result.skipped_undated}")
    verb = "deleted" if execute else "would delete"
    for key in result.eligible:
        click.echo(f"  - {verb}: {key}")
    if execute:
        click.echo(f"  deleted: {result.deleted}  failed: {result.failed}")
    else:
        click.echo(f"  eligible: {len(result.eligible)}")
    if result.failed:
        for err in result.errors:
            click.echo(f"  error: {err}", err=True)
        raise SystemExit(1)


@cli.command()
def version() -> None:
    """Print DocsMCP version."""
    click.echo(f"docsmcp {__version__}")


if __name__ == "__main__":
    cli()
