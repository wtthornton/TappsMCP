"""Audit / metrics / capture CLI commands."""

from __future__ import annotations

import os
from pathlib import Path

import click


@click.command("usage-gaps-hint")
@click.option(
    "--project-root",
    default=".",
    help="Project root directory.",
)
def usage_gaps_hint_cmd(project_root: str) -> None:
    """Print a one-line prior-session pipeline reminder for SessionStart hooks (TAP-3578)."""
    from pathlib import Path

    from tapps_mcp.tools.usage import format_session_start_gap_hint

    hint = format_session_start_gap_hint(Path(project_root).resolve())
    if hint:
        click.echo(hint)


@click.command("audit-fleet")
@click.option(
    "--period",
    type=click.Choice(["1d", "7d", "30d"]),
    default="1d",
    show_default=True,
    help="Trailing window for tool-call and pipeline metrics.",
)
@click.option(
    "--roots",
    default="",
    help="Comma-separated project roots (default: TAPPS_FLEET_ROOTS or scan parent dir).",
)
@click.option(
    "--scan-parent",
    default=".",
    help="When --roots is empty, scan immediate children of this directory.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--no-brain",
    is_flag=True,
    default=False,
    help="Skip brain telemetry merge (local JSONL only).",
)
def audit_fleet_cmd(
    period: str,
    roots: str,
    scan_parent: str,
    output_format: str,
    no_brain: bool,
) -> None:
    """Audit TAPPS usage across bootstrapped projects (local JSONL + brain merge).

    Discovers projects via ``--roots``, ``TAPPS_FLEET_ROOTS``, or by scanning
    ``--scan-parent`` for ``.tapps-mcp.yaml`` markers.
    """
    import json
    from pathlib import Path

    from tapps_mcp.tools.fleet_audit import format_fleet_audit_markdown, run_fleet_audit

    explicit: list[Path] | None = None
    if roots.strip():
        explicit = [Path(p.strip()) for p in roots.split(",") if p.strip()]

    report = run_fleet_audit(
        period=period,
        roots=explicit,
        scan_parent=Path(scan_parent),
        include_brain=not no_brain,
    )
    if output_format == "markdown":
        click.echo(format_fleet_audit_markdown(report))
    else:
        click.echo(json.dumps(report, indent=2))


@click.command("loop-metrics-record")
def loop_metrics_record_cmd() -> None:
    """Record loop-metrics from Cursor/Claude stop-hook stdin (TAP-3918)."""
    import json
    import sys

    from tapps_mcp.tools.loop_metrics import record_loop_metrics_from_hook_payload

    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    result = record_loop_metrics_from_hook_payload(payload)
    followup = result.get("followup_message")
    if followup:
        click.echo(json.dumps({"followup_message": followup}))


@click.command("tool-usage-fleet")
@click.option(
    "--period",
    type=click.Choice(["1d", "7d", "30d"]),
    default="1d",
    show_default=True,
    help="Trailing window for tool-call metrics.",
)
@click.option(
    "--roots",
    default="",
    help="Comma-separated project roots (default: TAPPS_FLEET_ROOTS or scan parent dir).",
)
@click.option(
    "--scan-parent",
    default=".",
    help="When --roots is empty, scan immediate children of this directory.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--no-brain",
    is_flag=True,
    default=False,
    help="Skip brain telemetry merge (local JSONL only).",
)
def tool_usage_fleet_cmd(
    period: str,
    roots: str,
    scan_parent: str,
    output_format: str,
    no_brain: bool,
) -> None:
    """Per-tool fleet usage leaderboard (TAP-3919)."""
    import json
    from pathlib import Path

    from tapps_mcp.tools.fleet_audit import (
        format_tool_usage_fleet_markdown,
        run_tool_usage_fleet,
    )

    explicit: list[Path] | None = None
    if roots.strip():
        explicit = [Path(p.strip()) for p in roots.split(",") if p.strip()]

    report = run_tool_usage_fleet(
        period=period,
        roots=explicit,
        scan_parent=Path(scan_parent),
        include_brain=not no_brain,
    )
    if output_format == "markdown":
        click.echo(format_tool_usage_fleet_markdown(report))
    else:
        click.echo(json.dumps(report, indent=2))


@click.command("check-agents-md-stamp")
@click.option(
    "--project-root",
    default=".",
    help="Project root directory (defaults to current dir).",
)
def check_agents_md_stamp(project_root: str) -> None:
    """Release gate — exit 1 if AGENTS.md version marker != pyproject version (TAP-982).

    Minimal, single-purpose check suitable for release CI. Faster than a full
    ``doctor`` run and reports only the stamp-vs-package comparison so the
    failure message is unambiguous.
    """
    from pathlib import Path

    from tapps_mcp.distribution.doctor import check_agents_md_stamp_matches_package

    result = check_agents_md_stamp_matches_package(Path(project_root))
    status = "OK" if result.ok else "FAIL"
    click.echo(f"[{status}] {result.name}: {result.message}")
    if result.detail:
        click.echo(f"       {result.detail}")
    if not result.ok:
        raise SystemExit(1)


@click.command("auto-capture")
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
@click.option(
    "--transcript-turns",
    default=None,
    type=int,
    help=(
        "Max transcript turns read when payload has no inline context "
        "(default: memory_hooks.auto_capture.transcript_turns, 40)."
    ),
)
@click.option(
    "--transcript-max-bytes",
    default=None,
    type=int,
    help=(
        "Byte cap on transcript text read "
        "(default: memory_hooks.auto_capture.transcript_max_bytes, 32768)."
    ),
)
def auto_capture(
    project_root: str,
    max_facts: int,
    transcript_turns: int | None,
    transcript_max_bytes: int | None,
) -> None:
    """Extract durable facts from stdin (Stop hook JSON) and save to memory (Epic 65.5).

    Read JSON from stdin (Claude Code Stop event), extract decision-like facts,
    and save to project memory. Invoked by memory_auto_capture Stop hook.

    Echoes one JSON line to stdout with the result summary; writes a WARNING
    to stderr naming the reason when nothing was saved.
    """
    import asyncio
    import json
    import sys
    from pathlib import Path

    project_root_path = Path(
        os.environ.get("CLAUDE_PROJECT_DIR")
        or os.environ.get("TAPPS_MCP_PROJECT_ROOT")
        or project_root
    ).resolve()
    raw = sys.stdin.read()
    from tapps_mcp.memory.auto_capture import run_auto_capture

    result = asyncio.run(
        run_auto_capture(
            raw,
            project_root_path,
            max_facts=max_facts,
            transcript_turns=transcript_turns,
            transcript_max_bytes=transcript_max_bytes,
        )
    )
    click.echo(
        json.dumps(
            {
                "saved": result.get("saved", 0),
                "facts": result.get("facts", 0),
                "reason": result.get("reason"),
                "session_id": result.get("session_id"),
            }
        )
    )
    if result.get("saved", 0) == 0:
        click.echo(
            f"WARNING: auto-capture saved 0 facts (reason={result.get('reason')})",
            err=True,
        )


@click.command("compact-index")
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root directory (default: CLAUDE_PROJECT_DIR or current).",
)
def compact_index_cmd(project_root: str) -> None:
    """Index pre-compaction session state in brain (PreCompact hook, TAP-2017).

    Read JSON from stdin (Claude Code PreCompact event), index the session
    context via memory_index_session, and write a compaction marker so
    tapps_session_start can surface prior session context on rehydration.

    Disabled by setting TAPPS_MCP_COMPACTION_REHYDRATE=false.
    """
    import asyncio
    import sys
    from pathlib import Path

    project_root_path = Path(
        os.environ.get("CLAUDE_PROJECT_DIR")
        or os.environ.get("TAPPS_MCP_PROJECT_ROOT")
        or project_root
    ).resolve()
    raw = sys.stdin.read()
    from tapps_mcp.memory.compact_index import run_compact_index

    asyncio.run(run_compact_index(raw, project_root_path))


@click.command("pipeline-mark")
@click.argument(
    "kind",
    type=click.Choice(["contract-verified", "creator-verifier"], case_sensitive=False),
)
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Project root (default: CWD).",
)
def pipeline_mark_cmd(kind: str, project_root: Path | None) -> None:
    """Record a contract-verified or creator-verifier mark (clears usage gaps)."""
    from tapps_mcp.tools.contract_telemetry import record_pipeline_mark

    root = (project_root or Path.cwd()).expanduser().resolve()
    normalized = kind.lower()
    if normalized == "contract-verified":
        record_pipeline_mark(root, kind="contract-verified", source="cli")
    else:
        record_pipeline_mark(root, kind="creator-verifier", source="cli")
    click.echo(f"Recorded pipeline-mark kind={normalized} under {root / '.tapps-mcp'}")


@click.command("lookup-docs")
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
    cache = KBCache(
        settings.project_root / ".tapps-mcp-cache",
        max_mb=settings.cache_max_mb,
    )

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

        from tapps_mcp.tools.lookup_telemetry import record_lookup_event

        record_lookup_event(
            settings.project_root,
            library=result.library or library,
            topic=result.topic or topic,
            source="cli",
            resolved_library=result.library if result.library != library else None,
        )

    asyncio.run(_run())
