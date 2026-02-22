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
    "env": {
        "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}",
    },
}

_SERVER_INSTRUCTIONS = (
    "Code quality scoring (0-100 across 7 categories), security scanning "
    "(Bandit + secret detection), quality gates (pass/fail against configurable "
    "presets), documentation lookup, domain expert consultation, and project "
    "profiling for Python projects."
)


def _build_server_entry(host: str) -> dict[str, Any]:
    """Build the tapps-mcp server config entry for the given host.

    Claude Code gets an extra ``instructions`` field for Tool Search discovery.
    All platforms get the ``env`` block with ``TAPPS_MCP_PROJECT_ROOT``.
    """
    entry = dict(_TAPPS_SERVER_ENTRY)
    entry["env"] = dict(_TAPPS_SERVER_ENTRY["env"])
    if host == "claude-code":
        entry["instructions"] = _SERVER_INSTRUCTIONS
    return entry


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


def _get_config_path(host: str, project_root: Path, scope: str = "user") -> Path:
    """Return the config file path for a given host and scope.

    Args:
        host: One of ``"claude-code"``, ``"cursor"``, ``"vscode"``.
        project_root: The project root directory.
        scope: ``"user"`` for user-level config, ``"project"`` for
            project-level ``.mcp.json``. Only affects ``claude-code``.

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
    merged[servers_key]["tapps-mcp"] = _build_server_entry(host)
    return merged


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def _generate_config(
    host: str,
    project_root: Path,
    *,
    force: bool = False,
    scope: str = "user",
    dry_run: bool = False,
) -> bool:
    """Generate (or merge) the MCP config for the given host.

    Args:
        host: Target host name.
        project_root: Project root directory.
        force: If ``True``, overwrite any existing ``tapps-mcp`` entry without
            prompting. Intended for non-interactive use (CI, scripts).
        scope: ``"user"`` or ``"project"``. Only affects ``claude-code``.

    Returns:
        ``True`` if configuration was successfully written, ``False`` if the
        operation was aborted or failed (e.g. invalid JSON).
    """
    config_path = _get_config_path(host, project_root, scope=scope)
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
            if not force and not click.confirm("Overwrite the existing tapps-mcp entry?"):
                click.echo("Aborted.")
                return False

        merged = _merge_config(existing, host)
    else:
        servers_key_new = _get_servers_key(host)
        merged = {servers_key_new: {"tapps-mcp": _build_server_entry(host)}}

    if dry_run:
        click.echo(
            click.style(
                f"[DRY-RUN] Would write configuration to {config_path}",
                fg="cyan",
            )
        )
        click.echo("  tapps-mcp entry would be added/updated. Run without --dry-run to apply.")
        return True

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


def _check_config(host: str, project_root: Path, scope: str = "user") -> bool:
    """Verify that the tapps-mcp entry exists and looks valid.

    Args:
        host: Target host name.
        project_root: Project root directory.
        scope: ``"user"`` or ``"project"``. Only affects ``claude-code``.

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

    click.echo(click.style(f"tapps-mcp is correctly configured in {config_path}", fg="green"))
    return True


def _validate_config_file(config_path: Path, servers_key: str) -> str | None:
    """Return an error string if *config_path* is invalid, else ``None``."""
    if not config_path.exists():
        return f"Config file not found: {config_path}"

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError:
        return f"Invalid JSON in {config_path}"

    if not isinstance(data, dict):
        return f"Invalid structure in {config_path}"

    servers = data.get(servers_key, {})
    entry = servers.get("tapps-mcp") if isinstance(servers, dict) else None
    if not isinstance(entry, dict):
        return f"tapps-mcp entry not found in {config_path} under '{servers_key}'"

    command = entry.get("command", "")
    return (
        f"Unexpected command in tapps-mcp config: '{command}' (expected 'tapps-mcp')"
        if command != "tapps-mcp"
        else None
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _configure_multiple_hosts(
    hosts: list[str],
    project_root: Path,
    *,
    check: bool = False,
    force: bool = False,
    scope: str = "user",
    rules: bool = True,
    dry_run: bool = False,
) -> bool:
    """Configure (or check) multiple hosts, reporting per-host results.

    Returns ``True`` if ALL hosts succeeded, ``False`` if any failed.
    """
    all_ok = True
    for host in hosts:
        click.echo("")
        click.echo(click.style(f"--- {host} ---", bold=True))
        if check:
            ok = _check_config(host, project_root, scope=scope)
        else:
            ok = _generate_config(host, project_root, force=force, scope=scope, dry_run=dry_run)
            if ok and rules and not dry_run:
                _generate_rules(host, project_root)
        if not ok:
            all_ok = False
    return all_ok


def _generate_rules(host: str, project_root: Path) -> None:
    """Generate platform rule files, hooks, agents, and skills for the given host.

    Delegates to ``_bootstrap_claude`` and ``_bootstrap_cursor`` from
    ``tapps_mcp.pipeline.init``, and uses ``platform_generators`` for hooks,
    subagents, and skills.
    """
    from tapps_mcp.pipeline.init import (
        _bootstrap_claude,
        _bootstrap_claude_settings,
        _bootstrap_cursor,
    )
    from tapps_mcp.pipeline.platform_generators import (
        generate_bugbot_rules,
        generate_ci_workflow,
        generate_claude_hooks,
        generate_copilot_instructions,
        generate_cursor_hooks,
        generate_cursor_rules,
        generate_skills,
        generate_subagent_definitions,
    )

    if host == "claude-code":
        action = _bootstrap_claude(project_root)
        if action == "created":
            click.echo(click.style("  Created CLAUDE.md with TAPPS pipeline rules", fg="green"))
        elif action == "updated":
            click.echo(click.style("  Updated CLAUDE.md with TAPPS pipeline rules", fg="green"))
        elif action == "skipped":
            click.echo("  CLAUDE.md already contains TAPPS rules (skipped)")
        settings_action = _bootstrap_claude_settings(project_root)
        if settings_action == "created":
            click.echo(click.style("  Created .claude/settings.json with permissions", fg="green"))
        elif settings_action == "updated":
            click.echo(click.style("  Updated .claude/settings.json with permissions", fg="green"))
        elif settings_action == "skipped":
            click.echo("  .claude/settings.json already has TappsMCP permissions (skipped)")
        hooks_result = generate_claude_hooks(project_root)
        _echo_gen_result("hooks", hooks_result)
        agents_result = generate_subagent_definitions(project_root, "claude")
        _echo_gen_result("agents", agents_result)
        skills_result = generate_skills(project_root, "claude")
        _echo_gen_result("skills", skills_result)
        generate_ci_workflow(project_root)
        click.echo(click.style("  Generated .github/workflows/tapps-quality.yml", fg="green"))
        generate_copilot_instructions(project_root)
        click.echo(click.style("  Generated .github/copilot-instructions.md", fg="green"))
    elif host == "cursor":
        action = _bootstrap_cursor(project_root)
        if action == "created":
            click.echo(click.style("  Created .cursor/rules/tapps-pipeline.md", fg="green"))
        elif action == "updated":
            click.echo(click.style("  Updated .cursor/rules/tapps-pipeline.md", fg="green"))
        elif action == "skipped":
            click.echo("  .cursor/rules/tapps-pipeline.md already exists (skipped)")
        hooks_result = generate_cursor_hooks(project_root)
        _echo_gen_result("hooks", hooks_result)
        agents_result = generate_subagent_definitions(project_root, "cursor")
        _echo_gen_result("agents", agents_result)
        skills_result = generate_skills(project_root, "cursor")
        _echo_gen_result("skills", skills_result)
        rules_result = generate_cursor_rules(project_root)
        _echo_gen_result("cursor rules", rules_result)
        generate_bugbot_rules(project_root)
        click.echo(click.style("  Generated .cursor/BUGBOT.md", fg="green"))
        generate_ci_workflow(project_root)
        click.echo(click.style("  Generated .github/workflows/tapps-quality.yml", fg="green"))
        generate_copilot_instructions(project_root)
        click.echo(click.style("  Generated .github/copilot-instructions.md", fg="green"))
    elif host == "vscode":
        generate_ci_workflow(project_root)
        click.echo(click.style("  Generated .github/workflows/tapps-quality.yml", fg="green"))
        generate_copilot_instructions(project_root)
        click.echo(click.style("  Generated .github/copilot-instructions.md", fg="green"))


def _echo_gen_result(kind: str, result: dict[str, Any]) -> None:
    """Print a summary line for a generation result."""
    created = result.get("created") or result.get("scripts_created") or []
    if created:
        click.echo(click.style(f"  Generated {kind}: {', '.join(created)}", fg="green"))
    else:
        click.echo(f"  {kind.capitalize()} already up to date (skipped)")


def run_init(
    *,
    mcp_host: str = "auto",
    project_root: str = ".",
    check: bool = False,
    force: bool = False,
    scope: str = "user",
    rules: bool = True,
    dry_run: bool = False,
) -> bool:
    """Run the init command logic.

    Called from the CLI ``init`` command.

    Args:
        mcp_host: Target host or ``"auto"`` for detection.
        project_root: Project root directory as a string path.
        check: If ``True``, verify existing configuration instead of generating.
        force: If ``True``, skip overwrite confirmation prompts.
        scope: ``"user"`` for user-scope config or ``"project"`` for project-scope
            ``.mcp.json``. Only affects ``claude-code`` host.
        rules: If ``True``, also generate platform rule files (CLAUDE.md or
            .cursor/rules/tapps-pipeline.md) alongside MCP config.
        dry_run: If ``True``, show what would be written without making changes.
    """
    root = Path(project_root).resolve()
    log.info(
        "init_command",
        host=mcp_host,
        project_root=str(root),
        check=check,
        force=force,
        scope=scope,
        rules=rules,
        dry_run=dry_run,
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
            return True
        click.echo(f"Detected MCP host(s): {', '.join(hosts)}")
        return _configure_multiple_hosts(
            hosts,
            root,
            check=check,
            force=force,
            scope=scope,
            rules=rules,
            dry_run=dry_run,
        )

    if check:
        return _check_config(mcp_host, root, scope=scope)

    ok = _generate_config(mcp_host, root, force=force, scope=scope, dry_run=dry_run)
    if ok and rules and not dry_run:
        _generate_rules(mcp_host, root)
    return ok
