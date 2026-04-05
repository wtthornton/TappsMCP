"""CLI entry point for tapps-mcp."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from pathlib import Path

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
    help="Also register the docs-mcp server in generated MCP JSON (Epic 80.7).",
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
    uv_flag: bool | None,
    uv_extra: str | None,
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
def upgrade(mcp_host: str, project_root: str, force: bool, dry_run: bool, scope: str) -> None:
    """Refresh generated files after upgrading the `tapps-mcp` package.

    Re-merges AGENTS.md, platform rules, hooks, agents, skills, and Claude/Cursor settings.
    Creates a timestamped backup under `.tapps-mcp/backups/` before overwriting.
    Preserves custom MCP command paths. Review `.tapps-mcp.yaml` after major upgrades if you
    relied on older default flags (memory pipeline, hooks). See docs/UPGRADE_FOR_CONSUMERS.md.
    """
    from tapps_mcp.distribution.setup_generator import run_upgrade

    success = run_upgrade(
        mcp_host=mcp_host,
        project_root=project_root,
        force=force,
        dry_run=dry_run,
        scope=scope,
    )
    if not success:
        raise SystemExit(1)


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
    Use `--quick` to skip per-tool version probes.
    """
    from tapps_mcp.distribution.doctor import run_doctor

    success = run_doctor(project_root=project_root, quick=quick)
    if not success:
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
            for e in err_list:
                click.echo(f"  - {e}", err=True)
        raise SystemExit(1)
    click.echo("All skills passed spec validation.")


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


def _get_project_root() -> "Path":
    """Resolve project root from TAPPS_MCP_PROJECT_ROOT env var or cwd."""
    from pathlib import Path

    root = os.environ.get("TAPPS_MCP_PROJECT_ROOT", ".")
    return Path(root).resolve()


# ---------------------------------------------------------------------------
# Memory CLI group (Story 53.1)
# ---------------------------------------------------------------------------


@main.group()
def memory() -> None:
    """Manage shared project memories (no MCP server required)."""


@memory.command("list")
@click.option("--tier", type=click.Choice(["architectural", "pattern", "context"]), default=None)
@click.option("--scope", type=click.Choice(["project", "branch", "session"]), default=None)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def memory_list(tier: str | None, scope: str | None, as_json: bool) -> None:
    """List all memory entries with optional filters."""
    import json

    from tapps_core.memory.store import MemoryStore

    store = MemoryStore(_get_project_root(), store_dir=".tapps-mcp")
    try:
        entries = store.list_all(tier=tier, scope=scope)
        if as_json:
            click.echo(json.dumps([e.model_dump(mode="json") for e in entries], indent=2))
            return
        if not entries:
            click.echo("No memories found.")
            return
        click.echo(f"{'Key':<30} {'Tier':<15} {'Scope':<10} {'Confidence':<12} Value")
        click.echo("-" * 90)
        for e in entries:
            value_preview = e.value[:40].replace("\n", " ")
            if len(e.value) > 40:
                value_preview += "..."
            click.echo(
                f"{e.key:<30} {e.tier.value:<15} {e.scope.value:<10} "
                f"{e.confidence:<12.2f} {value_preview}"
            )
    finally:
        store.close()


@memory.command("save")
@click.option("--key", required=True, help="Memory key (lowercase slug).")
@click.option("--value", required=True, help="Memory content.")
@click.option(
    "--tier",
    type=click.Choice(["architectural", "pattern", "context"]),
    default="pattern",
)
@click.option("--tags", default="", help="Comma-separated tags.")
def memory_save(key: str, value: str, tier: str, tags: str) -> None:
    """Save a memory entry."""
    import json

    from tapps_core.memory.store import MemoryStore

    store = MemoryStore(_get_project_root(), store_dir=".tapps-mcp")
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        result = store.save(key=key, value=value, tier=tier, tags=tag_list)
        if isinstance(result, dict) and "error" in result:
            click.echo(f"Error: {result['message']}", err=True)
            raise SystemExit(1)
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    finally:
        store.close()


@memory.command("get")
@click.option("--key", required=True, help="Memory key to retrieve.")
def memory_get(key: str) -> None:
    """Retrieve a memory entry by key."""
    import json

    from tapps_core.memory.store import MemoryStore

    store = MemoryStore(_get_project_root(), store_dir=".tapps-mcp")
    try:
        entry = store.get(key)
        if entry is None:
            click.echo(f"Memory '{key}' not found.", err=True)
            raise SystemExit(1)
        click.echo(json.dumps(entry.model_dump(mode="json"), indent=2))
    finally:
        store.close()


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
def memory_recall(query: str, project_root: str, max_results: int, min_score: float) -> None:
    """Search memories and output XML for auto-recall hook injection.

    Used by the memory_auto_recall hook (Epic 65.4). Outputs
    <memory_context>...</memory_context> to stdout.
    Handles: no MemoryStore, empty results (graceful fallback).
    """
    import sys
    from pathlib import Path

    from tapps_core.memory.retrieval import MemoryRetriever, ScoredMemory
    from tapps_core.memory.store import MemoryStore

    root = _get_project_root() if project_root == "." else Path(project_root).resolve()
    max_results = max(1, min(max_results, 10))
    min_score = max(0.0, min(min_score, 1.0))

    store: MemoryStore | None = None
    scored: list[ScoredMemory] = []
    try:
        store = MemoryStore(root, store_dir=".tapps-mcp")
        # M2: Load profile scoring config for source_trust multipliers
        scoring_config = getattr(getattr(store, "profile", None), "scoring", None)
        retriever = MemoryRetriever(scoring_config=scoring_config)
        scored = retriever.search(
            query,
            store,
            limit=max_results,
            min_confidence=min_score,
        )
    except Exception:
        import structlog

        structlog.get_logger(__name__).debug("memory_search_failed", exc_info=True)
        sys.exit(0)
    finally:
        if store is not None:
            store.close()

    if not scored:
        sys.exit(0)

    def _escape_xml_text(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _escape_xml_attr(s: str) -> str:
        return _escape_xml_text(s).replace('"', "&quot;")

    parts: list[str] = []
    for sm in scored:
        entry = sm.entry
        parts.append(
            f'  <memory key="{_escape_xml_attr(entry.key)}" tier="{entry.tier.value}">'
            f"{_escape_xml_text(entry.value)}</memory>"
        )
    xml = "<memory_context>\n" + "\n".join(parts) + "\n</memory_context>"
    click.echo(xml)


@memory.command("search")
@click.option("--query", required=True, help="Search query.")
@click.option("--limit", default=10, type=int, help="Max results.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def memory_search(query: str, limit: int, as_json: bool) -> None:
    """Search memories by full-text query."""
    import json

    from tapps_core.memory.store import MemoryStore

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
            click.echo(f"{e.key:<30} {e.tier.value:<15} {e.confidence:<12.2f} {value_preview}")
    finally:
        store.close()


@memory.command("delete")
@click.option("--key", required=True, help="Memory key to delete.")
def memory_delete(key: str) -> None:
    """Delete a memory entry."""
    from tapps_core.memory.store import MemoryStore

    store = MemoryStore(_get_project_root(), store_dir=".tapps-mcp")
    try:
        deleted = store.delete(key)
        if not deleted:
            click.echo(f"Memory '{key}' not found.", err=True)
            raise SystemExit(1)
        click.echo(f"Deleted memory '{key}'.")
    finally:
        store.close()


@memory.command("import-file")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True))
@click.option("--overwrite", is_flag=True, help="Overwrite existing keys.")
def memory_import(file_path: str, overwrite: bool) -> None:
    """Import memories from a JSON file."""
    from pathlib import Path

    from tapps_core.memory.io import import_memories
    from tapps_core.memory.store import MemoryStore
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
    help="Output JSON file path.",
)
def memory_export(file_path: str) -> None:
    """Export memories to a JSON file."""
    from pathlib import Path

    from tapps_core.memory.io import export_memories
    from tapps_core.memory.store import MemoryStore
    from tapps_core.security.path_validator import PathValidator

    root = _get_project_root()
    store = MemoryStore(root, store_dir=".tapps-mcp")
    validator = PathValidator(root)
    try:
        result = export_memories(store, Path(file_path), validator)
        click.echo(f"Exported {result['exported_count']} memories to {result['file_path']}")
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

    asyncio.run(_run())


@main.command("research")
@click.option("--question", required=True, help="Technical question to research.")
@click.option("--domain", default=None, help="Expert domain override.")
@click.option("--library", default=None, help="Library for docs supplement.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def research_cmd(question: str, domain: str | None, library: str | None, as_json: bool) -> None:
    """Combined expert consultation + docs lookup (no MCP server required)."""
    import asyncio
    import json

    from tapps_core.experts.engine import consult_expert

    result = consult_expert(question=question, domain=domain)

    # Optionally supplement with docs lookup
    docs_content: str | None = None
    if library:
        from tapps_core.config.settings import load_settings
        from tapps_core.knowledge.cache import KBCache
        from tapps_core.knowledge.lookup import LookupEngine

        settings = load_settings()
        cache = KBCache(settings.project_root / ".tapps-mcp-cache")

        async def _lookup() -> str | None:
            engine = LookupEngine(cache, settings=settings)
            try:
                lr = await engine.lookup(library=library, topic="overview", mode="code")
            finally:
                await engine.close()
            return lr.content if lr.success else None

        docs_content = asyncio.run(_lookup())

    if as_json:
        output = result.model_dump(mode="json")
        if docs_content:
            output["docs_supplement"] = docs_content[:2000]
        click.echo(json.dumps(output, indent=2))
        return

    click.echo(f"Domain: {result.domain} | Expert: {result.expert_name}")
    click.echo(f"Confidence: {result.confidence:.0%}")
    click.echo(f"Sources: {', '.join(result.sources) if result.sources else 'none'}")
    if result.recommendation:
        click.echo(f"Recommendation: {result.recommendation}")
    click.echo("---")
    click.echo(result.answer)
    if docs_content:
        preview = docs_content[:1000]
        click.echo("\n--- Documentation supplement ---")
        click.echo(preview)


@main.command("consult-expert")
@click.option("--question", required=True, help="Technical question to ask.")
@click.option("--domain", default=None, help="Expert domain override.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def consult_expert_cmd(question: str, domain: str | None, as_json: bool) -> None:
    """Consult a domain expert (no MCP server required)."""
    import json

    from tapps_core.experts.engine import consult_expert

    result = consult_expert(question=question, domain=domain)

    if as_json:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
        return

    click.echo(f"Domain: {result.domain} | Expert: {result.expert_name}")
    click.echo(f"Confidence: {result.confidence:.0%}")
    click.echo(f"Sources: {', '.join(result.sources) if result.sources else 'none'}")
    if result.recommendation:
        click.echo(f"Recommendation: {result.recommendation}")
    click.echo("---")
    click.echo(result.answer)


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
