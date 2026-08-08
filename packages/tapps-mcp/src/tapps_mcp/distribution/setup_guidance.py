"""What we tell the user after writing an MCP config.

Next-step instructions per host, the Context7 operator-secrets hint, and a live
Context7 probe so a bad or missing key surfaces at setup time rather than during
the first ``tapps_lookup_docs`` call mid-edit.
Split out of ``setup_generator`` (TAP-5733).
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from tapps_mcp.distribution.setup_wrappers import operator_env_path


def _print_next_steps(host: str, *, project_root: Path | None = None) -> None:
    """Print helpful next-steps after config generation.

    Args:
        host: The host that was configured.
        project_root: Consumer project root (for Context7 hint context).
    """
    click.echo("")
    click.echo("Next steps:")
    click.echo(
        "  • Pipeline: tapps_lookup_docs **before** external API edits → "
        "tapps_quick_check after edits → /tapps-finish-task before done"
    )
    if host == "claude-code":
        click.echo("  1. Restart Claude Code (or run: claude mcp list)")
        click.echo("  2. Ask Claude to use TappsMCP tools")
    elif host == "cursor":
        click.echo("  1. Restart Cursor (or reload the window)")
        click.echo("  2. The MCP tools will be available in Cursor's agent mode")
        if project_root is not None:
            click.echo(
                "  3. Operator secrets: ~/.tapps-operator.env (Context7 + brain bearer) — "
                "serve wrappers source it before spawn; see docs/operations/OPERATOR-SECRETS.md"
            )
    elif host == "vscode":
        click.echo("  1. Restart VS Code (or reload the window)")
        click.echo("  2. The MCP tools will be available in Copilot chat")
    _print_context7_hint_if_missing()


def _print_context7_hint_if_missing() -> None:
    """Print a one-time hint about TAPPS_MCP_CONTEXT7_API_KEY (Issue #79)."""
    if os.environ.get("TAPPS_MCP_CONTEXT7_API_KEY") or os.environ.get("CONTEXT7_API_KEY"):
        return
    if operator_env_path().is_file():
        return
    click.echo("")
    click.echo(
        click.style(
            "Optional: set operator secrets in ~/.tapps-operator.env for live Context7 docs.",
            fg="cyan",
        )
    )
    click.echo("  See docs/operations/OPERATOR-SECRETS.md — one file shared across all repos.")
    click.echo("  Without it, tapps_lookup_docs falls back to LlmsTxt (reduced coverage).")
    click.echo("  Get a key: https://context7.com")


def _verify_context7_live(root: Path, api_key_override: str | None = None) -> None:
    """Live-probe Context7 after scaffolding so a bad key surfaces now, not mid-edit.

    Warn-only: the llms.txt fallback keeps lookups working when Context7 is
    down or unconfigured. Skipped when docs route through tapps-brain. When
    ``api_key_override`` is given (init just received a ``--context7-api-key``),
    that key is probed directly — it may not be exported in the process env yet.
    """
    from pydantic import SecretStr

    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.brain_docs import docs_via_brain_enabled
    from tapps_mcp.diagnostics import probe_context7

    try:
        settings = load_settings(project_root=root)
    except Exception:
        return
    if docs_via_brain_enabled(settings):
        return

    api_key = SecretStr(api_key_override) if api_key_override else settings.context7_api_key
    if api_key is None:
        return

    diag = probe_context7(root, api_key, force=True)
    if diag.status == "available":
        latency = f"{diag.latency_ms:.0f}ms" if diag.latency_ms is not None else ""
        click.echo(click.style(f"  Context7 verified — reachable ({latency}).", fg="green"))
    elif diag.status == "unauthorized":
        click.echo(
            click.style(
                "  Context7 key rejected (expired/revoked). Rotate TAPPS_MCP_CONTEXT7_API_KEY "
                "— https://context7.com. Lookups will use the llms.txt fallback meanwhile.",
                fg="yellow",
            )
        )
    elif diag.status == "unreachable":
        click.echo(
            click.style(
                f"  Context7 unreachable ({diag.detail or 'network error'}). "
                "llms.txt fallback active; re-run doctor once connectivity returns.",
                fg="yellow",
            )
        )
