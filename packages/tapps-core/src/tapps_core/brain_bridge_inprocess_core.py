"""In-process circuit-breaker / write-queue / lifecycle mixin for :class:`BrainBridge`.

Split out of ``brain_bridge_inprocess.py`` (TAP-6736, further split). No
behavior change: each method body below is moved byte-for-byte. Composed as
``_InProcessCoreMixin`` alongside ``_InProcessOpsMixin`` into the public
``BrainBridge`` class.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from tapps_brain import AgentBrain

from tapps_core.brain_bridge_errors import (
    _BRAIN_VERSION_CEILING,
    _BRAIN_VERSION_FLOOR,
    _CB_FAILURE_THRESHOLD,
    _CB_RESET_SECONDS,
    _DRAIN_DEADLINE_SECONDS,
    _RETRY_ATTEMPTS,
    _RETRY_BASE,
    _RETRY_MAX,
    _WRITE_QUEUE_CAP,
    BrainBridgeUnavailable,
)

_T = TypeVar("_T")



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


class _InProcessCoreMixin:
    """Circuit breaker, retry wrapper, offline write queue, and lifecycle."""

    def __init__(self, brain: AgentBrain) -> None:
        self._brain = brain
        self._failures: int = 0
        self._open_at: float | None = None
        self._write_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_WRITE_QUEUE_CAP)
        self._drain_task: asyncio.Task[None] | None = None
        # TAP-519: populated by ``create_brain_bridge`` when a remote brain
        # HTTP URL is configured. Callers (e.g. tapps_session_start) can read
        # ``bridge.version_check`` to surface the result in their health field.
        self._version_check: dict[str, Any] = {
            "ok": True,
            "skipped": True,
            "degraded": False,
            "url": "",
            "floor": _BRAIN_VERSION_FLOOR,
            "ceiling": _BRAIN_VERSION_CEILING,
            "version": None,
            "errors": [],
            "warnings": [],
        }
        # TAP-2014: optional approval gate for hive promotion.
        # Set by the caller (tapps-mcp server_helpers) after bridge creation.
        # When set, hive_propagate checks this callable(memory_key) -> bool
        # before propagating each entry; refused entries are counted separately.
        self.elevation_guard: Callable[[str], bool] | None = None

    # -------------------------------------------------------------------------
    # Circuit breaker
    # -------------------------------------------------------------------------

    @property
    def circuit_open(self) -> bool:
        """True when the circuit is open (calls blocked)."""
        if self._open_at is None:
            return False
        if time.monotonic() - self._open_at >= _CB_RESET_SECONDS:
            self._failures = 0
            self._open_at = None
            return False
        return True

    @property
    def queue_depth(self) -> int:
        """Number of writes currently queued."""
        return self._write_queue.qsize()

    @property
    def version_check(self) -> dict[str, Any]:
        """Result of the remote tapps-brain version probe (TAP-519).

        When no ``brain_http_url`` was configured at factory time, this
        returns a ``{"ok": True, "skipped": True, ...}`` sentinel.
        """
        return dict(self._version_check)

    def _set_version_check(self, result: dict[str, Any]) -> None:
        """Populate the version-check payload (factory-only helper)."""
        self._version_check = result

    @property
    def circuit_state(self) -> str:
        """Circuit state as a stable string — ``"open"`` or ``"closed"``.

        Exposed via :meth:`status` for server_info consumers so they do not
        need to consume the mutating :attr:`circuit_open` check.
        """
        return "open" if self.circuit_open else "closed"

    def status(self) -> dict[str, Any]:
        """Non-blocking diagnostic snapshot of bridge health (TAP-517).

        Safe to call from read-only paths like ``tapps_server_info``.
        """
        return {
            "queue_depth": self.queue_depth,
            "queue_cap": _WRITE_QUEUE_CAP,
            "circuit_state": self.circuit_state,
            "failures": self._failures,
        }

    def _record_success(self) -> None:
        self._failures = 0

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= _CB_FAILURE_THRESHOLD:
            if self._open_at is None:
                _log().warning("brain_bridge.circuit_opened", failures=self._failures)
            self._open_at = time.monotonic()

    # -------------------------------------------------------------------------
    # Core call wrapper
    # -------------------------------------------------------------------------

    async def _call(self, fn: Callable[[], _T]) -> _T:
        """Run *fn* in a thread with retry and circuit-breaker enforcement."""
        if self.circuit_open:
            raise BrainBridgeUnavailable("circuit open")

        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                result: _T = await asyncio.to_thread(fn)
                self._record_success()
                return result
            except BrainBridgeUnavailable:
                raise
            except Exception as exc:
                last_exc = exc
                self._record_failure()
                if self.circuit_open:
                    break
                if attempt < _RETRY_ATTEMPTS - 1:
                    delay = min(_RETRY_BASE * (2**attempt), _RETRY_MAX)
                    delay += random.uniform(0, delay * 0.1)  # noqa: S311  (jitter, not crypto)
                    await asyncio.sleep(delay)

        raise BrainBridgeUnavailable(f"all retries exhausted: {last_exc}") from last_exc

    # -------------------------------------------------------------------------
    # Write queue
    # -------------------------------------------------------------------------

    def _enqueue_write(self, entry: dict[str, Any]) -> bool:
        """Queue a write for later drain. Returns False when queue is full.

        Logs a ``brain_write_queue_full`` warning on overflow (TAP-517) so
        operators can see when the offline buffer is dropping writes.
        """
        try:
            self._write_queue.put_nowait(entry)
            return True
        except asyncio.QueueFull:
            _log().warning(
                "brain_write_queue_full",
                queue_depth=self._write_queue.qsize(),
                queue_cap=_WRITE_QUEUE_CAP,
                dropped_key=entry.get("key"),
            )
            return False

    async def _drain_write_queue(self) -> None:
        # Claim self._drain_task so the recursive _maybe_start_drain triggered
        # by each self.save() below sees an active task and does not spawn a
        # parallel drain that races against this one.
        self._drain_task = asyncio.current_task()
        while not self._write_queue.empty():
            if self.circuit_open:
                break
            try:
                entry = self._write_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                await self._replay_queued_write(entry)
            except Exception as exc:
                _log().warning("brain_bridge.drain_failed", error=str(exc))

    async def _replay_queued_write(self, entry: dict[str, Any]) -> None:
        """Replay one queued write entry.

        The base queue only ever holds ``save`` kwargs; HttpBrainBridge
        overrides this to also route KG-event entries (TAP-1947) back through
        :meth:`record_kg_event`.
        """
        await self.save(**entry)

    def _maybe_start_drain(self) -> None:
        if (
            not self.circuit_open
            and not self._write_queue.empty()
            and (self._drain_task is None or self._drain_task.done())
        ):
            try:
                loop = asyncio.get_running_loop()
                self._drain_task = loop.create_task(self._drain_write_queue())
            except RuntimeError:
                pass


    # -------------------------------------------------------------------------
    # Raw store access (for callers that need the full MemoryStore API)
    # -------------------------------------------------------------------------

    @property
    def store(self) -> Any:
        """Return the underlying ``MemoryStore`` (Postgres-backed in v3).

        Use this for operations not yet covered by the async BrainBridge API
        (e.g. ``snapshot()``, ``history()``, ``update_fields()``). Callers that
        use ``bridge.store`` directly bypass the circuit breaker — prefer async
        methods when available.
        """
        return self._brain.store

    # -------------------------------------------------------------------------
    # Startup health check (TAP-523)
    # -------------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """Synchronously probe DSN reachability and pool config validity.

        Intended to run once at MCP server startup so misconfiguration is
        surfaced at session-start time rather than inside the first memory
        tool call. Returns a structured report; callers decide whether to
        fail fast based on ``ok``.

        Checks performed:

        1. DSN reachability — calls ``store.count()`` to force a connection.
        2. Pool config validity — inspects the
           ``TAPPS_BRAIN_PG_POOL_MAX_WAITING`` and
           ``TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS`` env vars (if set)
           and rejects non-integer / negative values.
        3. Optional native health — calls ``store.health()`` when available
           for extra diagnostics (current count, schema version, etc.).
        """
        errors: list[str] = []
        warnings: list[str] = []
        details: dict[str, Any] = {}

        # --- DSN reachability ------------------------------------------------
        dsn_reachable = False
        try:
            entry_count = self._brain.store.count()
            dsn_reachable = True
            details["entry_count"] = int(entry_count)
        except Exception as exc:
            errors.append(f"dsn_unreachable: {exc}")

        # --- Pool config validity -------------------------------------------
        pool_config_valid = True
        for env_name in (
            "TAPPS_BRAIN_PG_POOL_MAX_WAITING",
            "TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS",
        ):
            raw = os.environ.get(env_name, "")
            if not raw:
                continue
            try:
                value = int(raw)
            except ValueError:
                errors.append(f"invalid_pool_config: {env_name}={raw!r} is not an integer")
                pool_config_valid = False
                continue
            if value < 0:
                errors.append(f"invalid_pool_config: {env_name}={value} must be >= 0")
                pool_config_valid = False
                continue
            details[env_name.lower()] = value
            if env_name == "TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS" and 0 < value < 30:
                warnings.append(
                    f"{env_name}={value}s is unusually short "
                    "(connections will churn heavily; minimum 30s recommended)"
                )

        # --- Optional native health ------------------------------------------
        native_health_ok = False
        health_fn = getattr(self._brain.store, "health", None)
        if callable(health_fn):
            try:
                raw_health = health_fn()
                native_health_ok = True
                if hasattr(raw_health, "model_dump"):
                    details["native_health"] = raw_health.model_dump()
                elif isinstance(raw_health, dict):
                    details["native_health"] = raw_health
                else:
                    details["native_health"] = {"value": str(raw_health)}
            except Exception as exc:
                warnings.append(f"native_health_probe_failed: {exc}")

        ok = not errors and dsn_reachable and pool_config_valid
        return {
            "ok": ok,
            "dsn_reachable": dsn_reachable,
            "pool_config_valid": pool_config_valid,
            "native_health_ok": native_health_ok,
            "errors": errors,
            "warnings": warnings,
            "details": details,
        }

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def drain_blocking(self, timeout: float = _DRAIN_DEADLINE_SECONDS) -> dict[str, int]:
        """Synchronously drain the offline write queue (TAP-517).

        Bypasses ``_call`` / ``asyncio.to_thread`` because this path runs from
        shutdown hooks (atexit / SIGTERM) where the event loop may already be
        gone. Bounded by *timeout* seconds; remaining entries are left on the
        queue and reported in the return dict.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        drained = 0
        dropped = 0
        while not self._write_queue.empty():
            if time.monotonic() >= deadline:
                break
            try:
                entry = self._write_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                self._brain.store.save(**entry)
                drained += 1
            except Exception as exc:
                _log().warning(
                    "brain_bridge.drain_blocking_entry_failed",
                    error=str(exc),
                    key=entry.get("key"),
                )
                dropped += 1
        remaining = self._write_queue.qsize()
        if drained or dropped or remaining:
            _log().info(
                "brain_bridge.drain_blocking_complete",
                drained=drained,
                dropped=dropped,
                remaining=remaining,
                deadline_exceeded=time.monotonic() >= deadline,
            )
        return {"drained": drained, "dropped": dropped, "remaining": remaining}

    def close(self, drain_timeout: float = _DRAIN_DEADLINE_SECONDS) -> None:
        """Drain queued writes (bounded) then close the AgentBrain pool."""
        try:
            self.drain_blocking(drain_timeout)
        except Exception as exc:
            _log().warning("brain_bridge.drain_on_close_failed", error=str(exc))
        try:
            self._brain.close()
        except Exception as exc:
            _log().warning("brain_bridge.close_failed", error=str(exc))


# -----------------------------------------------------------------------------
# HTTP transport (TAP-596)
# -----------------------------------------------------------------------------


