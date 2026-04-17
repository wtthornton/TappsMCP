"""BrainBridge: async wrapper over tapps-brain v3 AgentBrain.

All sync AgentBrain/MemoryStore calls are offloaded via asyncio.to_thread.
Resilience: circuit breaker + exponential-backoff retry + offline write queue.

Usage::

    from tapps_core.brain_bridge import create_brain_bridge

    bridge = create_brain_bridge(settings)  # None if TAPPS_BRAIN_DATABASE_URL unset
    if bridge:
        results = await bridge.search("query")
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import structlog

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
        """Queue a write for later drain. Returns False when queue is full."""
        try:
            self._write_queue.put_nowait(entry)
            return True
        except asyncio.QueueFull:
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
    # Lifecycle
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying AgentBrain connection pool."""
        try:
            self._brain.close()
        except Exception as exc:
            logger.warning("brain_bridge.close_failed", error=str(exc))


# -----------------------------------------------------------------------------
# Factory
# -----------------------------------------------------------------------------


def create_brain_bridge(settings: Any = None) -> BrainBridge | None:
    """Create a :class:`BrainBridge` from settings or environment.

    Returns ``None`` when ``TAPPS_BRAIN_DATABASE_URL`` is not configured so
    callers can gate memory operations without raising.

    Resolution order for the Postgres DSN:

    1. ``settings.memory.database_url``
    2. ``TAPPS_BRAIN_DATABASE_URL`` environment variable
    """
    from tapps_brain import AgentBrain

    # --- Resolve DSN ---------------------------------------------------------
    dsn = ""
    if settings is not None:
        memory = getattr(settings, "memory", None)
        if memory is not None:
            dsn = str(getattr(memory, "database_url", "") or "")
    if not dsn:
        dsn = os.environ.get("TAPPS_BRAIN_DATABASE_URL", "")
    if not dsn:
        return None

    # Export so AgentBrain's internal init picks it up
    os.environ.setdefault("TAPPS_BRAIN_DATABASE_URL", dsn)

    # --- Resolve optional settings -------------------------------------------
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

    # ADR-010 / EPIC-069: declare the registered project slug on the wire so
    # AgentBrain hits the project registry instead of deriving a per-directory
    # hash. When the setting is empty we leave any pre-set env var untouched
    # (user may export TAPPS_BRAIN_PROJECT directly).
    if project_id:
        os.environ["TAPPS_BRAIN_PROJECT"] = project_id

    # EPIC-066 (tapps-brain v3.7.0): pool tuning pass-through. Only set env
    # vars when the setting is non-zero so we don't override operator-provided
    # values or clobber tapps-brain's own defaults.
    if pg_pool_max_waiting:
        os.environ["TAPPS_BRAIN_PG_POOL_MAX_WAITING"] = str(pg_pool_max_waiting)
    if pg_pool_max_lifetime_seconds:
        os.environ["TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS"] = str(pg_pool_max_lifetime_seconds)

    # --- Construct & probe ---------------------------------------------------
    try:
        brain = AgentBrain(
            agent_id="tapps-mcp",
            project_dir=project_root or None,
            profile=profile,
            hive_dsn=hive_dsn,
        )
        # Probe the store to fail fast on bad DSN before returning
        brain.store.count()
        return BrainBridge(brain)
    except Exception as exc:
        logger.warning("brain_bridge.init_failed", error=str(exc))
        return None
