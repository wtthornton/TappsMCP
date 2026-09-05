"""In-process AgentBrain-delegating read/write/maintenance methods mixin.

Split out of ``brain_bridge_inprocess.py`` (TAP-6736, further split). No
behavior change: each method body below is moved byte-for-byte. Composed as
``_InProcessOpsMixin`` alongside ``_InProcessCoreMixin`` into the public
``BrainBridge`` class.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from tapps_core.brain_bridge_errors import BrainBridgeUnavailable


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


class _InProcessOpsMixin:
    """Read, write, hive, and maintenance operations delegating to AgentBrain."""

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

    async def recall(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Relevance-ranked recall for auto-recall injection (TAP-6701).

        Distinct from :meth:`search`: this is the ranked-recall surface, not
        the structured filter search. The in-process :class:`tapps_brain.AgentBrain`
        (``agent_brain.py::recall``) has no composite-score computation — it
        returns ``confidence`` only, never ``score``. Callers must treat a
        missing ``score`` key on this path as legitimate (see
        :class:`HttpBrainBridge.recall` for the scored HTTP counterpart).
        """

        def _fn() -> list[dict[str, Any]]:
            return self._brain.recall(query, max_results=max_results)

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

    async def docs_lookup(
        self,
        library: str,
        topic: str = "overview",
        mode: str = "code",
    ) -> dict[str, Any]:
        """In-process bridge does not host doc RAG — use HTTP transport."""
        raise BrainBridgeUnavailable("docs_lookup requires HTTP brain bridge")

    async def docs_warm(self, libraries: list[str]) -> dict[str, Any]:
        """In-process bridge does not host doc RAG — use HTTP transport."""
        raise BrainBridgeUnavailable("docs_warm requires HTTP brain bridge")

    async def web_research(
        self,
        query: str,
        *,
        source: str = "auto",
        freshness: str = "volatile",
        max_results: int = 5,
    ) -> dict[str, Any]:
        """In-process bridge does not host web research — use HTTP transport."""
        raise BrainBridgeUnavailable("web_research requires HTTP brain bridge")

    async def research_fetch(
        self,
        url: str,
        *,
        freshness: str = "evergreen",
    ) -> dict[str, Any]:
        """In-process bridge does not host research fetch — use HTTP transport."""
        raise BrainBridgeUnavailable("research_fetch requires HTTP brain bridge")

    async def memory_profile_info(self) -> dict[str, Any]:
        """Describe the active memory profile.

        In-process callers read ``store.profile`` directly; only the HTTP
        transport needs a round-trip (brain ``profile_info``, ``full`` profile).
        """
        raise BrainBridgeUnavailable("memory_profile_info requires HTTP brain bridge")

    async def memory_profile_switch(self, name: str) -> dict[str, Any]:
        """Switch the active memory profile (brain ``profile_switch``)."""
        raise BrainBridgeUnavailable("memory_profile_switch requires HTTP brain bridge")

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

    @staticmethod
    def _entry_key_or_empty(entry: Any) -> str:
        """Extract the memory key from a dict or object entry, or ``""``."""
        if hasattr(entry, "key"):
            return str(entry.key) if entry.key else ""
        if isinstance(entry, dict):
            raw = entry.get("key")
            return str(raw) if raw else ""
        return ""

    def _apply_elevation_guard(
        self, entries: list[Any], guard: Any
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        """Split *entries* into (approved, refused-detail-dicts) via *guard*.

        Extracted from :meth:`hive_propagate` (TAP-6736) to cut its
        cyclomatic complexity — pure refactor, no behavior change.
        """
        if guard is None:
            return entries, []
        refused: list[dict[str, Any]] = []
        approved_entries: list[Any] = []
        for entry in entries:
            key = self._entry_key_or_empty(entry)
            if key and not guard(key):
                refused.append(
                    {"key": key, "refused": True, "reason": "elevation_approval_required"}
                )
                _log().warning(
                    "hive_propagate.refused_no_approval",
                    memory_key=key,
                    hint="Call brain_propose_hive_elevation then brain_approve_hive_elevation",
                )
            else:
                approved_entries.append(entry)
        return approved_entries, refused

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

        TAP-2014: when :attr:`elevation_guard` is set, each entry's key is
        checked against the approval store before propagation.  Entries without
        a valid approval are counted in ``refused_no_approval`` and excluded
        from the propagation batch.
        """
        # TAP-2014: apply elevation guard before entering the sync _fn block.
        filtered, refused = self._apply_elevation_guard(entries, self.elevation_guard)

        if refused and not filtered:
            return {
                "enabled": True,
                "degraded": False,
                "propagated": 0,
                "skipped_private": 0,
                "refused_no_approval": len(refused),
                "scanned": len(entries),
                "details": refused,
                "error": "elevation_approval_required",
                "message": (
                    "All entries refused: no approved hive elevation proposal found. "
                    "Call brain_propose_hive_elevation(memory_key, justification) then "
                    "brain_approve_hive_elevation(proposal_id) before retrying."
                ),
            }

        def _fn() -> dict[str, Any]:
            from tapps_brain.backends import PropagationEngine

            hive = self._brain.hive
            if hive is None:
                return {
                    "enabled": True,
                    "degraded": True,
                    "propagated": 0,
                    "skipped_private": 0,
                    "refused_no_approval": len(refused),
                    "scanned": len(entries),
                    "details": refused,
                    "message": "Hive backend not available.",
                }

            propagated = 0
            skipped_private = 0
            details: list[dict[str, Any]] = list(refused)

            for entry in filtered:
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
                "refused_no_approval": len(refused),
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

    async def promote_instinct(
        self,
        *,
        key: str,
        value: str,
        tier: str,
        scope: str,
        signal: str,
        actor: str,
        evidence: str,
    ) -> dict[str, Any]:
        """Promote a staged instinct to a served brain memory entry (KB-3.8, Ruling 8).

        Not yet supported over the in-process :class:`AgentBrain`/
        :class:`~tapps_brain.store.MemoryStore` path — ``learning_promote`` is
        a staged capability (TAP-6701 M1 ships the client call; a later wave
        ships the brain-side handler and the live ``--apply``).
        :class:`HttpBrainBridge` overrides this once that lands.
        """
        raise NotImplementedError(
            "promote_instinct requires the HTTP brain path (brain_http_url) — "
            "the in-process AgentBrain has no learning-promote capability yet"
        )

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
        """Scan for similar entries and merge them (periodic consolidation scan).

        With ``dry_run=True``, only report how many consolidation groups would
        be merged without mutating the store (``run_periodic_consolidation_scan``
        has no dry-run mode, so the group scan is performed directly).
        """
        from tapps_brain.auto_consolidation import run_periodic_consolidation_scan
        from tapps_brain.similarity import find_consolidation_groups

        project_root = Path(str(self._brain.store.project_root or "."))

        def _fn() -> dict[str, Any]:
            if dry_run:
                active = [e for e in self._brain.store.list_all() if not e.contradicted]
                groups = find_consolidation_groups(active, min_group_size=3)
                return {
                    "scanned": True,
                    "groups_found": len(groups),
                    "entries_consolidated": 0,
                    "consolidated_entries": [],
                    "skipped_reason": "dry_run",
                }
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
            _log().warning("brain_bridge.maintain.gc_failed", error=str(exc))

        try:
            consol_result = await self.consolidate(dry_run=False)
            # PeriodicScanResult uses ``groups_found`` (not ``groups_formed``).
            consolidated = int(
                consol_result.get("groups_found", consol_result.get("groups_formed", 0))
            )
        except Exception as exc:
            _log().warning("brain_bridge.maintain.consolidate_failed", error=str(exc))

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
            _log().warning("brain_bridge.maintain.dedup_failed", error=str(exc))

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

