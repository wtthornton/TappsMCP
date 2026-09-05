"""``.mcp.json`` refresh for a single host during upgrade.

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913).

The host's MCP config is the one artifact whose upgrade is a *decision tree*
rather than a regeneration: heal a broken ``${workspaceFolder}`` env, migrate a
legacy monolith entry to the NLT servers, sync a named bundle, preserve a custom
set, or leave a healthy file alone. TAP-6913 splits that tree into a pure
decision (:func:`_decide`) and a single write step, so the dry-run preview and
the live run are guaranteed to be reading the same plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.distribution.nlt_mcp_config import DEFAULT_NLT_BUNDLE
from tapps_mcp.pipeline.upgrade_signals import mcp_json_has_tapps_entry

log = get_logger(__name__)


@dataclass(frozen=True)
class _McpConfigDecision:
    """What the upgrade intends to do to one host's MCP config.

    ``bundle is None`` means the file is already in its target state (or is
    deliberately left alone), so dry-run and live report the same value.
    Otherwise ``bundle`` is the NLT bundle a live run regenerates with;
    ``dry_value`` is the preview text and ``live_value`` the post-write status.
    """

    dry_value: Any
    live_value: Any
    bundle: str | None = None


def _terminal(value: Any) -> _McpConfigDecision:
    """A decision with no write step — the same value in both modes."""
    return _McpConfigDecision(dry_value=value, live_value=value)


@dataclass(frozen=True)
class _McpConfigState:
    """On-disk facts about one host's MCP config, gathered once per upgrade."""

    config_path: Path
    include_docs_mcp: bool
    uv_launch: Any
    error: str | None
    already_opted_in: bool
    needs_heal: bool
    needs_nlt_migration: bool
    sync_bundle: bool
    normalized_bundle: str
    generate_bundle: str
    on_disk_bundle: str | None
    bundle_mismatch: bool


def mcp_json_has_unresolved_workspacefolder(project_root: Path, host: str) -> bool:
    """TAP-2199: return ``True`` when the on-disk ``.mcp.json`` still contains the
    broken literal ``${workspaceFolder}`` in the tapps-mcp or docs-mcp env block.

    Used by :func:`upgrade_mcp_config` to force a regenerate even when the
    file would otherwise pass ``_validate_config_file``. Without this,
    consumers who installed before the fix never get the env block rewritten.
    """
    import json as _json

    from tapps_mcp.distribution.setup_generator import _get_config_path, _get_servers_key

    config_path = _get_config_path(host, project_root)
    if not config_path.exists():
        return False
    try:
        data = _json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    servers = data.get(_get_servers_key(host))
    if not isinstance(servers, dict):
        return False
    return any(_entry_has_unresolved_env(entry) for entry in servers.values())


def _entry_has_unresolved_env(entry: Any) -> bool:
    """True when one server entry's project-root env var still holds a template."""
    if not isinstance(entry, dict):
        return False
    env = entry.get("env")
    if not isinstance(env, dict):
        return False
    for key in ("TAPPS_MCP_PROJECT_ROOT", "DOCS_MCP_PROJECT_ROOT"):
        value = env.get(key)
        if isinstance(value, str) and "${" in value:
            return True
    return False


def _gather_state(
    host: str,
    project_root: Path,
    *,
    mcp_bundle: str | None,
) -> _McpConfigState:
    """Read the on-disk config once and derive every flag the decision needs."""
    from tapps_mcp.distribution.nlt_mcp_config import (
        DEFAULT_NLT_BUNDLE,
        bundle_matches_mcp_config,
        match_bundle_for_servers,
        needs_legacy_nlt_migration,
        normalize_mcp_bundle,
    )
    from tapps_mcp.distribution.setup_generator import (
        _build_uv_run_tapps_launch,
        _get_config_path,
        _get_servers_key,
        _load_mcp_config_json,
        _should_include_docs_mcp,
        _should_use_uv_launch,
        _validate_config_file,
    )

    config_path = _get_config_path(host, project_root)
    servers_key = _get_servers_key(host)
    existing: dict[str, object] = {}
    if config_path.exists():
        parsed = _load_mcp_config_json(config_path)
        if isinstance(parsed, dict):
            existing = parsed
    include_docs_mcp = _should_include_docs_mcp(
        False,
        existing=existing,
        servers_key=servers_key,
    )
    use_uv, extra_auto, _ = _should_use_uv_launch(project_root, uv_mode=None)
    already_opted_in = mcp_json_has_tapps_entry(project_root)
    raw_servers = existing.get(servers_key)
    servers_dict = raw_servers if isinstance(raw_servers, dict) else {}
    # None = preserve custom on-disk set (do not sync / re-expand to full).
    sync_bundle = mcp_bundle is not None
    normalized_bundle = normalize_mcp_bundle(mcp_bundle) if sync_bundle else DEFAULT_NLT_BUNDLE
    # When preserving a custom set, only regenerate when on-disk matches a
    # named bundle (heal/migrate); never silently expand custom → full.
    on_disk_bundle = match_bundle_for_servers(servers_dict)
    return _McpConfigState(
        config_path=config_path,
        include_docs_mcp=include_docs_mcp,
        uv_launch=_build_uv_run_tapps_launch(extra_auto) if use_uv else None,
        error=_validate_config_file(config_path, servers_key),
        already_opted_in=already_opted_in,
        needs_heal=mcp_json_has_unresolved_workspacefolder(project_root, host),
        needs_nlt_migration=needs_legacy_nlt_migration(servers_dict),
        sync_bundle=sync_bundle,
        normalized_bundle=normalized_bundle,
        generate_bundle=normalized_bundle
        if sync_bundle
        else (on_disk_bundle or DEFAULT_NLT_BUNDLE),
        on_disk_bundle=on_disk_bundle,
        bundle_mismatch=(
            sync_bundle
            and already_opted_in
            and not bundle_matches_mcp_config(servers_dict, normalized_bundle)
        ),
    )


def _decide_opted_in(state: _McpConfigState, *, force: bool) -> _McpConfigDecision | None:
    """Decisions that apply only to a project already wired for TappsMCP.

    Returns ``None`` when none of them fires, so the caller falls through to
    the consent-gated branches.
    """
    if state.needs_heal:
        if not state.sync_bundle and state.on_disk_bundle is None:
            return _terminal(
                "needs-heal deferred: custom nlt-* set with ${workspaceFolder}; "
                "run: tapps-mcp mcp-bundle set <bundle> (or fix env paths manually)"
            )
        return _McpConfigDecision(
            dry_value=(
                "needs-heal: ${workspaceFolder} in env block "
                "(TAP-2199 — rerun without dry_run to fix)"
            ),
            live_value="healed: rewrote ${workspaceFolder} to absolute project root (TAP-2199)",
            bundle=state.generate_bundle,
        )
    if state.needs_nlt_migration and force:
        return _McpConfigDecision(
            dry_value="needs-migration: legacy tapps-mcp/docs-mcp → NLT nlt-* servers",
            live_value=(
                "migrated: legacy monolith → NLT plugin (nlt-code-quality + nlt-platform-admin)"
            ),
            bundle=state.generate_bundle,
        )
    if not state.sync_bundle:
        return _terminal(
            "ok (custom nlt-* set preserved; run: tapps-mcp mcp-bundle set <bundle> to sync)"
        )
    if state.bundle_mismatch:
        return _McpConfigDecision(
            dry_value=(
                f"needs-bundle-sync: enabled servers != mcp_bundle={state.normalized_bundle!r}"
            ),
            live_value=f"synced: rewrote MCP config for mcp_bundle={state.normalized_bundle!r}",
            bundle=state.normalized_bundle,
        )
    return None


def _decide(state: _McpConfigState, *, force: bool) -> _McpConfigDecision:
    """Pick the single action for this config — identical for dry-run and live."""
    if state.already_opted_in:
        decision = _decide_opted_in(state, force=force)
        if decision is not None:
            return decision
    if state.error is None:
        return _terminal("ok")
    if not state.already_opted_in and not force:
        return _terminal(
            {
                "action": "skipped (no existing tapps-mcp entry)",
                "hint": (
                    "Run `tapps_init` or pass force=True to create "
                    f"{state.config_path.name} with the tapps-mcp server entry."
                ),
            }
        )
    return _McpConfigDecision(
        dry_value=f"needs-fix: {state.error}",
        live_value="regenerated",
        bundle=state.generate_bundle,
    )


def upgrade_mcp_config(
    host: str,
    project_root: Path,
    result: dict[str, Any],
    *,
    force: bool,
    dry_run: bool,
    mcp_bundle: str | None = DEFAULT_NLT_BUNDLE,
) -> None:
    """Populate result["components"]["mcp_config"] for one host.

    The ``mcp_config`` skip token is handled by the caller before this
    function is invoked.

    Consent gate: only regenerates ``.mcp.json`` when the user has previously
    opted in (entry exists) or ``force=True``.  Missing entries are not
    treated as broken — greenfield projects should go through ``tapps_init``.

    When *mcp_bundle* is ``None``, a custom on-disk ``nlt-*`` set is preserved
    (no rewrite to ``full``). Use ``tapps-mcp mcp-bundle set <name>`` to opt in
    to a named bundle sync.

    TAP-2199: when the on-disk env block still contains the literal
    ``${workspaceFolder}`` we self-heal by forcing a regen regardless of
    ``_validate_config_file`` verdict. The merge in ``_generate_config``
    overlays the new (absolute) env values over the broken ones, so user
    customizations on other keys survive.
    """
    state = _gather_state(host, project_root, mcp_bundle=mcp_bundle)
    decision = _decide(state, force=force)

    if decision.bundle is None or dry_run:
        result["components"]["mcp_config"] = decision.dry_value if dry_run else decision.live_value
        return

    from tapps_mcp.distribution.setup_generator import _generate_config

    _generate_config(
        host,
        project_root,
        force=True,
        upgrade_mode=True,
        with_docs_mcp=state.include_docs_mcp,
        uv_launch=state.uv_launch,
        use_nlt_plugin=True,
        mcp_bundle=decision.bundle,
    )
    result["components"]["mcp_config"] = decision.live_value
