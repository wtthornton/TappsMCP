"""MCP server entry construction and merging.

Builds the per-server JSON blocks (command, args, env, instructions) that land
in ``.mcp.json`` / ``.cursor/mcp.json``, and merges them into whatever the
consumer already has on disk without clobbering unrelated servers or
user-customized env. Split out of ``setup_generator`` (TAP-5733).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tapps_core.brain_bridge import BRAIN_PROFILE_FACADE, BRAIN_PROFILE_SERVER
from tapps_mcp.distribution.nlt_mcp_config import (
    _LEGACY_MCP_SERVER_IDS,
    NLT_SERVER_ORDER,
    NLT_SERVER_SPECS,
    commented_servers_for_bundle,
    mcp_config_servers_for_bundle,
    normalize_mcp_bundle,
)
from tapps_mcp.distribution.setup_config_io import _get_servers_key
from tapps_mcp.distribution.setup_launch import (
    _build_nlt_launch,
    _preserve_launch_on_upgrade,
    _resolve_docsmcp_launch,
    _resolve_tapps_mcp_launch,
)

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

# Literal emitted in mcp.json env; wrapper treats this as "unset" when mapping tokens.
_BRAIN_AUTH_TOKEN_ENV_PLACEHOLDER = "${TAPPS_BRAIN_AUTH_TOKEN}"  # noqa: S105


def _derive_brain_project_id(project_root: Path | None) -> str:
    """TAP-1336: Derive ``X-Project-Id`` slug for MCP env blocks.

    Prefers ``memory.brain_project_id`` from ``.tapps-mcp.yaml`` when set so
    init/upgrade does not overwrite an explicit registration slug with the
    directory name. Falls back to :func:`tapps_core.config.settings._slugify_project_root`.
    """
    if project_root is None:
        return ""
    try:
        resolved = Path(project_root).resolve()
    except (OSError, RuntimeError):
        return ""
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=resolved)
        explicit = (settings.memory.brain_project_id or "").strip()
        if explicit:
            return explicit
    except Exception:
        pass
    from tapps_core.config.settings import _slugify_project_root

    return _slugify_project_root(resolved)


def _resolve_project_root_value(host: str, project_root: Path | None) -> str:
    """Return the value to emit for ``TAPPS_MCP_PROJECT_ROOT`` / ``DOCS_MCP_PROJECT_ROOT``.

    TAP-2199: never emit the literal ``${workspaceFolder}``. Claude Code CLI
    does not expand VS Code variables, so a literal ``${workspaceFolder}``
    leaks into the server process and ``Path("${workspaceFolder}")`` silently
    creates a phantom ``./${workspaceFolder}/`` directory at the real project
    root. Resolving to an absolute path at render time fixes this uniformly
    across Claude Code, Cursor, and VS Code (all three host launchers accept
    a literal absolute path).
    """
    if host == "claude-code":
        # Claude Code launches with CWD == project root; "." is unambiguous
        # and keeps the file portable across machines.
        return "."
    if project_root is None:
        # Defensive: callers in legacy paths may not pass project_root.
        # Resolve against cwd so we still emit a real absolute path rather
        # than the broken literal.
        return str(Path.cwd().resolve())
    return str(project_root.resolve())


def _build_server_entry(
    host: str,
    *,
    uv_launch: tuple[str, list[str]] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build the tapps-mcp server config entry for the given host.

    Claude Code gets an extra ``instructions`` field for Tool Search discovery.
    All platforms get the ``env`` block with ``TAPPS_MCP_PROJECT_ROOT``,
    the tapps-brain memory connection (TAP-1336): ``HTTP_URL``, ``AUTH_TOKEN``
    via ``${TAPPS_BRAIN_AUTH_TOKEN}`` substitution, and ``PROJECT_ID`` derived
    from the project directory name, plus ``TAPPS_MCP_CONTEXT7_API_KEY`` via
    ``${TAPPS_MCP_CONTEXT7_API_KEY}`` substitution so ``tapps_lookup_docs``
    routes through Context7 whenever the consumer has the env var exported.
    Without these defaults, brand-new ``tapps_init`` installs hit the brain
    server with no auth/identity (``brain_auth_token_missing``) and silently
    fall back to the llms.txt provider for docs lookup.

    The auth token uses env-var substitution rather than a literal value so
    consuming projects can safely commit ``.mcp.json``. The merge logic in
    :func:`_merge_config` preserves any user-customized values on upgrade.

    Claude Code uses ``"."`` (launch CWD == project root). Cursor and VS Code
    get the resolved absolute path. TAP-2199: we never emit the literal
    ``${workspaceFolder}`` because Claude Code CLI does not expand VS Code
    variables and the server then mkdirs a phantom ``${workspaceFolder}/``
    directory at the real project root.

    Uses :func:`_resolve_tapps_mcp_launch` for command and args unless
    *uv_launch* is provided (Issue #77 — consumer uv projects).
    """
    if uv_launch is not None:
        command, args = uv_launch
    else:
        command, args = _resolve_tapps_mcp_launch()
    project_root_value = _resolve_project_root_value(host, project_root)
    env: dict[str, str] = {
        "TAPPS_MCP_PROJECT_ROOT": project_root_value,
        "TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://localhost:8080",
        "TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN": _BRAIN_AUTH_TOKEN_ENV_PLACEHOLDER,
        # ADR-0012: the tapps-mcp server backs the full tapps_memory facade,
        # which exercises the whole read+write+hive+KG+feedback surface — so it
        # needs the ``full`` profile, not ``coder`` (which gates ~18 of those
        # tools on tapps-brain v3.20.0+). Operator-overridable knob — export
        # TAPPS_BRAIN_PROFILE=operator for a maintenance session.
        "TAPPS_BRAIN_PROFILE": BRAIN_PROFILE_SERVER,
        # TAP-3572: dual-write keeps local JSONL for fleet audit even when brain is up.
        "TAPPS_METRICS_STORAGE": "dual",
    }
    from tapps_core.knowledge.brain_docs import (
        apply_docs_via_brain_mcp_env,
        docs_via_brain_enabled,
    )

    if not docs_via_brain_enabled():
        env["TAPPS_MCP_CONTEXT7_API_KEY"] = "${TAPPS_MCP_CONTEXT7_API_KEY}"
    env = apply_docs_via_brain_mcp_env(env)
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
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build the docs-mcp server entry (optional ``--with-docs-mcp``, Epic 80.7).

    When *uv_launch* is provided (consumer uv project, Issue #79 sub-issue),
    mirrors the same ``uv run`` pattern but launches ``docsmcp serve`` instead
    of ``tapps-mcp serve``. TAP-2199: ``DOCS_MCP_PROJECT_ROOT`` resolves the
    same way as ``TAPPS_MCP_PROJECT_ROOT`` — never the literal
    ``${workspaceFolder}``.
    """
    if uv_launch is not None:
        # Derive a docs-mcp equivalent: replace 'tapps-mcp' with 'docsmcp' in args.
        command = uv_launch[0]
        args = [("docsmcp" if a == "tapps-mcp" else a) for a in uv_launch[1]]
        # Replace 'serve' keyword coming after the tool name — already present.
    else:
        command, args = _resolve_docsmcp_launch()
    project_root_value = _resolve_project_root_value(host, project_root)
    entry: dict[str, Any] = {
        "type": "stdio",
        "command": command,
        "args": args,
        "env": {
            "DOCS_MCP_PROJECT_ROOT": project_root_value,
            # ADR-0012: docs-mcp needs only the brain_* facade surface.
            "TAPPS_BRAIN_PROFILE": BRAIN_PROFILE_FACADE,
        },
    }
    if host == "claude-code":
        entry["instructions"] = _DOCS_SERVER_INSTRUCTIONS
    return entry


# ---------------------------------------------------------------------------
# Config merging
# ---------------------------------------------------------------------------


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
        if _preserve_launch_on_upgrade(
            upgrade_mode,
            old_entry,
            binary_name="tapps-mcp",
            project_root=project_root,
        ):
            new_entry["command"] = old_entry["command"]
            if "args" in old_entry:
                new_entry["args"] = old_entry["args"]
        old_env = old_entry.get("env")
        new_env = new_entry.get("env") or {}
        if isinstance(old_env, dict):
            # Epic 80.5: keep unrelated env keys (e.g. API keys) when merging/replacing
            merged_env = {**old_env, **new_env}
            from tapps_core.knowledge.brain_docs import apply_docs_via_brain_mcp_env

            new_entry["env"] = apply_docs_via_brain_mcp_env(merged_env)

    merged[servers_key]["tapps-mcp"] = new_entry

    return merged


def _merge_docsmcp_entry(
    merged: dict[str, Any],
    host: str,
    *,
    upgrade_mode: bool = False,
    uv_launch: tuple[str, list[str]] | None = None,
    project_root: Path | None = None,
) -> None:
    """Merge or add the ``docs-mcp`` server entry into *merged*."""
    servers_key = _get_servers_key(host)
    merged.setdefault(servers_key, {})
    new_docs = _build_docsmcp_server_entry(host, uv_launch=uv_launch, project_root=project_root)
    old_docs = merged[servers_key].get("docs-mcp")
    if isinstance(old_docs, dict):
        if _preserve_launch_on_upgrade(
            upgrade_mode,
            old_docs,
            binary_name="docsmcp",
            project_root=project_root,
        ):
            new_docs["command"] = old_docs["command"]
            if "args" in old_docs:
                new_docs["args"] = old_docs["args"]
        old_env = old_docs.get("env")
        new_env = new_docs.get("env") or {}
        if isinstance(old_env, dict):
            new_docs["env"] = {**old_env, **new_env}
    merged[servers_key]["docs-mcp"] = new_docs


# ---------------------------------------------------------------------------
# NLT MCP plugin (Epic 109)
# ---------------------------------------------------------------------------


def _build_nlt_server_entry(
    server_id: str,
    host: str,
    *,
    uv_launch: tuple[str, list[str]] | None = None,
    project_root: Path | None = None,
    upgrade_mode: bool = False,
    old_entry: dict[str, Any] | None = None,
    mcp_transport: str = "stdio",
    fleet_host: str | None = None,
) -> dict[str, Any]:
    """Build one NLT plugin server entry for MCP host config."""
    if mcp_transport == "http":
        from tapps_mcp.distribution.nlt_http_fleet import build_nlt_http_mcp_entry

        return build_nlt_http_mcp_entry(
            server_id,
            project_root=project_root,
            fleet_host=fleet_host,
            host=host,
        )

    spec = NLT_SERVER_SPECS[server_id]
    launch = _build_nlt_launch(server_id, uv_launch, project_root=project_root)

    if spec["env_kind"] == "docs":
        entry = _build_docsmcp_server_entry(
            host,
            uv_launch=launch,
            project_root=project_root,
        )
    else:
        entry = _build_server_entry(
            host,
            uv_launch=launch,
            project_root=project_root,
        )

    if isinstance(old_entry, dict):
        binary_name = str(spec["serve_command"])
        if _preserve_launch_on_upgrade(
            upgrade_mode,
            old_entry,
            binary_name=binary_name,
            project_root=project_root,
        ):
            entry["command"] = old_entry["command"]
            if "args" in old_entry:
                entry["args"] = old_entry["args"]
        old_env = old_entry.get("env")
        new_env = entry.get("env") or {}
        if isinstance(old_env, dict):
            merged_env = {**old_env, **new_env}
            from tapps_core.knowledge.brain_docs import apply_docs_via_brain_mcp_env

            entry["env"] = apply_docs_via_brain_mcp_env(merged_env)

    return entry


def _collect_legacy_tapps_env(old_servers: dict[str, Any]) -> dict[str, str]:
    """Pull env vars from legacy ``tapps-mcp`` or primary NLT server for migration."""
    merged: dict[str, str] = {}
    for key in ("tapps-mcp", "nlt-build", "nlt-code-quality", "nlt-setup", "nlt-platform-admin"):
        entry = old_servers.get(key)
        if not isinstance(entry, dict):
            continue
        env = entry.get("env")
        if isinstance(env, dict):
            merged.update({str(k): str(v) for k, v in env.items() if isinstance(v, str)})
    return merged


# Legacy server ids that map onto a canonical NLT id when migrating an old config.
_LEGACY_NLT_ALIASES: tuple[tuple[str, str], ...] = (
    ("nlt-code-quality", "nlt-build"),
    ("nlt-platform-admin", "nlt-setup"),
    ("tapps-mcp", "nlt-build"),
)


def _resolve_old_nlt_entry(server_id: str, old_servers: dict[str, Any]) -> dict[str, Any] | None:
    """Return the prior on-disk entry for *server_id*, following legacy renames."""
    old_entry = old_servers.get(server_id)
    if isinstance(old_entry, dict):
        return old_entry
    for legacy_id, canonical in _LEGACY_NLT_ALIASES:
        if server_id == canonical:
            legacy_entry = old_servers.get(legacy_id)
            if isinstance(legacy_entry, dict):
                return legacy_entry
    return None


def _apply_legacy_env(entry: dict[str, Any], legacy_env: dict[str, str]) -> None:
    """Fold migrated legacy env into *entry* without losing freshly-derived values."""
    cur_env = entry.get("env")
    if not isinstance(cur_env, dict):
        cur_env = {}
    merged_env = {**cur_env, **legacy_env}
    # TAP-2199: absolute roots from _build_nlt_server_entry beat legacy
    # ``${workspaceFolder}``; explicit brain project id from yaml beats
    # stale legacy env from prior init runs.
    for key in (
        "TAPPS_MCP_PROJECT_ROOT",
        "DOCS_MCP_PROJECT_ROOT",
        "TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID",
    ):
        if key in cur_env:
            merged_env[key] = cur_env[key]
    entry["env"] = merged_env


def _merge_nlt_config(
    existing: dict[str, Any],
    host: str,
    *,
    mcp_bundle: str = "full",
    upgrade_mode: bool = False,
    uv_launch: tuple[str, list[str]] | None = None,
    project_root: Path | None = None,
    mcp_transport: str = "stdio",
    fleet_host: str | None = None,
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    """Merge NLT plugin server entries into *existing* config."""
    bundle = normalize_mcp_bundle(mcp_bundle)
    enabled = mcp_config_servers_for_bundle(bundle)
    commented = commented_servers_for_bundle(bundle)
    servers_key = _get_servers_key(host)
    merged = dict(existing)
    raw_servers = merged.get(servers_key)
    old_servers: dict[str, Any] = raw_servers if isinstance(raw_servers, dict) else {}
    legacy_env = _collect_legacy_tapps_env(old_servers)

    preserved: dict[str, Any] = {
        name: entry
        for name, entry in old_servers.items()
        if name not in NLT_SERVER_ORDER and name not in _LEGACY_MCP_SERVER_IDS
    }

    nlt_servers: dict[str, Any] = {}
    for server_id in NLT_SERVER_ORDER:
        entry = _build_nlt_server_entry(
            server_id,
            host,
            uv_launch=uv_launch,
            project_root=project_root,
            upgrade_mode=upgrade_mode,
            old_entry=_resolve_old_nlt_entry(server_id, old_servers),
            mcp_transport=mcp_transport,
            fleet_host=fleet_host,
        )
        if server_id == "nlt-build" and legacy_env and mcp_transport != "http":
            _apply_legacy_env(entry, legacy_env)
        nlt_servers[server_id] = entry

    merged[servers_key] = {**preserved, **nlt_servers}
    return merged, enabled, commented


def _serialize_nlt_mcp_config(
    merged: dict[str, Any],
    host: str,
    *,
    enabled: tuple[str, ...],
    commented: tuple[str, ...] = (),
) -> str:
    """Serialize MCP config as strict JSON (enabled NLT servers only).

    Disabled / opt-in servers are omitted from the file (TAP-4811). Hosts
    require strict JSON; commented JSONC blocks broke ``json.loads`` and
    prevented MCP servers from loading. Callers surface opt-in hints on
    CLI stdout via ``commented`` / ``commented_servers_for_bundle``.
    """
    del commented  # Kept for call-site compatibility; never written to disk.
    servers_key = _get_servers_key(host)
    servers = merged.get(servers_key)
    if not isinstance(servers, dict):
        servers = {}

    enabled_servers: dict[str, Any] = {
        sid: servers[sid] for sid in enabled if sid in servers and isinstance(servers[sid], dict)
    }
    for name, entry in servers.items():
        if name in NLT_SERVER_ORDER or name in _LEGACY_MCP_SERVER_IDS:
            continue
        if isinstance(entry, dict):
            enabled_servers[name] = entry

    out: dict[str, Any] = {k: v for k, v in merged.items() if k != servers_key}
    out[servers_key] = enabled_servers
    return json.dumps(out, indent=2) + "\n"


def _config_has_tapps_or_nlt(servers: dict[str, Any]) -> bool:
    """Return True when TappsMCP (legacy or NLT) is already configured."""
    from tapps_mcp.distribution.nlt_mcp_config import list_nlt_server_ids_in_config

    if "tapps-mcp" in servers:
        return True
    return bool(list_nlt_server_ids_in_config(servers))
