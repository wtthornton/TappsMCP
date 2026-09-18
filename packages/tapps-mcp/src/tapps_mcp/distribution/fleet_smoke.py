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

from tapps_core.http.auth import FLEET_CREDENTIAL_HEADER, FleetAuthConfig
from tapps_core.http.request_context import PROJECT_ROOT_HEADER
from tapps_mcp.distribution.nlt_http_fleet import (
    NLT_HTTP_FLEET_PORTS,
    build_http_fleet_url,
    resolve_fleet_host,
    resolve_http_project_root_header,
)

_MCP_ACCEPT = "application/json, text/event-stream"
_INIT_PROTOCOL = "2025-03-26"


def _fleet_auth_headers() -> dict[str, str]:
    """Operator-token header for the in-flight probe, when one is configured.

    Reads the same ``TAPPS_FLEET_AUTH_TOKEN`` config the fleet servers
    themselves resolve (:class:`FleetAuthConfig`). Without this, an
    auth-enabled fleet 401s every smoke/watchdog probe and the watchdog
    restart-loops all six servers as ``initialize_timeout`` (TAP-6062). No
    token configured -> no header, behavior unchanged.
    """
    operator_token = FleetAuthConfig.from_env().operator_token
    if not operator_token:
        return {}
    return {FLEET_CREDENTIAL_HEADER: operator_token}


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
        **_fleet_auth_headers(),
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


def probe_fleet_mcp_initialize(
    server_id: str,
    *,
    project_root: Path | None = None,
    fleet_host: str | None = None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Cheap liveness probe: ``initialize`` only (no tools/list).

    Detects event-loop starvation on shared HTTP fleet servers where TCP still
    accepts connections but ``/mcp`` never completes a handshake (Cursor stuck
    on "Loading tools"). Prefer this for the watchdog; use
    :func:`probe_fleet_mcp_session` for full deploy smoke.
    """
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
                "clientInfo": {"name": "tapps-mcp-fleet-liveness", "version": "1"},
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
    return {"ok": True, "server_id": server_id, "url": url, "stage": "initialize"}


def _establish_fleet_session(
    url: str,
    *,
    root_header: str,
    client_name: str,
    timeout: float,
) -> dict[str, Any]:
    """Run ``initialize`` + ``notifications/initialized`` against *url*.

    Shared by every probe below the cheap liveness-only one
    (:func:`probe_fleet_mcp_initialize`) so a session-establishment fix lands
    in one place. Returns ``{"ok": False, "stage": ..., ...}`` on failure, or
    ``{"ok": True, "session_id": ..., "init_payload": ...}`` on success --
    *init_payload* is the raw ``initialize`` response (callers that need
    ``serverInfo`` read it from there).
    """
    status, session_id, body = _post_mcp(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": _INIT_PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": "1"},
            },
        },
        project_root=root_header,
        timeout=timeout,
    )
    if status != 200 or not session_id:
        return {"ok": False, "stage": "initialize", "http_status": status, "error": body[:500]}

    init_payload = parse_sse_json(body)
    if init_payload is None or "result" not in init_payload:
        return {
            "ok": False,
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
        return {"ok": False, "stage": "initialized", "http_status": init_status}

    return {"ok": True, "session_id": session_id, "init_payload": init_payload}


def probe_fleet_mcp_session(
    server_id: str,
    *,
    project_root: Path | None = None,
    fleet_host: str | None = None,
    timeout: float = 15.0,
    port: int | None = None,
) -> dict[str, Any]:
    """Run initialize + initialized + tools/list against one fleet server.

    *port* overrides the fixed ``NLT_HTTP_FLEET_PORTS`` lookup -- used by the
    blue/green pre-flip profile smoke (TAP-7234), which starts a scratch
    instance of a tapps-mcp tool preset on an ephemeral port rather than
    probing a live, fixed-port fleet server. *server_id* is then just a
    label for the returned row, not a fleet-port key. Existing callers that
    omit *port* are unaffected.
    """
    root_header = resolve_http_project_root_header(project_root)
    if port is not None:
        host = fleet_host or resolve_fleet_host()
        url = f"http://{host}:{port}/mcp"
    else:
        if server_id not in NLT_HTTP_FLEET_PORTS:
            return {"ok": False, "server_id": server_id, "error": f"unknown server: {server_id}"}
        url = build_http_fleet_url(server_id, fleet_host=fleet_host)

    session = _establish_fleet_session(
        url, root_header=root_header, client_name="tapps-mcp-fleet-smoke", timeout=timeout
    )
    if not session["ok"]:
        return {"server_id": server_id, "url": url, **session}

    session_id = session["session_id"]
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

    server_info = session["init_payload"].get("result", {}).get("serverInfo", {})
    return {
        "ok": True,
        "server_id": server_id,
        "url": url,
        "tool_count": tool_count,
        "server_name": server_info.get("name"),
        "server_version": server_info.get("version"),
    }


def _parse_tool_call_response(
    server_id: str, url: str, tool_name: str, status: int, body: str
) -> dict[str, Any]:
    """Extract the tool's own JSON envelope from a ``tools/call`` response."""
    payload = parse_sse_json(body)
    if status != 200 or payload is None or "result" not in payload:
        return {
            "ok": False,
            "server_id": server_id,
            "url": url,
            "stage": "tools/call",
            "http_status": status,
            "error": body[:500],
        }

    result = payload["result"]
    if not isinstance(result, dict) or result.get("isError"):
        return {
            "ok": False,
            "server_id": server_id,
            "url": url,
            "stage": "tools/call",
            "error": f"tool {tool_name} returned isError: {body[:500]!r}",
        }

    text = ""
    for block in result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            break
    try:
        parsed = json.loads(text) if text else None
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "server_id": server_id,
            "url": url,
            "stage": "tools/call",
            "error": f"tool {tool_name} response was not a JSON object: {text[:200]!r}",
        }
    return {"ok": True, "server_id": server_id, "url": url, "tool": tool_name, "data": parsed}


def probe_fleet_tool_result(
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    project_root: Path | None = None,
    fleet_host: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Run initialize + initialized + ``tools/call`` and return the tool's own payload.

    ``probe_fleet_mcp_session``'s ``server_version`` comes from the
    ``initialize`` handshake's ``serverInfo``, which the ``mcp`` SDK fills in
    from ``pkg_version("mcp")`` when the server was constructed without an
    explicit ``version=`` (this fleet's ``FastMCP("TappsMCP", ...)`` call) --
    i.e. it names the MCP SDK's version, not the application's. A caller that
    needs the application's actual running version has to call a tool that
    reports it (``tapps_session_start`` -> ``data.server.version``) and read
    the answer from inside the tool's own response, not from the transport
    handshake.
    """
    if server_id not in NLT_HTTP_FLEET_PORTS:
        return {"ok": False, "server_id": server_id, "error": f"unknown server: {server_id}"}
    root_header = resolve_http_project_root_header(project_root)
    url = build_http_fleet_url(server_id, fleet_host=fleet_host)

    session = _establish_fleet_session(
        url, root_header=root_header, client_name="tapps-mcp-fleet-tool-probe", timeout=timeout
    )
    if not session["ok"]:
        return {"server_id": server_id, "url": url, **session}

    call_status, _, call_body = _post_mcp(
        url,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
        },
        project_root=root_header,
        session_id=session["session_id"],
        timeout=timeout,
    )
    return _parse_tool_call_response(server_id, url, tool_name, call_status, call_body)


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
