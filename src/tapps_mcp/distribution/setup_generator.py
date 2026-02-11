"""One-command setup generator for TappsMCP across MCP hosts.

Generates MCP configuration files for Claude Code, Cursor, and VS Code,
with auto-detection of installed hosts and config merging.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from tapps_mcp.common.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config templates per host
# ---------------------------------------------------------------------------

_TAPPS_SERVER_ENTRY: dict[str, Any] = {
    "command": "tapps-mcp",
    "args": ["serve"],
}

_HOST_CONFIGS: dict[str, dict[str, Any]] = {
    "claude-code": {
        "mcpServers": {
            "tapps-mcp": _TAPPS_SERVER_ENTRY,
        },
    },
    "cursor": {
        "mcpServers": {
            "tapps-mcp": _TAPPS_SERVER_ENTRY,
        },
    },
    "vscode": {
        "servers": {
            "tapps-mcp": _TAPPS_SERVER_ENTRY,
        },
    },
}

# ---------------------------------------------------------------------------
# Host detection
# ---------------------------------------------------------------------------


def _detect_hosts() -> list[str]:
    """Detect which MCP hosts are installed on this system.

    Returns:
        List of detected host names (e.g. ``["claude-code", "cursor"]``).
    """
    detected: list[str] = []

    # Claude Code: look for ~/.claude/ directory
    claude_dir = Path.home() / ".claude"
    if claude_dir.is_dir():
        detected.append("claude-code")

    # Cursor: platform-dependent settings path
    cursor_path = _get_cursor_settings_dir()
    if cursor_path is not None and cursor_path.is_dir():
        detected.append("cursor")

    # VS Code: platform-dependent settings path
    vscode_path = _get_vscode_settings_dir()
    if vscode_path is not None and vscode_path.is_dir():
        detected.append("vscode")

    return detected


def _get_cursor_settings_dir() -> Path | None:
    """Return the Cursor global settings directory, or ``None`` if unknown."""
    if sys.platform == "win32":
        appdata = Path.home() / "AppData" / "Roaming" / "Cursor"
    elif sys.platform == "darwin":
        appdata = Path.home() / "Library" / "Application Support" / "Cursor"
    else:
        appdata = Path.home() / ".config" / "Cursor"
    return appdata


def _get_vscode_settings_dir() -> Path | None:
    """Return the VS Code global settings directory, or ``None`` if unknown."""
    if sys.platform == "win32":
        appdata = Path.home() / "AppData" / "Roaming" / "Code"
    elif sys.platform == "darwin":
        appdata = Path.home() / "Library" / "Application Support" / "Code"
    else:
        appdata = Path.home() / ".config" / "Code"
    return appdata


# ---------------------------------------------------------------------------
# Config file paths
# ---------------------------------------------------------------------------


def _get_config_path(host: str, project_root: Path) -> Path:
    """Return the config file path for a given host.

    Args:
        host: One of ``"claude-code"``, ``"cursor"``, ``"vscode"``.
        project_root: The project root directory.

    Returns:
        The ``Path`` to the config file that should be written.
    """
    if host == "claude-code":
        return Path.home() / ".claude.json"
    if host == "cursor":
        return project_root / ".cursor" / "mcp.json"
    if host == "vscode":
        return project_root / ".vscode" / "mcp.json"
    msg = f"Unknown host: {host}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Config merging
# ---------------------------------------------------------------------------


def _get_servers_key(host: str) -> str:
    """Return the top-level key that holds server definitions.

    Args:
        host: One of ``"claude-code"``, ``"cursor"``, ``"vscode"``.

    Returns:
        ``"mcpServers"`` for Claude Code / Cursor, ``"servers"`` for VS Code.
    """
    if host == "vscode":
        return "servers"
    return "mcpServers"


def _merge_config(existing: dict[str, Any], host: str) -> dict[str, Any]:
    """Merge the tapps-mcp entry into an existing config dict.

    Only adds/replaces the ``tapps-mcp`` key inside the servers object;
    all other keys are preserved.

    Args:
        existing: The parsed JSON from the existing config file.
        host: The target host name.

    Returns:
        The merged config dict.
    """
    servers_key = _get_servers_key(host)
    merged = dict(existing)
    if servers_key not in merged:
        merged[servers_key] = {}
    merged[servers_key]["tapps-mcp"] = _TAPPS_SERVER_ENTRY.copy()
    return merged


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def _generate_config(host: str, project_root: Path, *, force: bool = False) -> bool:
    """Generate (or merge) the MCP config for the given host.

    Args:
        host: Target host name.
        project_root: Project root directory.
        force: If ``True``, overwrite any existing ``tapps-mcp`` entry without
            prompting. Intended for non-interactive use (CI, scripts).

    Returns:
        ``True`` if configuration was successfully written, ``False`` if the
        operation was aborted or failed (e.g. invalid JSON).
    """
    config_path = _get_config_path(host, project_root)
    servers_key = _get_servers_key(host)

    if config_path.exists():
        # Read existing config and merge
        try:
            raw = config_path.read_text(encoding="utf-8")
            existing = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            click.echo(
                click.style(
                    f"Invalid JSON in {config_path}.",
                    fg="red",
                )
            )
            click.echo(
                "  Please fix the file manually (or delete it) and re-run "
                "'tapps-mcp init' to avoid losing other MCP server entries."
            )
            return False

        # Check if tapps-mcp already configured
        if servers_key in existing and "tapps-mcp" in existing.get(servers_key, {}):
            click.echo(
                click.style(
                    f"tapps-mcp is already configured in {config_path}",
                    fg="yellow",
                )
            )
            if not force:
                if not click.confirm("Overwrite the existing tapps-mcp entry?"):
                    click.echo("Aborted.")
                    return False

        merged = _merge_config(existing, host)
    else:
        merged = _HOST_CONFIGS[host].copy()

    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        json.dumps(merged, indent=2) + "\n",
        encoding="utf-8",
    )

    click.echo(click.style(f"Configuration written to {config_path}", fg="green"))
    _print_next_steps(host)
    return True


def _print_next_steps(host: str) -> None:
    """Print helpful next-steps after config generation.

    Args:
        host: The host that was configured.
    """
    click.echo("")
    click.echo("Next steps:")
    if host == "claude-code":
        click.echo("  1. Restart Claude Code (or run: claude mcp list)")
        click.echo("  2. Ask Claude to use TappsMCP tools")
    elif host == "cursor":
        click.echo("  1. Restart Cursor (or reload the window)")
        click.echo("  2. The MCP tools will be available in Cursor's agent mode")
    elif host == "vscode":
        click.echo("  1. Restart VS Code (or reload the window)")
        click.echo("  2. The MCP tools will be available in Copilot chat")


# ---------------------------------------------------------------------------
# Check mode
# ---------------------------------------------------------------------------


def _check_config(host: str, project_root: Path) -> bool:
    """Verify that the tapps-mcp entry exists and looks valid.

    Args:
        host: Target host name.
        project_root: Project root directory.

    Returns:
        ``True`` if configuration looks valid, ``False`` otherwise.
    """
    config_path = _get_config_path(host, project_root)
    servers_key = _get_servers_key(host)

    if not config_path.exists():
        click.echo(click.style(f"Config file not found: {config_path}", fg="red"))
        click.echo(f"  Run: tapps-mcp init --host {host}")
        return False

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError:
        click.echo(click.style(f"Invalid JSON in {config_path}", fg="red"))
        return False

    servers = data.get(servers_key, {})
    if "tapps-mcp" not in servers:
        click.echo(
            click.style(
                f"tapps-mcp entry not found in {config_path} under '{servers_key}'",
                fg="red",
            )
        )
        click.echo(f"  Run: tapps-mcp init --host {host}")
        return False

    entry = servers["tapps-mcp"]
    command = entry.get("command", "")
    if command != "tapps-mcp":
        click.echo(
            click.style(
                f"Unexpected command in tapps-mcp config: '{command}' (expected 'tapps-mcp')",
                fg="yellow",
            )
        )
        return False

    click.echo(click.style(f"tapps-mcp is correctly configured in {config_path}", fg="green"))
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_init(
    *,
    mcp_host: str = "auto",
    project_root: str = ".",
    check: bool = False,
    force: bool = False,
) -> bool:
    """Run the init command logic.

    Called from the CLI ``init`` command.

    Args:
        mcp_host: Target host or ``"auto"`` for detection.
        project_root: Project root directory as a string path.
        check: If ``True``, verify existing configuration instead of generating.
    """
    root = Path(project_root).resolve()
    log.info(
        "init_command",
        host=mcp_host,
        project_root=str(root),
        check=check,
        force=force,
    )

    if mcp_host == "auto":
        hosts = _detect_hosts()
        if not hosts:
            click.echo(
                click.style(
                    "No MCP hosts detected. Please specify one with --host.",
                    fg="yellow",
                )
            )
            click.echo("  Supported hosts: claude-code, cursor, vscode")
            # Nothing to do, but this is not an error condition.
            return True
        click.echo(f"Detected MCP host(s): {', '.join(hosts)}")
        # Use the first detected host
        resolved_host = hosts[0]
        if len(hosts) > 1:
            click.echo(f"  Using: {resolved_host} (specify --host to choose another)")
    else:
        resolved_host = mcp_host

    if check:
        return _check_config(resolved_host, root)

    return _generate_config(resolved_host, root, force=force)
