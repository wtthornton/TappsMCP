"""Host-level shared HTTP MCP fleet (ADR-0024).

Six long-lived ``serve --transport http`` processes on fixed localhost ports.
Consumer ``.cursor/mcp.json`` entries use ``streamableHttp`` URLs plus
``X-Tapps-Project-Root`` so one fleet serves every Cursor window.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final, Literal

from tapps_core.http.request_context import PROJECT_ROOT_HEADER
from tapps_mcp.distribution.nlt_mcp_config import NLT_SERVER_ORDER, NLT_SERVER_SPECS

McpTransport = Literal["stdio", "http"]

DEFAULT_FLEET_HOST: Final[str] = "127.0.0.1"
DEFAULT_FLEET_CODE_ROOT_ENV: Final[str] = "TAPPS_FLEET_CODE_ROOT"
DEFAULT_FLEET_HOST_ENV: Final[str] = "TAPPS_FLEET_HOST"

# Fixed localhost ports — one per NLT profile (Epic 109 order).
NLT_HTTP_FLEET_PORTS: Final[dict[str, int]] = {
    "nlt-build": 8760,
    "nlt-memory": 8761,
    "nlt-setup": 8762,
    "nlt-linear-issues": 8763,
    "nlt-project-docs": 8764,
    "nlt-release-ship": 8765,
}

FLEET_PID_DIR: Final[Path] = Path.home() / ".tapps-mcp" / "fleet" / "pids"
FLEET_LOG_DIR: Final[Path] = Path.home() / ".tapps-mcp" / "fleet" / "logs"
FLEET_ENV_FILE: Final[Path] = Path.home() / ".tapps-mcp" / "fleet.env"


def read_fleet_supervised_pids() -> set[int]:
    """Return PIDs recorded by ``fleet start`` (ADR-0024 HTTP fleet)."""
    pids: set[int] = set()
    if not FLEET_PID_DIR.is_dir():
        return pids
    for pid_file in FLEET_PID_DIR.glob("*.pid"):
        try:
            pids.add(int(pid_file.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            continue
    return pids


def is_fleet_http_serve_command(cmd: str) -> bool:
    """True when *cmd* is a shared HTTP fleet ``serve`` (must not be reaped)."""
    return "--transport http" in cmd or "--transport=http" in cmd


def default_fleet_code_root() -> Path:
    """Prefer ``~/code`` when present; else home."""
    code = Path.home() / "code"
    if code.is_dir():
        return code.resolve()
    return Path.home().resolve()


def resolve_fleet_host() -> str:
    return os.environ.get(DEFAULT_FLEET_HOST_ENV, DEFAULT_FLEET_HOST).strip() or DEFAULT_FLEET_HOST


def resolve_fleet_code_root() -> Path:
    raw = os.environ.get(DEFAULT_FLEET_CODE_ROOT_ENV, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return default_fleet_code_root()


def build_http_fleet_url(server_id: str, *, fleet_host: str | None = None) -> str:
    """Return Streamable HTTP MCP endpoint for *server_id*."""
    canonical = server_id
    if canonical not in NLT_HTTP_FLEET_PORTS:
        msg = f"Unknown NLT server for HTTP fleet: {server_id}"
        raise KeyError(msg)
    host = fleet_host or resolve_fleet_host()
    port = NLT_HTTP_FLEET_PORTS[canonical]
    return f"http://{host}:{port}/mcp"


def resolve_mcp_transport(
    project_root: Path | None,
    *,
    explicit: str | None = None,
) -> McpTransport:
    """Resolve stdio vs http from CLI flag, yaml, or default stdio."""
    if explicit in ("stdio", "http"):
        return explicit  # type: ignore[return-value]
    if project_root is not None:
        try:
            from tapps_core.config.settings import load_settings

            settings = load_settings(project_root=project_root)
            transport = getattr(settings, "mcp_transport", "stdio")
            if transport in ("stdio", "http"):
                return transport  # type: ignore[return-value]
        except Exception:
            pass
    return "stdio"


def resolve_http_project_root_header(project_root: Path | None) -> str:
    """Absolute path for ``X-Tapps-Project-Root`` (never ``.`` or placeholders)."""
    if project_root is None:
        return str(Path.cwd().resolve())
    resolved = project_root.resolve()
    return str(resolved)


def http_entry_type_for_host(host: str) -> str:
    """MCP entry ``type`` string for an HTTP fleet server on *host*.

    Cursor names the Streamable HTTP transport ``streamableHttp``; Claude Code
    and VS Code name it ``http`` and *reject* ``streamableHttp`` entries
    outright ("unknown MCP server type"), silently dropping the server.
    """
    if host in ("claude-code", "vscode"):
        return "http"
    return "streamableHttp"


HTTP_FLEET_ENTRY_TYPES: Final[frozenset[str]] = frozenset({"streamableHttp", "http"})


def build_nlt_http_mcp_entry(
    server_id: str,
    *,
    project_root: Path | None = None,
    fleet_host: str | None = None,
    host: str = "cursor",
) -> dict[str, Any]:
    """Build one HTTP fleet MCP config entry for *server_id* on *host*."""
    return {
        "type": http_entry_type_for_host(host),
        "url": build_http_fleet_url(server_id, fleet_host=fleet_host),
        "headers": {
            PROJECT_ROOT_HEADER: resolve_http_project_root_header(project_root),
        },
    }


def is_valid_http_fleet_mcp_entry(entry: dict[str, Any]) -> bool:
    """Return True when *entry* is a valid shared-fleet HTTP block."""
    if entry.get("type") not in HTTP_FLEET_ENTRY_TYPES:
        return False
    url = entry.get("url")
    if not isinstance(url, str) or not url.startswith("http"):
        return False
    headers = entry.get("headers")
    if not isinstance(headers, dict):
        return False
    root = headers.get(PROJECT_ROOT_HEADER)
    return isinstance(root, str) and bool(root.strip()) and "${" not in root


def fleet_server_launch_specs() -> list[tuple[str, str, list[str], int]]:
    """Return ``(server_id, command, args, port)`` tuples for the fleet script."""
    from tapps_mcp.distribution.blue_green import CURRENT_LINK

    rows: list[tuple[str, str, list[str], int]] = []
    for server_id in NLT_SERVER_ORDER:
        spec = NLT_SERVER_SPECS[server_id]
        serve_cmd = str(spec["serve_command"])
        serve_args = [str(a) for a in spec["serve_args"]]
        port = NLT_HTTP_FLEET_PORTS[server_id]
        bin_path = CURRENT_LINK / "bin" / serve_cmd
        command = str(bin_path) if bin_path.is_file() else serve_cmd
        rows.append((server_id, command, serve_args, port))
    return rows


def sample_fleet_env_content() -> str:
    """Default ``~/.tapps-mcp/fleet.env`` contents."""
    root = default_fleet_code_root()
    lines = [
        "# TappsMCP shared HTTP fleet (ADR-0024)",
        "# Source operator secrets separately: ~/.tapps-operator.env",
        f"{DEFAULT_FLEET_CODE_ROOT_ENV}={root}",
        f"{DEFAULT_FLEET_HOST_ENV}={DEFAULT_FLEET_HOST}",
        "",
        "# Fleet processes inherit brain/context7 from ~/.tapps-operator.env",
        "# Per-project identity is sent by Cursor via X-Tapps-Project-Root header.",
        "",
    ]
    for server_id, port in NLT_HTTP_FLEET_PORTS.items():
        lines.append(f"# {server_id}: http://{DEFAULT_FLEET_HOST}:{port}/mcp")
    lines.append("")
    return "\n".join(lines)
