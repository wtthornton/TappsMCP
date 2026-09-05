"""Constants, helper functions, and exception hierarchy for BrainBridge.

Split out of ``brain_bridge.py`` (TAP-6736) to bring the megafile under the
70-point quality floor. No behavior change: every function/class body below
is moved byte-for-byte from the facade.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

from tapps_core.cache.atomic import AtomicJsonCache

# --- Circuit breaker ---------------------------------------------------------
_CB_FAILURE_THRESHOLD: int = 3
_CB_RESET_SECONDS: float = 30.0

# --- Retry -------------------------------------------------------------------
_RETRY_ATTEMPTS: int = 3
_RETRY_BASE: float = 0.5
_RETRY_MAX: float = 8.0

# --- Write queue -------------------------------------------------------------
_WRITE_QUEUE_CAP: int = 100

# --- Remote brain version probe (TAP-519) ------------------------------------
# Keep in sync with the ``tapps-brain`` pin in
# ``packages/tapps-core/pyproject.toml``. The floor is the minimum version
# known to ship all fields tapps-mcp consumes; the ceiling is the next major.
# 3.28.0 is the release that added the ``web_research`` / ``research_fetch``
# MCP tools this bridge binds for ``tapps_research`` (ADR-0033, supersedes the
# 3.24.0 floor in ADR-0013). Below it those calls fail at invocation time with
# an unknown-tool error instead of being caught by the startup version probe.
_BRAIN_VERSION_FLOOR: str = "3.28.0"
_BRAIN_VERSION_CEILING: str = "4.0.0"
_BRAIN_HEALTH_TIMEOUT_SECONDS: float = 5.0

# TAP-6591: health_check() is called synchronously from metrics collection's
# hot read path (execution_metrics._load_from_disk -> brain_metrics_bridge_available),
# so it needs a much tighter budget than the other (already-bounded,
# already-retried) brain calls that share _BRAIN_HEALTH_TIMEOUT_SECONDS.
_HEALTH_CHECK_PROBE_TIMEOUT_SECONDS: float = 1.0

# --- Shutdown drain ---------------------------------------------------------
# Bounded deadline (seconds) that ``close`` / ``drain_blocking`` waits for the
# offline write queue to drain on shutdown before giving up (TAP-517).
_DRAIN_DEADLINE_SECONDS: float = 5.0

# --- Tools-list pre-warm cache (TAP-1927) ------------------------------------
# TTL matches the brain's Cache-Control window (300 s). The cache file lives at
# ``.tapps-mcp/.brain-tools-list.<profile>.json`` relative to the project root
# and is written by the SessionStart hook via ``curl`` before the Python process
# starts.  When present and fresh, ``_negotiate_profile_locked`` reads from it
# instead of incurring the live MCP ``tools/list`` round-trip.
_TOOLS_CACHE_TTL_SECONDS: int = 300


def _read_tools_warm_cache(cache_path: Path) -> frozenset[str] | None:
    """Read the pre-warm tools-list cache file if present and not yet expired.

    Returns a frozenset of tool names when the file exists, is younger than
    :data:`_TOOLS_CACHE_TTL_SECONDS`, and parses as ``{"tools": [...]}``.
    Returns ``None`` on any miss, TTL expiry, or parse error so callers can
    fall through to the live MCP ``tools/list`` round-trip.
    """
    try:
        if not cache_path.exists():
            return None
        age = time.time() - cache_path.stat().st_mtime
        if age >= _TOOLS_CACHE_TTL_SECONDS:
            return None
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        tools = payload.get("tools", [])
        if not isinstance(tools, list) or not tools:
            return None
        names: frozenset[str] = frozenset(
            str(t["name"])
            for t in tools
            if isinstance(t, dict) and isinstance(t.get("name"), str) and t["name"]
        )
        return names or None
    except Exception:
        return None


def _write_tools_warm_cache(cache_path: Path, tools: frozenset[str]) -> None:
    """Write tool names to the pre-warm cache file (best-effort, silent on error).

    Shape matches the brain REST ``/v1/tools/list`` response:
    ``{"tools": [{"name": "<tool>"}, ...]}``.
    """
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tools": [{"name": n} for n in sorted(tools)]}
        AtomicJsonCache.write_json(cache_path, payload, indent=None)
    except Exception:
        # TAP-6081: still best-effort (a warm cache miss is harmless), but the
        # failure is no longer swallowed silently — a permanently unwritable
        # cache dir used to look identical to a healthy one.
        _log().warning("tools_warm_cache_write_failed", path=str(cache_path), exc_info=True)


# --- MCP streamable-HTTP transport ------------------------------------------
# FastMCP's streamable-HTTP transport (tapps-brain /mcp) is strict about both
# the trailing slash and content negotiation: a POST to /mcp receives 307
# Temporary Redirect → /mcp/, and a POST without these Accept values receives
# 406 Not Acceptable (TAP-516 regression found against brain 3.10.x).
_MCP_ACCEPT_HEADERS: dict[str, str] = {"Accept": "application/json, text/event-stream"}
_HTTP_ERROR_BODY_MAX = 500


def _tenant_override_headers(project_id: str | None) -> dict[str, str]:
    """Per-request ``X-Project-Id`` when a caller overrides the bridge default tenant.

    Cross-project recall (TAP-1257 / tapps-mcp #6) passes ``project_id`` on
    ``tapps_memory`` actions; the HTTP fleet bridge keeps its session-scoped
    default header but merges this override on individual ``tools/call`` posts
    without mutating :attr:`HttpBrainBridge._http_headers`.
    """
    pid = (project_id or "").strip()
    return {"X-Project-Id": pid} if pid else {}


def _raise_with_body(response: httpx.Response, tool_name: str) -> None:
    """Like ``response.raise_for_status()`` but includes the response body.

    httpx's :class:`HTTPStatusError` only carries the status code, so callers
    that wrap it (the bridge's retry loop) lose the actual error detail —
    e.g. ``{"error": "bad_request", "detail": "X-Project-Id header is required"}``
    becomes the opaque message ``"all retries exhausted: ... 400 ..."``. Capture
    up to :data:`_HTTP_ERROR_BODY_MAX` chars of the body so the underlying
    failure reaches the agent.
    """
    if response.status_code < 400:
        return
    try:
        body = response.text[:_HTTP_ERROR_BODY_MAX]
    except Exception:
        body = "<unreadable>"
    raise RuntimeError(f"tapps-brain HTTP {response.status_code} for {tool_name!r}: {body}")



def _log() -> Any:
    """Lazy accessor for the facade's structlog logger.

    A top-level ``import tapps_core.brain_bridge as _facade`` deadlocks when
    THIS module is the one that gets imported first (its own definitions
    aren't done yet when the facade tries to import back from it) — verified
    empirically while wiring the TAP-6736 split. Deferring the import to
    call time (only here, not at every call site) breaks the cycle cleanly.
    """
    import tapps_core.brain_bridge as _facade

    return _facade.logger


class BrainBridgeUnavailable(Exception):  # noqa: N818  (public API name predates the lint rule; renaming would break consumers)
    """Raised when the circuit is open or the bridge is not configured."""


# TAP-1616: tapps-brain's tool_filter raises ``McpError(code=-32602,
# data={"reason": "out_of_profile", ...})`` for gated tools. The wire
# contract (documented in the tapps-brain repo) advertises that shape on
# the JSON-RPC ``error`` envelope, but ``mcp`` 1.27.x's FastMCP HTTP
# transport currently wraps it as ``result.isError=true`` with a text-only
# message — the ``data`` payload never reaches the wire. The pattern below
# parses the canonical denial message so the bridge can surface
# :class:`ToolNotInProfileError` today; once upstream surfaces ``ErrorData``
# correctly the JSON-RPC branch in ``_do_mcp_post`` handles it natively
# and this fallback becomes inert.
_OUT_OF_PROFILE_MESSAGE = re.compile(
    r"Tool '(?P<tool>[^']+)' is not available in profile '(?P<profile>[^']+)'\."
)


def _parse_out_of_profile_message(message: str) -> tuple[str, str] | None:
    """Extract ``(tool, profile)`` from a brain tool-denial message, or None."""
    match = _OUT_OF_PROFILE_MESSAGE.search(message)
    if match is None:
        return None
    return match.group("tool"), match.group("profile")


class BrainMcpError(RuntimeError):
    """Raised when the brain returns a structured JSON-RPC error envelope.

    Preserves the original ``code``, ``data`` and ``tool_name`` so callers can
    discriminate between "tool gated by profile" (EPIC-073) and "tool removed
    from registry" without re-parsing the stringified message. Subclass of
    ``RuntimeError`` to keep ``except RuntimeError`` clauses (and the existing
    ``test_rpc_error_raises`` contract) working.
    """

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        data: Any = None,
        tool_name: str | None = None,
        field: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.data = data
        self.tool_name = tool_name
        self.field = field
        self.detail = detail


class BadJsonError(BrainMcpError):
    """Raised when the brain rejects a ``*_json`` argument as malformed
    (TAP-1967 / TAP-1968 / TAP-1969, v3.19.0+).

    Wire shape: JSON-RPC ``error.data == {"error": "bad_json",
    "field": "<arg-name>", "detail": "<json-decode-message>"}``. Permanent,
    non-retryable caller bug — the brain writes nothing on this path. Callers
    should surface ``field`` + ``detail`` to the agent so the typo is visible.
    """


class ToolNotInProfileError(BrainMcpError):
    """Raised when the brain rejects a tools/call because the tool is hidden
    by the active server-side profile (TAP-1616 — wire contract documented in
    the tapps-brain repo at ``docs/guides/mcp-client-repo-setup.md#profile-wire-contract``).

    Distinct from :class:`BrainMcpError` so callers can ``except`` exactly
    this case and (a) declare a wider ``X-Brain-Profile`` on subsequent
    sessions, or (b) surface the structured failure to the caller for re-
    routing. ``-32601 METHOD_NOT_FOUND`` continues to surface as the base
    ``BrainMcpError`` — the tool is genuinely gone.

    On the wire this is ``-32602 INVALID_PARAMS`` with
    ``data == {"reason": "out_of_profile", "tool": "<name>", "profile": "<name>"}``.
    """

    def __init__(
        self,
        message: str,
        *,
        tool: str,
        profile: str | None,
        data: Any = None,
        suggested_profile: str | None = None,
    ) -> None:
        super().__init__(message, code=-32602, data=data, tool_name=tool)
        self.tool = tool
        self.profile = profile
        # TAP-1972 (v3.19.0+): brain may include the smallest profile that
        # exposes the denied tool. ``None`` when no profile exposes it or the
        # brain pre-dates v3.19.0 — callers must tolerate either.
        self.suggested_profile = suggested_profile


class ProfileMismatchError(ToolNotInProfileError):
    """Raised when the bridge short-circuits a tool call whose name is missing
    from the server-negotiated ``exposed_tools`` set (TAP-1629).

    Where :class:`ToolNotInProfileError` represents a wire-level rejection
    (``-32602`` with ``reason=out_of_profile``), this subclass represents a
    *client-side* preflight rejection produced by :meth:`HttpBrainBridge._negotiate_profile_locked`:
    if the bridge already knows the tool will be denied, it raises this typed
    error before incurring the round-trip. Subclassing :class:`ToolNotInProfileError`
    keeps existing ``except`` clauses working and preserves the
    ``reason=out_of_profile`` ``data`` shape.
    """

    def __init__(
        self,
        message: str,
        *,
        tool: str,
        profile: str | None,
        exposed_tools: frozenset[str] | None = None,
    ) -> None:
        super().__init__(
            message,
            tool=tool,
            profile=profile,
            data={
                "reason": "out_of_profile",
                "tool": tool,
                "profile": profile,
                "transport": "client_preflight",
            },
        )
        self.exposed_tools = exposed_tools


# Regression snapshot captured at TAP-1961 merge time. The live set is
# registered by tapps-mcp from ``server_memory_tools`` dispatch maps; tests
# assert the derived set equals this snapshot.
_BRIDGE_USED_TOOLS_SNAPSHOT: frozenset[str] = frozenset(
    {
        "memory_save",
        "memory_get",
        "memory_delete",
        "memory_search",
        "memory_list",
        "memory_recall",
        "memory_reinforce",
        "memory_supersede",
        "hive_search",
        "hive_status",
        "hive_propagate",
        "agent_register",
        # TAP-1630: knowledge graph surface added by tapps_memory phase 2.
        "memory_find_related",
        "memory_relations",
        "memory_query_relations",
        "brain_get_neighbors",
        "brain_explain_connection",
        # TAP-1631: batch ops added by tapps_memory phase 3 (single round-trip).
        "memory_save_many",
        "memory_recall_many",
        "memory_reinforce_many",
        # TAP-1632: feedback flywheel + brain-health diagnostics surface.
        "feedback_rate",
        "feedback_gap",
        "flywheel_report",
        "flywheel_process",
        "diagnostics_report",
        # TAP-1633: native session memory (replaces the local session_index path).
        "memory_index_session",
        "memory_search_sessions",
        "tapps_brain_session_end",
        # TAP-1938: feedback flywheel — edge and memory feedback recording.
        "brain_record_feedback",
        # TAP-5365 / ADR-0030: brain-owned web research backing tapps_research.
        # Added in brain 3.28.0, which is why the version floor is 3.28.0
        # (ADR-0033).
        "web_research",
        "research_fetch",
        # Memory-profile introspection and switching. Both are in brain's
        # ``full`` profile, so the least-privilege SERVER profile is unchanged.
        "profile_info",
        "profile_switch",
        # Routed by the gc / contradictions / reseed / federate_* / maintain
        # actions in server_memory_tools._ACTION_BRAIN_TOOLS.
        "brain_status",
    }
)

_registered_bridge_used_tools: frozenset[str] | None = None


def register_bridge_used_tools(tools: frozenset[str] | set[str]) -> None:
    """Register the brain MCP tool names tapps-mcp invokes (TAP-1961).

    Called once at ``server_memory_tools`` import time. tapps-core tests that
    do not import tapps-mcp fall back to :data:`_BRIDGE_USED_TOOLS_SNAPSHOT`.
    """
    global _registered_bridge_used_tools
    _registered_bridge_used_tools = frozenset(tools)


def get_bridge_used_tools() -> frozenset[str]:
    """Return the registered bridge tool set, or the regression snapshot."""
    if _registered_bridge_used_tools is not None:
        return _registered_bridge_used_tools
    return _BRIDGE_USED_TOOLS_SNAPSHOT


def __getattr__(name: str) -> frozenset[str]:
    """Backward-compatible lazy alias for :func:`get_bridge_used_tools`."""
    if name == "_BRIDGE_USED_TOOLS":
        return get_bridge_used_tools()
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


# ---------------------------------------------------------------------------
# Capability-profile selection per consumer role (ADR-0012).
#
# tapps-brain gates its tool surface by the ``X-Brain-Profile`` header, and
# from v3.20.0 it enforces that gate on every ``tools/call`` — a tool absent
# from the negotiated profile fails with ``ToolNotInProfileError``. No single
# profile fits every consumer, so each role below names the *least-privilege*
# profile that still spans every tool that role calls:
#
#   SERVER  → "full":       the ``tapps_memory`` facade exercises the whole
#                           read+write+hive+KG+feedback surface
#                           (``_BRIDGE_USED_TOOLS``). ``full`` is the smallest
#                           profile that exposes all of it. Maintenance ops
#                           (``maintenance_gc`` / ``maintenance_consolidate``)
#                           are operator-only, are *not* in
#                           ``_BRIDGE_USED_TOOLS``, and degrade gracefully.
#   OPERATOR→ "operator":   CLI maintenance (gc / consolidate / config / export).
#   READONLY→ "reviewer":   read-only recall/search (e.g. CLI auto-recall,
#                           which calls only ``memory_search``).
#   HOOKS   → "coder":      auto-recall/capture/reinforce + KG reads only.
#   FACADE  → "agent_brain": ``brain_*`` facade only (docs-mcp KG queries).
#
# A consumer overrides any of these via ``memory.brain_profile`` in
# ``.tapps-mcp.yaml`` (or the ``TAPPS_BRAIN_PROFILE`` env var); that value
# wins over the ``default_profile`` passed to :func:`create_brain_bridge`.
# ---------------------------------------------------------------------------
BRAIN_PROFILE_SERVER: str = "full"
BRAIN_PROFILE_OPERATOR: str = "operator"
BRAIN_PROFILE_READONLY: str = "reviewer"
BRAIN_PROFILE_HOOKS: str = "coder"
BRAIN_PROFILE_FACADE: str = "agent_brain"

# Roles whose profile is broad enough that a ``_BRIDGE_USED_TOOLS`` member
# missing from the eager ``tools/list`` is benign deferred-loading (TAP-1985,
# still callable via ``tools/call``) rather than a genuine profile gate.
BRAIN_PROFILES_DEFERRED_OK: frozenset[str] = frozenset(
    {BRAIN_PROFILE_SERVER, BRAIN_PROFILE_OPERATOR}
)

# Intentionally narrow capability profiles — missing bridge tools vs eager
# tools/list is expected; do not warn at session start (TAP-4810).
BRAIN_PROFILES_NARROW_OK: frozenset[str] = frozenset(
    {
        BRAIN_PROFILE_READONLY,
        BRAIN_PROFILE_HOOKS,
        "seeder",
        BRAIN_PROFILE_FACADE,
    }
)


def _classify_mcp_error(exc: BaseException) -> str:
    """Return one of ``"gated"`` / ``"removed"`` / ``"other"`` for a brain failure.

    - ``"gated"``: tool exists but the caller's profile excludes it. Covers
      both the legacy ``{"error": "tool_not_in_profile"}`` shape and the
      TAP-1579 / TAP-1616 wire contract (``-32602`` with
      ``{"reason": "out_of_profile"}``), the latter raised as
      :class:`ToolNotInProfileError`.
    - ``"removed"``: tool name is not registered at all — surfaces as the
      generic ``"Unknown tool"`` string in the error message.
    - ``"other"``: anything else (network, timeout, payload validation, …).
    """
    if isinstance(exc, ToolNotInProfileError):
        return "gated"
    chain_parts: list[str] = [str(exc)]
    cause = exc.__cause__
    if cause is not None:
        chain_parts.append(str(cause))
        if isinstance(cause, ToolNotInProfileError):
            return "gated"
        data = getattr(cause, "data", None)
        if isinstance(data, dict) and (
            data.get("error") == "tool_not_in_profile" or data.get("reason") == "out_of_profile"
        ):
            return "gated"
    data = getattr(exc, "data", None)
    if isinstance(data, dict) and (
        data.get("error") == "tool_not_in_profile" or data.get("reason") == "out_of_profile"
    ):
        return "gated"
    chain = " ".join(chain_parts)
    if "Unknown tool" in chain:
        return "removed"
    return "other"


