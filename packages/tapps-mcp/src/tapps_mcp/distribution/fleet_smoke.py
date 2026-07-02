"""Streamable HTTP MCP smoke probes for the shared NLT fleet (ADR-0024).

TCP/port checks (``fleet status``, doctor liveness) only prove a process is
listening. Cursor clients need a full ``initialize`` + ``tools/list`` handshake
with the ``Accept: application/json, text/event-stream`` header — without that
probe, fleet restarts look healthy while every IDE session is dead.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tapps_core.http.request_context import PROJECT_ROOT_HEADER
from tapps_mcp.distribution.nlt_http_fleet import (
    NLT_HTTP_FLEET_PORTS,
    build_http_fleet_url,
    resolve_fleet_host,
    resolve_http_project_root_header,
)

_MCP_ACCEPT = "application/json, text/event-stream"
_INIT_PROTOCOL = "2025-03-26"


def parse_sse_json(body: str) -> dict[str, Any] | None:
    """Return the first JSON object from an SSE ``data:`` line."""
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                parsed = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def _post_mcp(
    url: str,
    payload: dict[str, Any],
    *,
    project_root: str,
    session_id: str | None = None,
    timeout: float = 15.0,
) -> tuple[int, str | None, str]:
    if not url.startswith("http://127.0.0.1:") and not url.startswith(
        f"http://{resolve_fleet_host()}:"
    ):
        msg = f"refusing non-local fleet URL: {url}"
        raise ValueError(msg)

    headers = {
        "Content-Type": "application/json",
        "Accept": _MCP_ACCEPT,
        PROJECT_ROOT_HEADER: project_root,
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    req = urllib.request.Request(  # noqa: S310 — URL validated localhost-only above
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.headers.get("mcp-session-id"), resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("mcp-session-id"), exc.read().decode()
    except OSError as exc:
        # Connection refused / reset / timeout (URLError is an OSError). A
        # just-restarted fleet server that has not bound its port yet must
        # surface as a failed probe stage, not crash the whole deploy.
        return 0, None, f"connection failed: {exc}"


def probe_fleet_mcp_session(
    server_id: str,
    *,
    project_root: Path | None = None,
    fleet_host: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Run initialize + initialized + tools/list against one fleet server."""
    if server_id not in NLT_HTTP_FLEET_PORTS:
        return {"ok": False, "server_id": server_id, "error": f"unknown server: {server_id}"}

    root_header = resolve_http_project_root_header(project_root)
    url = build_http_fleet_url(server_id, fleet_host=fleet_host)

    status, session_id, body = _post_mcp(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": _INIT_PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "tapps-mcp-fleet-smoke", "version": "1"},
            },
        },
        project_root=root_header,
        timeout=timeout,
    )
    if status != 200 or not session_id:
        return {
            "ok": False,
            "server_id": server_id,
            "url": url,
            "stage": "initialize",
            "http_status": status,
            "error": body[:500],
        }

    init_payload = parse_sse_json(body)
    if init_payload is None or "result" not in init_payload:
        return {
            "ok": False,
            "server_id": server_id,
            "url": url,
            "stage": "initialize",
            "error": f"invalid SSE payload: {body[:200]!r}",
        }

    init_status, _, _ = _post_mcp(
        url,
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        project_root=root_header,
        session_id=session_id,
        timeout=timeout,
    )
    if init_status not in (200, 202):
        return {
            "ok": False,
            "server_id": server_id,
            "url": url,
            "stage": "initialized",
            "http_status": init_status,
        }

    list_status, _, list_body = _post_mcp(
        url,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        project_root=root_header,
        session_id=session_id,
        timeout=timeout,
    )
    listed = parse_sse_json(list_body)
    tools = (listed or {}).get("result", {}).get("tools", [])
    tool_count = len(tools) if isinstance(tools, list) else 0
    if list_status != 200 or tool_count == 0:
        return {
            "ok": False,
            "server_id": server_id,
            "url": url,
            "stage": "tools/list",
            "http_status": list_status,
            "tool_count": tool_count,
            "error": list_body[:500],
        }

    server_info = init_payload.get("result", {}).get("serverInfo", {})
    return {
        "ok": True,
        "server_id": server_id,
        "url": url,
        "tool_count": tool_count,
        "server_name": server_info.get("name"),
        "server_version": server_info.get("version"),
    }


def smoke_test_fleet(
    *,
    project_root: Path | None = None,
    fleet_host: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Smoke-test every NLT HTTP fleet server with a Cursor-like MCP handshake."""
    host = fleet_host or resolve_fleet_host()
    servers: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    for server_id in NLT_HTTP_FLEET_PORTS:
        result = probe_fleet_mcp_session(
            server_id,
            project_root=project_root,
            fleet_host=host,
            timeout=timeout,
        )
        servers[server_id] = result
        if not result.get("ok"):
            stage = result.get("stage", "unknown")
            detail = result.get("error") or f"http={result.get('http_status')}"
            failures.append(f"{server_id} ({stage}): {detail}")

    passed = sum(1 for row in servers.values() if row.get("ok"))
    return {
        "ok": not failures,
        "passed": passed,
        "total": len(NLT_HTTP_FLEET_PORTS),
        "project_root": resolve_http_project_root_header(project_root),
        "fleet_host": host,
        "servers": servers,
        "failures": failures,
    }
