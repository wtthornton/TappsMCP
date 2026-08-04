"""Doctor checks for the shared HTTP MCP fleet and transport drift (TAP-5606 split).

Covers fleet endpoint discovery, TCP + MCP-initialize liveness probes,
crash-loop detection (ADR-0024), and Cursor/yaml transport-drift detection.
Split out of ``doctor_mcp`` to keep both modules within the maintainability
budget.
"""

from __future__ import annotations

from pathlib import Path

from tapps_core.common.logging import get_logger
from tapps_mcp.distribution.doctor_result import CheckResult

log = get_logger(__name__)


def _iter_http_fleet_endpoints(project_root: Path) -> list[tuple[str, str, str]]:
    """Return ``(host_label, server_name, url)`` for HTTP fleet entries.

    Scans the host MCP configs for shared-fleet (ADR-0024) HTTP entries
    (``streamableHttp`` on Cursor, ``http`` on Claude Code / VS Code) so
    doctor can probe whether their ports are actually listening.
    """
    from tapps_mcp.distribution.nlt_http_fleet import HTTP_FLEET_ENTRY_TYPES
    from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

    sources = (
        (Path(".cursor") / "mcp.json", "mcpServers", "Cursor"),
        (Path(".vscode") / "mcp.json", "servers", "VS Code"),
        (Path(".mcp.json"), "mcpServers", "Claude Code"),
    )
    endpoints: list[tuple[str, str, str]] = []
    for rel, servers_key, label in sources:
        path = project_root / rel
        if not path.exists():
            continue
        data = _load_mcp_config_json(path)
        if not isinstance(data, dict):
            continue
        servers = data.get(servers_key, {})
        if not isinstance(servers, dict):
            continue
        for name, entry in servers.items():
            if not isinstance(entry, dict) or entry.get("type") not in HTTP_FLEET_ENTRY_TYPES:
                continue
            url = entry.get("url")
            if isinstance(url, str) and url.startswith("http"):
                endpoints.append((label, str(name), url))
    return endpoints


def _probe_tcp(url: str, *, timeout: float = 0.5) -> bool:
    """Return ``True`` when a TCP connection to *url*'s host:port succeeds."""
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_fleet_mcp_initialize_all(
    endpoints: list[tuple[str, str, str]], project_root: Path
) -> list[str]:
    """Run the MCP initialize handshake against each distinct fleet server.

    Returns a list of ``"server (error)"`` strings for servers that fail.
    """
    from tapps_mcp.distribution.fleet_smoke import probe_fleet_mcp_initialize

    seen: set[str] = set()
    init_fail: list[str] = []
    for _label, srv, _url in endpoints:
        if srv in seen:
            continue
        seen.add(srv)
        probe = probe_fleet_mcp_initialize(srv, project_root=project_root)
        if not probe.get("ok"):
            err = probe.get("error") or probe.get("stage") or "initialize failed"
            init_fail.append(f"{srv} ({err})")
    return init_fail


def check_http_fleet_liveness(project_root: Path) -> CheckResult:
    """Probe shared HTTP MCP fleet ports + MCP initialize (ADR-0024 / TAP-5158).

    ``check_*_config`` only validates the *shape* of a ``streamableHttp`` entry.
    When the fleet was never started (``tapps-mcp fleet start``), every host
    server fails with an opaque transport error and no remediation. This probes
    each configured fleet port so the failure surfaces with a fix.

    TCP alone is insufficient: a starved uvicorn loop still accepts connections
    while Cursor sticks on "Loading tools". After TCP passes, reuse
    :func:`probe_fleet_mcp_initialize` (same path as ``fleet ensure``).
    """
    name = "HTTP MCP fleet liveness"
    endpoints = _iter_http_fleet_endpoints(project_root)
    if not endpoints:
        return CheckResult(name, True, "No streamableHttp MCP entries (stdio transport)")
    down = [(srv, url) for _label, srv, url in endpoints if not _probe_tcp(url)]
    if down:
        preview = ", ".join(f"{srv} ({url})" for srv, url in down[:4])
        return CheckResult(
            name,
            False,
            f"{len(down)}/{len(endpoints)} fleet endpoint(s) not listening: {preview}",
            "Start the shared HTTP MCP fleet with `tapps-mcp fleet start` (ADR-0024), "
            "or switch this repo to stdio: set `mcp_transport: stdio` in "
            ".tapps-mcp.yaml and re-run `tapps-mcp upgrade --host cursor`.",
        )

    init_fail = _probe_fleet_mcp_initialize_all(endpoints, project_root)
    if init_fail:
        seen_count = len({srv for _label, srv, _url in endpoints})
        preview = ", ".join(init_fail[:4])
        return CheckResult(
            name,
            False,
            f"{len(init_fail)}/{seen_count} fleet endpoint(s) accept TCP but MCP "
            f"initialize failed: {preview}",
            "Restart the fleet: `tapps-mcp fleet restart` (or "
            "`systemctl --user restart tapps-mcp-fleet.service`). "
            "Event-loop starvation leaves ports open while /mcp hangs.",
        )
    return CheckResult(
        name,
        True,
        f"All {len(endpoints)} fleet endpoint(s) reachable (TCP + initialize)",
    )


def check_fleet_crash_loop() -> CheckResult:
    """Detect the ADR-0024 crash-loop: PID files recorded but ports not listening.

    ``check_http_fleet_liveness`` reports ports being down, but cannot tell
    "never started" apart from "starts then dies". When ``fleet start`` records
    PID files yet nothing is listening, a supervisor is reaping the fleet — the
    classic symptom of a ``Type=oneshot`` watchdog without ``RemainAfterExit``
    tearing down its cgroup. Surface that distinctly with a targeted fix.
    """
    name = "HTTP MCP fleet stability"
    from tapps_mcp.distribution.nlt_http_fleet import (
        FLEET_PID_DIR,
        NLT_HTTP_FLEET_PORTS,
        resolve_fleet_host,
    )

    recorded = [
        server_id
        for server_id in NLT_HTTP_FLEET_PORTS
        if (FLEET_PID_DIR / f"{server_id}.pid").is_file()
    ]
    if not recorded:
        return CheckResult(name, True, "No fleet PID files (not supervised on this host)")
    host = resolve_fleet_host()
    dead = [
        server_id
        for server_id in recorded
        if not _probe_tcp(f"http://{host}:{NLT_HTTP_FLEET_PORTS[server_id]}/")
    ]
    if not dead:
        return CheckResult(name, True, f"{len(recorded)} supervised fleet server(s) listening")
    preview = ", ".join(dead[:4])
    return CheckResult(
        name,
        False,
        f"{len(dead)}/{len(recorded)} supervised fleet server(s) have PID files but "
        f"are not listening (started-then-died): {preview}",
        "The fleet is likely being reaped by a misconfigured systemd watchdog "
        "(a Type=oneshot unit without RemainAfterExit reaps its cgroup on exit). "
        "Refresh units with `tapps-mcp fleet install-systemd`, then "
        "`systemctl --user daemon-reload && systemctl --user restart "
        "tapps-mcp-fleet.service`. Inspect ~/.tapps-mcp/fleet/logs/*.log.",
    )


def _cursor_config_transport(project_root: Path) -> str | None:
    """Return ``"http"``/``"stdio"`` for the Cursor MCP config, ``None`` if absent."""
    from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

    path = project_root / ".cursor" / "mcp.json"
    if not path.exists():
        return None
    data = _load_mcp_config_json(path)
    if not isinstance(data, dict):
        return None
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict) or not servers:
        return None
    has_http = any(
        isinstance(entry, dict) and entry.get("type") == "streamableHttp"
        for entry in servers.values()
    )
    return "http" if has_http else "stdio"


def _yaml_mcp_transport(project_root: Path) -> str | None:
    """Return ``mcp_transport`` from ``.tapps-mcp.yaml`` (``None`` when unset)."""
    import yaml

    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.is_file():
        return None
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        log.debug("yaml_mcp_transport_load_failed", exc_info=True)
        return None
    if isinstance(loaded, dict):
        value = loaded.get("mcp_transport")
        if isinstance(value, str):
            return value
    return None


def check_mcp_transport_drift(project_root: Path) -> CheckResult:
    """Flag when the Cursor MCP config transport disagrees with yaml ``mcp_transport``.

    ``mcp_transport`` (``.tapps-mcp.yaml``) is the source of truth that
    ``init``/``upgrade`` use to regenerate ``.cursor/mcp.json``. When the
    generated config is ``streamableHttp`` but the yaml key is unset (defaults
    stdio) — or vice versa — the next ``upgrade`` silently flips transport.
    """
    name = "MCP transport drift"
    config_transport = _cursor_config_transport(project_root)
    if config_transport is None:
        return CheckResult(name, True, "No Cursor MCP config to compare")
    yaml_transport = _yaml_mcp_transport(project_root)
    effective_yaml = yaml_transport or "stdio"
    if config_transport == effective_yaml:
        return CheckResult(
            name,
            True,
            f".cursor/mcp.json and .tapps-mcp.yaml agree (mcp_transport={config_transport})",
        )
    return CheckResult(
        name,
        False,
        (
            f".cursor/mcp.json is {config_transport} but .tapps-mcp.yaml "
            f"mcp_transport={yaml_transport or '<unset, defaults stdio>'}"
        ),
        "Reconcile transport so `upgrade` cannot silently flip it: run "
        f"`tapps-mcp init --host cursor --mcp-transport {config_transport} --force` "
        "to persist the yaml key, or regenerate the config to match yaml.",
    )
