"""CLI helpers for ``tapps-mcp mcp-bundle show|set``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_mcp.distribution.nlt_mcp_config import (
    NLT_BUNDLES,
    _load_enabled_mcp_servers,
    enabled_servers_for_bundle,
    list_nlt_server_ids_in_config,
    match_bundle_for_servers,
    normalize_mcp_bundle,
    persist_mcp_bundle_yaml,
)


def read_yaml_mcp_bundle(project_root: Path) -> str | None:
    """Return ``mcp_bundle`` from ``.tapps-mcp.yaml``, or None if unset."""
    import yaml

    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return None
    try:
        raw = config_path.read_text(encoding="utf-8-sig")
        data = yaml.safe_load(raw) if raw.strip() else {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("mcp_bundle")
    return value if isinstance(value, str) else None


def show_mcp_bundle(project_root: Path) -> dict[str, Any]:
    """Collect yaml + on-disk NLT server status for ``mcp-bundle show``."""
    yaml_bundle = read_yaml_mcp_bundle(project_root)
    servers = _load_enabled_mcp_servers(project_root)
    enabled = list_nlt_server_ids_in_config(servers)
    matched = match_bundle_for_servers(servers)
    return {
        "project_root": str(project_root),
        "yaml_mcp_bundle": yaml_bundle,
        "on_disk_servers": enabled,
        "on_disk_matches_bundle": matched,
        "resolved": (
            normalize_mcp_bundle(yaml_bundle)
            if yaml_bundle is not None
            else (matched or "custom" if enabled else "full")
        ),
    }


def set_mcp_bundle(
    project_root: Path,
    bundle: str,
    *,
    hosts: tuple[str, ...] = ("claude-code", "cursor", "vscode"),
    dry_run: bool = False,
) -> dict[str, Any]:
    """Persist ``mcp_bundle`` and rewrite host MCP configs to that set."""
    from tapps_mcp.distribution.setup_generator import (
        _build_uv_run_tapps_launch,
        _generate_config,
        _get_config_path,
        _should_use_uv_launch,
    )

    if bundle not in NLT_BUNDLES:
        msg = f"Unknown bundle {bundle!r}; expected one of {sorted(NLT_BUNDLES)}"
        raise ValueError(msg)
    normalized = normalize_mcp_bundle(bundle)

    enabled = list(enabled_servers_for_bundle(normalized))
    result: dict[str, Any] = {
        "bundle": normalized,
        "enabled_servers": enabled,
        "yaml_written": False,
        "hosts_updated": [],
        "hosts_skipped": [],
        "dry_run": dry_run,
        "reload_hint": "Reload MCP servers in your IDE (Cursor / Claude Code / VS Code).",
    }

    if dry_run:
        result["yaml_would_write"] = True
        for host in hosts:
            path = _get_config_path(host, project_root)
            if path.exists() or host in {"claude-code", "cursor"}:
                result["hosts_updated"].append(host)
            else:
                result["hosts_skipped"].append(host)
        return result

    persist_mcp_bundle_yaml(project_root, normalized)
    result["yaml_written"] = True

    use_uv, extra_auto, _ = _should_use_uv_launch(project_root, uv_mode=None)
    uv_launch = _build_uv_run_tapps_launch(extra_auto) if use_uv else None

    for host in hosts:
        path = _get_config_path(host, project_root)
        # Always refresh cursor + claude-code; vscode only when already present.
        if host == "vscode" and not path.exists():
            result["hosts_skipped"].append(host)
            continue
        ok = _generate_config(
            host,
            project_root,
            force=True,
            upgrade_mode=path.exists(),
            with_docs_mcp=False,
            uv_launch=uv_launch,
            use_nlt_plugin=True,
            mcp_bundle=normalized,
        )
        if ok:
            result["hosts_updated"].append(host)
        else:
            result["hosts_skipped"].append(host)

    return result


__all__ = [
    "read_yaml_mcp_bundle",
    "set_mcp_bundle",
    "show_mcp_bundle",
]
