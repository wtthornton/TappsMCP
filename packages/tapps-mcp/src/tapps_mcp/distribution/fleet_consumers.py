"""Audit and repair HTTP fleet consumer MCP configs (ADR-0024).

Walks sibling checkouts under a scan parent (default ``~/code``) and verifies
that Cursor / VS Code / Claude Code MCP entries point at the shared localhost
fleet with the correct ``X-Tapps-Project-Root``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

from tapps_core.http.request_context import PROJECT_ROOT_HEADER
from tapps_mcp.distribution.nlt_http_fleet import (
    NLT_HTTP_FLEET_PORTS,
    build_nlt_http_mcp_entry,
    http_entry_type_for_host,
)
from tapps_mcp.distribution.nlt_mcp_config import (
    NLT_BUNDLES,
    NLT_SERVER_ORDER,
    normalize_mcp_bundle,
)

DEFAULT_SCAN_PARENT: Final[Path] = Path.home() / "code"

# Scratch / archive trees — skip unless explicitly listed via --roots.
DEFAULT_SKIP_NAMES: Final[frozenset[str]] = frozenset(
    {
        "_archive-nlt-engine-stale-clone-2026-05-04",
        "AgentForge-verify4595",
        "NLTlabsPE-main",
        "NLTlabsPE-mainrun",
        "nlt-engine-tap-4851-s2",
    }
)

# Non-fleet MCP servers commonly co-located with nlt-* (not treated as errors).
INTENTIONAL_EXTRA_SERVERS: Final[frozenset[str]] = frozenset(
    {
        "agentforge",
        "firecrawl",
        "github",
        "context7",
        "exa",
        "memory",
        "playwright",
        "sequential-thinking",
    }
)

_HTTP_TYPES: Final[frozenset[str]] = frozenset({"http", "streamableHttp"})

_HOST_SPECS: Final[tuple[tuple[str, str, str], ...]] = (
    # (label, relative path, json key)
    ("cursor", ".cursor/mcp.json", "mcpServers"),
    ("vscode", ".vscode/mcp.json", "servers"),
    ("claude", ".mcp.json", "mcpServers"),
)


def _yaml_scalar(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(rf"^{re.escape(key)}:\s*(\S+)", text, flags=re.MULTILINE)
    return match.group(1) if match else None


def _stamp_version(path: Path, marker: str) -> str | None:
    if not path.is_file():
        return None
    head = path.read_text(encoding="utf-8", errors="replace")[:240]
    match = re.search(rf"{re.escape(marker)}:\s*([0-9.]+)", head)
    return match.group(1) if match else None


def _load_servers(path: Path, key: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"__parse_error__": str(exc)}
    if not isinstance(data, dict):
        return {"__parse_error__": "root must be an object"}
    servers = data.get(key)
    if servers is None and key == "servers" and isinstance(data.get("mcpServers"), dict):
        # Common drift: VS Code file written with Claude/Cursor key.
        return dict(data["mcpServers"])
    if not isinstance(servers, dict):
        return {"__parse_error__": f"missing '{key}' object"}
    return dict(servers)


def _package_version() -> str:
    try:
        from tapps_mcp import __version__

        return str(__version__)
    except Exception:
        return ""


def _enabled_servers(project_root: Path) -> tuple[str, ...]:
    bundle_raw = _yaml_scalar(project_root / ".tapps-mcp.yaml", "mcp_bundle")
    bundle = normalize_mcp_bundle(bundle_raw)
    return tuple(NLT_BUNDLES.get(bundle, NLT_SERVER_ORDER))


def _cursor_uses_http_fleet(project_root: Path) -> bool:
    servers = _load_servers(project_root / ".cursor" / "mcp.json", "mcpServers")
    if not servers or "__parse_error__" in servers:
        return False
    return any(
        server_id in NLT_HTTP_FLEET_PORTS
        and isinstance(entry, dict)
        and entry.get("type") in _HTTP_TYPES
        for server_id, entry in servers.items()
    )


def discover_http_fleet_consumers(
    *,
    scan_parent: Path | None = None,
    roots: list[Path] | None = None,
    skip_names: frozenset[str] = DEFAULT_SKIP_NAMES,
) -> list[Path]:
    """Return project roots that consume (or declare) the shared HTTP fleet."""
    found: list[Path] = []
    if roots:
        candidates = [p.expanduser().resolve() for p in roots]
    else:
        parent = (scan_parent or DEFAULT_SCAN_PARENT).expanduser().resolve()
        if not parent.is_dir():
            return []
        candidates = sorted(p for p in parent.iterdir() if p.is_dir() and p.name not in skip_names)

    for root in candidates:
        if not root.is_dir():
            continue
        yaml_path = root / ".tapps-mcp.yaml"
        transport = _yaml_scalar(yaml_path, "mcp_transport")
        if transport == "http" or _cursor_uses_http_fleet(root):
            found.append(root.resolve())
    return found


def audit_consumer(project_root: Path, *, package_version: str | None = None) -> dict[str, Any]:
    """Audit one consumer project's MCP fleet wiring."""
    root = project_root.resolve()
    pkg = package_version or _package_version()
    transport = _yaml_scalar(root / ".tapps-mcp.yaml", "mcp_transport")
    enabled = _enabled_servers(root)
    issues: list[str] = []

    if transport != "http":
        issues.append(f"yaml mcp_transport={transport!r} (want 'http')")

    for label, rel, key in _HOST_SPECS:
        path = root / rel
        want_type = http_entry_type_for_host("cursor" if label == "cursor" else "claude-code")
        # VS Code shares Claude's ``http`` type name.
        if label == "vscode":
            want_type = "http"
        servers = _load_servers(path, key)
        if servers is None:
            if label == "cursor":
                issues.append("missing .cursor/mcp.json")
            continue
        if "__parse_error__" in servers:
            issues.append(f"{label}: {servers['__parse_error__']}")
            continue

        for server_id in enabled:
            if server_id not in servers:
                issues.append(f"{label}: missing {server_id}")
                continue
            entry = servers[server_id]
            if not isinstance(entry, dict):
                issues.append(f"{label}: {server_id} is not an object")
                continue
            typ = entry.get("type")
            if typ not in _HTTP_TYPES:
                issues.append(f"{label}: {server_id} type={typ!r}")
                continue
            if typ != want_type:
                issues.append(f"{label}: {server_id} type={typ!r} prefer={want_type!r}")
            want_url = f"http://127.0.0.1:{NLT_HTTP_FLEET_PORTS[server_id]}/mcp"
            if entry.get("url") != want_url:
                issues.append(f"{label}: {server_id} url={entry.get('url')!r}")
            raw_headers = entry.get("headers")
            headers = raw_headers if isinstance(raw_headers, dict) else {}
            root_hdr = headers.get(PROJECT_ROOT_HEADER)
            if root_hdr != str(root):
                issues.append(
                    f"{label}: {server_id} {PROJECT_ROOT_HEADER}={root_hdr!r} want={str(root)!r}"
                )

        for server_id in servers:
            if server_id in NLT_HTTP_FLEET_PORTS or server_id in INTENTIONAL_EXTRA_SERVERS:
                continue
            issues.append(f"{label}: unexpected extra server {server_id!r}")

        # VS Code must use the ``servers`` key (not ``mcpServers``).
        if label == "vscode" and path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {}
            if isinstance(raw, dict) and "mcpServers" in raw and "servers" not in raw:
                issues.append("vscode: uses mcpServers key (want servers)")

    agents_v = _stamp_version(root / "AGENTS.md", "tapps-agents-version")
    claude_v = _stamp_version(root / "CLAUDE.md", "tapps-claude-version")
    if pkg and agents_v and agents_v != pkg:
        issues.append(f"AGENTS.md stamp {agents_v} != {pkg}")
    # Respect upgrade_skip_files: CLAUDE.md opt-outs are not failures.
    skip_files = _yaml_listish(root / ".tapps-mcp.yaml", "upgrade_skip_files")
    if pkg and claude_v and claude_v != pkg and "CLAUDE.md" not in skip_files:
        issues.append(f"CLAUDE.md stamp {claude_v} != {pkg}")

    return {
        "project": root.name,
        "root": str(root),
        "transport": transport,
        "enabled_servers": list(enabled),
        "ok": not issues,
        "issues": issues,
    }


def _yaml_listish(path: Path, key: str) -> set[str]:
    """Best-effort extract of a simple YAML list under *key*."""
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        rf"^{re.escape(key)}:\s*\n((?:[ \t]+-[ \t]*.+\n?)+)",
        text,
        flags=re.MULTILINE,
    )
    if not match:
        return set()
    values: set[str] = set()
    for line in match.group(1).splitlines():
        item = re.sub(r"^\s*-\s*", "", line).strip().strip("'\"")
        if item:
            values.add(item)
    return values


def audit_consumers(
    *,
    scan_parent: Path | None = None,
    roots: list[Path] | None = None,
    skip_names: frozenset[str] = DEFAULT_SKIP_NAMES,
) -> dict[str, Any]:
    """Audit all discovered HTTP fleet consumers."""
    pkg = _package_version()
    projects = [
        audit_consumer(root, package_version=pkg)
        for root in discover_http_fleet_consumers(
            scan_parent=scan_parent, roots=roots, skip_names=skip_names
        )
    ]
    failed = [p for p in projects if not p["ok"]]
    return {
        "package_version": pkg,
        "total": len(projects),
        "ok": len(projects) - len(failed),
        "fail": len(failed),
        "projects": projects,
    }


def _ensure_yaml_transport(path: Path) -> bool:
    if not path.is_file():
        path.write_text("mcp_transport: http\n", encoding="utf-8")
        return True
    text = path.read_text(encoding="utf-8")
    if re.search(r"^mcp_transport:\s*", text, flags=re.MULTILINE):
        new = re.sub(
            r"^mcp_transport:\s*\S+",
            "mcp_transport: http",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if new != text:
            path.write_text(new, encoding="utf-8")
            return True
        return False
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + "mcp_transport: http\n", encoding="utf-8")
    return True


def _repair_mcp_json(
    path: Path,
    *,
    project_root: Path,
    host: str,
    json_key: str,
    enabled: tuple[str, ...],
) -> bool:
    """Rewrite nlt-* entries to HTTP fleet; preserve non-nlt servers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}

    # Normalize VS Code key drift.
    if host == "vscode" and "mcpServers" in data and "servers" not in data:
        data["servers"] = data.pop("mcpServers")

    servers = data.setdefault(json_key, {})
    if not isinstance(servers, dict):
        servers = {}
        data[json_key] = servers

    changed = False
    for server_id in enabled:
        want = build_nlt_http_mcp_entry(server_id, project_root=project_root, host=host)
        cur = servers.get(server_id)
        if isinstance(cur, dict) and "instructions" in cur:
            want = {**want, "instructions": cur["instructions"]}
        if cur != want:
            servers[server_id] = want
            changed = True

    for server_id, entry in list(servers.items()):
        if server_id not in NLT_HTTP_FLEET_PORTS or not isinstance(entry, dict):
            continue
        if entry.get("type") not in _HTTP_TYPES and server_id not in enabled:
            continue
        if server_id in enabled:
            continue  # already rewritten above
        # Fix root/url/type on leftover nlt entries outside the active bundle.
        want = build_nlt_http_mcp_entry(server_id, project_root=project_root, host=host)
        if isinstance(entry.get("instructions"), str):
            want = {**want, "instructions": entry["instructions"]}
        if entry != want:
            servers[server_id] = want
            changed = True

    if host == "vscode" and "mcpServers" in data:
        data.pop("mcpServers", None)
        changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def repair_consumer(project_root: Path) -> dict[str, Any]:
    """Repair one consumer's YAML + Cursor/VS Code/Claude MCP fleet wiring."""
    root = project_root.resolve()
    enabled = _enabled_servers(root)
    changes: list[str] = []
    if _ensure_yaml_transport(root / ".tapps-mcp.yaml"):
        changes.append("yaml")
    for label, rel, key in _HOST_SPECS:
        host = "cursor" if label == "cursor" else ("vscode" if label == "vscode" else "claude-code")
        path = root / rel
        if label != "cursor" and not path.is_file() and not path.parent.is_dir():
            continue
        if _repair_mcp_json(
            path,
            project_root=root,
            host=host,
            json_key=key,
            enabled=enabled,
        ):
            changes.append(label)
    return {"project": root.name, "root": str(root), "changes": changes}


def repair_consumers(
    *,
    scan_parent: Path | None = None,
    roots: list[Path] | None = None,
    skip_names: frozenset[str] = DEFAULT_SKIP_NAMES,
) -> dict[str, Any]:
    """Repair all discovered HTTP fleet consumers."""
    repaired: list[dict[str, Any]] = []
    unchanged: list[str] = []
    for root in discover_http_fleet_consumers(
        scan_parent=scan_parent, roots=roots, skip_names=skip_names
    ):
        result = repair_consumer(root)
        if result["changes"]:
            repaired.append(result)
        else:
            unchanged.append(root.name)
    return {
        "repaired": repaired,
        "unchanged": unchanged,
        "repaired_count": len(repaired),
        "unchanged_count": len(unchanged),
    }


__all__ = [
    "DEFAULT_SCAN_PARENT",
    "DEFAULT_SKIP_NAMES",
    "audit_consumer",
    "audit_consumers",
    "discover_http_fleet_consumers",
    "repair_consumer",
    "repair_consumers",
]
