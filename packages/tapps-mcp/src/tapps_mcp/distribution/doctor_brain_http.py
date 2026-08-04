"""Doctor checks for tapps-brain HTTP mode: auth, profile, and latency (TAP-5606 split).

Covers stale frozen-exe backup detection, the ``tapps-brain`` package import
check, HTTP-bridge auth completeness + live auth probe, the capability-profile
probe (REST ``/v1/tools/list`` with ETag cache, JSON-RPC handshake fallback),
and the ``/metrics`` probe-latency histogram check.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from tapps_mcp.distribution.doctor_context7 import _env_file_get_value
from tapps_mcp.distribution.doctor_mcp import (
    _brain_http_url_for_checks,
    _doctor_brain_headers,
    _resolve_brain_auth_token,
)
from tapps_mcp.distribution.doctor_result import CheckResult, doctor_facade_attr


def check_stale_exe_backups() -> CheckResult:
    """Check for stale ``.old`` exe backups next to the running binary.

    Only relevant when running as a frozen exe.  Stale backups indicate
    previous replace-exe operations where cleanup did not complete.
    """
    import sys as _sys

    from tapps_mcp.distribution.exe_manager import detect_stale_backups

    if not getattr(_sys, "frozen", False):
        return CheckResult(
            "Stale exe backups",
            True,
            "Not running as frozen exe (check not applicable)",
        )

    old_files = detect_stale_backups()
    if not old_files:
        return CheckResult("Stale exe backups", True, "No stale .old backups found")

    names = [f.name for f in old_files]
    return CheckResult(
        "Stale exe backups",
        False,
        f"Stale exe backup(s) found: {', '.join(names)}",
        "These will be cleaned up automatically on next startup, "
        "or delete them manually if no other tapps-mcp processes are running.",
    )


def check_tapps_brain() -> CheckResult:
    """Check that the tapps-brain memory library is importable.

    tapps-brain was extracted from tapps-core as a standalone library.
    All memory modules in tapps-core delegate to tapps-brain; if it is
    missing, memory operations will fail at runtime.
    """
    try:
        import tapps_brain

        version = getattr(tapps_brain, "__version__", "(unknown)")
        return CheckResult(
            "tapps-brain library",
            True,
            f"tapps-brain {version} available",
        )
    except ImportError as exc:
        return CheckResult(
            "tapps-brain library",
            False,
            "tapps-brain not importable (memory subsystem unavailable)",
            f"Error: {exc}. Install: pip install tapps-brain>=1.0.0",
        )


def _run_auth_probe(http_url: str, settings: Any) -> dict[str, Any] | None:
    """TAP-2098: run a synchronous :meth:`HttpBrainBridge.auth_probe` for the
    doctor check.

    Builds a transient ``HttpBrainBridge`` from doctor-resolved settings so
    we never share state with the long-lived server bridge. Returns the
    probe dict (carrying ``ok``, ``gated``, ``suggested_profile`` …) or
    ``None`` when the probe cannot run.
    """
    try:
        from tapps_core.brain_bridge import HttpBrainBridge
    except Exception:
        return None
    try:
        headers = _doctor_brain_headers(settings)
        bridge = HttpBrainBridge(http_url, headers)
        result = bridge.auth_probe()
    except Exception:
        return None
    return result if isinstance(result, dict) else None


def check_brain_http_auth(root: Path) -> CheckResult:
    """Verify that HTTP-bridge auth config is complete when HTTP mode is active.

    When ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` is set, the client must also have
    ``memory.brain_auth_token`` (env: ``TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN``) and
    ``memory.brain_project_id``. Missing either silently sends unauthenticated
    (or partially authenticated) requests and every memory/hive call returns
    401 or 403 — but ``memory_status.degraded`` looked OK until we fixed it
    because the old probe only hit ``/health`` (unauthenticated).

    A common mistake is exporting ``TAPPS_BRAIN_AUTH_TOKEN`` in the shell but
    not mapping it to ``TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN`` for CLI doctor
    (MCP hosts expand ``${TAPPS_BRAIN_AUTH_TOKEN}`` in ``.mcp.json`` at launch).
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain HTTP auth",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=root)
        token_present = _resolve_brain_auth_token(settings) is not None
        project_id_present = bool(settings.memory.brain_project_id)
    except Exception as exc:
        return CheckResult(
            "tapps-brain HTTP auth",
            False,
            f"Could not load settings: {exc}",
            "Fix .tapps-mcp.yaml or env vars and re-run doctor.",
        )

    if token_present and project_id_present:
        # TAP-2098: config looks good — actually probe the wire so the operator
        # sees ``out_of_profile`` denials (server returns 200 with a JSON-RPC
        # ``error.data.reason == "out_of_profile"`` envelope) before the first
        # runtime memory call fails. ``suggested_profile`` (v3.19.0+) becomes
        # the remediation hint.
        probe = doctor_facade_attr("_run_auth_probe", _run_auth_probe)(http_url, settings)
        if probe is not None and probe.get("gated"):
            tool = probe.get("tool") or "probe tool"
            profile = probe.get("profile") or "<unset>"
            suggested = probe.get("suggested_profile")
            hint = (
                f"Set TAPPS_BRAIN_PROFILE (or memory.brain_profile in "
                f".tapps-mcp.yaml) to {suggested!r} to expose {tool!r}."
                if suggested
                else (
                    f"No profile suggested by brain — pick a profile that "
                    f"exposes {tool!r} (e.g. ``operator`` or ``full``)."
                )
            )
            return CheckResult(
                "tapps-brain HTTP auth",
                False,
                f"HTTP auth ok but profile {profile!r} hides {tool!r}",
                hint,
            )
        return CheckResult(
            "tapps-brain HTTP auth",
            True,
            f"HTTP mode configured with bearer token + project id ({http_url})",
        )

    missing: list[str] = []
    hints: list[str] = []
    if not token_present:
        missing.append("brain_auth_token")
        hints.append(
            "Set TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN or memory.brain_auth_token in "
            ".tapps-mcp.yaml (same value as TAPPS_BRAIN_AUTH_TOKEN is fine). "
            "Shell CLI (`tapps-mcp memory save/get`, `session-end`) reads this "
            "env directly — export it in .env/direnv even when MCP expands "
            "${TAPPS_BRAIN_AUTH_TOKEN} at IDE launch."
        )
    if not project_id_present:
        missing.append("brain_project_id")
        hints.append(
            "Set TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID or memory.brain_project_id "
            "in .tapps-mcp.yaml (registered tapps-brain project slug)."
        )

    return CheckResult(
        "tapps-brain HTTP auth",
        False,
        f"HTTP mode active but missing: {', '.join(missing)}",
        " ".join(hints),
    )


# TAP-2115: module-level ETag cache for /v1/tools/list responses, keyed by
# (http_url, profile-header). Lets repeat `tapps doctor` invocations within
# the brain's 300 s Cache-Control window short-circuit to 304 + cached set.
_TOOLS_CATALOG_CACHE: dict[tuple[str, str], tuple[str, frozenset[str]]] = {}


class _ProfileProbeError(Exception):
    """Internal control-flow exception for check_brain_profile failures."""

    def __init__(self, detail: str, hint: str = "") -> None:
        super().__init__(detail)
        self.detail = detail
        self.hint = hint


def _fetch_exposed_tools(
    http_url: str,
    headers: dict[str, str],
    httpx_mod: Any,
    mcp_accept_headers: dict[str, str],
) -> tuple[set[str], str]:
    """TAP-2115 (consumes TAP-1971): fetch the exposed tool set, preferring
    the cacheable REST endpoint and falling back to the JSON-RPC handshake
    on older brains.

    Returns ``(exposed_tool_names, source_label)`` where ``source_label`` is
    one of ``"rest"``, ``"rest-cached"`` (304 hit), or ``"jsonrpc"``.
    """
    try:
        return _fetch_exposed_tools_rest(http_url, headers, httpx_mod)
    except _ProfileProbeFallbackError:
        return _fetch_exposed_tools_jsonrpc(http_url, headers, httpx_mod, mcp_accept_headers)


class _ProfileProbeFallbackError(Exception):
    """Internal signal that the REST path is unavailable; try JSON-RPC."""


def _parse_tools_list_response(response: Any) -> set[str]:
    """Extract tool names from a ``/v1/tools/list`` JSON response body."""
    try:
        payload = response.json()
    except Exception as exc:
        raise _ProfileProbeError(
            f"/v1/tools/list returned non-JSON body: {exc}",
            "Brain misconfigured; expected application/json with a `tools` array.",
        ) from exc
    tools = payload.get("tools", []) if isinstance(payload, dict) else []
    return {
        str(t["name"])
        for t in tools
        if isinstance(t, dict) and isinstance(t.get("name"), str) and t["name"]
    }


def _fetch_exposed_tools_rest(
    http_url: str, headers: dict[str, str], httpx_mod: Any
) -> tuple[set[str], str]:
    """GET ``/v1/tools/list`` with ``If-None-Match`` from the module cache.

    Sends only ``X-Brain-Profile`` and ``If-None-Match`` — the REST endpoint
    is unauthenticated and Origin-exempt (TAP-1843), so we deliberately do
    NOT forward the bearer token here. Raises :class:`_ProfileProbeFallbackError`
    when the endpoint isn't available (404 ⇒ pre-TAP-1843 brain) so the
    caller can switch to the JSON-RPC handshake.
    """
    profile_header = headers.get("X-Brain-Profile") or ""
    cache_key = (http_url, profile_header)
    cached = _TOOLS_CATALOG_CACHE.get(cache_key)
    req_headers: dict[str, str] = {}
    if profile_header:
        req_headers["X-Brain-Profile"] = profile_header
    if cached is not None:
        req_headers["If-None-Match"] = cached[0]
    try:
        response = httpx_mod.get(
            f"{http_url.rstrip('/')}/v1/tools/list",
            headers=req_headers,
            timeout=5.0,
            follow_redirects=True,
        )
    except Exception:
        raise _ProfileProbeFallbackError from None
    if response.status_code == 304 and cached is not None:
        return set(cached[1]), "rest-cached"
    if response.status_code == 404:
        raise _ProfileProbeFallbackError
    if response.status_code != 200:
        raise _ProfileProbeError(
            f"/v1/tools/list returned {response.status_code}",
            "Brain rejected the REST tool-list probe; check brain version + profile name.",
        )
    exposed = _parse_tools_list_response(response)
    etag = response.headers.get("etag") or response.headers.get("ETag") or ""
    if etag:
        _TOOLS_CATALOG_CACHE[cache_key] = (etag, frozenset(exposed))
    return exposed, "rest"


def _fetch_exposed_tools_jsonrpc(
    http_url: str,
    headers: dict[str, str],
    httpx_mod: Any,
    mcp_accept_headers: dict[str, str],
) -> tuple[set[str], str]:
    """Legacy fallback: full MCP handshake + JSON-RPC ``tools/list``.

    Kept for brains <3.18.0 that don't expose the REST endpoint.
    """
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
        init_response = httpx_mod.post(
            f"{http_url.rstrip('/')}/mcp/",
            json=init_payload,
            headers={**headers, **mcp_accept_headers},
            timeout=5.0,
            follow_redirects=True,
        )
        init_response.raise_for_status()
    except Exception as exc:
        raise _ProfileProbeError(
            f"Could not initialize MCP session at {http_url}: {exc}",
            "Brain may be down or unreachable; see brain logs.",
        ) from exc
    session_id = init_response.headers.get("mcp-session-id", "")
    list_headers = {**headers, **mcp_accept_headers}
    if session_id:
        list_headers["Mcp-Session-Id"] = session_id
    try:
        list_response = httpx_mod.post(
            f"{http_url.rstrip('/')}/mcp/",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers=list_headers,
            timeout=5.0,
            follow_redirects=True,
        )
        list_response.raise_for_status()
        payload = list_response.json()
    except Exception as exc:
        raise _ProfileProbeError(
            f"tools/list failed: {exc}",
            "Brain returned an error to tools/list; check brain version + auth.",
        ) from exc
    tools_meta = payload.get("result", {}).get("tools", [])
    exposed = {
        str(t["name"])
        for t in tools_meta
        if isinstance(t, dict) and isinstance(t.get("name"), str) and t["name"]
    }
    return exposed, "jsonrpc"


def _probe_warm_cache_status(root: Path, headers: dict[str, str]) -> str:
    """TAP-1927: return a short human-readable label for the warm-cache state.

    Labels: ``warm(<age>s)`` when the pre-warm file is present and within TTL,
    ``stale(<age>s)`` when it exists but has expired, or ``miss`` when absent.
    """
    import re as _re
    import time as _time

    from tapps_core.brain_bridge import _TOOLS_CACHE_TTL_SECONDS

    raw_profile = headers.get("X-Brain-Profile") or ""
    safe_profile = _re.sub(r"[^A-Za-z0-9_-]", "_", raw_profile) if raw_profile else ""
    cache_file = root / ".tapps-mcp" / f".brain-tools-list.{safe_profile}.json"
    try:
        if not cache_file.exists():
            return "miss"
        age = _time.time() - cache_file.stat().st_mtime
        age_s = int(age)
        if age < _TOOLS_CACHE_TTL_SECONDS:
            return f"warm({age_s}s)"
        return f"stale({age_s}s)"
    except Exception:
        return "miss"


def check_brain_profile(root: Path) -> CheckResult:
    """TAP-1629 / TAP-2100: probe the tapps-brain capability profile via tools/list.

    Surfaces (a) the declared ``X-Brain-Profile`` header, (b) the count of
    tools the active profile's eager ``tools/list`` returns, and (c) any
    tools the HTTP bridge invokes that are missing from that catalog.

    Under tapps-brain v3.19.0+ (TAP-1985), the ``full`` and ``operator``
    profiles default to an 8-tool eager catalog with the remaining tools
    deferred-loaded — these are still callable via ``tools/call`` but
    absent from ``tools/list``. After TAP-2100 the bridge no longer
    preflight-rejects on this list, so missing entries are diagnostic, not
    runtime-blocking. A genuine profile mismatch (e.g. switching to
    ``coder`` on a brain that hides ``memory_save``) still surfaces as
    :class:`ToolNotInProfileError` on the first call.

    Skipped (passing) when HTTP mode is not active.
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain capability profile",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    try:
        import tapps_mcp.server_memory_tools  # noqa: F401 — TAP-1961 registration
        from tapps_core.brain_bridge import (
            _MCP_ACCEPT_HEADERS,
            BRAIN_PROFILE_SERVER,
            BRAIN_PROFILES_DEFERRED_OK,
            get_bridge_used_tools,
        )
        from tapps_core.config.settings import load_settings
    except Exception as exc:
        return CheckResult(
            "tapps-brain capability profile",
            False,
            f"Could not load bridge modules: {exc}",
            "Re-run after fixing the import error.",
        )

    try:
        settings = load_settings(project_root=root)
        headers = _doctor_brain_headers(settings)
    except Exception as exc:
        return CheckResult(
            "tapps-brain capability profile",
            False,
            f"Could not build brain auth headers: {exc}",
            "Fix .tapps-mcp.yaml or env vars and re-run doctor.",
        )

    # ADR-0012: when no profile is configured, the runtime server bridge applies
    # BRAIN_PROFILE_SERVER as its default_profile. Probe with that same effective
    # profile so the diagnosis matches what the tapps_memory facade actually uses.
    if "X-Brain-Profile" not in headers:
        headers["X-Brain-Profile"] = BRAIN_PROFILE_SERVER
        effective_profile = BRAIN_PROFILE_SERVER
        declared = f"{BRAIN_PROFILE_SERVER} (server default)"
    else:
        effective_profile = headers["X-Brain-Profile"]
        declared = effective_profile

    # TAP-1927: report the warm-cache status alongside the live probe result.
    _warm_cache_label = doctor_facade_attr("_probe_warm_cache_status", _probe_warm_cache_status)(
        root, headers
    )

    try:
        import httpx as _httpx
    except Exception as exc:
        return CheckResult(
            "tapps-brain capability profile",
            False,
            f"httpx unavailable: {exc}",
        )

    try:
        exposed, source = doctor_facade_attr("_fetch_exposed_tools", _fetch_exposed_tools)(
            http_url, headers, doctor_facade_attr("httpx", _httpx), _MCP_ACCEPT_HEADERS
        )
    except _ProfileProbeError as exc:
        return CheckResult(
            "tapps-brain capability profile",
            False,
            exc.detail,
            exc.hint,
        )

    gated_used = sorted(get_bridge_used_tools() - exposed)

    if not gated_used:
        return CheckResult(
            "tapps-brain capability profile",
            True,
            f"profile={declared}, exposed={len(exposed)} tools "
            f"({source}), no bridge mismatch; warm-cache={_warm_cache_label}",
        )

    # ADR-0012: distinguish a benign deferred-loading gap (``full``/``operator``,
    # where the missing tools carry ``defer_loading`` and remain callable via
    # tools/call — TAP-1985) from a genuine profile gate (``coder``/``reviewer``/
    # ``agent_brain``/``seeder``, where the tools are absent from the profile and
    # tools/call rejects them with ToolNotInProfileError).
    if effective_profile in BRAIN_PROFILES_DEFERRED_OK:
        return CheckResult(
            "tapps-brain capability profile",
            True,
            f"profile={declared}, {len(gated_used)} bridge tool(s) deferred from eager "
            f"tools/list but callable via tools/call ({source}); warm-cache={_warm_cache_label}",
        )

    return CheckResult(
        "tapps-brain capability profile",
        False,
        f"profile={declared} GATES {len(gated_used)} bridge tool(s) ({source}): "
        f"{', '.join(gated_used)}; these calls fail with ToolNotInProfileError on "
        f"tapps-brain v3.20.0+; warm-cache={_warm_cache_label}",
        "The declared profile is too narrow for the tapps_memory facade. Set "
        "memory.brain_profile (or TAPPS_BRAIN_PROFILE) to 'full' (ADR-0012) — or "
        "'operator' if maintenance ops must run live — so the bridge's tools are "
        "exposed. 'coder'/'reviewer'/'agent_brain' are intended for narrower consumers.",
    )


_BRAIN_PROBE_METRIC = "tapps_brain_mcp_probe_duration_seconds"


def _parse_histogram_quantiles(
    metrics_text: str,
    metric: str,
    quantiles: tuple[float, ...],
) -> dict[float, float] | None:
    """Parse a Prometheus histogram from ``/metrics`` text into quantiles.

    Returns ``{quantile: seconds}`` computed from the cumulative
    ``<metric>_bucket{le=...}`` counts via linear interpolation within the
    matched bucket (the ``histogram_quantile`` algorithm). Bucket counts are
    summed across label sets at the same ``le`` (equivalent to PromQL
    ``sum by (le)``) so multi-series histograms aggregate cleanly. Returns
    ``None`` when the metric/buckets are absent or the total count is zero.
    """
    import math
    import re

    pattern = re.compile(
        r"^" + re.escape(metric) + r'_bucket\{[^}]*\ble="([^"]+)"[^}]*\}\s+([0-9.eE+]+)',
        re.MULTILINE,
    )
    agg: dict[float, float] = {}
    for le_raw, count_raw in pattern.findall(metrics_text):
        try:
            le = math.inf if le_raw in ("+Inf", "Inf") else float(le_raw)
            count = float(count_raw)
        except ValueError:
            continue
        agg[le] = agg.get(le, 0.0) + count
    if not agg:
        return None
    buckets = sorted(agg.items())  # ascending by le; +Inf sorts last
    total = buckets[-1][1]
    if total <= 0:
        return None

    out: dict[float, float] = {}
    for q in quantiles:
        rank = q * total
        prev_le = 0.0
        prev_count = 0.0
        value = buckets[-1][0]
        for le, cum in buckets:
            if cum >= rank:
                if math.isinf(le):
                    # quantile falls in the +Inf bucket — best lower-bound
                    # estimate is the largest finite le seen so far.
                    value = prev_le
                else:
                    bucket_count = cum - prev_count
                    value = (
                        le
                        if bucket_count <= 0
                        else prev_le + (le - prev_le) * (rank - prev_count) / bucket_count
                    )
                break
            prev_le = le
            prev_count = cum
        out[q] = value
    return out


def check_brain_probe_latency(root: Path) -> CheckResult:
    """TAP-1931: surface tapps-brain MCP probe latency quantiles in doctor.

    GETs ``{brain_http_url}/metrics`` and parses the
    ``tapps_brain_mcp_probe_duration_seconds`` histogram (TAP-1849) into
    p50 / p95 / p99. Reports ``unavailable`` (passing) on any error or when
    the metric is absent — telemetry gaps must never fail the doctor run.
    Profile parity stays in :func:`check_brain_profile`; this check is
    latency-only.

    Skipped (passing) when HTTP mode is not active.
    """
    name = "tapps-brain probe latency"
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            name,
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    headers: dict[str, str] = {}
    # Prefer TAPPS_BRAIN_METRICS_TOKEN for /metrics (TAP-547); auth token is rejected with 403.
    # Resolve from process env, then ~/.tapps-operator.env / project .env — CLI doctor often
    # runs without direnv; MCP serve wrappers already source those files (TAP-3255).
    metrics_token = (os.environ.get("TAPPS_BRAIN_METRICS_TOKEN") or "").strip()
    if not metrics_token:
        metrics_token = (
            _env_file_get_value(Path.home() / ".tapps-operator.env", "TAPPS_BRAIN_METRICS_TOKEN")
            or _env_file_get_value(root / ".env", "TAPPS_BRAIN_METRICS_TOKEN")
            or ""
        ).strip()
    if metrics_token:
        headers = {"Authorization": f"Bearer {metrics_token}"}
        os.environ.setdefault("TAPPS_BRAIN_METRICS_TOKEN", metrics_token)
    else:
        try:
            from tapps_core.config.settings import load_settings

            headers = _doctor_brain_headers(load_settings(project_root=root))
        except Exception:
            headers = {}

    metrics_url = http_url.rstrip("/") + "/metrics"
    try:
        resp = doctor_facade_attr("httpx", httpx).get(metrics_url, headers=headers, timeout=5.0)
    except Exception as exc:
        return CheckResult(name, True, f"probe latency: unavailable ({type(exc).__name__})")
    if resp.status_code != 200:
        return CheckResult(
            name, True, f"probe latency: unavailable (/metrics HTTP {resp.status_code})"
        )

    quantiles = _parse_histogram_quantiles(resp.text, _BRAIN_PROBE_METRIC, (0.5, 0.95, 0.99))
    if not quantiles:
        return CheckResult(name, True, "probe latency: unavailable (metric absent in /metrics)")

    return CheckResult(
        name,
        True,
        "mcp_probe_duration "
        f"p50: {quantiles[0.5]:.3f}s / p95: {quantiles[0.95]:.3f}s "
        f"/ p99: {quantiles[0.99]:.3f}s",
    )
