"""Standalone CLI validation commands."""

from __future__ import annotations

import os

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
