"""Plaintext-secret detection, env migration, and gitignore hygiene.

A generated ``.mcp.json`` is meant to be committable, so any literal API key or
token in an ``env`` block is a finding (Issue #80.3). This module spots those,
migrates env across Claude Code project/user scopes (Issue #80.2), and keeps
TappsMCP runtime artifacts out of ``git status``.
Split out of ``setup_generator`` (TAP-5733).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from tapps_mcp.distribution.setup_config_io import _get_servers_key, _other_scope_config_path

# Keys that look secret-ish. Values matching these (substring, case-insensitive)
# are treated as secrets when written in plaintext to .mcp.json.
_SECRET_KEY_PATTERNS = ("key", "token", "secret", "password", "passwd", "credential")
# Known non-secret env keys TappsMCP itself emits — skip these.
_NON_SECRET_ENV_KEYS = frozenset(
    {
        "TAPPS_MCP_PROJECT_ROOT",
        "DOCS_MCP_PROJECT_ROOT",
        "VIRTUAL_ENV",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
    }
)


def _looks_like_secret_key(name: str) -> bool:
    """Return ``True`` if env var *name* looks like a secret (case-insensitive).

    Keys ending in ``_FILE`` / ``_PATH`` are treated as path pointers (e.g.
    ``AGENTFORGE_API_KEY_FILE=/path/to/.env``), not as secret values themselves.
    """
    if name in _NON_SECRET_ENV_KEYS:
        return False
    lowered = name.lower()
    if lowered.endswith(("_file", "_path")):
        return False
    return any(pat in lowered for pat in _SECRET_KEY_PATTERNS)


def _value_is_plaintext_secret(value: Any) -> bool:
    """Return ``True`` when *value* is a non-empty string not using env-var interpolation."""
    if not isinstance(value, str) or not value.strip():
        return False
    # ${VAR} or $VAR references → not plaintext secret (interpolation)
    return not value.strip().startswith("$")


def _value_looks_like_filesystem_path(value: Any) -> bool:
    """Return ``True`` when *value* looks like an absolute or relative filesystem path."""
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped or stripped.startswith("$"):
        return False
    if stripped.startswith(("/", "~/", "./", "../")):
        return True
    # Windows drive path (C:\...) or UNC
    if len(stripped) >= 3 and stripped[1] == ":" and stripped[2] in ("\\", "/"):
        return True
    return False


def _collect_plaintext_secrets(entry: dict[str, Any]) -> list[str]:
    """Return env var names in *entry*'s ``env`` block that look like plaintext secrets."""
    env = entry.get("env")
    if not isinstance(env, dict):
        return []
    found: list[str] = []
    for key, value in env.items():
        key_str = str(key)
        if not _looks_like_secret_key(key_str):
            continue
        if not _value_is_plaintext_secret(value):
            continue
        # Path-like values are pointers, not embedded secrets.
        if _value_looks_like_filesystem_path(value):
            continue
        found.append(key_str)
    return found


# ---------------------------------------------------------------------------
# Env migration across scopes (Issue #80.2)
# ---------------------------------------------------------------------------


def _read_other_scope_servers(other: Path, servers_key: str) -> dict[str, Any]:
    """Return the servers mapping from *other*, or ``{}`` when unreadable."""
    try:
        raw = other.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    servers = data.get(servers_key) or {}
    return servers if isinstance(servers, dict) else {}


def _load_existing_env_from_other_scope(
    host: str,
    project_root: Path,
    scope: str,
) -> dict[str, str]:
    """Return env vars registered for tapps-mcp in the *other* scope, if any.

    Used to migrate env (e.g. ``CONTEXT7_API_KEY``) when the user re-scopes
    their config (Issue #80.2). Never raises.
    """
    other = _other_scope_config_path(host, project_root, scope)
    if other is None or not other.exists():
        return {}
    servers = _read_other_scope_servers(other, _get_servers_key(host))
    entry = servers.get("tapps-mcp")
    if not isinstance(entry, dict):
        entry = servers.get("nlt-build") or servers.get("nlt-code-quality")
    if not isinstance(entry, dict):
        return {}
    env = entry.get("env")
    if not isinstance(env, dict):
        return {}
    # Keep only string→string pairs; drop TAPPS_MCP_PROJECT_ROOT (scope-specific).
    return {
        str(k): str(v)
        for k, v in env.items()
        if isinstance(v, str) and str(k) != "TAPPS_MCP_PROJECT_ROOT"
    }


# ---------------------------------------------------------------------------
# .gitignore hygiene
# ---------------------------------------------------------------------------


def _ensure_gitignore_entry(project_root: Path, entry: str) -> bool | None:
    """Append *entry* to ``.gitignore`` if missing (best-effort).

    Returns ``True`` if appended, ``False`` if already present, ``None`` on error
    or when ``.gitignore`` does not exist (we do not create one here).
    """
    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        return None
    try:
        text = gitignore.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = {line.strip() for line in text.splitlines()}
    if entry in lines:
        return False
    try:
        suffix = "" if text.endswith("\n") else "\n"
        gitignore.write_text(f"{text}{suffix}{entry}\n", encoding="utf-8")
    except OSError:
        return None
    return True


# Runtime / upgrade artifacts that must not clutter ``git status``. Backups are
# for local rollback only — git already versions the originals.
_TAPPS_RUNTIME_GITIGNORE_ENTRIES: tuple[str, ...] = (
    ".tapps-mcp/backups/",
    ".tapps-mcp/hook-backups/",
    ".tapps-mcp/.session-start-*",
    ".tapps-mcp/.tapps-session-id",
    ".tapps-mcp/.linear-snapshot-sentinel-*",
    ".tapps-mcp/.linear-validate-sentinel",
    ".tapps-mcp/.validation-marker",
    ".tapps-mcp/.validation-progress.json",
    ".tapps-mcp/.lookup-docs-events.jsonl",
    ".tapps-mcp/.brain-tools-list.full.json",
    ".tapps-mcp/metrics/",
    ".tapps-mcp/sessions/",
    ".tapps-mcp/profile-cache.json",
    ".tapps-mcp/call-graph-index.json",
    ".tapps-mcp/test-edges-index.json",
    ".tapps-mcp-cache/",
)

# Broader ignores that already cover the runtime entries above.
_TAPPS_RUNTIME_GITIGNORE_COVERED_BY: frozenset[str] = frozenset(
    {
        ".tapps-mcp/",
        ".tapps-mcp/*",
        "/.tapps-mcp/",
    }
)


def ensure_tapps_runtime_gitignore(project_root: Path) -> list[str]:
    """Ensure ``.gitignore`` covers TappsMCP runtime/upgrade artifacts.

    Appends missing entries from :data:`_TAPPS_RUNTIME_GITIGNORE_ENTRIES`.
    When ``.tapps-mcp/`` (or equivalent) is already ignored, skips individual
    entries under that tree. Does not create ``.gitignore`` if absent.

    Returns:
        List of entries newly appended (empty when nothing changed).
    """
    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        return []
    try:
        text = gitignore.read_text(encoding="utf-8")
    except OSError:
        return []
    lines = {line.strip() for line in text.splitlines() if line.strip()}
    whole_tree_ignored = bool(lines & _TAPPS_RUNTIME_GITIGNORE_COVERED_BY)
    added: list[str] = []
    for entry in _TAPPS_RUNTIME_GITIGNORE_ENTRIES:
        if whole_tree_ignored and entry.startswith(".tapps-mcp/"):
            continue
        if entry in lines:
            continue
        result = _ensure_gitignore_entry(project_root, entry)
        if result is True:
            added.append(entry)
            lines.add(entry)
    return added


# ---------------------------------------------------------------------------
# Post-write warning (Issue #80.3)
# ---------------------------------------------------------------------------


def _flagged_plaintext_secret_names(merged: dict[str, Any], servers_key: str) -> list[str]:
    """Return the sorted set of plaintext secret env names across all server entries."""
    servers = merged.get(servers_key) or {}
    if not isinstance(servers, dict):
        return []
    flagged: set[str] = set()
    for entry in servers.values():
        if isinstance(entry, dict):
            flagged.update(_collect_plaintext_secrets(entry))
    return sorted(flagged)


def _echo_plaintext_secret_warning(config_path: Path, names: list[str]) -> None:
    """Print the plaintext-secret warning plus an env-var interpolation example."""
    click.echo(
        click.style(
            f"  WARNING: {config_path.name} contains plaintext secret(s): {', '.join(names)}",
            fg="yellow",
        )
    )
    click.echo("    Use env-var interpolation instead (Claude Code supports ${VAR}):")
    example = names[0]
    click.echo(f"      export {example}=...   # in ~/.bashrc or ~/.zshrc")
    click.echo(f'      "{example}": "${{{example}}}"   # in {config_path.name}')


def _nudge_gitignore_for_secrets(config_path: Path, project_root: Path) -> None:
    """Add the secret-bearing config to ``.gitignore``, or say why we could not."""
    if config_path.parent not in (project_root, project_root / ".cursor", project_root / ".vscode"):
        return
    # Compute the gitignore path relative to project_root.
    try:
        gi_entry = str(config_path.relative_to(project_root))
    except ValueError:
        gi_entry = config_path.name
    result = _ensure_gitignore_entry(project_root, gi_entry)
    if result is True:
        click.echo(
            click.style(
                f"  Added '{gi_entry}' to .gitignore (contains plaintext secrets).",
                fg="cyan",
            )
        )
    elif result is None and not (project_root / ".gitignore").exists():
        click.echo(
            click.style(
                f"  No .gitignore found; consider ignoring '{gi_entry}'.",
                fg="yellow",
            )
        )


def _warn_plaintext_secrets(
    config_path: Path,
    merged: dict[str, Any],
    host: str,
    project_root: Path,
    scope: str,
) -> None:
    """Warn when the written MCP config contains plaintext secret values (Issue #80.3)."""
    names = _flagged_plaintext_secret_names(merged, _get_servers_key(host))
    if not names:
        return

    _echo_plaintext_secret_warning(config_path, names)

    # Only nudge .gitignore for project-scope files inside the repo.
    if host == "claude-code" and scope != "project":
        return
    _nudge_gitignore_for_secrets(config_path, project_root)
