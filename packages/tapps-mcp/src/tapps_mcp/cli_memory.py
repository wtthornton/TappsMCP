"""Memory CLI command group."""

from __future__ import annotations

from typing import Any, Literal, cast

import click

# ---------------------------------------------------------------------------
# Memory CLI group (Story 53.1)
# ---------------------------------------------------------------------------


@click.group("memory")
def memory_group() -> None:
    """Manage shared project memories (no MCP server required)."""


@memory_group.command("list")
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

    from tapps_mcp.cli import _brain_bridge_unavailable_message, _create_cli_brain_bridge

    async def _list() -> list[dict[str, object]]:
        bridge = _create_cli_brain_bridge()
        if bridge is None:
            raise RuntimeError("bridge_unavailable")
        try:
            # BrainBridge.list_memories filters by tier; scope is client-side.
            entries = await bridge.list_memories(limit=500, tier=tier)
            if scope:
                entries = [e for e in entries if e.get("scope") == scope]
            return entries
        finally:
            bridge.close()

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


@memory_group.command("save")
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

    from tapps_mcp.cli import _brain_bridge_unavailable_message, _create_cli_brain_bridge

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    async def _save() -> dict[str, object]:
        bridge = _create_cli_brain_bridge()
        if bridge is None:
            raise RuntimeError("bridge_unavailable")
        save_kwargs: dict[str, Any] = {}
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


@memory_group.command("get")
@click.option("--key", required=True, help="Memory key to retrieve.")
def memory_get(key: str) -> None:
    """Retrieve a memory entry by key via BrainBridge (HTTP or in-process DSN)."""
    import asyncio
    import json

    from tapps_mcp.cli import _brain_bridge_unavailable_message, _create_cli_brain_bridge

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


@memory_group.command("recall")
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
    from tapps_mcp.cli import _get_project_root

    root = _get_project_root() if project_root == "." else Path(project_root).resolve()
    max_results = max(1, min(max_results, 10))
    min_score = max(0.0, min(min_score, 1.0))

    async def _recall() -> tuple[list[dict[str, object]], list[dict[str, Any]]]:
        settings = load_settings(project_root=root)
        # Read-only auto-recall calls ``brain_recall`` (VAL-21 / TAP-6701),
        # the relevance-ranked recall that carries a wire ``score`` per hit
        # (BrainBridge.recall) rather than ``memory_search``'s unranked,
        # score-less structured filter. ``brain_recall`` sits in the same
        # least-privilege ``reviewer`` profile ``memory_search`` used
        # (ADR-0012; mcp_profiles.yaml:277), so no profile widening is
        # needed. ``coder`` hides both and silently returned no hits on
        # v3.20.0+.
        bridge = create_brain_bridge(settings, default_profile=BRAIN_PROFILE_READONLY)
        if bridge is None:
            return [], []
        try:
            pinned: list[dict[str, object]] = []
            for key in recall_keys:
                entry = await bridge.get(key)
                if entry is not None:
                    pinned.append(entry)
            hits = await bridge.recall(query, max_results=max_results)
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
    # Wire "score" (KB-3.1 composite retrieval score) is the only filter key;
    # a hit missing it (older-brain response) is passed through unfiltered
    # rather than defaulting to a fabricated confidence value.
    filtered = []
    score_absent = False
    for hit in hits:
        score = hit.get("score")
        if score is None:
            score_absent = True
            filtered.append(hit)
            continue
        if float(score) >= min_score:
            filtered.append(hit)
    if score_absent:
        import structlog

        structlog.get_logger(__name__).debug(
            "memory_recall_score_absent",
            hint="hit missing wire 'score' key; passed through unfiltered",
        )
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
    hits: list[dict[str, Any]],
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


@memory_group.command("search")
@click.option("--query", required=True, help="Search query.")
@click.option("--limit", default=10, type=int, help="Max results.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def memory_search(query: str, limit: int, as_json: bool) -> None:
    """Search memories via BrainBridge (HTTP or DSN) or local MemoryStore fallback."""
    import asyncio
    import json

    from tapps_core.brain_bridge import BRAIN_PROFILE_READONLY, create_brain_bridge
    from tapps_core.config.settings import load_settings
    from tapps_mcp.cli import _get_project_root

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


@memory_group.command("promote-instincts")
@click.option(
    "--project",
    default=None,
    help="Homunculus project name to scan (default: this checkout's project root).",
)
@click.option(
    "--dry-run/--apply",
    "dry_run",
    default=True,
    help="Preview candidates (default) or write promotions after operator ACCEPT.",
)
@click.option(
    "--report",
    "report_path",
    default=None,
    type=click.Path(path_type=str),
    help="Path for the dry-run diff report (default: reports/promote-instincts.md).",
)
@click.option(
    "--operator",
    default=None,
    help="Operator name for promoted_by=operator:<name> (required with --apply).",
)
def memory_promote_instincts(
    project: str | None,
    dry_run: bool,
    report_path: str | None,
    operator: str | None,
) -> None:
    """Preview or apply staged-instinct -> brain-memory promotions (KB-3.8, Ruling 8).

    ``--dry-run`` (default) only reads ``~/.claude/homunculus/`` and writes a
    diff report; it never touches the brain. ``--apply`` requires
    ``--operator`` and calls ``BrainBridge.promote_instinct`` for each
    candidate lacking ``promoted_key:`` (idempotent — a second run makes 0
    additional promote calls), then appends ``promoted_key:`` to the
    instinct's frontmatter.
    """
    from pathlib import Path

    from tapps_mcp.cli import _get_project_root
    from tapps_mcp.tools.instinct_promotion import select_instinct_candidates, write_dry_run_report

    homunculus_root = Path.home() / ".claude" / "homunculus"
    candidates = select_instinct_candidates(
        homunculus_root, _get_project_root(), project_name=project
    )
    out_path = write_dry_run_report(candidates, Path(report_path) if report_path else None)
    click.echo(out_path.read_text(encoding="utf-8"))
    click.echo(f"Report written to {out_path}")

    if dry_run:
        return
    if not operator:
        click.echo("Error: --operator is required with --apply.", err=True)
        raise SystemExit(2)
    if not candidates:
        click.echo("No candidates to apply.")
        return
    _run_promote_apply(candidates, operator)


def _run_promote_apply(candidates: list[dict[str, object]], operator: str) -> None:
    """Apply promotions via a fresh BrainBridge (SC-6: never invoked from this lane's tests
    against a real brain — only reachable through ``--apply``, which callers must mock)."""
    import asyncio

    from tapps_mcp.cli import _brain_bridge_unavailable_message, _create_cli_brain_bridge
    from tapps_mcp.tools.instinct_promotion import apply_promotions

    async def _apply() -> list[dict[str, object]]:
        bridge = _create_cli_brain_bridge()
        if bridge is None:
            raise RuntimeError("bridge_unavailable")
        try:
            return await apply_promotions(candidates, bridge, operator=operator)
        finally:
            bridge.close()

    try:
        results = asyncio.run(_apply())
    except NotImplementedError as exc:
        # In-process BrainBridge (no brain_http_url configured) has no
        # learning_promote capability yet — see BrainBridge.promote_instinct.
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(2) from None
    except RuntimeError as exc:
        if str(exc) == "bridge_unavailable":
            click.echo(_brain_bridge_unavailable_message(), err=True)
            raise SystemExit(2) from None
        raise
    click.echo(f"Promoted {len(results)} instinct(s).")


@memory_group.command("delete")
@click.option("--key", required=True, help="Memory key to delete.")
def memory_delete(key: str) -> None:
    """Delete a memory entry via BrainBridge."""
    import asyncio

    from tapps_mcp.cli import _brain_bridge_unavailable_message, _create_cli_brain_bridge

    async def _delete() -> bool:
        bridge = _create_cli_brain_bridge()
        if bridge is None:
            raise RuntimeError("bridge_unavailable")
        try:
            return bool(await bridge.delete(key))
        finally:
            bridge.close()

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


@memory_group.command("import-file")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True))
@click.option("--overwrite", is_flag=True, help="Overwrite existing keys.")
def memory_import(file_path: str, overwrite: bool) -> None:
    """Import memories from a JSON file."""
    from pathlib import Path

    from tapps_brain.io import import_memories
    from tapps_brain.store import MemoryStore

    from tapps_core.security.path_validator import PathValidator
    from tapps_mcp.cli import _get_project_root

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


@memory_group.command("export-file")
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
    from tapps_mcp.cli import _get_project_root

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
            export_format=cast("Literal['json', 'markdown']", export_format),
        )
        click.echo(f"Exported {result['exported_count']} memories to {result['file_path']}")
    finally:
        store.close()


@memory_group.command("reseed")
@click.option(
    "--confirm",
    is_flag=True,
    required=True,
    help="Confirm re-seeding from the detected project profile.",
)
def memory_reseed(confirm: bool) -> None:
    """Re-seed memories from the project profile (auto-seeded entries only)."""
    from tapps_mcp.cli import _get_project_root

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
