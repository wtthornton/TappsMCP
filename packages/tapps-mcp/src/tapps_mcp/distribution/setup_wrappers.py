"""Stdio wrapper scripts for GUI-launched MCP hosts.

Cursor and Claude Code launch MCP servers from a GUI process that does not
expand ``${VAR}`` in ``mcp.json`` and often omits ``~/.local/bin`` from PATH
(TAP-3255). Every stdio entry therefore points at a generated shell wrapper
that sources operator + project env, reaps stale profile orphans (ADR-0005),
prefers the blue/green ``current`` release, then execs the real binary.
Split out of ``setup_generator`` (TAP-5733).
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from tapps_mcp.distribution.setup_config_io import _load_mcp_config_json
from tapps_mcp.distribution.setup_entries import _BRAIN_AUTH_TOKEN_ENV_PLACEHOLDER
from tapps_mcp.distribution.setup_launch import _build_nlt_launch, _resolve_tapps_mcp_launch

# TAP-3255: Cursor GUI launches may not expand ${VAR} in mcp.json — wrapper sources .env first.
# Operator-wide secrets (Context7, brain bearer) live in ~/.tapps-operator.env (one per machine).
_OPERATOR_ENV_REL = Path(".tapps-operator.env")
_CURSOR_MCP_WRAPPER_REL = Path(".cursor/bin/tapps-mcp-serve.sh")
_CLAUDE_MCP_WRAPPER_REL = Path(".claude/bin/tapps-mcp-serve.sh")
_STDIO_WRAPPER_HOSTS = frozenset({"cursor", "claude-code"})


def _stdio_wrapper_rel(host: str, server_id: str = "tapps-mcp") -> Path:
    """Return the stdio wrapper script path for *host* (Cursor or Claude Code).

    Cursor: ``.cursor/bin/<server_id>-serve.sh`` (legacy tapps-mcp name kept).
    Claude Code: ``.claude/bin/<server_id>-serve.sh`` — same ``../..`` project-root
    walk as Cursor so deploy-local flips of ``~/.tapps-mcp/current`` are picked up
    on MCP reload (TAP-5155 / ADR-0023).
    """
    if host == "claude-code":
        if server_id == "tapps-mcp":
            return _CLAUDE_MCP_WRAPPER_REL
        return Path(f".claude/bin/{server_id}-serve.sh")
    if server_id == "tapps-mcp":
        return _CURSOR_MCP_WRAPPER_REL
    return Path(f".cursor/bin/{server_id}-serve.sh")


def _cursor_wrapper_rel(server_id: str = "tapps-mcp") -> Path:
    """Return the Cursor wrapper script path for an MCP server entry."""
    return _stdio_wrapper_rel("cursor", server_id)


def operator_env_path() -> Path:
    """Return the operator-wide secrets file path (``~/.tapps-operator.env``)."""
    return Path.home() / _OPERATOR_ENV_REL


def _parse_cursor_wrapper_launch(wrapper_path: Path) -> tuple[str, list[str]] | None:
    """Extract the embedded ``exec`` launch command from an existing wrapper script."""
    if not wrapper_path.is_file():
        return None
    try:
        text = wrapper_path.read_text(encoding="utf-8")
    except OSError:
        return None
    candidates: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("exec "):
            continue
        launch_part = stripped[5:]
        suffix = ' "$@"'
        launch_part = launch_part.removesuffix(suffix)
        if "_blue_green" in launch_part:
            continue
        parts = shlex.split(launch_part)
        if parts:
            candidates.append((parts[0], [str(a) for a in parts[1:]]))
    return candidates[-1] if candidates else None


def _nlt_profile_from_serve_args(args: list[str]) -> str | None:
    """Return ``nlt-*`` profile name when *args* includes ``serve --profile``."""
    for idx, arg in enumerate(args):
        if arg == "--profile" and idx + 1 < len(args):
            profile = args[idx + 1]
            if profile.startswith("nlt-"):
                return profile
    return None


def _render_profile_stale_reap_bash(profile: str, *, min_age_seconds: int = 45) -> str:
    """Bash block: kill stale ``serve --profile`` orphans for one NLT profile (mawk-safe)."""
    return f"""
# ADR-0005: reap stale orphans for this profile before exec (Cursor fleet hardening).
if command -v ps &>/dev/null && command -v awk &>/dev/null; then
  _STALE_PIDS=$(ps -eo pid,etimes,cmd 2>/dev/null | \\
    awk '$2 > {min_age_seconds} && /serve --profile {profile}/ && !/--transport http|--transport=http/ {{print $1}}' || true)
  if [[ -n "${{_STALE_PIDS:-}}" ]]; then
    echo "[TappsMCP] Reaping stale serve PIDs for {profile}: $_STALE_PIDS" >&2
    echo "$_STALE_PIDS" | xargs kill 2>/dev/null || true
  fi
fi
"""


def _render_cursor_mcp_wrapper_script(command: str, args: list[str]) -> str:
    """Shell script that sources operator + project env then execs tapps-mcp (TAP-3255)."""
    tool = Path(command).name
    args_quoted = " ".join(shlex.quote(a) for a in args)
    launch = " ".join([shlex.quote(command), *[shlex.quote(a) for a in args]])
    # Always prefer ``~/.tapps-mcp/current/bin`` at runtime when present so deploy-local
    # flips take effect on the next MCP reload without rewriting wrapper scripts.
    blue_green_block = f"""_blue_green="${{HOME}}/.tapps-mcp/current/bin/{tool}"
if [[ -x "$_blue_green" ]]; then
  echo "[TappsMCP] Using blue/green release: $_blue_green" >&2
  exec "$_blue_green" {args_quoted} "$@"
fi
"""
    return f"""#!/usr/bin/env bash
# Generated by tapps-mcp init/upgrade (TAP-3255). Sources ~/.tapps-operator.env and
# project .env before spawning the MCP server so GUI-launched Cursor inherits operator
# secrets (Context7, brain bearer) without relying on ${{...}} substitution in mcp.json.
set -euo pipefail
ROOT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/../.." && pwd)"
cd "$ROOT"
# Cursor GUI often omits ~/.local/bin (uv tool install shims) from PATH.
export PATH="${{HOME}}/.local/bin:${{PATH}}"
_operator_env="${{HOME}}/{_OPERATOR_ENV_REL.name}"
if [[ -f "$_operator_env" ]]; then
  set +u
  set -a
  # shellcheck disable=SC1091
  source "$_operator_env"
  set +a
  set -u
fi
if [[ -f .env ]]; then
  set +u
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  set -u
fi
if [[ -n "${{TAPPS_BRAIN_AUTH_TOKEN:-}}" ]]; then
  _mem_token="${{TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN:-}}"
  if [[ -z "$_mem_token" || "$_mem_token" == '{_BRAIN_AUTH_TOKEN_ENV_PLACEHOLDER}' ]]; then
    export TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN="$TAPPS_BRAIN_AUTH_TOKEN"
  fi
fi
if [[ -z "${{TAPPS_MCP_CONTEXT7_API_KEY:-}}" && -n "${{CONTEXT7_API_KEY:-}}" ]]; then
  export TAPPS_MCP_CONTEXT7_API_KEY="$CONTEXT7_API_KEY"
fi
echo "[TappsMCP] Launching MCP server: {launch}" >&2
{blue_green_block}exec {shlex.quote(command)} {args_quoted} "$@"
"""


def _write_cursor_mcp_wrapper(
    project_root: Path,
    *,
    uv_launch: tuple[str, list[str]] | None = None,
    wrapper_rel: Path | None = None,
) -> Path:
    """Write a Cursor MCP wrapper script and return its absolute path."""
    if uv_launch is not None:
        command, args = uv_launch
    else:
        command, args = _resolve_tapps_mcp_launch()
    rel = wrapper_rel or _CURSOR_MCP_WRAPPER_REL
    wrapper_path = project_root / rel
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text(
        _render_cursor_mcp_wrapper_script(command, args),
        encoding="utf-8",
    )
    wrapper_path.chmod(wrapper_path.stat().st_mode | 0o111)
    return wrapper_path.resolve()


def _mcp_config_has_stdio_entries(config_path: Path) -> bool:
    """True when *config_path* has NLT/tapps stdio entries (not HTTP fleet URLs)."""
    if not config_path.is_file():
        return False
    data = _load_mcp_config_json(config_path)
    if not isinstance(data, dict):
        return False
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return False
    for entry in servers.values():
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        if entry_type in {"http", "streamableHttp"}:
            continue
        if isinstance(entry.get("command"), str) and entry["command"]:
            return True
    return False


def regenerate_nlt_stdio_wrappers(project_root: Path) -> list[str]:
    """Rewrite NLT stdio wrappers for Cursor and/or Claude Code under *project_root*.

    Used after ``deploy-local`` flips ``~/.tapps-mcp/current`` so new MCP launches
    pick up the symlink target without a full ``tapps-mcp init``. Skips hosts whose
    MCP config is HTTP-only (ADR-0024).
    """
    from tapps_mcp.distribution.nlt_mcp_config import NLT_SERVER_ORDER

    root = project_root.resolve()
    hosts: list[str] = []
    if _mcp_config_has_stdio_entries(root / ".cursor" / "mcp.json"):
        hosts.append("cursor")
    if _mcp_config_has_stdio_entries(root / ".mcp.json"):
        hosts.append("claude-code")
    written: list[str] = []
    for host in hosts:
        for server_id in NLT_SERVER_ORDER:
            command, args = _build_nlt_launch(server_id, None, project_root=root)
            wrapper = _write_cursor_mcp_wrapper(
                root,
                uv_launch=(command, args),
                wrapper_rel=_stdio_wrapper_rel(host, server_id),
            )
            written.append(str(wrapper.relative_to(root)))
    return written


def regenerate_cursor_nlt_wrappers(project_root: Path) -> list[str]:
    """Rewrite NLT stdio wrappers (Cursor + Claude) for *project_root*.

    Kept name for call-site compatibility; delegates to
    :func:`regenerate_nlt_stdio_wrappers` (TAP-5155).
    """
    return regenerate_nlt_stdio_wrappers(project_root)


def _resolve_wrapper_launch(
    entry: dict[str, Any],
    project_root: Path,
    *,
    uv_launch: tuple[str, list[str]] | None = None,
) -> tuple[str, list[str]]:
    """Resolve the server launch command embedded in the Cursor wrapper script."""
    if uv_launch is not None:
        return uv_launch
    cmd = entry.get("command")
    args = entry.get("args", [])
    if isinstance(cmd, str) and cmd:
        if cmd.endswith("tapps-mcp-serve.sh"):
            wrapper_path = Path(cmd)
            if not wrapper_path.is_absolute():
                wrapper_path = project_root / _CURSOR_MCP_WRAPPER_REL
            parsed = _parse_cursor_wrapper_launch(wrapper_path)
            if parsed is not None:
                return parsed
        elif isinstance(args, list):
            return cmd, [str(a) for a in args]
    return _resolve_tapps_mcp_launch()


def _apply_cursor_launch_wrapper(
    entry: dict[str, Any],
    project_root: Path,
    *,
    uv_launch: tuple[str, list[str]] | None = None,
    server_id: str = "tapps-mcp",
    host: str = "cursor",
) -> None:
    """Point a stdio MCP entry at the env-sourcing wrapper script (Cursor/Claude)."""
    if server_id.startswith("nlt-"):
        command, args = _build_nlt_launch(server_id, uv_launch, project_root=project_root)
    else:
        command, args = _resolve_wrapper_launch(entry, project_root, uv_launch=uv_launch)
    wrapper = _write_cursor_mcp_wrapper(
        project_root,
        uv_launch=(command, args),
        wrapper_rel=_stdio_wrapper_rel(host, server_id),
    )
    entry["command"] = str(wrapper)
    entry["args"] = []
