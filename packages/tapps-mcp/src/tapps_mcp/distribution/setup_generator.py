"""One-command setup generator for TappsMCP across MCP hosts.

Generates MCP configuration files for Claude Code, Cursor, and VS Code,
with auto-detection of installed hosts and config merging.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import click

from tapps_core.common.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config templates per host
# ---------------------------------------------------------------------------

_TAPPS_SERVER_ENTRY: dict[str, Any] = {
    "type": "stdio",
    "command": "tapps-mcp",
    "args": ["serve"],
    "env": {
        "TAPPS_MCP_PROJECT_ROOT": ".",
    },
}

_SERVER_INSTRUCTIONS = (
    "Code quality scoring (0-100 across 7 categories), security scanning "
    "(Bandit + secret detection), quality gates (pass/fail against configurable "
    "presets), documentation lookup, domain expert consultation, and project "
    "profiling for Python projects."
)

_DOCS_SERVER_INSTRUCTIONS = (
    "Documentation MCP: epic/story/prompt generators, artifact validation, "
    "and planning helpers for Markdown docs in this repo."
)

# Placeholder for uv-based configs when ``tapps-mcp`` is not on PATH (Epic 80.5).
_TAPPS_MCP_UV_ROOT_PLACEHOLDER = "<PATH_TO_TAPPS_MCP_MONOREPO_ROOT>"


def _resolve_tapps_mcp_monorepo_root() -> str | None:
    """Best-effort lookup of the tapps-mcp monorepo root on disk (Issue #79 sub).

    Resolution order:
    1. Walk up from ``tapps_mcp.__file__`` looking for a ``packages/tapps-mcp``
       layout plus a ``pyproject.toml`` at the workspace root.
    2. Return ``None`` if no monorepo layout is detected (e.g. pip install).
    """
    try:
        import tapps_mcp as _pkg
    except Exception:
        return None
    pkg_file = getattr(_pkg, "__file__", None)
    if not pkg_file:
        return None
    # Expect ``<root>/packages/tapps-mcp/src/tapps_mcp/__init__.py``:
    # parents[0]=tapps_mcp, [1]=src, [2]=packages/tapps-mcp, [3]=packages, [4]=monorepo root.
    try:
        resolved = Path(pkg_file).resolve()
        pkg_dir = resolved.parents[2]
        packages_dir = resolved.parents[3]
        monorepo = resolved.parents[4]
    except IndexError:
        return None
    if (
        pkg_dir.name == "tapps-mcp"
        and packages_dir.name == "packages"
        and (monorepo / "pyproject.toml").exists()
    ):
        return str(monorepo)
    return None


def _resolve_tapps_mcp_launch() -> tuple[str, list[str]]:
    """Return ``command`` and ``args`` to launch ``tapps-mcp serve``.

    Resolution order:
    1. PyInstaller frozen exe: ``sys.executable`` + ``["serve"]``.
    2. ``tapps-mcp`` on PATH: ``"tapps-mcp"`` + ``["serve"]``.
    3. Monorepo checkout: ``uv run --directory <monorepo-root> tapps-mcp serve``
       when the installed ``tapps_mcp`` package lives inside a monorepo layout.
    4. Fallback: ``uv run --directory <placeholder> tapps-mcp serve``.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ["serve"]
    if shutil.which("tapps-mcp") is not None:
        return "tapps-mcp", ["serve"]
    directory = _resolve_tapps_mcp_monorepo_root() or _TAPPS_MCP_UV_ROOT_PLACEHOLDER
    return (
        "uv",
        [
            "run",
            "--directory",
            directory,
            "tapps-mcp",
            "serve",
        ],
    )


def _resolve_docsmcp_launch() -> tuple[str, list[str]]:
    """Return command + args to launch DocsMCP (``docsmcp serve``)."""
    if shutil.which("docsmcp") is not None:
        return "docsmcp", ["serve"]
    directory = _resolve_tapps_mcp_monorepo_root() or _TAPPS_MCP_UV_ROOT_PLACEHOLDER
    return (
        "uv",
        [
            "run",
            "--directory",
            directory,
            "docsmcp",
            "serve",
        ],
    )


# ---------------------------------------------------------------------------
# uv / pyproject detection for consumer projects (Issue #77)
# ---------------------------------------------------------------------------

_UV_AUTO_EXTRA_CANDIDATES = ("mcp", "tapps-mcp", "tapps")


def _detect_uv_context(project_root: Path) -> dict[str, Any] | None:
    """Detect whether *project_root* is a uv-managed project that ships tapps-mcp.

    Returns a dict with ``has_uv_lock``, ``has_pyproject``, ``tapps_mcp_extra``
    (name of an optional-dependency group that references ``tapps-mcp``, or
    ``None``), and ``uv_available``. Returns ``None`` when no pyproject.toml
    exists at all.
    """
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return None

    info: dict[str, Any] = {
        "has_uv_lock": (project_root / "uv.lock").exists(),
        "has_pyproject": True,
        "tapps_mcp_extra": None,
        "uv_available": shutil.which("uv") is not None,
    }

    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    # Look through [project.optional-dependencies] + [dependency-groups]
    def _has_tapps(entries: Any) -> bool:
        if not isinstance(entries, list):
            return False
        return any(isinstance(e, str) and "tapps-mcp" in e.lower() for e in entries)

    opt = data.get("project", {}).get("optional-dependencies") or {}
    dep_groups = data.get("dependency-groups") or {}

    found_extra: str | None = None
    for name in _UV_AUTO_EXTRA_CANDIDATES:
        if _has_tapps(opt.get(name)) or _has_tapps(dep_groups.get(name)):
            found_extra = name
            break
    if found_extra is None:
        # Fall back: any group that mentions tapps-mcp.
        for name, entries in {**opt, **dep_groups}.items():
            if _has_tapps(entries):
                found_extra = str(name)
                break

    info["tapps_mcp_extra"] = found_extra
    return info


def _should_use_uv_launch(
    project_root: Path,
    *,
    uv_mode: str | None,
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Decide whether to emit a ``uv run`` launcher for *project_root*.

    Args:
        project_root: Consumer project root.
        uv_mode: One of ``"on"`` (force), ``"off"`` (force classic), or
            ``None`` (auto-detect).

    Returns:
        ``(use_uv, extra_name, detection_info)`` tuple.
    """
    if uv_mode == "off":
        return False, None, None
    ctx = _detect_uv_context(project_root)
    if uv_mode == "on":
        # Forced: emit uv-run even if we couldn't find a group.
        extra = (ctx or {}).get("tapps_mcp_extra") if ctx else None
        return True, extra, ctx
    if ctx is None:
        return False, None, None
    # Auto: only flip to uv when pyproject lists tapps-mcp in a known extra
    # AND uv is available (or uv.lock is present → likely to be available).
    if ctx["tapps_mcp_extra"] is not None and (ctx["uv_available"] or ctx["has_uv_lock"]):
        return True, ctx["tapps_mcp_extra"], ctx
    return False, None, ctx


def _build_uv_run_tapps_launch(extra: str | None) -> tuple[str, list[str]]:
    """Return (command, args) for ``uv run --extra <extra> --no-sync tapps-mcp serve``."""
    args = ["run"]
    if extra:
        args.extend(["--extra", extra])
    args.extend(["--no-sync", "tapps-mcp", "serve"])
    return "uv", args


def _detect_command_path() -> str:
    """Return the primary executable name or path for MCP configs (compat shim).

    Prefer :func:`_resolve_tapps_mcp_launch` for full ``command`` + ``args``.
    """
    cmd, _args = _resolve_tapps_mcp_launch()
    return cmd


def _derive_brain_project_id(project_root: Path | None) -> str:
    """TAP-1336: Derive a default ``X-Project-Id`` slug from the project dir name.

    Lowercased, with whitespace collapsed to dashes. Falls back to ``""`` when
    the path is unusable, in which case tapps-mcp emits a hard error at
    runtime telling the agent to set ``TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID``
    explicitly. We deliberately do not silently invent a slug.
    """
    if project_root is None:
        return ""
    try:
        name = Path(project_root).resolve().name
    except (OSError, RuntimeError):
        return ""
    if not name:
        return ""
    return "-".join(name.lower().split())


def _build_server_entry(
    host: str,
    *,
    uv_launch: tuple[str, list[str]] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build the tapps-mcp server config entry for the given host.

    Claude Code gets an extra ``instructions`` field for Tool Search discovery.
    All platforms get the ``env`` block with ``TAPPS_MCP_PROJECT_ROOT`` and
    the tapps-brain memory connection (TAP-1336): ``HTTP_URL``, ``AUTH_TOKEN``
    via ``${TAPPS_BRAIN_AUTH_TOKEN}`` substitution, and ``PROJECT_ID`` derived
    from the project directory name. Without this, brand-new ``tapps_init``
    installs hit the brain server with no auth/identity and
    ``tapps_session_start`` hard-fails with ``brain_auth_token_missing``.

    The auth token uses env-var substitution rather than a literal value so
    consuming projects can safely commit ``.mcp.json``. The merge logic in
    :func:`_merge_config` preserves any user-customized values on upgrade.

    Claude Code uses ``"."`` because it launches the MCP server with CWD set to
    the project root and does **not** resolve VS Code variables like
    ``${workspaceFolder}``.  Cursor and VS Code resolve ``${workspaceFolder}``
    natively so it is used there.

    Uses :func:`_resolve_tapps_mcp_launch` for command and args unless
    *uv_launch* is provided (Issue #77 — consumer uv projects).
    """
    if uv_launch is not None:
        command, args = uv_launch
    else:
        command, args = _resolve_tapps_mcp_launch()
    # Claude Code CWD == project root; VS Code/Cursor resolve ${workspaceFolder}
    project_root_value = "." if host == "claude-code" else "${workspaceFolder}"
    env: dict[str, str] = {
        "TAPPS_MCP_PROJECT_ROOT": project_root_value,
        "TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://localhost:8080",
        "TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN": "${TAPPS_BRAIN_AUTH_TOKEN}",
    }
    project_id = _derive_brain_project_id(project_root)
    if project_id:
        env["TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID"] = project_id
    entry: dict[str, Any] = {
        "type": "stdio",
        "command": command,
        "args": args,
        "env": env,
    }
    if host == "claude-code":
        entry["instructions"] = _SERVER_INSTRUCTIONS
    return entry


def _build_docsmcp_server_entry(
    host: str,
    *,
    uv_launch: tuple[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Build the docs-mcp server entry (optional ``--with-docs-mcp``, Epic 80.7).

    When *uv_launch* is provided (consumer uv project, Issue #79 sub-issue),
    mirrors the same ``uv run`` pattern but launches ``docsmcp serve`` instead
    of ``tapps-mcp serve``.
    """
    if uv_launch is not None:
        # Derive a docs-mcp equivalent: replace 'tapps-mcp' with 'docsmcp' in args.
        command = uv_launch[0]
        args = [("docsmcp" if a == "tapps-mcp" else a) for a in uv_launch[1]]
        # Replace 'serve' keyword coming after the tool name — already present.
    else:
        command, args = _resolve_docsmcp_launch()
    project_root_value = "." if host == "claude-code" else "${workspaceFolder}"
    entry: dict[str, Any] = {
        "type": "stdio",
        "command": command,
        "args": args,
        "env": {"DOCS_MCP_PROJECT_ROOT": project_root_value},
    }
    if host == "claude-code":
        entry["instructions"] = _DOCS_SERVER_INSTRUCTIONS
    return entry


def is_tapps_mcp_package_layout(project_root: Path) -> bool:
    """Return True if *project_root* looks like ``.../packages/tapps-mcp`` (Epic 80.3)."""
    resolved = project_root.resolve()
    parts = resolved.parts
    min_segments = 2
    return len(parts) >= min_segments and parts[-2] == "packages" and parts[-1] == "tapps-mcp"


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


def _merge_config(
    existing: dict[str, Any],
    host: str,
    *,
    upgrade_mode: bool = False,
    uv_launch: tuple[str, list[str]] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Merge the tapps-mcp entry into an existing config dict.

    Only adds/replaces the ``tapps-mcp`` key inside the servers object;
    all other keys are preserved.

    When *upgrade_mode* is ``True`` and an existing ``tapps-mcp`` entry
    already has ``command`` and ``args``, those values are preserved.
    Only ``env`` and ``instructions`` are updated. This prevents
    overwriting custom exe paths (e.g. PyInstaller binaries) during
    ``tapps-mcp upgrade``.

    Args:
        existing: The parsed JSON from the existing config file.
        host: The target host name.
        upgrade_mode: If ``True``, preserve existing command/args.

    Returns:
        The merged config dict.
    """
    servers_key = _get_servers_key(host)
    merged = dict(existing)
    if servers_key not in merged:
        merged[servers_key] = {}

    new_entry = _build_server_entry(host, uv_launch=uv_launch, project_root=project_root)
    old_entry = merged[servers_key].get("tapps-mcp")
    if isinstance(old_entry, dict):
        if upgrade_mode and "command" in old_entry:
            # Preserve custom command paths (exe/uv) during upgrade
            new_entry["command"] = old_entry["command"]
            if "args" in old_entry:
                new_entry["args"] = old_entry["args"]
        old_env = old_entry.get("env")
        new_env = new_entry.get("env") or {}
        if isinstance(old_env, dict):
            # Epic 80.5: keep unrelated env keys (e.g. API keys) when merging/replacing
            new_entry["env"] = {**old_env, **new_env}

    merged[servers_key]["tapps-mcp"] = new_entry

    return merged


# ---------------------------------------------------------------------------
# Env migration (Issue #80.2) + secret detection (Issue #80.3)
# ---------------------------------------------------------------------------

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
    """Return ``True`` if env var *name* looks like a secret (case-insensitive)."""
    if name in _NON_SECRET_ENV_KEYS:
        return False
    lowered = name.lower()
    return any(pat in lowered for pat in _SECRET_KEY_PATTERNS)


def _value_is_plaintext_secret(value: Any) -> bool:
    """Return ``True`` when *value* is a non-empty string not using env-var interpolation."""
    if not isinstance(value, str) or not value.strip():
        return False
    # ${VAR} or $VAR references → not plaintext secret (interpolation)
    stripped = value.strip()
    return not (stripped.startswith("${") or stripped.startswith("$"))


def _collect_plaintext_secrets(entry: dict[str, Any]) -> list[str]:
    """Return env var names in *entry*'s ``env`` block that look like plaintext secrets."""
    env = entry.get("env")
    if not isinstance(env, dict):
        return []
    found: list[str] = []
    for key, value in env.items():
        if _looks_like_secret_key(str(key)) and _value_is_plaintext_secret(value):
            found.append(str(key))
    return found


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
    try:
        raw = other.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    servers_key = _get_servers_key(host)
    servers = data.get(servers_key) or {}
    if not isinstance(servers, dict):
        return {}
    entry = servers.get("tapps-mcp")
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


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def _generate_config(
    host: str,
    project_root: Path,
    *,
    force: bool = False,
    scope: str = "project",
    dry_run: bool = False,
    upgrade_mode: bool = False,
    with_docs_mcp: bool = False,
    uv_launch: tuple[str, list[str]] | None = None,
    extra_env: dict[str, str] | None = None,
) -> bool:
    """Generate (or merge) the MCP config for the given host.

    Args:
        host: Target host name.
        project_root: Project root directory.
        force: If ``True``, overwrite any existing ``tapps-mcp`` entry without
            prompting. Intended for non-interactive use (CI, scripts).
        scope: ``"project"`` (default) or ``"user"``. Only affects ``claude-code``.
        with_docs_mcp: When ``True``, also write a ``docs-mcp`` server entry (Epic 80.7).

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
            if not force:
                if sys.stdin.isatty():
                    if not click.confirm("Overwrite the existing tapps-mcp entry?"):
                        click.echo("Aborted.")
                        return False
                else:
                    assume = os.environ.get("TAPPS_MCP_INIT_ASSUME_YES", "").strip().lower()
                    if assume not in ("1", "true", "yes", "y", "on"):
                        click.echo(
                            click.style(
                                "Non-interactive session: skipping overwrite of existing "
                                "tapps-mcp entry.",
                                fg="yellow",
                            )
                        )
                        click.echo(
                            "  Re-run with --force or set TAPPS_MCP_INIT_ASSUME_YES=1 "
                            "to overwrite without prompting."
                        )
                        return True

        merged = _merge_config(
            existing,
            host,
            upgrade_mode=upgrade_mode,
            uv_launch=uv_launch,
            project_root=project_root,
        )
    else:
        servers_key_new = _get_servers_key(host)
        merged = {
            servers_key_new: {
                "tapps-mcp": _build_server_entry(
                    host, uv_launch=uv_launch, project_root=project_root
                ),
            }
        }

    # Issue #80.2: When creating a new config for claude-code, migrate env vars
    # (e.g. CONTEXT7_API_KEY) from the *other* scope so the user doesn't silently
    # lose them after re-scoping.
    migrated_env = _load_existing_env_from_other_scope(host, project_root, scope)
    if migrated_env:
        servers_key_m = _get_servers_key(host)
        entry = merged[servers_key_m].get("tapps-mcp")
        if isinstance(entry, dict):
            cur_env = entry.get("env")
            if not isinstance(cur_env, dict):
                cur_env = {}
            # Keep scope-specific TAPPS_MCP_PROJECT_ROOT from the new entry;
            # pull in any other keys from the old scope that are not already set.
            entry["env"] = {**migrated_env, **cur_env}
            other_path = _other_scope_config_path(host, project_root, scope)
            migrated_keys = sorted(k for k in migrated_env if k not in (cur_env or {}))
            if migrated_keys and not dry_run:
                click.echo(
                    click.style(
                        f"  Migrated env vars from {other_path}: {', '.join(migrated_keys)}",
                        fg="cyan",
                    )
                )

    # Issue #79: inject extra env vars (e.g. Context7 API key) into tapps-mcp entry.
    if extra_env:
        tapps_entry = merged.get(servers_key, {}).get("tapps-mcp")
        if isinstance(tapps_entry, dict):
            env = tapps_entry.get("env")
            if not isinstance(env, dict):
                env = {}
            tapps_entry["env"] = {**env, **extra_env}

    if with_docs_mcp:
        merged.setdefault(servers_key, {})
        old_docs = merged[servers_key].get("docs-mcp")
        new_docs = _build_docsmcp_server_entry(host, uv_launch=uv_launch)
        if isinstance(old_docs, dict):
            old_env = old_docs.get("env")
            new_env = new_docs.get("env") or {}
            if isinstance(old_env, dict):
                new_docs["env"] = {**old_env, **new_env}
        merged[servers_key]["docs-mcp"] = new_docs

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

    # Issue #80.3: warn when plaintext secrets end up in the config file,
    # and offer to append the project-scope file to .gitignore.
    _warn_plaintext_secrets(config_path, merged, host, project_root, scope)

    _print_next_steps(host, project_root=project_root)
    return True


def _warn_plaintext_secrets(
    config_path: Path,
    merged: dict[str, Any],
    host: str,
    project_root: Path,
    scope: str,
) -> None:
    """Warn when the written MCP config contains plaintext secret values (Issue #80.3)."""
    servers_key = _get_servers_key(host)
    servers = merged.get(servers_key) or {}
    if not isinstance(servers, dict):
        return
    flagged: dict[str, list[str]] = {}
    for server_name, entry in servers.items():
        if isinstance(entry, dict):
            secrets = _collect_plaintext_secrets(entry)
            if secrets:
                flagged[str(server_name)] = secrets
    if not flagged:
        return

    names = sorted({name for vals in flagged.values() for name in vals})
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

    # Only nudge .gitignore for project-scope files inside the repo.
    if host == "claude-code" and scope != "project":
        return
    rel_name = config_path.name
    if config_path.parent not in (project_root, project_root / ".cursor", project_root / ".vscode"):
        return
    # Compute the gitignore path relative to project_root.
    try:
        gi_entry = str(config_path.relative_to(project_root))
    except ValueError:
        gi_entry = rel_name
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


def _print_next_steps(host: str, *, project_root: Path | None = None) -> None:
    """Print helpful next-steps after config generation.

    Args:
        host: The host that was configured.
        project_root: Consumer project root (for Context7 hint context).
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
    _print_context7_hint_if_missing()


def _print_context7_hint_if_missing() -> None:
    """Print a one-time hint about TAPPS_MCP_CONTEXT7_API_KEY (Issue #79)."""
    if os.environ.get("TAPPS_MCP_CONTEXT7_API_KEY") or os.environ.get("CONTEXT7_API_KEY"):
        return
    click.echo("")
    click.echo(
        click.style(
            "Optional: set TAPPS_MCP_CONTEXT7_API_KEY for live docs via Context7.",
            fg="cyan",
        )
    )
    click.echo("  Without it, tapps_lookup_docs falls back to LlmsTxt (reduced coverage).")
    click.echo("  Get a key: https://context7.com")


# ---------------------------------------------------------------------------
# Check mode
# ---------------------------------------------------------------------------


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

    click.echo(click.style(f"tapps-mcp is correctly configured in {config_path}", fg="green"))
    return True


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
    # Check if the filename portion matches (handle both / and \ separators)
    name = Path(command.replace("\\", "/")).name.lower()
    return name in ("tapps-mcp", "tapps-mcp.exe")


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
    args = entry.get("args", [])
    return (
        f"Unexpected command in tapps-mcp config: '{command}'"
        f" (expected 'tapps-mcp', 'uv run tapps-mcp serve', or path to tapps-mcp.exe)"
        if not _is_valid_tapps_command(command, args if isinstance(args, list) else None)
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
    scope: str = "project",
    rules: bool = True,
    dry_run: bool = False,
    with_docs_mcp: bool = False,
    uv_launch: tuple[str, list[str]] | None = None,
    extra_env: dict[str, str] | None = None,
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
            ok = _generate_config(
                host,
                project_root,
                force=force,
                scope=scope,
                dry_run=dry_run,
                with_docs_mcp=with_docs_mcp,
                uv_launch=uv_launch,
                extra_env=extra_env,
            )
            if ok and rules and not dry_run:
                _generate_rules(host, project_root)
            elif ok and rules and dry_run:
                _preview_rules(host, project_root)
        if not ok:
            all_ok = False
    return all_ok


def _generate_rules(
    host: str,
    project_root: Path,
    engagement_level: str | None = None,
) -> None:
    """Generate platform rule files, hooks, agents, and skills for the given host.

    Delegates to ``_bootstrap_claude`` and ``_bootstrap_cursor`` from
    ``tapps_mcp.pipeline.init``, and uses ``platform_generators`` for hooks,
    subagents, and skills. When *engagement_level* is None, reads from
    project_root/.tapps-mcp.yaml or defaults to ``"medium"``.
    """
    if engagement_level is None:
        engagement_level = _read_engagement_level_from_project(project_root)
    if engagement_level not in ("high", "medium", "low"):
        engagement_level = "medium"

    from tapps_mcp.pipeline.init import (
        _bootstrap_claude,
        _bootstrap_claude_settings,
        _bootstrap_cursor,
    )
    from tapps_mcp.pipeline.platform_generators import (
        generate_bugbot_rules,
        generate_claude_hooks,
        generate_copilot_instructions,
        generate_cursor_hooks,
        generate_cursor_rules,
        generate_skills,
        generate_subagent_definitions,
    )

    # Always generate AGENTS.md and TECH_STACK.md (core bootstrap files).
    _generate_core_docs(project_root, engagement_level=engagement_level)

    if host == "claude-code":
        action = _bootstrap_claude(project_root, engagement_level=engagement_level)
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
        hooks_result = generate_claude_hooks(project_root, engagement_level=engagement_level)
        _echo_gen_result("hooks", hooks_result)
        agents_result = generate_subagent_definitions(project_root, "claude")
        _echo_gen_result("agents", agents_result)
        skills_result = generate_skills(project_root, "claude", engagement_level=engagement_level)
        _echo_gen_result("skills", skills_result)
        generate_copilot_instructions(project_root)
        click.echo(click.style("  Generated .github/copilot-instructions.md", fg="green"))
    elif host == "cursor":
        action = _bootstrap_cursor(project_root, engagement_level=engagement_level)
        if action == "created":
            click.echo(click.style("  Created .cursor/rules/tapps-pipeline.md", fg="green"))
        elif action == "updated":
            click.echo(click.style("  Updated .cursor/rules/tapps-pipeline.md", fg="green"))
        elif action == "skipped":
            click.echo("  .cursor/rules/tapps-pipeline.md already exists (skipped)")
        hooks_result = generate_cursor_hooks(project_root, engagement_level=engagement_level)
        _echo_gen_result("hooks", hooks_result)
        agents_result = generate_subagent_definitions(project_root, "cursor")
        _echo_gen_result("agents", agents_result)
        skills_result = generate_skills(project_root, "cursor", engagement_level=engagement_level)
        _echo_gen_result("skills", skills_result)
        rules_result = generate_cursor_rules(project_root)
        _echo_gen_result("cursor rules", rules_result)
        generate_bugbot_rules(project_root)
        click.echo(click.style("  Generated .cursor/BUGBOT.md", fg="green"))
        generate_copilot_instructions(project_root)
        click.echo(click.style("  Generated .github/copilot-instructions.md", fg="green"))
    elif host == "vscode":
        generate_copilot_instructions(project_root)
        click.echo(click.style("  Generated .github/copilot-instructions.md", fg="green"))


def _generate_core_docs(
    project_root: Path,
    *,
    engagement_level: str | None = None,
) -> None:
    """Generate AGENTS.md and TECH_STACK.md if they don't already exist.

    Called from ``_generate_rules`` so that CLI ``init`` produces the same
    core docs that the MCP ``tapps_init`` tool creates.
    """
    from tapps_mcp.pipeline.agents_md import update_agents_md
    from tapps_mcp.prompts.prompt_loader import load_agents_template

    level = engagement_level or _read_engagement_level_from_project(project_root)
    agents_path = project_root / "AGENTS.md"
    template_content = load_agents_template(level)

    if agents_path.exists():
        try:
            action, _detail = update_agents_md(agents_path, template_content, overwrite=False)
            if action == "validated":
                click.echo("  AGENTS.md is up to date (skipped)")
            else:
                click.echo(click.style(f"  AGENTS.md: {action}", fg="green"))
        except Exception:
            click.echo("  AGENTS.md update failed (skipped)")
    else:
        agents_path.write_text(template_content, encoding="utf-8")
        click.echo(click.style("  Created AGENTS.md", fg="green"))

    tech_stack_path = project_root / "TECH_STACK.md"
    if not tech_stack_path.exists():
        try:
            from tapps_mcp.project.profiler import detect_project_profile

            profile = detect_project_profile(project_root)
            from tapps_mcp.pipeline.init import _render_tech_stack_md

            content = _render_tech_stack_md(profile)
            tech_stack_path.write_text(content, encoding="utf-8")
            click.echo(click.style("  Created TECH_STACK.md", fg="green"))
        except Exception:
            click.echo("  TECH_STACK.md generation failed (skipped)")
    else:
        click.echo("  TECH_STACK.md already exists (skipped)")


def _preview_rules(
    host: str,
    project_root: Path,
    engagement_level: str | None = None,
) -> None:
    """Preview which rule/hook/agent/skill files would be generated (dry-run).

    Enumerates the same files as :func:`_generate_rules` without writing
    anything, so ``--dry-run`` output is complete.
    """
    files: list[str] = []

    if host == "claude-code":
        files.extend(
            [
                "CLAUDE.md",
                ".claude/settings.json",
                ".claude/hooks/ (tapps-session-start, tapps-stop, ...)",
                ".claude/agents/ (tapps-reviewer, tapps-validator, ...)",
                ".claude/skills/ (tapps-score, tapps-validate, ...)",
                ".github/workflows/tapps-quality.yml",
                ".github/copilot-instructions.md",
            ]
        )
    elif host == "cursor":
        files.extend(
            [
                ".cursor/rules/tapps-pipeline.md",
                ".cursor/hooks/ (tapps-before-mcp, ...)",
                ".cursor/agents/ (tapps-reviewer, tapps-validator, ...)",
                ".cursor/skills/ (tapps-score, tapps-validate, ...)",
                ".cursor/rules/ (tapps-quality, ...)",
                ".cursor/BUGBOT.md",
                ".github/workflows/tapps-quality.yml",
                ".github/copilot-instructions.md",
            ]
        )
    elif host == "vscode":
        files.extend(
            [
                ".github/workflows/tapps-quality.yml",
                ".github/copilot-instructions.md",
            ]
        )

    # Common files generated by bootstrap_pipeline (via MCP tool or upgrade)
    files.extend(
        [
            "AGENTS.md",
            "TECH_STACK.md",
        ]
    )

    if files:
        click.echo(click.style("[DRY-RUN] Would also create/update:", fg="cyan"))
        for f in files:
            click.echo(f"  - {f}")


def _echo_gen_result(kind: str, result: dict[str, Any]) -> None:
    """Print a summary line for a generation result."""
    created = result.get("created") or result.get("scripts_created") or []
    if created:
        click.echo(click.style(f"  Generated {kind}: {', '.join(created)}", fg="green"))
    else:
        click.echo(f"  {kind.capitalize()} already up to date (skipped)")


def _read_engagement_level_from_project(project_root: Path) -> str:
    """Read llm_engagement_level from project_root/.tapps-mcp.yaml if present."""
    import yaml

    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return "medium"
    try:
        with config_path.open(encoding="utf-8-sig") as f:
            data = yaml.safe_load(f)
        level = (data or {}).get("llm_engagement_level", "medium")
        return level if level in ("high", "medium", "low") else "medium"
    except Exception:
        return "medium"


def _write_engagement_level_to_yaml(project_root: Path, level: str) -> None:
    """Write or merge llm_engagement_level into project_root/.tapps-mcp.yaml."""
    import yaml

    config_path = project_root / ".tapps-mcp.yaml"
    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8-sig") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    data["llm_engagement_level"] = level
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def run_init(
    *,
    mcp_host: str = "auto",
    project_root: str = ".",
    check: bool = False,
    force: bool = False,
    scope: str = "project",
    rules: bool = True,
    dry_run: bool = False,
    engagement_level: str | None = None,
    allow_package_init: bool = False,
    with_docs_mcp: bool = False,
    uv_mode: str | None = None,
    uv_extra: str | None = None,
    context7_api_key: str | None = None,
    overwrite_tech_stack: bool = False,
) -> bool:
    """Run the init command logic.

    Called from the CLI ``init`` command.

    Args:
        mcp_host: Target host or ``"auto"`` for detection.
        project_root: Project root directory as a string path.
        check: If ``True``, verify existing configuration instead of generating.
        force: If ``True``, skip overwrite confirmation prompts.
        scope: ``"project"`` for project-scope ``.mcp.json`` (default) or
            ``"user"`` for user-scope config. Only affects ``claude-code`` host.
        rules: If ``True``, also generate platform rule files (CLAUDE.md or
            .cursor/rules/tapps-pipeline.md) alongside MCP config.
        dry_run: If ``True``, show what would be written without making changes.
        engagement_level: When set (high/medium/low), write to .tapps-mcp.yaml and
            use for platform rules. When ``None``, rules use medium or existing config.
        allow_package_init: Allow init when ``project_root`` is ``.../packages/tapps-mcp``.
        with_docs_mcp: Also register the docs-mcp server (Epic 80.7).
        context7_api_key: When set, write ``TAPPS_MCP_CONTEXT7_API_KEY`` into the
            MCP env block using ``${TAPPS_MCP_CONTEXT7_API_KEY}`` interpolation and
            print an export reminder (Issue #79).
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
        engagement_level=engagement_level,
        allow_package_init=allow_package_init,
        with_docs_mcp=with_docs_mcp,
    )

    allow_pkg = allow_package_init or os.environ.get(
        "TAPPS_MCP_ALLOW_PACKAGE_INIT",
        "",
    ).strip().lower() in ("1", "true", "yes", "y", "on")
    if not check and not allow_pkg and is_tapps_mcp_package_layout(root):
        click.echo(
            click.style(
                "Refusing init: project root is the tapps-mcp package directory "
                "(.../packages/tapps-mcp).",
                fg="red",
            )
        )
        click.echo("  Target your consumer repo with: --project-root <path>")
        click.echo(
            "  Example: uv --directory <TappMCP-monorepo> run tapps-mcp init "
            "--project-root <consumer-app>"
        )
        click.echo(
            "  Package maintainers: set TAPPS_MCP_ALLOW_PACKAGE_INIT=1 or use --allow-package-init."
        )
        return False

    # Issue #77: decide launch form (classic tapps-mcp vs `uv run --extra ...`).
    use_uv, extra_auto, _uv_ctx = _should_use_uv_launch(root, uv_mode=uv_mode)
    uv_launch: tuple[str, list[str]] | None = None
    if use_uv:
        chosen_extra = uv_extra or extra_auto
        uv_launch = _build_uv_run_tapps_launch(chosen_extra)
        click.echo(
            click.style(
                f"uv project detected — emitting '{' '.join([uv_launch[0], *uv_launch[1]])}'",
                fg="cyan",
            )
        )

    # Issue #79: build extra_env dict for Context7 key (uses ${VAR} interpolation
    # so the literal key is never written to the config file).
    extra_env: dict[str, str] | None = None
    if context7_api_key:
        extra_env = {"TAPPS_MCP_CONTEXT7_API_KEY": "${TAPPS_MCP_CONTEXT7_API_KEY}"}
        click.echo(
            click.style(
                "  Context7 configured — using ${TAPPS_MCP_CONTEXT7_API_KEY} interpolation.",
                fg="cyan",
            )
        )
        click.echo(
            f"  Add to your shell profile:  export TAPPS_MCP_CONTEXT7_API_KEY='{context7_api_key}'"
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
            with_docs_mcp=with_docs_mcp,
            uv_launch=uv_launch,
            extra_env=extra_env,
        )

    if check:
        return _check_config(mcp_host, root, scope=scope)

    if engagement_level is not None and not dry_run:
        _write_engagement_level_to_yaml(root, engagement_level)

    ok = _generate_config(
        mcp_host,
        root,
        force=force,
        scope=scope,
        dry_run=dry_run,
        with_docs_mcp=with_docs_mcp,
        uv_launch=uv_launch,
        extra_env=extra_env,
    )
    if ok and rules and not dry_run:
        _generate_rules(mcp_host, root, engagement_level=engagement_level)
    elif ok and rules and dry_run:
        _preview_rules(mcp_host, root, engagement_level=engagement_level)
    return ok


# ---------------------------------------------------------------------------
# Upgrade command
# ---------------------------------------------------------------------------


def _format_upgrade_result(result: dict[str, Any], *, dry_run: bool = False) -> None:
    """Format the structured result from :func:`upgrade_pipeline` for CLI output.

    Translates the dict returned by ``upgrade_pipeline()`` into human-readable
    ``click.echo()`` lines, keeping a single source of truth for upgrade logic
    in ``pipeline/upgrade.py``.
    """
    prefix = "[DRY-RUN] " if dry_run else ""
    version = result.get("version", "?")

    click.echo("")
    click.echo(click.style(f"{prefix}=== TappsMCP Upgrade (v{version}) ===", bold=True))
    click.echo("")

    # AGENTS.md
    click.echo(click.style("--- AGENTS.md ---", bold=True))
    agents = result.get("components", {}).get("agents_md", {})
    agents_action = agents.get("action", "unknown")
    agents_detail = agents.get("detail", "")
    agents_text = agents_action
    if agents_detail:
        agents_text = f"{agents_action} ({agents_detail})"
    color = "green" if agents_action == "up-to-date" else "yellow"
    click.echo(click.style(f"  AGENTS.md: {agents_text}", fg=color))

    # Karpathy guidelines block (AGENTS.md + CLAUDE.md)
    kp = result.get("components", {}).get("karpathy_guidelines", {})
    if kp:
        click.echo("")
        click.echo(click.style("--- Karpathy guidelines ---", bold=True))
        sha = (kp.get("source_sha") or "")[:7]
        ok_actions = {"unchanged", "added", "refreshed", "skipped_file_missing"}
        for rel, action in (kp.get("files") or {}).items():
            fg = "green" if action in ok_actions else "yellow"
            click.echo(click.style(f"  {rel}: {action}", fg=fg))
        if sha:
            click.echo(f"  pinned to: {sha}")

    # Per-platform results
    platforms: list[dict[str, Any]] = result.get("components", {}).get("platforms", [])
    for platform in platforms:
        host = platform.get("host", "unknown")
        click.echo("")
        click.echo(click.style(f"--- {host} ---", bold=True))

        if "error" in platform:
            click.echo(click.style(f"  Error: {platform['error']}", fg="red"))
            continue

        components = platform.get("components", {})
        for key, value in components.items():
            if isinstance(value, dict):
                created = value.get("scripts_created") or value.get("created") or []
                if created:
                    click.echo(click.style(f"  Generated {key}: {', '.join(created)}", fg="green"))
                else:
                    click.echo(f"  {key.capitalize()} already up to date (skipped)")
            elif isinstance(value, str):
                ok_statuses = ("ok", "skipped", "up-to-date")
                fg = "green" if value in ok_statuses else "yellow"
                click.echo(click.style(f"  {key}: {value}", fg=fg))

    # Summary
    click.echo("")
    errors: list[str] = result.get("errors", [])
    if dry_run:
        click.echo(
            click.style("Dry run complete. Run without --dry-run to apply changes.", fg="cyan")
        )
    elif not errors:
        click.echo(click.style("Upgrade complete!", fg="green"))
        click.echo(
            "\nFor the full consumer requirements checklist, see docs/TAPPS_MCP_REQUIREMENTS.md"
        )
    else:
        for err in errors:
            click.echo(click.style(f"  Error: {err}", fg="red"))
        click.echo(click.style("Upgrade completed with issues. Check output above.", fg="yellow"))


def run_upgrade(
    *,
    mcp_host: str = "auto",
    project_root: str = ".",
    force: bool = False,
    dry_run: bool = False,
    scope: str = "project",
    emit_json: bool = False,
) -> bool:
    """Validate and update all TappsMCP-generated files.

    Called from the CLI ``upgrade`` command.  Delegates to
    :func:`~tapps_mcp.pipeline.upgrade.upgrade_pipeline` for the actual
    work and formats the structured result for human-readable CLI output.

    Args:
        mcp_host: Target host or ``"auto"`` for detection.
        project_root: Project root directory as a string path.
        force: If ``True``, overwrite all generated files without prompting.
        dry_run: If ``True``, show what would be updated without making changes.
        scope: ``"project"`` (default) or ``"user"``. Only affects ``claude-code``.
        emit_json: If ``True``, print the structured result dict as JSON to stdout
            instead of the text summary. Surfaces ``dry_run_summary`` and per-
            component ``managed_files`` / ``preserved_files`` so the CLI matches
            the MCP tool's precision (3.2.0/3.2.1).
    """
    import json

    from tapps_mcp.pipeline.upgrade import upgrade_pipeline

    if emit_json:
        # Route all structlog output to stderr so stdout stays pure JSON for
        # piping into jq/other tools. Without this, the default structlog
        # config writes INFO lines to stdout and corrupts the payload.
        import logging

        from tapps_core.common.logging import setup_logging

        setup_logging(level="WARNING")
        # Belt-and-braces: drop stdlib loggers below WARNING as well in case
        # code paths invoked by the pipeline use stdlib logging directly.
        logging.getLogger().setLevel(logging.WARNING)

    root = Path(project_root).resolve()
    log.info(
        "upgrade_command",
        host=mcp_host,
        project_root=str(root),
        force=force,
        dry_run=dry_run,
        scope=scope,
    )

    # Map CLI host names to pipeline platform names
    platform = ""
    if mcp_host == "claude-code":
        platform = "claude"
    elif mcp_host == "cursor":
        platform = "cursor"
    elif mcp_host != "auto":
        platform = mcp_host

    result = upgrade_pipeline(root, platform=platform, force=force, dry_run=dry_run)
    if emit_json:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        _format_upgrade_result(result, dry_run=dry_run)
    return bool(result.get("success", True))
