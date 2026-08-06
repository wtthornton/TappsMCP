"""Doctor checks for tapps-brain health + version floor/delta (TAP-5606 split).

Covers the flywheel/diagnostics health summary (via an MCP tools/call
handshake) and version-floor / version-delta checks that compare the live
brain HTTP service against the ``tapps-core``-pinned floor.
"""

from __future__ import annotations

import re
from importlib.metadata import requires as _requires
from pathlib import Path
from typing import Any

import httpx

from tapps_mcp.distribution.doctor_mcp import (
    _brain_http_url_for_checks,
    _doctor_brain_headers,
)
from tapps_mcp.distribution.doctor_result import CheckResult, doctor_facade_attr

__all__ = ["check_brain_health", "check_brain_version_floor", "check_brain_version_delta", "_requires"]


def check_brain_health(root: Path) -> CheckResult:
    """TAP-1632: pull flywheel + diagnostics summary from tapps-brain.

    Synchronously calls ``flywheel_report`` and ``diagnostics_report``
    against the configured HTTP brain and renders a compact summary so
    operators can see at a glance whether feedback is flowing into the
    flywheel and whether brain-side quality metrics are degrading.
    Skipped (passing) when HTTP mode is not active.
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain health",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    try:
        from tapps_core.brain_bridge import _MCP_ACCEPT_HEADERS
        from tapps_core.config.settings import load_settings
    except Exception as exc:
        return CheckResult(
            "tapps-brain health",
            False,
            f"Could not load bridge modules: {exc}",
            "Re-run after fixing the import error.",
        )

    try:
        settings = load_settings(project_root=root)
        headers = _doctor_brain_headers(settings)
    except Exception as exc:
        return CheckResult(
            "tapps-brain health",
            False,
            f"Could not build brain auth headers: {exc}",
            "Fix .tapps-mcp.yaml or env vars and re-run doctor.",
        )

    try:
        import httpx as _httpx
    except Exception as exc:
        return CheckResult(
            "tapps-brain health",
            False,
            f"httpx unavailable: {exc}",
        )

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "tapps-mcp-doctor", "version": "1"},
        },
    }
    try:
        init_response = _httpx.post(
            f"{http_url.rstrip('/')}/mcp/",
            json=init_payload,
            headers={**headers, **_MCP_ACCEPT_HEADERS},
            timeout=5.0,
            follow_redirects=True,
        )
        init_response.raise_for_status()
    except Exception as exc:
        return CheckResult(
            "tapps-brain health",
            False,
            f"Could not initialize MCP session: {exc}",
            "Brain may be down or unreachable; see brain logs.",
        )

    session_id = init_response.headers.get("mcp-session-id", "")
    call_headers = {**headers, **_MCP_ACCEPT_HEADERS}
    if session_id:
        call_headers["Mcp-Session-Id"] = session_id

    def _tool_call(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = _httpx.post(
                f"{http_url.rstrip('/')}/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": args},
                },
                headers=call_headers,
                timeout=5.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None
        result = payload.get("result", {})
        if not isinstance(result, dict) or result.get("isError"):
            return None
        content = result.get("content", [])
        if not content or content[0].get("type") != "text":
            return None
        try:
            import json as _json

            parsed = _json.loads(content[0]["text"])
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    flywheel = _tool_call("flywheel_report", {"period_days": 7})
    diagnostics = _tool_call("diagnostics_report", {"record_history": False})

    if flywheel is None and diagnostics is None:
        return CheckResult(
            "tapps-brain health",
            False,
            "Could not fetch flywheel_report or diagnostics_report from brain",
            "These tools require tapps-brain 3.17+ and the operator/full profile.",
        )

    parts: list[str] = []
    if flywheel is not None:
        gaps = flywheel.get("gap_count") or flywheel.get("gaps") or 0
        rates = flywheel.get("rating_count") or flywheel.get("ratings") or 0
        period = flywheel.get("period_days", 7)
        parts.append(f"flywheel: {gaps} gap(s) / {rates} rating(s) in {period}d")
    if diagnostics is not None:
        score = diagnostics.get("health_score") or diagnostics.get("score")
        if score is not None:
            parts.append(f"diagnostics health_score={score}")
        else:
            parts.append("diagnostics: snapshot available")

    return CheckResult(
        "tapps-brain health",
        True,
        "; ".join(parts) if parts else "brain reports clean health",
        (
            "Detail under `tapps_memory(action=health)` and the brain's "
            "flywheel_report/diagnostics_report tools."
        ),
    )


def _parse_version_tuple(ver_str: str) -> tuple[int, int, int]:
    """Parse ``'3.18.0'`` → ``(3, 18, 0)``.  Returns ``(0, 0, 0)`` on error."""
    try:
        parts = ver_str.split(".")[:3]
        return (
            int(parts[0]),
            int(parts[1]) if len(parts) > 1 else 0,
            int(parts[2]) if len(parts) > 2 else 0,
        )
    except Exception:
        return (0, 0, 0)


def _read_brain_floor_pin() -> str | None:
    """Return the ``tapps-brain`` floor version from ``tapps-core`` package metadata.

    Parses ``requires('tapps-core')`` looking for a ``tapps-brain>=X.Y.Z`` entry and
    returns ``X.Y.Z``.  Returns ``None`` when the metadata is unavailable or the
    requirement cannot be parsed.
    """
    try:
        for req in doctor_facade_attr("_requires", _requires)("tapps-core") or []:
            m = re.match(r"^tapps.brain\s*>=\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)", req, re.IGNORECASE)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def check_brain_version_floor(root: Path) -> CheckResult:
    """Fail when the running brain HTTP service is below the pinned version floor.

    Uses :func:`tapps_core.brain_bridge.check_brain_version` against the resolved
    HTTP URL so operators see the same hard floor enforcement as
    ``brain_bridge_health.details.brain_version`` at session start.
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain version floor",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    from tapps_core.brain_bridge import _BRAIN_VERSION_FLOOR, check_brain_version

    probe = check_brain_version(http_url)
    floor = probe.get("floor") or _BRAIN_VERSION_FLOOR
    version = probe.get("version")
    if probe.get("skipped"):
        return CheckResult(
            "tapps-brain version floor",
            True,
            "Version probe skipped (no HTTP URL)",
        )
    if probe.get("degraded") and not version:
        return CheckResult(
            "tapps-brain version floor",
            False,
            f"Could not reach brain at {http_url} for version probe",
            "Start tapps-brain-http and re-run doctor.",
        )
    if probe.get("ok"):
        return CheckResult(
            "tapps-brain version floor",
            True,
            f"brain {version} satisfies >={floor}",
        )
    errors = probe.get("errors") or probe.get("warnings") or []
    detail = errors[0] if errors else f"brain {version!s} below required >={floor}"
    return CheckResult(
        "tapps-brain version floor",
        False,
        detail,
        f"Upgrade tapps-brain-http to >={floor} (see ADR-0013).",
    )


def check_brain_version_delta(root: Path) -> CheckResult:
    """TAP-2025: compare the running brain-service version against the pinned floor.

    Reads the ``tapps-brain>=X.Y.Z`` floor constraint from ``tapps-core``'s
    installed package metadata and compares it against the live
    ``brain_version`` field returned by ``{brain_http_url}/healthz``.

    Emits WARN when the running brain version is more than 2 minor versions
    ahead of the floor pin — a signal that it is time to bump the pin.
    Emits CRITICAL when the major version differs (API-breaking).

    The check is skipped (passes) when HTTP mode is inactive.
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain version delta",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    # Probe /healthz (v3.19.0+) first; fall back to /health for older brains
    brain_ver_str: str | None = None
    for path in ("/healthz", "/health"):
        try:
            resp = doctor_facade_attr("httpx", httpx).get(
                f"{http_url.rstrip('/')}{path}", timeout=3.0
            )
            resp.raise_for_status()
            body = resp.json()
            brain_ver_str = body.get("brain_version") or body.get("version")
            if brain_ver_str:
                break
        except Exception:
            continue

    if not brain_ver_str:
        return CheckResult(
            "tapps-brain version delta",
            True,
            "Brain health endpoint did not return a version — skipping delta check",
        )

    floor_str = doctor_facade_attr("_read_brain_floor_pin", _read_brain_floor_pin)()
    if not floor_str:
        return CheckResult(
            "tapps-brain version delta",
            True,
            f"Running brain {brain_ver_str} (floor pin unresolvable from tapps-core metadata)",
        )

    running = _parse_version_tuple(brain_ver_str)
    floor = _parse_version_tuple(floor_str)
    running_str = ".".join(str(v) for v in running)
    floor_str_fmt = ".".join(str(v) for v in floor)

    if running[0] != floor[0]:
        return CheckResult(
            "tapps-brain version delta",
            False,
            f"CRITICAL: major version mismatch — running {running_str}, floor pin {floor_str_fmt}",
            "Update the tapps-brain pin in tapps-core/pyproject.toml and re-install.",
        )

    minor_delta = running[1] - floor[1]
    if minor_delta > 2:
        return CheckResult(
            "tapps-brain version delta",
            False,
            (
                f"WARN: running brain {running_str} is {minor_delta} minor version(s) "
                f"ahead of floor pin {floor_str_fmt}"
            ),
            f"Bump tapps-brain floor in tapps-core/pyproject.toml to >={running_str}.",
        )

    return CheckResult(
        "tapps-brain version delta",
        True,
        (
            f"brain {running_str} within 2 minor versions of floor pin "
            f"{floor_str_fmt} (delta={minor_delta})"
        ),
    )
