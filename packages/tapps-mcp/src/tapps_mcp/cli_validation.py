"""Standalone CLI validation commands."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click


def _echo_validate_changed_data(data: dict[str, object]) -> None:
    """Print batch validation summary and per-file failure diagnostics."""
    summary = data.get("summary", "")
    if summary:
        click.echo(str(summary))
    rows = data.get("summary_rows")
    for row in rows if isinstance(rows, list) else []:
        click.echo(str(row))
    per_file = data.get("per_file_results")
    for entry in per_file if isinstance(per_file, list) else []:
        if not isinstance(entry, dict) or entry.get("status") != "FAIL":
            continue
        for finding in entry.get("top_findings") or []:
            if not isinstance(finding, dict):
                continue
            code = finding.get("code", "")
            message = finding.get("message", "")
            line = finding.get("line", "?")
            click.echo(f"  {code}: {message} (line {line})")
        for hint in entry.get("improvement_hints") or []:
            click.echo(f"  hint: {hint}")


@click.command("validate-changed")
@click.option(
    "--quick/--full",
    default=True,
    help="Quick (ruff-only) or full validation. Default: quick.",
)
@click.option(
    "--file-paths",
    "--paths",
    default="",
    help="Comma-separated file paths (default: git auto-detect changed files).",
)
@click.option(
    "--security-depth",
    type=click.Choice(["none", "basic", "full"]),
    default=None,
    help="Security scan depth (overrides --quick/--full default).",
)
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root (default: current directory).",
)
def validate_changed_cmd(
    quick: bool, file_paths: str, security_depth: str | None, project_root: str
) -> None:
    """Validate changed Python files (same logic as the MCP tool).

    Run this before ending a session to confirm changed files pass quality gates.
    Without --file-paths, uses git to detect changed files, then runs quick
    (ruff-only) or full (ruff + mypy + bandit + radon + vulture) checks per file.
    """
    import asyncio

    if project_root != ".":
        os.chdir(project_root)

    asyncio.run(_run_validate_changed(quick, file_paths, security_depth))


async def _run_validate_changed(quick: bool, file_paths: str, security_depth: str | None) -> None:
    """Run validation and render its CLI result."""
    from tapps_mcp.server_pipeline_tools import tapps_validate_changed
    from tapps_mcp.tools.validate_changed_cli_exit import validate_changed_cli_exit_code

    kwargs: dict[str, object] = {
        "file_paths": file_paths,
        "quick": quick,
        "include_security": not quick if security_depth is None else security_depth != "none",
    }
    if security_depth is not None:
        kwargs["security_depth"] = security_depth
    result = await tapps_validate_changed(**kwargs)  # type: ignore[arg-type]
    if not result.get("success"):
        click.echo(result.get("error", "Validation failed."), err=True)
        raise SystemExit(1)
    raw_data = result.get("data", {})
    data = raw_data if isinstance(raw_data, dict) else {}
    _echo_validate_changed_data(data)
    code = validate_changed_cli_exit_code(data, explicit_paths=bool(file_paths.strip()))
    if code != 0:
        raise SystemExit(code)


@click.command("quick-check")
@click.option(
    "--file-path",
    required=True,
    help="Path to the Python file to validate.",
)
@click.option(
    "--preset",
    default="standard",
    show_default=True,
    type=click.Choice(["standard", "strict", "framework"]),
    help="Quality gate preset.",
)
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root (default: current directory).",
)
def quick_check_cmd(file_path: str, preset: str, project_root: str) -> None:
    """Quick score + gate + security for one file (MCP tapps_quick_check equivalent)."""
    import asyncio

    from tapps_mcp.server_scoring_tools import tapps_quick_check

    if project_root != ".":
        os.chdir(project_root)

    async def _run() -> None:
        result = await tapps_quick_check(file_path, preset=preset)
        if not result.get("success"):
            click.echo(result.get("error", "Quick check failed."), err=True)
            raise SystemExit(1)
        data = result.get("data", {})
        path = data.get("file_path", file_path)
        score = data.get("overall_score", 0)
        gate = "pass" if data.get("gate_passed") else "fail"
        click.echo(f"{path}: score={score}, gate={gate}")
        for issue in data.get("lint_issues") or []:
            if isinstance(issue, dict):
                click.echo(
                    f"  {issue.get('code', '')}: {issue.get('message', '')} "
                    f"(line {issue.get('line', '?')})"
                )
        if not data.get("gate_passed", False):
            raise SystemExit(1)

    asyncio.run(_run())


@click.command("session-budget")
@click.option(
    "--transcript",
    "--transcript-path",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=str),
    help="Path to session transcript (JSONL format).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output as JSON (default: human-readable).",
)
@click.option(
    "--threshold",
    type=int,
    default=110000,
    show_default=True,
    help="Token threshold for 'over' verdict.",
)
def session_budget_cmd(transcript: str, as_json: bool, threshold: int) -> None:
    """Measure session transcript size and check if it exceeds budget threshold.

    Reads a Claude Code session transcript (JSONL format) and estimates token count.
    Returns whether the transcript exceeds the configured threshold (default 110K tokens).
    Use this to detect when a session needs rotation to a fresh context.
    """
    from tapps_mcp.distribution.context_budget import _estimate_tokens

    transcript_path = Path(transcript)
    if not transcript_path.is_file():
        raise click.ClickException(f"Transcript not found: {transcript}")

    try:
        total_bytes = 0
        message_count = 0
        tool_use_count = 0
        try:
            with transcript_path.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Count bytes of this entry
                    total_bytes += len(line.encode("utf-8"))
                    message_count += 1

                    # Count tool uses
                    msg = entry.get("message") or {}
                    for blk in msg.get("content") or []:
                        if isinstance(blk, dict) and blk.get("type") == "tool_use":
                            tool_use_count += 1
        except OSError as exc:
            raise click.ClickException(f"Failed to read transcript: {exc}") from exc

        estimated_tokens = _estimate_tokens(total_bytes)
        over_budget = estimated_tokens > threshold

        result = {
            "transcript_path": str(transcript_path),
            "total_bytes": total_bytes,
            "estimated_tokens": estimated_tokens,
            "threshold_tokens": threshold,
            "over": over_budget,
            "message_count": message_count,
            "tool_use_count": tool_use_count,
        }

        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            status = "OVER" if over_budget else "OK"
            click.echo(
                f"{status}: {estimated_tokens:,} tokens (threshold: {threshold:,}) "
                f"| messages: {message_count} | tools: {tool_use_count}"
            )
            if over_budget:
                delta = estimated_tokens - threshold
                click.echo(
                    f"  → over by {delta:,} tokens; consider session rotation "
                    f"(write handoff, prompt user, start fresh)"
                )

    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
