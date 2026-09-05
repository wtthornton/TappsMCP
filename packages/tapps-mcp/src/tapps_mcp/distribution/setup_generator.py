"""One-command setup generator for TappsMCP across MCP hosts.

Generates MCP configuration files for Claude Code, Cursor, and VS Code,
with auto-detection of installed hosts and config merging.

This module is the ``init``/``upgrade`` entry point and the stable import
surface for the whole setup subsystem. The implementation lives in focused
siblings (TAP-5733), all re-exported here so existing
``from tapps_mcp.distribution.setup_generator import X`` call sites keep working:

- :mod:`~tapps_mcp.distribution.setup_launch` — which binary to exec
- :mod:`~tapps_mcp.distribution.setup_config_io` — config paths, JSONC, validation
- :mod:`~tapps_mcp.distribution.setup_entries` — server entry building + merging
- :mod:`~tapps_mcp.distribution.setup_wrappers` — stdio wrapper scripts
- :mod:`~tapps_mcp.distribution.setup_secrets` — secret detection + gitignore
- :mod:`~tapps_mcp.distribution.setup_docs` — rules, hooks, agents, skills, core docs
- :mod:`~tapps_mcp.distribution.setup_config_gen` — write/merge one host config
- :mod:`~tapps_mcp.distribution.setup_upgrade_cli` — upgrade output + ``run_upgrade``
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import click

from tapps_core.common.logging import get_logger
from tapps_mcp.distribution.nlt_mcp_config import DEFAULT_NLT_BUNDLE
from tapps_mcp.distribution.setup_config_gen import _generate_config
from tapps_mcp.distribution.setup_config_io import (
    _check_config,
    _filter_hosts_for_check,
    _get_config_path,
    _get_servers_key,
    _host_config_exists,
    _is_valid_tapps_command,
    _load_mcp_config_json,
    _other_scope_config_path,
    _strip_jsonc_comments,
    _validate_config_file,
)
from tapps_mcp.distribution.setup_docs import (
    _echo_gen_result,
    _ensure_project_yaml_defaults,
    _generate_core_docs,
    _generate_rules,
    _preview_rules,
    _read_engagement_level_from_project,
    _write_engagement_level_to_yaml,
    _write_mcp_transport_to_yaml,
)
from tapps_mcp.distribution.setup_entries import (
    _BRAIN_AUTH_TOKEN_ENV_PLACEHOLDER,
    _DOCS_SERVER_INSTRUCTIONS,
    _SERVER_INSTRUCTIONS,
    _build_docsmcp_server_entry,
    _build_nlt_server_entry,
    _build_server_entry,
    _collect_legacy_tapps_env,
    _config_has_tapps_or_nlt,
    _derive_brain_project_id,
    _merge_config,
    _merge_docsmcp_entry,
    _merge_nlt_config,
    _resolve_project_root_value,
    _serialize_nlt_mcp_config,
)
from tapps_mcp.distribution.setup_guidance import (
    _print_context7_hint_if_missing,
    _print_next_steps,
    _verify_context7_live,
)
from tapps_mcp.distribution.setup_launch import (
    _TAPPS_MCP_UV_ROOT_PLACEHOLDER,
    _UV_AUTO_EXTRA_CANDIDATES,
    _adapt_uv_launch_for_nlt,
    _build_nlt_launch,
    _build_uv_run_tapps_launch,
    _detect_command_path,
    _detect_uv_context,
    _preserve_launch_on_upgrade,
    _resolve_dev_monorepo_launch,
    _resolve_docsmcp_launch,
    _resolve_global_cli,
    _resolve_tapps_mcp_launch,
    _resolve_tapps_mcp_monorepo_root,
    _should_include_docs_mcp,
    _should_use_uv_launch,
    is_tapps_mcp_dev_monorepo,
    is_tapps_mcp_package_layout,
)
from tapps_mcp.distribution.setup_secrets import (
    _NON_SECRET_ENV_KEYS,
    _SECRET_KEY_PATTERNS,
    _TAPPS_RUNTIME_GITIGNORE_COVERED_BY,
    _TAPPS_RUNTIME_GITIGNORE_ENTRIES,
    _collect_plaintext_secrets,
    _ensure_gitignore_entry,
    _load_existing_env_from_other_scope,
    _looks_like_secret_key,
    _value_is_plaintext_secret,
    _value_looks_like_filesystem_path,
    _warn_plaintext_secrets,
    ensure_tapps_runtime_gitignore,
)
from tapps_mcp.distribution.setup_upgrade_cli import _format_upgrade_result, run_upgrade
from tapps_mcp.distribution.setup_wrappers import (
    _CLAUDE_MCP_WRAPPER_REL,
    _CURSOR_MCP_WRAPPER_REL,
    _OPERATOR_ENV_REL,
    _STDIO_WRAPPER_HOSTS,
    _apply_cursor_launch_wrapper,
    _cursor_wrapper_rel,
    _mcp_config_has_stdio_entries,
    _nlt_profile_from_serve_args,
    _parse_cursor_wrapper_launch,
    _render_cursor_mcp_wrapper_script,
    _render_profile_stale_reap_bash,
    _resolve_wrapper_launch,
    _stdio_wrapper_rel,
    _write_cursor_mcp_wrapper,
    operator_env_path,
    regenerate_cursor_nlt_wrappers,
    regenerate_nlt_stdio_wrappers,
)

log = get_logger(__name__)

__all__ = [
    "_BRAIN_AUTH_TOKEN_ENV_PLACEHOLDER",
    "_CLAUDE_MCP_WRAPPER_REL",
    "_CURSOR_MCP_WRAPPER_REL",
    "_DOCS_SERVER_INSTRUCTIONS",
    "_NON_SECRET_ENV_KEYS",
    "_OPERATOR_ENV_REL",
    "_SECRET_KEY_PATTERNS",
    "_SERVER_INSTRUCTIONS",
    "_STDIO_WRAPPER_HOSTS",
    "_TAPPS_MCP_UV_ROOT_PLACEHOLDER",
    "_TAPPS_RUNTIME_GITIGNORE_COVERED_BY",
    "_TAPPS_RUNTIME_GITIGNORE_ENTRIES",
    "_UV_AUTO_EXTRA_CANDIDATES",
    "_adapt_uv_launch_for_nlt",
    "_apply_cursor_launch_wrapper",
    "_build_docsmcp_server_entry",
    "_build_nlt_launch",
    "_build_nlt_server_entry",
    "_build_server_entry",
    "_build_uv_run_tapps_launch",
    "_check_config",
    "_collect_legacy_tapps_env",
    "_collect_plaintext_secrets",
    "_config_has_tapps_or_nlt",
    "_configure_multiple_hosts",
    "_cursor_wrapper_rel",
    "_derive_brain_project_id",
    "_detect_command_path",
    "_detect_hosts",
    "_detect_uv_context",
    "_echo_gen_result",
    "_ensure_gitignore_entry",
    "_ensure_project_yaml_defaults",
    "_filter_hosts_for_check",
    "_format_upgrade_result",
    "_generate_config",
    "_generate_core_docs",
    "_generate_rules",
    "_get_config_path",
    "_get_cursor_settings_dir",
    "_get_servers_key",
    "_get_vscode_settings_dir",
    "_host_config_exists",
    "_is_valid_tapps_command",
    "_load_existing_env_from_other_scope",
    "_load_mcp_config_json",
    "_looks_like_secret_key",
    "_mcp_config_has_stdio_entries",
    "_merge_config",
    "_merge_docsmcp_entry",
    "_merge_nlt_config",
    "_nlt_profile_from_serve_args",
    "_other_scope_config_path",
    "_parse_cursor_wrapper_launch",
    "_preserve_launch_on_upgrade",
    "_preview_rules",
    "_print_context7_hint_if_missing",
    "_print_next_steps",
    "_read_engagement_level_from_project",
    "_render_cursor_mcp_wrapper_script",
    "_render_profile_stale_reap_bash",
    "_resolve_dev_monorepo_launch",
    "_resolve_docsmcp_launch",
    "_resolve_global_cli",
    "_resolve_project_root_value",
    "_resolve_tapps_mcp_launch",
    "_resolve_tapps_mcp_monorepo_root",
    "_resolve_wrapper_launch",
    "_serialize_nlt_mcp_config",
    "_should_include_docs_mcp",
    "_should_use_uv_launch",
    "_stdio_wrapper_rel",
    "_strip_jsonc_comments",
    "_validate_config_file",
    "_value_is_plaintext_secret",
    "_value_looks_like_filesystem_path",
    "_verify_context7_live",
    "_warn_plaintext_secrets",
    "_write_cursor_mcp_wrapper",
    "_write_engagement_level_to_yaml",
    "_write_mcp_transport_to_yaml",
    "ensure_tapps_runtime_gitignore",
    "is_tapps_mcp_dev_monorepo",
    "is_tapps_mcp_package_layout",
    "operator_env_path",
    "regenerate_cursor_nlt_wrappers",
    "regenerate_nlt_stdio_wrappers",
    "run_init",
    "run_upgrade",
]

# Env values that mean "yes" for TAPPS_MCP_ALLOW_PACKAGE_INIT.
_TRUTHY_ENV_VALUES = ("1", "true", "yes", "y", "on")


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
    mcp_bundle: str = DEFAULT_NLT_BUNDLE,
    use_nlt_plugin: bool = False,
    engagement_level: str | None = None,
    mcp_transport: str | None = None,
) -> bool:
    """Configure (or check) multiple hosts, reporting per-host results.

    Returns ``True`` if ALL hosts succeeded, ``False`` if any failed.
    """
    hosts_to_run = _filter_hosts_for_check(hosts, project_root, scope=scope) if check else hosts
    all_ok = True
    for host in hosts_to_run:
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
                mcp_bundle=mcp_bundle,
                use_nlt_plugin=use_nlt_plugin,
                mcp_transport=mcp_transport,
            )
            _generate_host_scaffolding(
                ok, host, project_root, rules=rules, dry_run=dry_run, level=engagement_level
            )
        all_ok = all_ok and ok
    if all_ok and not check and not dry_run:
        _ensure_project_yaml_defaults(project_root)
    return all_ok


def _strip_direct_brain_entries(root: Path) -> None:
    """Drop any direct tapps-brain MCP server entries — the bridge owns that link."""
    from tapps_mcp.distribution.doctor import strip_brain_mcp_entries

    stripped = strip_brain_mcp_entries(root)
    if stripped.get("stripped"):
        click.echo(
            click.style(
                "  Removed direct tapps-brain MCP server entries (bridge-only): "
                + ", ".join(stripped["stripped"]),
                fg="cyan",
            )
        )


def _refuses_package_layout_init(root: Path, *, allow_package_init: bool) -> bool:
    """Return True (and explain) when *root* is the tapps-mcp package dir itself."""
    allow_pkg = (
        allow_package_init
        or os.environ.get(
            "TAPPS_MCP_ALLOW_PACKAGE_INIT",
            "",
        )
        .strip()
        .lower()
        in _TRUTHY_ENV_VALUES
    )
    if allow_pkg or not is_tapps_mcp_package_layout(root):
        return False
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
    return True


def _resolve_init_launch(
    root: Path, *, uv_mode: str | None, uv_extra: str | None
) -> tuple[str, list[str]] | None:
    """Decide the launch form for generated entries (Issue #77) and report it."""
    use_uv, extra_auto, _uv_ctx = _should_use_uv_launch(root, uv_mode=uv_mode)
    if not use_uv:
        if shutil.which("tapps-mcp") is not None:
            click.echo(
                click.style(
                    "Global tapps-mcp detected — emitting 'tapps-mcp serve'",
                    fg="cyan",
                )
            )
        return None

    uv_launch = _build_uv_run_tapps_launch(uv_extra or extra_auto)
    if is_tapps_mcp_dev_monorepo(root):
        click.echo(
            click.style(
                "Dev monorepo — emitting uv run launch (Epic 116; avoids mutating fleet global CLI)",
                fg="cyan",
            )
        )
    click.echo(
        click.style(
            f"uv project detected — emitting '{' '.join([uv_launch[0], *uv_launch[1]])}'",
            fg="cyan",
        )
    )
    return uv_launch


def _resolve_context7_extra_env(
    context7_api_key: str | None,
    root: Path,
    *,
    dry_run: bool,
    check: bool,
) -> dict[str, str] | None:
    """Return the Context7 env block for the MCP config, probing the key when live.

    Issue #79: emit ``${TAPPS_MCP_CONTEXT7_API_KEY}`` interpolation so the literal
    key is never written to the config file.
    """
    from tapps_core.knowledge.brain_docs import docs_via_brain_enabled

    if not context7_api_key or docs_via_brain_enabled():
        return None
    click.echo(
        click.style(
            "  Context7 configured — using ${TAPPS_MCP_CONTEXT7_API_KEY} interpolation.",
            fg="cyan",
        )
    )
    click.echo(
        f"  Add to your shell profile:  export TAPPS_MCP_CONTEXT7_API_KEY='{context7_api_key}'"
    )
    if not dry_run and not check:
        _verify_context7_live(root, api_key_override=context7_api_key)
    return {"TAPPS_MCP_CONTEXT7_API_KEY": "${TAPPS_MCP_CONTEXT7_API_KEY}"}


def _generate_host_scaffolding(
    ok: bool,
    host: str,
    project_root: Path,
    *,
    rules: bool,
    dry_run: bool,
    level: str | None,
    overwrite_tech_stack: bool = False,
) -> None:
    """Write (or preview) the rules/hooks/agents/skills that accompany a host config."""
    if not ok or not rules:
        return
    if dry_run:
        _preview_rules(host)
    else:
        _generate_rules(
            host,
            project_root,
            engagement_level=level,
            overwrite_tech_stack=overwrite_tech_stack,
        )


def _maybe_enable_docs_mcp(with_docs_mcp: bool) -> bool:
    """Turn on the docs-mcp entry when ``docsmcp`` is installed globally."""
    if with_docs_mcp or not _should_include_docs_mcp(False):
        return with_docs_mcp
    click.echo(
        click.style(
            "Global docsmcp detected — including docs-mcp server entry",
            fg="cyan",
        )
    )
    return True


def _report_no_hosts_detected() -> None:
    """Explain that auto-detection found no MCP host to configure."""
    click.echo(
        click.style(
            "No MCP hosts detected. Please specify one with --host.",
            fg="yellow",
        )
    )
    click.echo("  Supported hosts: claude-code, cursor, vscode")


def _persist_transport_choice(root: Path, mcp_transport: str | None) -> None:
    """Keep ``.tapps-mcp.yaml`` and the generated host config on the same transport."""
    from tapps_mcp.distribution.nlt_http_fleet import resolve_mcp_transport

    effective_transport = resolve_mcp_transport(root, explicit=mcp_transport)
    # Persist whenever transport is explicit or resolves to http so the
    # generated host config and .tapps-mcp.yaml never drift — a plain
    # `upgrade` must not silently flip an http repo back to stdio.
    if mcp_transport is not None or effective_transport == "http":
        _write_mcp_transport_to_yaml(root, effective_transport)
    if effective_transport == "http":
        from tapps_mcp.distribution.fleet_control import ensure_fleet_env_file

        ensure_fleet_env_file()


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
    mcp_bundle: str = DEFAULT_NLT_BUNDLE,
    use_nlt_plugin: bool = True,
    mcp_transport: str | None = None,
) -> bool:
    """Run the init command logic.

    Args:
        mcp_host: Target host or ``"auto"`` for detection.
        project_root: Project root directory as a string path.
        check: If ``True``, verify existing configuration instead of generating.
        force: If ``True``, skip overwrite confirmation prompts.
        scope: ``"project"`` for project-scope ``.mcp.json`` (default) or
            ``"user"`` for user-scope config. Only affects ``claude-code`` host.
        rules: If ``True``, also generate platform rule files (CLAUDE.md or
            .cursor/rules/tapps-pipeline.mdc) alongside MCP config.
        dry_run: If ``True``, show what would be written without making changes.
        engagement_level: When set (high/medium/low), write to .tapps-mcp.yaml and
            use for platform rules. When ``None``, rules use medium or existing config.
        allow_package_init: Allow init when ``project_root`` is ``.../packages/tapps-mcp``.
        with_docs_mcp: Legacy monolith — also register docs-mcp (ignored when NLT plugin is on).
        mcp_bundle: NLT bundle (``developer``, ``minimal``, ``planning``, ``docs``, ``release``).
        use_nlt_plugin: Write NLT ``nlt-*`` servers (default). Set ``False`` for legacy monolith.
        context7_api_key: When set, write ``TAPPS_MCP_CONTEXT7_API_KEY`` into the
            MCP env block using ``${TAPPS_MCP_CONTEXT7_API_KEY}`` interpolation and
            print an export reminder (Issue #79).
    """
    root = Path(project_root).resolve()
    live_run = not check and not dry_run

    if live_run:
        _strip_direct_brain_entries(root)

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

    if not check and _refuses_package_layout_init(root, allow_package_init=allow_package_init):
        return False

    uv_launch = _resolve_init_launch(root, uv_mode=uv_mode, uv_extra=uv_extra)
    with_docs_mcp = _maybe_enable_docs_mcp(with_docs_mcp)
    extra_env = _resolve_context7_extra_env(context7_api_key, root, dry_run=dry_run, check=check)

    if live_run:
        if engagement_level is not None:
            _write_engagement_level_to_yaml(root, engagement_level)
        _persist_transport_choice(root, mcp_transport)

    if mcp_host == "auto":
        hosts = _detect_hosts()
        if not hosts:
            _report_no_hosts_detected()
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
            mcp_bundle=mcp_bundle,
            use_nlt_plugin=use_nlt_plugin,
            engagement_level=engagement_level,
            mcp_transport=mcp_transport,
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
        mcp_bundle=mcp_bundle,
        use_nlt_plugin=use_nlt_plugin,
        mcp_transport=mcp_transport,
    )
    _generate_host_scaffolding(
        ok,
        mcp_host,
        root,
        rules=rules,
        dry_run=dry_run,
        level=engagement_level,
        overwrite_tech_stack=overwrite_tech_stack,
    )
    if ok and not dry_run:
        _ensure_project_yaml_defaults(root)
    return ok
