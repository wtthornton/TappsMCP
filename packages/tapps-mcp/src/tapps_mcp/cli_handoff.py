"""Cross-session handoff CLI command group."""

from __future__ import annotations

import click


@click.group("handoff")
def handoff_group() -> None:
    """Cross-session handoff utilities."""


@handoff_group.command("write")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="Read handoff markdown from a file (else stdin when piped).",
)
@click.option(
    "--project-root",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    help="Project root directory.",
)
@click.option(
    "--no-brain-mirror",
    is_flag=True,
    help="Skip brain mirror (file only).",
)
@click.option(
    "--session-end",
    "with_session_end",
    is_flag=True,
    help="Also run session-end flywheel after write.",
)
@click.option(
    "--allow-lint-warnings",
    is_flag=True,
    help="Allow advisory lint warnings (still fails on P0/Open errors).",
)
def handoff_write(
    file_path: str | None,
    project_root: str,
    no_brain_mirror: bool,
    with_session_end: bool,
    allow_lint_warnings: bool,
) -> None:
    """Atomically write session handoff file, mirror to brain, and lint schema."""
    import json
    import sys
    from pathlib import Path

    from tapps_mcp.cli import _get_project_root
    from tapps_mcp.tools.handoff_write import HandoffWriteError, write_handoff_sync

    root = _get_project_root() if project_root == "." else Path(project_root).resolve()
    if file_path:
        markdown = Path(file_path).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        markdown = sys.stdin.read()
    else:
        click.echo("Provide --file or pipe handoff markdown on stdin.", err=True)
        raise SystemExit(2)

    if not markdown.strip():
        click.echo("Handoff markdown is empty.", err=True)
        raise SystemExit(2)

    try:
        result = write_handoff_sync(
            root,
            markdown,
            mirror_brain=not no_brain_mirror,
            run_session_end=with_session_end,
            fail_on_lint_errors=True,
        )
    except HandoffWriteError as exc:
        click.echo("Handoff schema lint failed:", err=True)
        for err in exc.errors:
            click.echo(f"  error: {err}", err=True)
        for warn in exc.warnings:
            click.echo(f"  warning: {warn}", err=True)
        raise SystemExit(1) from exc

    if not allow_lint_warnings and result.lint.warnings:
        click.echo("Handoff lint warnings (use --allow-lint-warnings to persist anyway):", err=True)
        for warn in result.lint.warnings:
            click.echo(f"  warning: {warn}", err=True)
        raise SystemExit(1)

    payload = {
        "file_path": result.file_path,
        "linear_p0": result.doc.linear_p0,
        "metadata": result.metadata,
        "lint": {
            "ok": result.lint.ok,
            "errors": result.lint.errors,
            "warnings": result.lint.warnings,
        },
        "brain_mirror": result.brain_mirror,
        "session_end": result.session_end,
    }
    click.echo(json.dumps(payload, indent=2))
