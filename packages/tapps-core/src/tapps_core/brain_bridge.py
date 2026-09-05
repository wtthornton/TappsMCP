"""BrainBridge: async wrapper over tapps-brain.

Two transport modes are supported:

- **HTTP** (recommended): :class:`HttpBrainBridge` routes all calls through the
  tapps-brain HTTP MCP API at ``{brain_http_url}/mcp``. Requires only
  ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` and ``TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN``.
  Selected automatically by :func:`create_brain_bridge` when ``brain_http_url`` is set.

- **In-process** (legacy/local-dev): :class:`BrainBridge` wraps a local
  :class:`tapps_brain.AgentBrain` and offloads sync calls via ``asyncio.to_thread``.
  Requires ``TAPPS_BRAIN_DATABASE_URL``.

Both share the same circuit-breaker, exponential-backoff retry, and offline write-queue
primitives.

Usage::

    from tapps_core.brain_bridge import create_brain_bridge

    bridge = create_brain_bridge(settings)  # None if neither transport is configured
    if bridge:
        results = await bridge.search("query")

Module layout (TAP-6736)
~~~~~~~~~~~~~~~~~~~~~~~~
This facade re-exports the full public surface but the implementation lives in
sibling modules, split out to bring the megafile under the quality gate:

- :mod:`tapps_core.brain_bridge_errors` — constants, helpers, exception hierarchy.
- :mod:`tapps_core.brain_bridge_inprocess` (+ ``_inprocess_core`` / ``_inprocess_ops``)
  — the in-process :class:`BrainBridge`.
- :mod:`tapps_core.brain_bridge_http_session` — HTTP session/negotiation/POST layer.
- :mod:`tapps_core.brain_bridge_http_health` — HTTP health/auth/close probes.
- :mod:`tapps_core.brain_bridge_http_memory` — HTTP memory CRUD + KG reads.
- :mod:`tapps_core.brain_bridge_http_kg_hive` — HTTP KG-write/hive/feedback/session/maintenance.

:class:`HttpBrainBridge` is composed here from the four HTTP mixins plus the
in-process :class:`BrainBridge` base so ``isinstance(bridge, HttpBrainBridge)``
and ``isinstance(bridge, BrainBridge)`` both continue to hold.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple

import httpx
import structlog
from packaging.version import InvalidVersion, Version

from tapps_core.brain_bridge_errors import (
    _BRAIN_HEALTH_TIMEOUT_SECONDS,
    _BRAIN_VERSION_CEILING,
    _BRAIN_VERSION_FLOOR,
    _BRIDGE_USED_TOOLS_SNAPSHOT,
    _CB_FAILURE_THRESHOLD,
    _CB_RESET_SECONDS,
    _MCP_ACCEPT_HEADERS,
    _TOOLS_CACHE_TTL_SECONDS,
    _WRITE_QUEUE_CAP,
    BRAIN_PROFILE_FACADE,
    BRAIN_PROFILE_HOOKS,
    BRAIN_PROFILE_OPERATOR,
    BRAIN_PROFILE_READONLY,
    BRAIN_PROFILE_SERVER,
    BRAIN_PROFILES_DEFERRED_OK,
    BRAIN_PROFILES_NARROW_OK,
    BadJsonError,
    BrainBridgeUnavailable,
    BrainMcpError,
    ProfileMismatchError,
    ToolNotInProfileError,
    _classify_mcp_error,
    _read_tools_warm_cache,
    _tenant_override_headers,
    _write_tools_warm_cache,
    get_bridge_used_tools,
    register_bridge_used_tools,
)
from tapps_core.brain_bridge_http_health import _HttpHealthMixin
from tapps_core.brain_bridge_http_kg_hive import _HttpKgHiveMixin
from tapps_core.brain_bridge_http_memory import _HttpMemoryMixin
from tapps_core.brain_bridge_http_session import _HttpSessionMixin
from tapps_core.brain_bridge_inprocess import BrainBridge

logger = structlog.get_logger(__name__)

__all__ = [
    "BRAIN_PROFILES_DEFERRED_OK",
    "BRAIN_PROFILES_NARROW_OK",
    "BRAIN_PROFILE_FACADE",
    "BRAIN_PROFILE_HOOKS",
    "BRAIN_PROFILE_OPERATOR",
    "BRAIN_PROFILE_READONLY",
    "BRAIN_PROFILE_SERVER",
    "_BRAIN_VERSION_FLOOR",
    "_BRIDGE_USED_TOOLS_SNAPSHOT",
    "_CB_FAILURE_THRESHOLD",
    "_CB_RESET_SECONDS",
    "_MCP_ACCEPT_HEADERS",
    "_TOOLS_CACHE_TTL_SECONDS",
    "_WRITE_QUEUE_CAP",
    "BadJsonError",
    "BrainBridge",
    "BrainBridgeUnavailable",
    "BrainMcpError",
    "HttpBrainBridge",
    "ProfileMismatchError",
    "ToolNotInProfileError",
    "_classify_mcp_error",
    "_read_tools_warm_cache",
    "_tenant_override_headers",
    "_write_tools_warm_cache",
    "check_brain_version",
    "create_brain_bridge",
    "get_bridge_used_tools",
    "register_bridge_used_tools",
]
# NOTE: ``_BRIDGE_USED_TOOLS`` is intentionally absent from ``__all__`` — it is
# resolved dynamically via the module ``__getattr__`` below (Ruff's F822 flags
# it as "undefined" if listed, since it has no real module-level binding), but
# ``from tapps_core.brain_bridge import _BRIDGE_USED_TOOLS`` still works.


def __getattr__(name: str) -> frozenset[str]:
    """Backward-compatible lazy alias for :func:`get_bridge_used_tools`."""
    if name == "_BRIDGE_USED_TOOLS":
        return get_bridge_used_tools()
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


# -----------------------------------------------------------------------------
# HTTP transport (TAP-596)
# -----------------------------------------------------------------------------


class HttpBrainBridge(_HttpKgHiveMixin, _HttpMemoryMixin, _HttpHealthMixin, _HttpSessionMixin, BrainBridge):
    """BrainBridge that routes all calls through the tapps-brain HTTP MCP API.

    Selected by :func:`create_brain_bridge` when ``settings.memory.brain_http_url``
    (or ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL``) is non-empty.  ``TAPPS_BRAIN_DATABASE_URL``
    is **not** required in this path.

    All data methods use :meth:`_http_mcp_call` which wraps the same circuit-breaker /
    exponential-backoff retry / offline write-queue logic as the in-process path.

    MCP JSON-RPC transport
    ~~~~~~~~~~~~~~~~~~~~~~
    Each call POSTs a ``tools/call`` request to ``{brain_http_url}/mcp``::

        POST {brain_http_url}/mcp
        Content-Type: application/json
        Authorization: Bearer <token>
        X-Project-Id: <slug>
        X-Agent-Id: <id>

        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "<tool>", "arguments": {...}}}

    Tool name mapping (tapps-brain-http MCP surface)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ========================  =====================
    BrainBridge method        MCP tool name
    ========================  =====================
    search                    memory_search
    get                       memory_get
    list_memories             memory_list
    recall_for_prompt         memory_recall
    save                      memory_save
    delete                    memory_delete
    reinforce                 memory_reinforce
    supersede                 memory_supersede
    gc                        maintenance_gc (operator profile only)
    consolidate               maintenance_consolidate (operator profile only)
    hive_search               hive_search
    hive_status               hive_status
    hive_propagate            hive_propagate
    agent_register            agent_register
    ========================  =====================

    Verify this mapping against the live tapps-brain-http server when deploying.

    Composed from :class:`_HttpKgHiveMixin` (KG-write/hive/feedback/session/
    maintenance), :class:`_HttpMemoryMixin` (memory CRUD + KG reads),
    :class:`_HttpHealthMixin` (health/auth/close probes),
    :class:`_HttpSessionMixin` (session handshake, negotiation, POST layer),
    and :class:`BrainBridge` (shared circuit-breaker / retry primitives) —
    see the module docstring for why the implementation lives in five files
    (TAP-6736).
    """

    is_http_mode: bool = True


# -----------------------------------------------------------------------------
# Remote brain version probe (TAP-519)
# -----------------------------------------------------------------------------


def check_brain_version(
    brain_http_url: str,
    *,
    floor: str = _BRAIN_VERSION_FLOOR,
    ceiling: str = _BRAIN_VERSION_CEILING,
    timeout: float = _BRAIN_HEALTH_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe a remote tapps-brain's ``/health`` endpoint and validate its version.

    Intended for startup use: GETs ``{brain_http_url}/health`` (no auth — the
    endpoint is unauthenticated as of tapps-brain v3.8.0) and compares the
    reported ``version`` against the pinned floor/ceiling range declared in
    ``packages/tapps-core/pyproject.toml``.

    Return shape matches the ``health_check()`` style used elsewhere in this
    module so callers can fold the result into a larger health payload::

        {
            "ok": bool,
            "skipped": bool,        # True when brain_http_url is empty
            "degraded": bool,       # True on network / parse failure (non-fatal)
            "url": str,
            "floor": str,
            "ceiling": str,
            "version": str | None,  # reported by brain, may be None on failure
            "errors": list[str],
            "warnings": list[str],
        }

    When ``brain_http_url`` is empty (the default for in-process AgentBrain
    deployments) the probe is skipped and ``ok`` is True — the caller has no
    remote brain to validate.
    """
    result: dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "degraded": False,
        "url": brain_http_url,
        "floor": floor,
        "ceiling": ceiling,
        "version": None,
        "errors": [],
        "warnings": [],
    }

    if not brain_http_url:
        result["skipped"] = True
        return result

    health_url = brain_http_url.rstrip("/") + "/health"

    try:
        response = httpx.get(health_url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        # Network / HTTP failure — don't block bridge creation, but mark
        # degraded so operators see the issue in any surfacing health field.
        msg = f"tapps-brain health probe failed at {health_url}: {exc}"
        logger.warning("brain_bridge.version_check.network_error", error=str(exc), url=health_url)
        result["ok"] = False
        result["degraded"] = True
        result["warnings"].append(msg)
        return result
    except ValueError as exc:
        # JSON decode failure
        msg = f"tapps-brain health response at {health_url} was not valid JSON: {exc}"
        logger.warning("brain_bridge.version_check.bad_json", error=str(exc), url=health_url)
        result["ok"] = False
        result["degraded"] = True
        result["warnings"].append(msg)
        return result

    raw_version = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(raw_version, str) or not raw_version:
        msg = f"tapps-brain health response at {health_url} missing 'version' field"
        logger.error("brain_bridge.version_check.missing_version", url=health_url, payload=payload)
        result["ok"] = False
        result["errors"].append(msg)
        return result

    result["version"] = raw_version

    try:
        actual = Version(raw_version)
        floor_v = Version(floor)
        ceiling_v = Version(ceiling)
    except InvalidVersion as exc:
        msg = f"tapps-brain reported unparseable version {raw_version!r}: {exc}"
        logger.error("brain_bridge.version_check.invalid_version", version=raw_version)
        result["ok"] = False
        result["errors"].append(msg)
        return result

    if actual < floor_v or actual >= ceiling_v:
        msg = (
            f"tapps-brain version {raw_version} does not satisfy required range "
            f">={floor},<{ceiling} (pinned in packages/tapps-core/pyproject.toml)"
        )
        logger.error(
            "brain_bridge.version_check.mismatch",
            actual=raw_version,
            floor=floor,
            ceiling=ceiling,
        )
        result["ok"] = False
        result["errors"].append(msg)
        return result

    logger.info(
        "brain_bridge.version_check.ok",
        version=raw_version,
        floor=floor,
        ceiling=ceiling,
    )
    return result


# -----------------------------------------------------------------------------
# Factory
# -----------------------------------------------------------------------------


class _InProcessConfig(NamedTuple):
    """Resolved settings for the in-process :class:`BrainBridge` path.

    Extracted from :func:`create_brain_bridge` (TAP-6736) to cut its
    cyclomatic complexity — pure refactor, no behavior change.
    """

    project_root: str | None
    profile: str
    hive_dsn: str | None
    project_id: str
    pg_pool_max_waiting: int
    pg_pool_max_lifetime_seconds: int


def _resolve_inprocess_dsn(settings: Any) -> str:
    """Resolve the Postgres DSN for the in-process path from settings or env."""
    dsn = ""
    if settings is not None:
        memory = getattr(settings, "memory", None)
        if memory is not None:
            dsn = str(getattr(memory, "database_url", "") or "")
    if not dsn:
        dsn = os.environ.get("TAPPS_BRAIN_DATABASE_URL", "")
    return dsn


def _resolve_inprocess_settings(settings: Any) -> _InProcessConfig:
    """Resolve project root / profile / hive DSN / pool tuning from settings."""
    project_root: str | None = None
    profile = "repo-brain"
    hive_dsn: str | None = None
    project_id: str = ""
    pg_pool_max_waiting: int = 0
    pg_pool_max_lifetime_seconds: int = 0

    if settings is not None:
        project_root = str(getattr(settings, "project_root", None) or "")
        memory = getattr(settings, "memory", None)
        if memory is not None:
            profile = str(getattr(memory, "profile", None) or "repo-brain")
            raw_hive = str(getattr(memory, "hive_dsn", None) or "")
            hive_dsn = raw_hive or None
            project_id = str(getattr(memory, "project_id", "") or "")
            pg_pool_max_waiting = int(getattr(memory, "pg_pool_max_waiting", 0) or 0)
            pg_pool_max_lifetime_seconds = int(
                getattr(memory, "pg_pool_max_lifetime_seconds", 0) or 0
            )

    return _InProcessConfig(
        project_root=project_root,
        profile=profile,
        hive_dsn=hive_dsn,
        project_id=project_id,
        pg_pool_max_waiting=pg_pool_max_waiting,
        pg_pool_max_lifetime_seconds=pg_pool_max_lifetime_seconds,
    )


def _apply_inprocess_env_overrides(config: _InProcessConfig) -> None:
    """Apply the resolved in-process settings as env vars for AgentBrain."""
    # ADR-010 / EPIC-069: declare the registered project slug on the wire.
    if config.project_id:
        os.environ["TAPPS_BRAIN_PROJECT"] = config.project_id

    # EPIC-066: pool tuning pass-through; only set when non-zero.
    if config.pg_pool_max_waiting:
        os.environ["TAPPS_BRAIN_PG_POOL_MAX_WAITING"] = str(config.pg_pool_max_waiting)
    if config.pg_pool_max_lifetime_seconds:
        os.environ["TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS"] = str(
            config.pg_pool_max_lifetime_seconds
        )


def create_brain_bridge(settings: Any = None, *, default_profile: str = "") -> BrainBridge | None:
    """Create a :class:`BrainBridge` from settings or environment.

    Dispatch order:

    1. When ``settings.memory.brain_http_url`` is set (or the env var
       ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL``), create an :class:`HttpBrainBridge`
       that routes all calls through the tapps-brain HTTP MCP API.
       ``TAPPS_BRAIN_DATABASE_URL`` is **not** required in this path.
    2. Otherwise fall back to the in-process :class:`BrainBridge` wrapping a
       local :class:`tapps_brain.AgentBrain`. Requires ``TAPPS_BRAIN_DATABASE_URL``
       (or ``settings.memory.database_url``).
    3. Return ``None`` when neither transport is configured.

    Args:
        settings: Optional settings object. When omitted, transport and auth are
            resolved from environment variables only.
        default_profile: Fallback ``X-Brain-Profile`` header value for the HTTP
            path (TAP-1924/1925). Applied only when no explicit profile is
            configured via ``settings.memory.brain_profile`` *and* the
            ``TAPPS_BRAIN_PROFILE`` env var is unset. Callers should pass the
            minimum profile that covers their tool surface (e.g. ``"coder"`` for
            the tapps-mcp server, ``"agent_brain"`` for docs-mcp). The empty
            string (default) preserves the existing behaviour — no header sent,
            server-side default profile applies.
    """
    # --- Resolve transport settings ------------------------------------------
    brain_http_url: str = ""
    if settings is not None:
        memory = getattr(settings, "memory", None)
        if memory is not None:
            raw_http_url = getattr(memory, "brain_http_url", "")
            # Guard against MagicMock in tests: only treat str values as URLs.
            brain_http_url = raw_http_url if isinstance(raw_http_url, str) else ""
    if not brain_http_url:
        brain_http_url = os.environ.get("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "")

    # --- HTTP path -----------------------------------------------------------
    if brain_http_url:
        return _create_http_bridge(brain_http_url, settings, default_profile=default_profile)

    # --- In-process path -----------------------------------------------------
    from tapps_brain import AgentBrain

    from tapps_core.agent_identity import get_stable_agent_id

    dsn = _resolve_inprocess_dsn(settings)
    if not dsn:
        return None
    os.environ.setdefault("TAPPS_BRAIN_DATABASE_URL", dsn)

    inprocess_config = _resolve_inprocess_settings(settings)
    _apply_inprocess_env_overrides(inprocess_config)

    try:
        brain = AgentBrain(
            # Ruling 9 (TAP-6701): logical agent id (brain_project_id / project_id
            # / dir name), matching the HTTP path's X-Agent-Id resolver — not a
            # hardcoded literal, so both bridge paths agree.
            agent_id=get_stable_agent_id(settings),
            project_dir=inprocess_config.project_root or None,
            profile=inprocess_config.profile,
            hive_dsn=inprocess_config.hive_dsn,
        )
    except Exception as exc:
        logger.warning("brain_bridge.init_failed", error=str(exc))
        return None

    bridge = BrainBridge(brain)
    # TAP-523: validate DSN reachability + pool config before returning.
    report = bridge.health_check()
    if not report["ok"]:
        logger.warning(
            "brain_bridge.health_check_failed",
            errors=report["errors"],
            warnings=report["warnings"],
        )
        with contextlib.suppress(Exception):
            brain.close()
        return None
    if report["warnings"]:
        logger.info(
            "brain_bridge.health_check_warnings",
            warnings=report["warnings"],
        )

    # TAP-519: version probe is no-op when no HTTP URL is set.
    version_check = check_brain_version("")
    bridge._set_version_check(version_check)
    # TAP-517: register shutdown hooks for offline write queue drain.
    _register_shutdown_hooks(bridge)
    return bridge


def _create_http_bridge(
    brain_http_url: str, settings: Any, *, default_profile: str = ""
) -> BrainBridge | None:
    """Create an :class:`HttpBrainBridge` for the tapps-brain HTTP API."""
    from tapps_core.brain_auth import BrainAuthConfigError, build_brain_headers

    headers: dict[str, str] = {}
    if settings is not None:
        try:
            headers = build_brain_headers(settings)
        except BrainAuthConfigError as exc:
            logger.warning("brain_bridge.http_auth_error", error=str(exc))
            return None
    else:
        token = os.environ.get("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN", "")
        project_id = os.environ.get("TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if project_id:
            headers["X-Project-Id"] = project_id

    # TAP-1924/1925: apply the caller-supplied default profile when no explicit
    # profile was resolved by build_brain_headers (settings.memory.brain_profile
    # or TAPPS_BRAIN_PROFILE env) and no TAPPS_BRAIN_PROFILE override is present.
    # Setting the header here means HttpBrainBridge.__init__'s env-fallback
    # path will see it already set and skip the re-derive.
    if "X-Brain-Profile" not in headers and default_profile:
        env_profile = os.environ.get("TAPPS_BRAIN_PROFILE", "").strip()
        if not env_profile:
            headers["X-Brain-Profile"] = default_profile

    if "Authorization" not in headers:
        logger.warning(
            "brain_bridge.http_auth_missing",
            http_url=brain_http_url,
            hint=(
                "HTTP bridge has no Authorization header — every /mcp call will "
                "return 401/403. Set TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN in the "
                "environment or memory.brain_auth_token in .tapps-mcp.yaml. "
                "Export TAPPS_BRAIN_AUTH_TOKEN in the shell for MCP ${...} "
                "substitution and CLI fallback (same value)."
            ),
        )

    # TAP-1927: resolve the project-local cache directory for the tools-list
    # pre-warm file.  Use settings.project_root when available; fall back to
    # the TAPPS_PROJECT_ROOT env var; finally None (disables caching).
    _cache_dir: Path | None = None
    if settings is not None:
        _proj_root = getattr(settings, "project_root", None)
        if _proj_root:
            _cache_dir = Path(str(_proj_root)) / ".tapps-mcp"
    if _cache_dir is None:
        _env_root = os.environ.get("TAPPS_PROJECT_ROOT", "").strip()
        if _env_root:
            _cache_dir = Path(_env_root) / ".tapps-mcp"

    bridge = HttpBrainBridge(brain_http_url, headers, cache_dir=_cache_dir)

    version_check = check_brain_version(brain_http_url)
    if not version_check["ok"] and not version_check["skipped"]:
        logger.error(
            "brain_bridge.version_check_failed",
            errors=version_check["errors"],
            warnings=version_check["warnings"],
            version=version_check["version"],
            floor=version_check["floor"],
            ceiling=version_check["ceiling"],
        )
    bridge._set_version_check(version_check)
    _register_shutdown_hooks(bridge)
    return bridge


_shutdown_hooks_registered: bool = False


_PROCESS_START_MONOTONIC: float = time.monotonic()

# Written to fd 2 the instant a fatal signal is caught, before any unwinding.
# Grep key for the fleet logs and for ``journalctl --user -g``.
SIGNAL_EXIT_LOG_PREFIX = "tapps.signal_exit"


def format_signal_exit_line(signum: int, *, now_monotonic: float | None = None) -> str:
    """Render the one-line death record the SIGTERM handler writes.

    Split out of the handler so it is unit-testable — the handler body itself
    is the one place a normal test cannot drive.
    """
    try:
        name = signal.Signals(signum).name
    except ValueError:
        name = "UNKNOWN"
    monotonic = time.monotonic() if now_monotonic is None else now_monotonic
    uptime = max(0.0, monotonic - _PROCESS_START_MONOTONIC)
    return (
        f"{SIGNAL_EXIT_LOG_PREFIX} signal={name} signum={signum} "
        f"pid={os.getpid()} ppid={os.getppid()} exit_status=0 "
        f"uptime_s={uptime:.1f}\n"
    )


def _register_shutdown_hooks(bridge: BrainBridge) -> None:
    """Wire atexit + SIGTERM drain hooks for *bridge* (TAP-517).

    atexit covers normal interpreter shutdown and ``sys.exit``. SIGTERM by
    default kills the process without running atexit, so we route it through
    ``sys.exit(0)`` to get the bounded drain. Signal registration only works
    on the main thread of the main interpreter, so we swallow failures from
    worker threads / embedded contexts.
    """
    global _shutdown_hooks_registered
    if _shutdown_hooks_registered:
        return

    atexit.register(bridge.close)

    def _sigterm_drain_exit(signum: int, _frame: Any) -> None:
        # TAP-6053: this handler used to be a bare ``sys.exit(0)``. That made
        # every signalled death indistinguishable from a clean one — exit
        # status 0, no record that a signal arrived at all, and (because the
        # SystemExit unwinds from wherever the loop happened to be) only an
        # incidental ``SystemExit: 0`` traceback out of ``selectors.poll``.
        # Both 2026-08-13 fleet deaths left exactly that and nothing else.
        # Write the cause to fd 2 *before* unwinding. ``os.write`` on an
        # already-open descriptor is safe from a handler; structlog's lock is
        # not — taking it here can deadlock against an interrupted emit.
        try:
            os.write(2, format_signal_exit_line(signum).encode("utf-8", "replace"))
        except (OSError, ValueError):
            pass
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, _sigterm_drain_exit)
    except (OSError, ValueError):
        # Non-main-thread, embedded interpreter, or platform without
        # SIGTERM — atexit still covers normal shutdown paths.
        logger.debug("brain_bridge.sigterm_register_skipped")

    _shutdown_hooks_registered = True
