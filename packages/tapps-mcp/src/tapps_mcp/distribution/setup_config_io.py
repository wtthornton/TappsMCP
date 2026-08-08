"""MCP host config file locations, JSONC parsing, and validation.

Owns *where* each host keeps its config, *how* to read it (hosts allow JSONC),
and *whether* what is on disk still points at a usable TappsMCP launcher.
Split out of ``setup_generator`` (TAP-5733).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from tapps_mcp.distribution.nlt_mcp_config import list_nlt_server_ids_in_config

# ---------------------------------------------------------------------------
# Config file paths
# ---------------------------------------------------------------------------


def _get_config_path(host: str, project_root: Path, scope: str = "project") -> Path:
    """Return the config file path for a given host and scope.

    Args:
        host: One of ``"claude-code"``, ``"cursor"``, ``"vscode"``.
        project_root: The project root directory.
        scope: ``"project"`` for project-level ``.mcp.json`` (default), or
            ``"user"`` for user-level config. Only affects ``claude-code``.

    Returns:
        The ``Path`` to the config file that should be written.
    """
    if host == "claude-code":
        if scope == "project":
            return project_root / ".mcp.json"
        return Path.home() / ".claude.json"
    if host == "cursor":
        return project_root / ".cursor" / "mcp.json"
    if host == "vscode":
        return project_root / ".vscode" / "mcp.json"
    msg = f"Unknown host: {host}"
    raise ValueError(msg)


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


def _other_scope_config_path(host: str, project_root: Path, scope: str) -> Path | None:
    """Return the config path for the *other* scope, when migration applies.

    Only Claude Code has distinct project/user scopes. Returns ``None`` for
    other hosts or when *scope* is unrecognized.
    """
    if host != "claude-code":
        return None
    if scope == "project":
        return _get_config_path(host, project_root, scope="user")
    if scope == "user":
        return _get_config_path(host, project_root, scope="project")
    return None


def _host_config_exists(host: str, project_root: Path, scope: str = "project") -> bool:
    """Return True when the host's MCP config file exists in *project_root*."""
    return _get_config_path(host, project_root, scope=scope).exists()


def _filter_hosts_for_check(
    hosts: list[str], project_root: Path, scope: str = "project"
) -> list[str]:
    """Limit ``init --check`` to hosts already configured in the project.

    Cursor-only consumers should not fail because Claude Code or VS Code is
    installed globally but not bootstrapped in this repo. When no host config
    exists yet, fall back to checking every detected host.
    """
    configured = [h for h in hosts if _host_config_exists(h, project_root, scope=scope)]
    return configured or hosts


# ---------------------------------------------------------------------------
# JSONC parsing
# ---------------------------------------------------------------------------


def _strip_jsonc_comments(raw: str) -> str:
    """Remove ``//`` line comments and trailing commas for JSONC mcp.json parsing."""
    import re

    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        kept = line
        if "//" in line:
            in_string = False
            escaped = False
            cut = len(line)
            for idx, ch in enumerate(line):
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if not in_string and line[idx : idx + 2] == "//":
                    cut = idx
                    break
            kept = line[:cut].rstrip()
        lines.append(kept)
    text = "\n".join(lines)
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _load_mcp_config_json(config_path: Path) -> dict[str, Any]:
    """Load MCP JSON/JSONC from *config_path*; return ``{}`` on empty/missing."""
    if not config_path.exists():
        return {}
    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(_strip_jsonc_comments(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Validation / check mode
# ---------------------------------------------------------------------------


def _is_valid_tapps_command(command: str, args: list[str] | None = None) -> bool:
    """Return ``True`` if *command* (+ *args*) launches tapps-mcp.

    Accepts:
    - ``"tapps-mcp"`` (bare name, on PATH)
    - ``"uv"`` / ``"npx"`` when *args* contain ``"tapps-mcp"`` and ``"serve"``
    - Any absolute or relative path whose filename is ``tapps-mcp`` or
      ``tapps-mcp.exe`` (PyInstaller / standalone binary).
    """
    if command == "tapps-mcp":
        return True
    # uv / npx are valid launchers when args route to tapps-mcp serve
    if command in ("uv", "npx") and args is not None:
        return "tapps-mcp" in args and "serve" in args
    # Cursor wrapper generated by tapps-mcp init/upgrade (TAP-3255, Epic 109 NLT)
    name = Path(command.replace("\\", "/")).name.lower()
    if name == "tapps-mcp-serve.sh" or name.endswith("-serve.sh"):
        return True
    return name in ("tapps-mcp", "tapps-mcp.exe")


def _read_servers_block(config_path: Path, servers_key: str) -> dict[str, Any] | str:
    """Return the servers mapping from *config_path*, or an error string."""
    if not config_path.exists():
        return f"Config file not found: {config_path}"

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(_strip_jsonc_comments(raw))
    except json.JSONDecodeError:
        return f"Invalid JSON in {config_path}"

    if not isinstance(data, dict):
        return f"Invalid structure in {config_path}"

    servers = data.get(servers_key, {})
    if not isinstance(servers, dict):
        return f"Invalid structure in {config_path}"
    return servers


def _find_primary_server_entry(servers: dict[str, Any]) -> dict[str, Any] | None:
    """Return the tapps-mcp entry (or its NLT successor) from a servers mapping."""
    entry = servers.get("tapps-mcp")
    if not isinstance(entry, dict):
        entry = servers.get("nlt-build") or servers.get("nlt-code-quality")
    return entry if isinstance(entry, dict) else None


def _describe_entry_problem(entry: dict[str, Any], config_path: Path) -> str | None:
    """Return an error string when *entry* is not a usable launcher, else ``None``."""
    from tapps_mcp.distribution.nlt_http_fleet import (
        describe_http_fleet_entry_problem,
        is_remote_mcp_entry,
        is_valid_http_fleet_mcp_entry,
    )

    if is_valid_http_fleet_mcp_entry(entry):
        return None

    # A remote entry has no `command` to be "unexpected" (TAP-5723). Report
    # what is actually wrong with it rather than blaming an absent command.
    if is_remote_mcp_entry(entry):
        return f"{describe_http_fleet_entry_problem(entry)} in {config_path}"

    command = entry.get("command", "")
    args = entry.get("args", [])
    if _is_valid_tapps_command(command, args if isinstance(args, list) else None):
        return None
    if isinstance(args, list) and any("--profile" in str(a) for a in args):
        wrapper_name = Path(str(command).replace("\\", "/")).name.lower()
        if wrapper_name.endswith("-serve.sh") or wrapper_name == "tapps-mcp-serve.sh":
            return None
    return (
        f"Unexpected command in tapps-mcp config: '{command}'"
        f" (expected 'tapps-mcp', 'uv run tapps-mcp serve', or path to tapps-mcp.exe)"
    )


def _validate_config_file(config_path: Path, servers_key: str) -> str | None:
    """Return an error string if *config_path* is invalid, else ``None``."""
    servers = _read_servers_block(config_path, servers_key)
    if isinstance(servers, str):
        return servers

    entry = _find_primary_server_entry(servers)
    if entry is None:
        return f"tapps-mcp / nlt-build entry not found in {config_path} under '{servers_key}'"

    return _describe_entry_problem(entry, config_path)


def _check_config(host: str, project_root: Path, scope: str = "project") -> bool:
    """Verify that the tapps-mcp entry exists and looks valid.

    Args:
        host: Target host name.
        project_root: Project root directory.
        scope: ``"project"`` (default) or ``"user"``. Only affects ``claude-code``.

    Returns:
        ``True`` if configuration looks valid, ``False`` otherwise.
    """
    config_path = _get_config_path(host, project_root, scope=scope)
    servers_key = _get_servers_key(host)

    error = _validate_config_file(config_path, servers_key)
    if error is not None:
        click.echo(click.style(error, fg="red" if "Unexpected" not in error else "yellow"))
        if "not found" in error.lower():
            click.echo(f"  Run: tapps-mcp init --host {host}")
        return False

    click.echo(click.style(f"TappsMCP is correctly configured in {config_path}", fg="green"))
    data = _load_mcp_config_json(config_path)
    servers = data.get(servers_key, {})
    if isinstance(servers, dict):
        nlt_ids = list_nlt_server_ids_in_config(servers)
        if nlt_ids:
            click.echo(
                click.style(
                    f"  NLT plugin: {len(nlt_ids)} enabled server(s): {', '.join(nlt_ids)}",
                    fg="cyan",
                )
            )
    return True
