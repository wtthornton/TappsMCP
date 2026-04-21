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
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import os
import random
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import httpx
import structlog
from packaging.version import InvalidVersion, Version

if TYPE_CHECKING:
    from tapps_brain import AgentBrain

logger = structlog.get_logger(__name__)

_T = TypeVar("_T")

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
_BRAIN_VERSION_FLOOR: str = "3.7.2"
_BRAIN_VERSION_CEILING: str = "4.0.0"
_BRAIN_HEALTH_TIMEOUT_SECONDS: float = 5.0

# --- Shutdown drain ---------------------------------------------------------
# Bounded deadline (seconds) that ``close`` / ``drain_blocking`` waits for the
# offline write queue to drain on shutdown before giving up (TAP-517).
_DRAIN_DEADLINE_SECONDS: float = 5.0

# --- MCP streamable-HTTP transport ------------------------------------------
# FastMCP's streamable-HTTP transport (tapps-brain /mcp) is strict about both
# the trailing slash and content negotiation: a POST to /mcp receives 307
# Temporary Redirect → /mcp/, and a POST without these Accept values receives
# 406 Not Acceptable (TAP-516 regression found against brain 3.10.x).
_MCP_ACCEPT_HEADERS: dict[str, str] = {"Accept": "application/json, text/event-stream"}


class BrainBridgeUnavailable(Exception):  # noqa: N818  (public API name predates the lint rule; renaming would break consumers)
    """Raised when the circuit is open or the bridge is not configured."""


class BrainBridge:
    """Async-safe wrapper over :class:`tapps_brain.AgentBrain`.

    Provides read and write operations against the tapps-brain v3 Postgres
    backend with built-in resilience:

    - ``asyncio.to_thread`` for every sync call
    - Circuit breaker (opens after 3 failures, resets after 30 s)
    - Exponential-backoff retry (3 attempts, base 0.5 s, max 8 s, ±10 % jitter)
    - Offline write queue (cap 100; drained asynchronously after circuit resets)
    """

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
                logger.warning("brain_bridge.circuit_opened", failures=self._failures)
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
            logger.warning(
                "brain_write_queue_full",
                queue_depth=self._write_queue.qsize(),
                queue_cap=_WRITE_QUEUE_CAP,
                dropped_key=entry.get("key"),
            )
            return False

    async def _drain_write_queue(self) -> None:
        while not self._write_queue.empty():
            if self.circuit_open:
                break
            try:
                entry = self._write_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                await self.save(**entry)
            except Exception as exc:
                logger.warning("brain_bridge.drain_failed", error=str(exc))

    def _maybe_start_drain(self) -> None:
        if not self.circuit_open and not self._write_queue.empty():
            if self._drain_task is None or self._drain_task.done():
                try:
                    loop = asyncio.get_running_loop()
                    self._drain_task = loop.create_task(self._drain_write_queue())
                except RuntimeError:
                    pass

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _to_dict(obj: Any) -> dict[str, Any]:
        if hasattr(obj, "model_dump"):
            d: dict[str, Any] = obj.model_dump()
            return d
        if hasattr(obj, "__dict__"):
            return dict(vars(obj))
        return {"value": str(obj)}

    # -------------------------------------------------------------------------
    # Read operations
    # -------------------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 10,
        tier: str | None = None,
    ) -> list[dict[str, Any]]:
        """Keyword + semantic search over the memory store."""

        def _fn() -> list[dict[str, Any]]:
            results = self._brain.store.search(query, tier=tier)
            return [self._to_dict(r) for r in results[:limit]]

        return await self._call(_fn)

    async def get(self, key: str) -> dict[str, Any] | None:
        """Fetch a single entry by key."""

        def _fn() -> dict[str, Any] | None:
            entry = self._brain.store.get(key)
            return self._to_dict(entry) if entry is not None else None

        return await self._call(_fn)

    async def list_memories(
        self,
        limit: int = 20,
        tier: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all entries, optionally filtered by tier."""

        def _fn() -> list[dict[str, Any]]:
            results = self._brain.store.list_all(tier=tier)
            return [self._to_dict(r) for r in results[:limit]]

        return await self._call(_fn)

    async def recall_for_prompt(
        self,
        query: str,
        max_tokens: int = 2000,
        threshold: float = 0.5,
    ) -> str | None:
        """Recall memories and format as a markdown list for prompt injection.

        Returns None when no results exceed *threshold*.
        """

        def _fn() -> list[dict[str, Any]]:
            return self._brain.recall(query, max_results=10)

        hits: list[dict[str, Any]] = await self._call(_fn)
        if not hits:
            return None

        lines: list[str] = []
        char_budget = max_tokens * 4  # ~4 chars per token
        for hit in hits:
            score = hit.get("score", hit.get("confidence", 1.0))
            if isinstance(score, (int, float)) and score < threshold:
                continue
            key = hit.get("key", "")
            value = hit.get("value", "")
            line = f"- [{key}] {value}" if key else f"- {value}"
            if sum(len(ln) for ln in lines) + len(line) > char_budget:
                break
            lines.append(line)

        return "\n".join(lines) if lines else None

    async def hive_search(
        self,
        query: str,
        limit: int = 10,
        namespaces: list[str] | None = None,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Search the hive namespace. Returns [] when hive DSN is not configured."""

        def _fn() -> list[dict[str, Any]]:
            hive = self._brain.hive
            if hive is None:
                return []
            kwargs: dict[str, Any] = {"limit": limit}
            if namespaces is not None:
                kwargs["namespaces"] = namespaces
            if min_confidence > 0.0:
                kwargs["min_confidence"] = min_confidence
            results: list[dict[str, Any]] = hive.search(query, **kwargs)
            return results

        return await self._call(_fn)

    async def hive_status(
        self,
        *,
        agent_id: str,
        agent_name: str = "unnamed",
        agent_profile: str = "repo-brain",
        project_root: str = ".",
        register: bool = True,
    ) -> dict[str, Any]:
        """Snapshot Hive state. Optionally registers this process as an agent.

        TAP-413 / EPIC-95.4: replaces direct ``tapps_brain.backends.AgentRegistry``
        + ``HiveBackend`` singletons in tapps-mcp. Returns ``degraded: true`` when
        the hive backend is not available (no DSN or init failed).
        """

        def _fn() -> dict[str, Any]:
            from tapps_brain.backends import AgentRegistry
            from tapps_brain.models import AgentRegistration

            hive = self._brain.hive
            if hive is None:
                return {
                    "enabled": True,
                    "degraded": True,
                    "message": "Hive backend not available (no DSN or init failed).",
                }

            registry = AgentRegistry()
            if register:
                with contextlib.suppress(Exception):
                    registry.register(
                        AgentRegistration(
                            id=agent_id,
                            name=agent_name,
                            profile=agent_profile,
                            project_root=project_root,
                        )
                    )

            namespaces = list(hive.list_namespaces())
            agents = [self._to_dict(a) for a in registry.list_agents()]
            return {
                "enabled": True,
                "degraded": False,
                "namespaces": namespaces,
                "namespace_count": len(namespaces),
                "agents": agents,
                "agent_count": len(agents),
            }

        return await self._call(_fn)

    async def hive_propagate(
        self,
        entries: list[Any],
        *,
        agent_id: str,
        agent_profile: str,
    ) -> dict[str, Any]:
        """Propagate local memory entries into Hive per their ``agent_scope``.

        Each entry's ``agent_scope`` decides routing: ``private`` stays local
        (counted as ``skipped_private``); ``domain`` goes to the agent profile
        namespace; ``hive`` goes to ``universal``. Returns ``degraded: true`` when
        the hive backend is not available.
        """

        def _fn() -> dict[str, Any]:
            from tapps_brain.backends import PropagationEngine

            hive = self._brain.hive
            if hive is None:
                return {
                    "enabled": True,
                    "degraded": True,
                    "propagated": 0,
                    "skipped_private": 0,
                    "scanned": 0,
                    "details": [],
                    "message": "Hive backend not available.",
                }

            propagated = 0
            skipped_private = 0
            details: list[dict[str, Any]] = []

            for entry in entries:
                conf = entry.confidence if entry.confidence >= 0.0 else 0.6
                tier_val = getattr(entry.tier, "value", str(entry.tier))
                source_val = getattr(entry.source, "value", str(entry.source))
                saved = PropagationEngine.propagate(
                    key=entry.key,
                    value=entry.value,
                    agent_scope=entry.agent_scope,
                    agent_id=agent_id,
                    agent_profile=agent_profile,
                    tier=str(tier_val),
                    confidence=conf,
                    source=str(source_val),
                    tags=entry.tags,
                    hive_store=hive,
                    auto_propagate_tiers=None,
                    private_tiers=None,
                )
                if saved is None:
                    skipped_private += 1
                else:
                    propagated += 1
                    details.append({"key": entry.key, "namespace": saved.get("namespace", "")})

            return {
                "enabled": True,
                "degraded": False,
                "propagated": propagated,
                "skipped_private": skipped_private,
                "scanned": len(entries),
                "details": details,
            }

        return await self._call(_fn)

    async def agent_register(
        self,
        *,
        agent_id: str,
        name: str,
        profile: str = "repo-brain",
        skills: list[str] | None = None,
        project_root: str = ".",
    ) -> dict[str, Any]:
        """Register an agent in the AgentRegistry (YAML-backed).

        Independent of hive backend availability — the registry is a local YAML
        file that records agents in the project. ``skills`` defaults to ``[]``.
        """

        def _fn() -> dict[str, Any]:
            from tapps_brain.backends import AgentRegistry
            from tapps_brain.models import AgentRegistration

            registry = AgentRegistry()
            registry.register(
                AgentRegistration(
                    id=agent_id,
                    name=name,
                    profile=profile,
                    skills=skills or [],
                    project_root=project_root,
                )
            )
            return {
                "agent_id": agent_id,
                "agent_name": name,
                "profile": profile,
                "skills": skills or [],
            }

        return await self._call(_fn)

    # -------------------------------------------------------------------------
    # Write operations
    # -------------------------------------------------------------------------

    async def save(
        self,
        key: str,
        value: str,
        *,
        tier: str = "pattern",
        scope: str = "project",
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Save a memory entry. Queues the write when circuit is open."""
        if self.circuit_open:
            queued = self._enqueue_write(
                {
                    "key": key,
                    "value": value,
                    "tier": tier,
                    "scope": scope,
                    "tags": tags,
                    **kwargs,
                }
            )
            return {
                "success": False,
                "degraded": True,
                "reason": "circuit open",
                "queued": queued,
                "queue_depth": self.queue_depth,
            }

        def _fn() -> dict[str, Any]:
            entry = self._brain.store.save(key, value, tier=tier, scope=scope, tags=tags, **kwargs)
            return self._to_dict(entry)

        result: dict[str, Any] = await self._call(_fn)
        self._maybe_start_drain()
        return result

    async def save_many(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Save multiple entries. Returns counts of saved/failed."""
        saved = 0
        failed = 0
        for entry in entries:
            try:
                await self.save(**entry)
                saved += 1
            except Exception:
                failed += 1
        return {"saved": saved, "failed": failed, "total": len(entries)}

    async def delete(self, key: str) -> bool:
        """Delete an entry by key."""

        def _fn() -> bool:
            result: bool = self._brain.store.delete(key)
            return result

        return await self._call(_fn)

    async def reinforce(self, key: str, boost: float = 0.1) -> dict[str, Any]:
        """Boost confidence on an existing entry."""

        def _fn() -> dict[str, Any]:
            entry = self._brain.store.reinforce(key, confidence_boost=boost)
            return self._to_dict(entry)

        return await self._call(_fn)

    async def supersede(self, key: str, new_value: str, **kwargs: Any) -> dict[str, Any]:
        """Replace the value of an architectural-tier entry in its chain."""

        def _fn() -> dict[str, Any]:
            entry = self._brain.store.supersede(key, new_value, **kwargs)
            return self._to_dict(entry)

        return await self._call(_fn)

    # -------------------------------------------------------------------------
    # Maintenance
    # -------------------------------------------------------------------------

    async def gc(self, dry_run: bool = False) -> dict[str, Any]:
        """Run garbage collection to prune stale / low-confidence entries."""

        def _fn() -> dict[str, Any]:
            result = self._brain.store.gc(dry_run=dry_run)
            return self._to_dict(result)

        return await self._call(_fn)

    async def consolidate(self, dry_run: bool = False) -> dict[str, Any]:
        """Scan for similar entries and merge them (periodic consolidation scan)."""
        from tapps_brain.auto_consolidation import run_periodic_consolidation_scan

        project_root = Path(str(self._brain.store.project_root or "."))

        def _fn() -> dict[str, Any]:
            result = run_periodic_consolidation_scan(
                self._brain.store,
                project_root,
                force=True,
            )
            return self._to_dict(result)

        return await self._call(_fn)

    async def undo_consolidation(self, consolidated_key: str) -> dict[str, Any]:
        """Restore source entries that were merged into ``consolidated_key``."""

        def _fn() -> dict[str, Any]:
            result = self._brain.store.undo_consolidation_merge(consolidated_key)
            return self._to_dict(result)

        return await self._call(_fn)

    async def detect_conflicts(
        self,
        profile: Any,
        project_root: Path | None = None,
        mark_contradicted: bool = True,
    ) -> dict[str, Any]:
        """Detect memories contradicting the project profile.

        Wraps :class:`tapps_brain.contradictions.ContradictionDetector` against
        all entries currently in the store. When *mark_contradicted* is True,
        flags each detected entry via ``store.update_fields(contradicted=True)``.
        """
        from tapps_brain.contradictions import ContradictionDetector

        root = project_root or Path(str(self._brain.store.project_root or "."))

        def _fn() -> dict[str, Any]:
            detector = ContradictionDetector(root)
            entries = self._brain.store.list_all()
            contradictions = detector.detect_contradictions(entries, profile)
            if mark_contradicted:
                for c in contradictions:
                    self._brain.store.update_fields(c.memory_key, contradicted=True)
            return {
                "contradictions": [self._to_dict(c) for c in contradictions],
                "count": len(contradictions),
                "checked_count": len(entries),
            }

        return await self._call(_fn)

    async def verify_integrity(self) -> dict[str, Any]:
        """Verify HMAC-SHA256 integrity of all stored entries."""

        def _fn() -> dict[str, Any]:
            result: dict[str, Any] = self._brain.store.verify_integrity()
            return result

        return await self._call(_fn)

    async def maintain(self) -> dict[str, Any]:
        """Run a full maintenance cycle: GC + consolidation + deduplication.

        Returns counts for each phase. Each phase runs independently — failure
        in one does not abort the others.
        """
        gc_archived = 0
        consolidated = 0
        deduplicated = 0

        try:
            gc_result = await self.gc(dry_run=False)
            gc_archived = int(gc_result.get("archived_count", 0))
        except Exception as exc:
            logger.warning("brain_bridge.maintain.gc_failed", error=str(exc))

        try:
            consol_result = await self.consolidate(dry_run=False)
            # PeriodicScanResult uses ``groups_found`` (not ``groups_formed``).
            consolidated = int(
                consol_result.get("groups_found", consol_result.get("groups_formed", 0))
            )
        except Exception as exc:
            logger.warning("brain_bridge.maintain.consolidate_failed", error=str(exc))

        def _dedup() -> int:
            snapshot = self._brain.store.snapshot()
            seen: dict[str, str] = {}
            removed = 0
            for entry in snapshot.entries:
                key = entry.value.strip().lower()
                if key in seen and seen[key] != entry.key:
                    if self._brain.store.delete(entry.key):
                        removed += 1
                else:
                    seen[key] = entry.key
            return removed

        try:
            deduplicated = await self._call(_dedup)
        except Exception as exc:
            logger.warning("brain_bridge.maintain.dedup_failed", error=str(exc))

        return {
            "gc_archived": gc_archived,
            "consolidated": consolidated,
            "deduplicated": deduplicated,
        }

    # -------------------------------------------------------------------------
    # Diagnostics
    # -------------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Return a health dict: status, postgres connectivity, entry_count."""

        def _fn() -> dict[str, Any]:
            report = self._brain.store.health()
            base = self._to_dict(report)
            store_ok: bool = bool(base.get("store_available", True))
            pg_ok: bool = bool(base.get("postgres_available", True))
            return {
                "status": "ok" if store_ok else "degraded",
                "postgres": "connected" if pg_ok else "unreachable",
                "entry_count": base.get("current_count", 0),
                **base,
            }

        return await self._call(_fn)

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
                logger.warning(
                    "brain_bridge.drain_blocking_entry_failed",
                    error=str(exc),
                    key=entry.get("key"),
                )
                dropped += 1
        remaining = self._write_queue.qsize()
        if drained or dropped or remaining:
            logger.info(
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
            logger.warning("brain_bridge.drain_on_close_failed", error=str(exc))
        try:
            self._brain.close()
        except Exception as exc:
            logger.warning("brain_bridge.close_failed", error=str(exc))


# -----------------------------------------------------------------------------
# HTTP transport (TAP-596)
# -----------------------------------------------------------------------------


class HttpBrainBridge(BrainBridge):
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
    gc                        memory_gc
    consolidate               memory_consolidate
    hive_search               hive_search
    hive_status               hive_status
    hive_propagate            hive_propagate
    agent_register            agent_register
    ========================  =====================

    Verify this mapping against the live tapps-brain-http server when deploying.
    """

    is_http_mode: bool = True

    def __init__(self, http_url: str, headers: dict[str, str]) -> None:
        # Initialise shared resilience state without a local AgentBrain.
        self._failures: int = 0
        self._open_at: float | None = None
        self._write_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_WRITE_QUEUE_CAP)
        self._drain_task: asyncio.Task[None] | None = None
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
        self._http_url: str = http_url.rstrip("/")
        self._http_headers: dict[str, str] = dict(headers)
        self._http_client: httpx.AsyncClient | None = None
        # TAP-836: brain 3.10.3+ enforces the MCP streamable-HTTP session
        # lifecycle — an initialize handshake returns an Mcp-Session-Id
        # that must accompany every subsequent tools/call. Cached lazily
        # on first call; cleared via close() or when the server rejects
        # the session ID and we need to re-handshake.
        self._session_id: str | None = None
        self._session_lock: asyncio.Lock = asyncio.Lock()

    # -------------------------------------------------------------------------
    # HTTP JSON-RPC call layer
    # -------------------------------------------------------------------------

    async def _http_mcp_call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tapps-brain MCP tool with circuit-breaker + retry semantics."""
        if self.circuit_open:
            raise BrainBridgeUnavailable("circuit open")

        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                result = await self._do_mcp_post(tool_name, arguments)
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
                    delay += random.uniform(0, delay * 0.1)  # noqa: S311
                    await asyncio.sleep(delay)

        raise BrainBridgeUnavailable(f"all retries exhausted: {last_exc}") from last_exc

    async def _ensure_session(self) -> str:
        """Return a valid MCP session id, establishing one via ``initialize``.

        brain 3.10.3+ requires the MCP streamable-HTTP session handshake
        (TAP-836). Older brains ignore the header so sending it is
        back-compat safe.
        """
        if self._session_id:
            return self._session_id
        async with self._session_lock:
            if self._session_id:
                return self._session_id
            if self._http_client is None:
                self._http_client = httpx.AsyncClient(
                    headers={**self._http_headers, **_MCP_ACCEPT_HEADERS},
                    timeout=30.0,
                    follow_redirects=True,
                )
            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "tapps-mcp", "version": "http-bridge"},
                },
            }
            response = await self._http_client.post(
                f"{self._http_url}/mcp/", json=init_payload
            )
            response.raise_for_status()
            session_id = response.headers.get("mcp-session-id")
            if not session_id:
                # Older brains that don't use the session model — use a
                # sentinel so we don't re-handshake every call.
                session_id = "__no_session__"
            self._session_id = session_id
            return session_id

    async def _do_mcp_post(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """POST a single ``tools/call`` to ``{brain_http_url}/mcp``."""
        import json as _json

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                headers={**self._http_headers, **_MCP_ACCEPT_HEADERS},
                timeout=30.0,
                follow_redirects=True,
            )
        session_id = await self._ensure_session()
        extra_headers: dict[str, str] = {}
        if session_id and session_id != "__no_session__":
            extra_headers["Mcp-Session-Id"] = session_id
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        response = await self._http_client.post(
            f"{self._http_url}/mcp/", json=payload, headers=extra_headers
        )
        # If the server rejects the session, drop it and retry once with a
        # fresh handshake. 404 = session not found (common after brain
        # restart); 400 with "Missing session ID" indicates we never got
        # an Mcp-Session-Id header in the first place.
        if response.status_code in (400, 404) and self._session_id:
            self._session_id = None
            session_id = await self._ensure_session()
            extra_headers = (
                {"Mcp-Session-Id": session_id}
                if session_id != "__no_session__"
                else {}
            )
            response = await self._http_client.post(
                f"{self._http_url}/mcp/", json=payload, headers=extra_headers
            )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        rpc_error = data.get("error")
        if rpc_error:
            raise RuntimeError(f"tapps-brain MCP RPC error: {rpc_error}")

        result: dict[str, Any] = data.get("result", {})
        if result.get("isError"):
            content = result.get("content", [])
            msg = content[0].get("text", str(result)) if content else str(result)
            raise RuntimeError(f"tapps-brain tool error: {msg}")

        content_items: list[dict[str, Any]] = result.get("content", [])
        if content_items and content_items[0].get("type") == "text":
            text = content_items[0]["text"]
            try:
                return _json.loads(text)
            except _json.JSONDecodeError:
                return {"value": text}
        return result

    # -------------------------------------------------------------------------
    # Read operations (HTTP overrides)
    # -------------------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 10,
        tier: str | None = None,
    ) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"query": query, "limit": limit}
        if tier is not None:
            args["tier"] = tier
        result = await self._http_mcp_call("memory_search", args)
        if isinstance(result, list):
            return result
        return result.get("results", []) if isinstance(result, dict) else []

    async def get(self, key: str) -> dict[str, Any] | None:
        result = await self._http_mcp_call("memory_get", {"key": key})
        if isinstance(result, dict) and result.get("key") and not result.get("error"):
            return result
        return None

    async def list_memories(
        self,
        limit: int = 20,
        tier: str | None = None,
    ) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"limit": limit}
        if tier is not None:
            args["tier"] = tier
        result = await self._http_mcp_call("memory_list", args)
        if isinstance(result, list):
            return result
        return result.get("entries", []) if isinstance(result, dict) else []

    async def recall_for_prompt(
        self,
        query: str,
        max_tokens: int = 2000,
        threshold: float = 0.5,
    ) -> str | None:
        args: dict[str, Any] = {"query": query, "max_tokens": max_tokens, "threshold": threshold}
        result = await self._http_mcp_call("memory_recall", args)
        if isinstance(result, str):
            return result or None
        if isinstance(result, dict):
            text = result.get("text") or result.get("content")
            return str(text) if text else None
        return None

    async def hive_search(
        self,
        query: str,
        limit: int = 10,
        namespaces: list[str] | None = None,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"query": query, "limit": limit}
        if namespaces is not None:
            args["namespaces"] = namespaces
        if min_confidence > 0.0:
            args["min_confidence"] = min_confidence
        result = await self._http_mcp_call("hive_search", args)
        if isinstance(result, list):
            return result
        return result.get("results", []) if isinstance(result, dict) else []

    async def hive_status(
        self,
        *,
        agent_id: str,
        agent_name: str = "unnamed",
        agent_profile: str = "repo-brain",
        project_root: str = ".",
        register: bool = True,
    ) -> dict[str, Any]:
        # brain 3.10+ hive_status takes no arguments and returns
        # {namespaces, total_entries, agents} with no "enabled" key. Inject
        # a synthetic "enabled": True so downstream callers (many) that
        # read result["enabled"] don't KeyError (TAP-800 drift 3).
        _ = agent_id, agent_name, agent_profile, project_root, register
        result = await self._http_mcp_call("hive_status", {})
        if not isinstance(result, dict):
            return {"enabled": True, "degraded": False}
        return result if "enabled" in result else {**result, "enabled": True}

    async def hive_propagate(
        self,
        entries: list[Any],
        *,
        agent_id: str,
        agent_profile: str,
    ) -> dict[str, Any]:
        # brain 3.10+ hive_propagate propagates a single memory by key per
        # call. Iterate over the batch the caller passed in and aggregate,
        # preserving the Python API's list-of-entries shape
        # (TAP-800 drift 4).
        _ = agent_id
        propagated = 0
        skipped_private = 0
        details: list[dict[str, Any]] = []
        for entry in entries:
            key: str | None
            if hasattr(entry, "key"):
                key = str(entry.key) if entry.key else None
            elif isinstance(entry, dict):
                raw = entry.get("key")
                key = str(raw) if raw else None
            else:
                key = None
            if not key:
                continue
            scope = getattr(entry, "agent_scope", None)
            if scope == "private":
                skipped_private += 1
                details.append({"key": key, "skipped": "private"})
                continue
            try:
                per = await self._http_mcp_call(
                    "hive_propagate",
                    {"key": key, "agent_scope": agent_profile or "hive"},
                )
            except Exception as exc:
                details.append({"key": key, "error": str(exc)})
                continue
            if isinstance(per, dict):
                details.append({"key": key, **per})
                if per.get("propagated") or per.get("success"):
                    propagated += 1
            else:
                details.append({"key": key})
                propagated += 1
        return {
            "enabled": True,
            "degraded": False,
            "propagated": propagated,
            "skipped_private": skipped_private,
            "scanned": len(entries),
            "details": details,
        }

    async def agent_register(
        self,
        *,
        agent_id: str,
        name: str,
        profile: str = "repo-brain",
        skills: list[str] | None = None,
        project_root: str = ".",
    ) -> dict[str, Any]:
        # brain 3.10+ agent_register dropped ``name`` and ``project_root``
        # and changed ``skills`` from list[str] to comma-joined str. The
        # Python signature keeps the old params for caller back-compat;
        # they're retained in the returned dict but not sent on the wire
        # (TAP-800 drift 2).
        _ = project_root
        args: dict[str, Any] = {
            "agent_id": agent_id,
            "profile": profile,
            "skills": ",".join(skills or []),
        }
        result = await self._http_mcp_call("agent_register", args)
        if isinstance(result, dict):
            return {"agent_name": name, **result}
        return {"agent_id": agent_id, "agent_name": name}

    # -------------------------------------------------------------------------
    # Write operations (HTTP overrides)
    # -------------------------------------------------------------------------

    async def save(
        self,
        key: str,
        value: str,
        *,
        tier: str = "pattern",
        scope: str = "project",
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self.circuit_open:
            queued = self._enqueue_write(
                {"key": key, "value": value, "tier": tier, "scope": scope, "tags": tags, **kwargs}
            )
            return {
                "success": False,
                "degraded": True,
                "reason": "circuit open",
                "queued": queued,
                "queue_depth": self.queue_depth,
            }
        args: dict[str, Any] = {"key": key, "value": value, "tier": tier, "scope": scope}
        if tags:
            args["tags"] = tags
        args.update(kwargs)
        result: dict[str, Any] = await self._http_mcp_call("memory_save", args)
        self._maybe_start_drain()
        return result if isinstance(result, dict) else {"key": key, "success": True}

    async def delete(self, key: str) -> bool:
        result = await self._http_mcp_call("memory_delete", {"key": key})
        if isinstance(result, bool):
            return result
        if isinstance(result, dict):
            return bool(result.get("deleted", result.get("success", False)))
        return False

    async def reinforce(self, key: str, boost: float = 0.1) -> dict[str, Any]:
        result = await self._http_mcp_call("memory_reinforce", {"key": key, "confidence_boost": boost})
        return result if isinstance(result, dict) else {"key": key}

    async def supersede(self, key: str, new_value: str, **kwargs: Any) -> dict[str, Any]:
        args: dict[str, Any] = {"key": key, "new_value": new_value, **kwargs}
        result = await self._http_mcp_call("memory_supersede", args)
        return result if isinstance(result, dict) else {"key": key}

    # -------------------------------------------------------------------------
    # Maintenance (HTTP overrides)
    # -------------------------------------------------------------------------

    async def gc(self, dry_run: bool = False) -> dict[str, Any]:
        result = await self._http_mcp_call("memory_gc", {"dry_run": dry_run})
        return result if isinstance(result, dict) else {"archived_count": 0}

    async def consolidate(self, dry_run: bool = False) -> dict[str, Any]:
        # brain 3.10+ removed ``memory_consolidate`` entirely with no drop-in
        # replacement. Fall through to a graceful degraded stub when the tool
        # is missing, so callers (hooks, background tasks) don't crash on
        # newer brain versions. Older brains still work via the RPC path.
        # Tracked in TAP-800 drift 1.
        # Retry-exhausted tool-not-found surfaces as BrainBridgeUnavailable
        # with the original RuntimeError as __cause__; check both.
        try:
            result = await self._http_mcp_call("memory_consolidate", {"dry_run": dry_run})
        except (RuntimeError, BrainBridgeUnavailable) as exc:
            chain = f"{exc} {exc.__cause__}"
            if "Unknown tool" in chain and "memory_consolidate" in chain:
                return {
                    "groups_found": 0,
                    "degraded": True,
                    "reason": "memory_consolidate removed in tapps-brain 3.10+",
                    "dry_run": dry_run,
                }
            raise
        return result if isinstance(result, dict) else {"groups_found": 0}

    # -------------------------------------------------------------------------
    # Diagnostics (HTTP overrides)
    # -------------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Return health dict by probing ``{brain_http_url}/health``."""
        try:
            response = httpx.get(
                f"{self._http_url}/health",
                timeout=_BRAIN_HEALTH_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            base = payload if isinstance(payload, dict) else {}
            return {"status": "ok", "postgres": "connected", **base}
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)}

    def health_check(self) -> dict[str, Any]:
        """Probe ``{brain_http_url}/health`` (replaces DSN-based health check)."""
        health_url = f"{self._http_url}/health"
        try:
            response = httpx.get(health_url, timeout=_BRAIN_HEALTH_TIMEOUT_SECONDS)
            response.raise_for_status()
            details: dict[str, Any] = {"http_url": self._http_url, "mode": "http"}
            with contextlib.suppress(Exception):
                payload = response.json()
                if isinstance(payload, dict):
                    details["brain_version"] = payload.get("version")
                    details["brain_status"] = payload.get("status")
            return {
                "ok": True,
                "dsn_reachable": True,
                "pool_config_valid": True,
                "native_health_ok": True,
                "errors": [],
                "warnings": [],
                "details": details,
            }
        except Exception as exc:
            return {
                "ok": False,
                "dsn_reachable": False,
                "pool_config_valid": True,
                "native_health_ok": False,
                "errors": [f"http_health_failed: {exc}"],
                "warnings": [],
                "details": {"http_url": self._http_url, "mode": "http"},
            }

    def auth_probe(self) -> dict[str, Any]:
        """Probe ``{brain_http_url}/mcp`` with a cheap authenticated call.

        Complements :meth:`health_check` which only probes the unauthenticated
        ``/health`` endpoint. This sends a real ``tools/call`` (``memory_list``
        with ``limit=1``) carrying the configured Bearer token and
        ``X-Project-Id`` / ``X-Agent-Id`` headers, so a failure here means the
        same auth that runtime memory calls use is rejected by the server.

        Returns a dict with ``ok`` (bool) and diagnostic fields:

        - ``ok=True, http_status=200`` — auth works.
        - ``ok=False, http_status=401|403, detail=<body>`` — server rejected auth.
        - ``ok=False, error=<str>`` — transport failed (DNS, connection refused, etc.).
        """
        # TAP-836: run the full initialize handshake synchronously. Brain
        # 3.10.3+ returns 400 "Missing session ID" on any tools/call that
        # doesn't carry an Mcp-Session-Id; we fall back to no-session
        # mode if the server doesn't return a session id (older brains).
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "tapps-mcp", "version": "http-bridge"},
            },
        }
        try:
            init_response = httpx.post(
                f"{self._http_url}/mcp/",
                json=init_payload,
                headers={**self._http_headers, **_MCP_ACCEPT_HEADERS},
                timeout=_BRAIN_HEALTH_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        except Exception as exc:
            return {"ok": False, "error": f"probe_failed: {exc}"}
        if init_response.status_code in (401, 403):
            return {
                "ok": False,
                "http_status": init_response.status_code,
                "detail": init_response.text[:200] if init_response.text else "",
            }
        session_id = init_response.headers.get("mcp-session-id", "")

        probe_headers = {**self._http_headers, **_MCP_ACCEPT_HEADERS}
        if session_id:
            probe_headers["Mcp-Session-Id"] = session_id
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "memory_list", "arguments": {"limit": 1}},
        }
        try:
            response = httpx.post(
                f"{self._http_url}/mcp/",
                json=payload,
                headers=probe_headers,
                timeout=_BRAIN_HEALTH_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        except Exception as exc:
            return {"ok": False, "error": f"probe_failed: {exc}"}
        if response.status_code == 200:
            return {"ok": True, "http_status": 200}
        detail = response.text[:200] if response.text else ""
        return {
            "ok": False,
            "http_status": response.status_code,
            "detail": detail,
        }

    @property
    def store(self) -> None:
        """Not available in HTTP mode — callers must use async BrainBridge methods."""
        return None

    # -------------------------------------------------------------------------
    # Lifecycle (HTTP overrides)
    # -------------------------------------------------------------------------

    def drain_blocking(self, timeout: float = _DRAIN_DEADLINE_SECONDS) -> dict[str, int]:
        """Drain the offline write queue via synchronous HTTP calls."""
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
                httpx.post(
                    f"{self._http_url}/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "memory_save", "arguments": entry},
                    },
                    headers={**self._http_headers, **_MCP_ACCEPT_HEADERS},
                    timeout=5.0,
                    follow_redirects=True,
                )
                drained += 1
            except Exception as exc:
                logger.warning(
                    "brain_bridge.drain_blocking_http_failed",
                    error=str(exc),
                    key=entry.get("key"),
                )
                dropped += 1
        remaining = self._write_queue.qsize()
        if drained or dropped or remaining:
            logger.info(
                "brain_bridge.drain_blocking_complete",
                drained=drained,
                dropped=dropped,
                remaining=remaining,
                deadline_exceeded=time.monotonic() >= deadline,
            )
        return {"drained": drained, "dropped": dropped, "remaining": remaining}

    def close(self, drain_timeout: float = _DRAIN_DEADLINE_SECONDS) -> None:
        """Drain queued writes then close the async HTTP client."""
        try:
            self.drain_blocking(drain_timeout)
        except Exception as exc:
            logger.warning("brain_bridge.drain_on_close_failed", error=str(exc))
        if self._http_client is not None:
            with contextlib.suppress(Exception):
                try:
                    loop = asyncio.get_event_loop()
                    if not loop.is_closed() and not loop.is_running():
                        loop.run_until_complete(self._http_client.aclose())
                except Exception:
                    pass
            self._http_client = None
        self._session_id = None


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


def create_brain_bridge(settings: Any = None) -> BrainBridge | None:
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
        return _create_http_bridge(brain_http_url, settings)

    # --- In-process path -----------------------------------------------------
    from tapps_brain import AgentBrain

    dsn = ""
    if settings is not None:
        memory = getattr(settings, "memory", None)
        if memory is not None:
            dsn = str(getattr(memory, "database_url", "") or "")
    if not dsn:
        dsn = os.environ.get("TAPPS_BRAIN_DATABASE_URL", "")
    if not dsn:
        return None

    os.environ.setdefault("TAPPS_BRAIN_DATABASE_URL", dsn)

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

    # ADR-010 / EPIC-069: declare the registered project slug on the wire.
    if project_id:
        os.environ["TAPPS_BRAIN_PROJECT"] = project_id

    # EPIC-066: pool tuning pass-through; only set when non-zero.
    if pg_pool_max_waiting:
        os.environ["TAPPS_BRAIN_PG_POOL_MAX_WAITING"] = str(pg_pool_max_waiting)
    if pg_pool_max_lifetime_seconds:
        os.environ["TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS"] = str(pg_pool_max_lifetime_seconds)

    try:
        brain = AgentBrain(
            agent_id="tapps-mcp",
            project_dir=project_root or None,
            profile=profile,
            hive_dsn=hive_dsn,
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


def _create_http_bridge(brain_http_url: str, settings: Any) -> BrainBridge | None:
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

    if "Authorization" not in headers:
        logger.warning(
            "brain_bridge.http_auth_missing",
            http_url=brain_http_url,
            hint=(
                "HTTP bridge has no Authorization header — every /mcp call will "
                "return 401/403. Set TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN (client "
                "bearer token) in the environment or memory.brain_auth_token in "
                ".tapps-mcp.yaml. Note: TAPPS_BRAIN_AUTH_TOKEN is tapps-brain's "
                "server-side token, not the client token."
            ),
        )

    bridge = HttpBrainBridge(brain_http_url, headers)

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

    def _sigterm_drain_exit(_signum: int, _frame: Any) -> None:
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, _sigterm_drain_exit)
    except (OSError, ValueError):
        # Non-main-thread, embedded interpreter, or platform without
        # SIGTERM — atexit still covers normal shutdown paths.
        logger.debug("brain_bridge.sigterm_register_skipped")

    _shutdown_hooks_registered = True
