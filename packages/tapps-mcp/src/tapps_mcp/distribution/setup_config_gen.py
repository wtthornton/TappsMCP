"""Write (or merge) the MCP config file for one host.

The orchestrator is :func:`_generate_config`: resolve transport, read whatever
is already on disk, decide whether we may overwrite it, merge in the TappsMCP /
NLT server entries, point stdio entries at their wrapper scripts, and write.
Split out of ``setup_generator`` (TAP-5733).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Literal

import click

from tapps_mcp.distribution.nlt_mcp_config import (
    DEFAULT_NLT_BUNDLE,
    NLT_SERVER_ORDER,
    enabled_servers_for_bundle,
    normalize_mcp_bundle,
)
from tapps_mcp.distribution.setup_config_io import (
    _get_config_path,
    _get_servers_key,
    _load_mcp_config_json,
    _other_scope_config_path,
)
from tapps_mcp.distribution.setup_entries import (
    _build_server_entry,
    _config_has_tapps_or_nlt,
    _merge_config,
    _merge_docsmcp_entry,
    _merge_nlt_config,
    _serialize_nlt_mcp_config,
)
from tapps_mcp.distribution.setup_guidance import _print_next_steps
from tapps_mcp.distribution.setup_launch import _should_include_docs_mcp
from tapps_mcp.distribution.setup_secrets import (
    _load_existing_env_from_other_scope,
    _warn_plaintext_secrets,
)
from tapps_mcp.distribution.setup_wrappers import (
    _STDIO_WRAPPER_HOSTS,
    _apply_cursor_launch_wrapper,
    _stdio_wrapper_rel,
)

# Env values that mean "yes" for TAPPS_MCP_INIT_ASSUME_YES.
_TRUTHY_ENV_VALUES = ("1", "true", "yes", "y", "on")

# Server ids whose ``env`` block may carry the user's extra env (first match wins).
_EXTRA_ENV_TARGET_IDS = (
    "tapps-mcp",
    "nlt-build",
    "nlt-code-quality",
    "nlt-setup",
    "nlt-platform-admin",
)

_OverwriteDecision = Literal["proceed", "abort", "skip"]


def _resolve_transport_and_fleet_host(
    project_root: Path, mcp_transport: str | None
) -> tuple[str, str]:
    """Return the effective ``(transport, fleet_host)`` for *project_root*."""
    from tapps_mcp.distribution.nlt_http_fleet import resolve_mcp_transport

    transport = resolve_mcp_transport(project_root, explicit=mcp_transport)
    fleet_host = "127.0.0.1"
    try:
        from tapps_core.config.settings import load_settings

        fleet_host = load_settings(project_root=project_root).mcp_fleet_host
    except Exception:
        pass
    return transport, fleet_host


def _report_invalid_json(config_path: Path) -> None:
    """Explain that *config_path* holds unparseable JSON and must be fixed by hand."""
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


def _decide_overwrite(config_path: Path, label: str, *, force: bool) -> _OverwriteDecision:
    """Decide whether to overwrite pre-existing TappsMCP entries in *config_path*.

    Returns ``"proceed"`` to overwrite, ``"abort"`` when the user declined at an
    interactive prompt, and ``"skip"`` when a non-interactive session declined to
    touch existing entries without ``--force``.
    """
    click.echo(
        click.style(
            f"{label} is already configured in {config_path}",
            fg="yellow",
        )
    )
    if force:
        return "proceed"
    if sys.stdin.isatty():
        if not click.confirm(f"Overwrite the existing {label} entries?"):
            click.echo("Aborted.")
            return "abort"
        return "proceed"
    assume = os.environ.get("TAPPS_MCP_INIT_ASSUME_YES", "").strip().lower()
    if assume in _TRUTHY_ENV_VALUES:
        return "proceed"
    click.echo(
        click.style(
            f"Non-interactive session: skipping overwrite of existing {label} entries.",
            fg="yellow",
        )
    )
    click.echo(
        "  Re-run with --force or set TAPPS_MCP_INIT_ASSUME_YES=1 to overwrite without prompting."
    )
    return "skip"


def _apply_migrated_env(
    merged: dict[str, Any],
    *,
    host: str,
    project_root: Path,
    scope: str,
    use_nlt_plugin: bool,
    dry_run: bool,
) -> None:
    """Carry env registered in the other Claude Code scope into the primary entry."""
    migrated_env = _load_existing_env_from_other_scope(host, project_root, scope)
    if not migrated_env:
        return
    servers_key = _get_servers_key(host)
    primary_key = "nlt-build" if use_nlt_plugin else "tapps-mcp"
    entry = merged.get(servers_key, {}).get(primary_key)
    if not isinstance(entry, dict):
        return
    cur_env = entry.get("env")
    if not isinstance(cur_env, dict):
        cur_env = {}
    entry["env"] = {**migrated_env, **cur_env}
    migrated_keys = sorted(k for k in migrated_env if k not in cur_env)
    if migrated_keys and not dry_run:
        other_path = _other_scope_config_path(host, project_root, scope)
        click.echo(
            click.style(
                f"  Migrated env vars from {other_path}: {', '.join(migrated_keys)}",
                fg="cyan",
            )
        )


def _apply_extra_env(
    merged: dict[str, Any], servers_key: str, extra_env: dict[str, str] | None
) -> None:
    """Fold *extra_env* into the first TappsMCP-shaped server entry that has a root."""
    if not extra_env:
        return
    servers_block = merged.get(servers_key, {})
    if not isinstance(servers_block, dict):
        return
    for env_key in _EXTRA_ENV_TARGET_IDS:
        tapps_entry = servers_block.get(env_key)
        if isinstance(tapps_entry, dict) and tapps_entry.get("env", {}).get(
            "TAPPS_MCP_PROJECT_ROOT"
        ):
            env = tapps_entry.get("env")
            if not isinstance(env, dict):
                env = {}
            tapps_entry["env"] = {**env, **extra_env}
            return


def _echo_dry_run_wrappers(
    host: str, project_root: Path, *, use_nlt_plugin: bool, transport: str
) -> None:
    """List the wrapper scripts a real run would write for *host*."""
    if host not in _STDIO_WRAPPER_HOSTS:
        return
    if not use_nlt_plugin:
        click.echo(f"  Would write {host} wrapper: {project_root / _stdio_wrapper_rel(host)}")
        return
    if transport == "http":
        click.echo("  Would write HTTP fleet URLs (no stdio wrappers).")
        return
    for sid in NLT_SERVER_ORDER:
        click.echo(f"  Would write {host} wrapper: {project_root / _stdio_wrapper_rel(host, sid)}")


def _echo_dry_run_plan(
    config_path: Path,
    host: str,
    project_root: Path,
    *,
    use_nlt_plugin: bool,
    mcp_bundle: str,
    nlt_enabled: tuple[str, ...],
    transport: str,
) -> None:
    """Describe what a real run would write, without touching the filesystem."""
    click.echo(
        click.style(
            f"[DRY-RUN] Would write configuration to {config_path}",
            fg="cyan",
        )
    )
    if use_nlt_plugin:
        bundle = normalize_mcp_bundle(mcp_bundle)
        recommended = enabled_servers_for_bundle(bundle)
        click.echo(
            f"  NLT bundle '{bundle}': "
            f"write all {len(nlt_enabled)} server(s) to MCP config; "
            f"recommended active: {', '.join(recommended)}."
        )
    else:
        click.echo("  tapps-mcp entry would be added/updated. Run without --dry-run to apply.")
    _echo_dry_run_wrappers(host, project_root, use_nlt_plugin=use_nlt_plugin, transport=transport)


def _apply_stdio_wrappers(
    merged: dict[str, Any],
    servers_key: str,
    host: str,
    project_root: Path,
    *,
    uv_launch: tuple[str, list[str]] | None,
    use_nlt_plugin: bool,
) -> None:
    """Repoint every stdio entry at its generated wrapper script."""
    servers_block = merged.get(servers_key, {})
    if not isinstance(servers_block, dict):
        return
    server_ids = NLT_SERVER_ORDER if use_nlt_plugin else ("tapps-mcp",)
    for sid in server_ids:
        entry = servers_block.get(sid)
        if not isinstance(entry, dict):
            continue
        if use_nlt_plugin:
            _apply_cursor_launch_wrapper(
                entry,
                project_root,
                uv_launch=uv_launch,
                server_id=sid,
                host=host,
            )
        else:
            _apply_cursor_launch_wrapper(
                entry,
                project_root,
                uv_launch=uv_launch,
                host=host,
            )


def _echo_nlt_summary(
    mcp_bundle: str, nlt_enabled: tuple[str, ...], nlt_commented: tuple[str, ...]
) -> None:
    """Report which NLT servers landed in the config and which were left out."""
    recommended = enabled_servers_for_bundle(normalize_mcp_bundle(mcp_bundle))
    click.echo(
        click.style(
            f"  NLT plugin: {len(nlt_enabled)} server(s) in MCP config "
            f"({', '.join(nlt_enabled)}). "
            f"Toggle in your IDE; recommended active: {', '.join(recommended)}.",
            fg="cyan",
        )
    )
    if nlt_commented:
        click.echo(
            click.style(
                "  Opt-in servers omitted from this JSON (strict JSON only): "
                f"{', '.join(nlt_commented)}. "
                "Re-run with a broader --bundle (e.g. --bundle full) or enable "
                "them in your IDE MCP settings.",
                fg="cyan",
            )
        )


def _read_existing_config(
    config_path: Path,
    servers_key: str,
    *,
    use_nlt_plugin: bool,
    force: bool,
) -> tuple[dict[str, Any], _OverwriteDecision]:
    """Load any config already at *config_path* and decide whether we may rewrite it.

    Returns the parsed config (``{}`` when absent) plus a decision: ``"proceed"``
    to write, ``"abort"`` on unparseable JSON or a declined prompt, ``"skip"``
    when a non-interactive run left existing entries alone.
    """
    if not config_path.exists():
        return {}, "proceed"

    existing = _load_mcp_config_json(config_path)
    if existing == {} and config_path.read_text(encoding="utf-8").strip():
        _report_invalid_json(config_path)
        return existing, "abort"

    old_servers = existing.get(servers_key, {})
    if isinstance(old_servers, dict) and _config_has_tapps_or_nlt(old_servers):
        label = "NLT TappsMCP" if use_nlt_plugin else "tapps-mcp"
        return existing, _decide_overwrite(config_path, label, force=force)
    return existing, "proceed"


def _build_merged_config(
    existing: dict[str, Any],
    host: str,
    servers_key: str,
    *,
    config_exists: bool,
    upgrade_mode: bool,
    uv_launch: tuple[str, list[str]] | None,
    project_root: Path,
    mcp_bundle: str,
    use_nlt_plugin: bool,
    transport: str,
    fleet_host: str,
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    """Merge TappsMCP entries into *existing*, returning the NLT enabled/opt-in split."""
    if use_nlt_plugin:
        return _merge_nlt_config(
            existing,
            host,
            mcp_bundle=mcp_bundle,
            upgrade_mode=upgrade_mode,
            uv_launch=uv_launch,
            project_root=project_root,
            mcp_transport=transport,
            fleet_host=fleet_host,
        )
    if config_exists:
        merged = _merge_config(
            existing,
            host,
            upgrade_mode=upgrade_mode,
            uv_launch=uv_launch,
            project_root=project_root,
        )
    else:
        merged = {
            servers_key: {
                "tapps-mcp": _build_server_entry(
                    host, uv_launch=uv_launch, project_root=project_root
                ),
            }
        }
    return merged, (), ()


def _write_merged_config(
    config_path: Path,
    merged: dict[str, Any],
    host: str,
    *,
    use_nlt_plugin: bool,
    nlt_enabled: tuple[str, ...],
    nlt_commented: tuple[str, ...],
) -> None:
    """Serialize *merged* to disk, creating parent directories as needed."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if use_nlt_plugin:
        text = _serialize_nlt_mcp_config(
            merged,
            host,
            enabled=nlt_enabled,
            commented=nlt_commented,
        )
    else:
        text = json.dumps(merged, indent=2) + "\n"
    config_path.write_text(text, encoding="utf-8")


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
    mcp_bundle: str = DEFAULT_NLT_BUNDLE,
    use_nlt_plugin: bool = False,
    mcp_transport: str | None = None,
) -> bool:
    """Generate (or merge) the MCP config for the given host.

    Args:
        host: Target host name.
        project_root: Project root directory.
        force: If ``True``, overwrite any existing TappsMCP entry without
            prompting. Intended for non-interactive use (CI, scripts).
        scope: ``"project"`` (default) or ``"user"``. Only affects ``claude-code``.
        with_docs_mcp: Legacy monolith mode — also write ``docs-mcp`` (Epic 80.7).
        mcp_bundle: NLT bundle name (``developer``, ``planning``, ``docs``, ``release``).
        use_nlt_plugin: When ``True``, write NLT ``nlt-*`` server entries (``tapps_init`` default).

    Returns:
        ``True`` if configuration was successfully written, ``False`` if the
        operation was aborted or failed (e.g. invalid JSON).
    """
    transport, fleet_host = _resolve_transport_and_fleet_host(project_root, mcp_transport)
    if transport == "http":
        click.echo(
            click.style(
                "HTTP fleet transport — ensure `tapps-mcp fleet start` is running "
                f"(six servers on {fleet_host}:8760-8765).",
                fg="cyan",
            )
        )

    config_path = _get_config_path(host, project_root, scope=scope)
    servers_key = _get_servers_key(host)
    config_exists = config_path.exists()

    existing, decision = _read_existing_config(
        config_path, servers_key, use_nlt_plugin=use_nlt_plugin, force=force
    )
    if decision != "proceed":
        return decision == "skip"

    merged, nlt_enabled, nlt_commented = _build_merged_config(
        existing,
        host,
        servers_key,
        config_exists=config_exists,
        upgrade_mode=upgrade_mode,
        uv_launch=uv_launch,
        project_root=project_root,
        mcp_bundle=mcp_bundle,
        use_nlt_plugin=use_nlt_plugin,
        transport=transport,
        fleet_host=fleet_host,
    )

    include_docs_mcp = (
        False
        if use_nlt_plugin
        else _should_include_docs_mcp(
            with_docs_mcp,
            existing=existing if config_exists else None,
            servers_key=servers_key,
        )
    )

    _apply_migrated_env(
        merged,
        host=host,
        project_root=project_root,
        scope=scope,
        use_nlt_plugin=use_nlt_plugin,
        dry_run=dry_run,
    )
    _apply_extra_env(merged, servers_key, extra_env)

    if include_docs_mcp:
        _merge_docsmcp_entry(
            merged,
            host,
            upgrade_mode=upgrade_mode,
            uv_launch=uv_launch,
            project_root=project_root,
        )

    if dry_run:
        _echo_dry_run_plan(
            config_path,
            host,
            project_root,
            use_nlt_plugin=use_nlt_plugin,
            mcp_bundle=mcp_bundle,
            nlt_enabled=nlt_enabled,
            transport=transport,
        )
        return True

    if host in _STDIO_WRAPPER_HOSTS and transport != "http":
        _apply_stdio_wrappers(
            merged,
            servers_key,
            host,
            project_root,
            uv_launch=uv_launch,
            use_nlt_plugin=use_nlt_plugin,
        )

    _write_merged_config(
        config_path,
        merged,
        host,
        use_nlt_plugin=use_nlt_plugin,
        nlt_enabled=nlt_enabled,
        nlt_commented=nlt_commented,
    )

    click.echo(click.style(f"Configuration written to {config_path}", fg="green"))
    if use_nlt_plugin:
        _echo_nlt_summary(mcp_bundle, nlt_enabled, nlt_commented)

    _warn_plaintext_secrets(config_path, merged, host, project_root, scope)

    _print_next_steps(host, project_root=project_root)
    return True
