"""HTTP KG-write/hive/feedback/session/maintenance mixin for :class:`HttpBrainBridge`.

Split out of ``brain_bridge_http_ops.py`` (TAP-6736, further split). No
behavior change: each method body below is moved byte-for-byte. Composed as
``_HttpKgHiveMixin`` alongside ``_HttpMemoryMixin``, the HTTP transport
mixins, and ``BrainBridge`` into the public ``HttpBrainBridge`` class in the
facade module.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from tapps_core.brain_bridge_errors import (
    _BRAIN_HEALTH_TIMEOUT_SECONDS,
    BrainBridgeUnavailable,
    _classify_mcp_error,
)
from tapps_core.knowledge.kg_keys import entity_uuid


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


class _HttpKgHiveMixin:
    """KG events, hive propagation, feedback, session index, and maintenance."""

    async def record_kg_event(
        self,
        event_type: str,
        entities: list[dict[str, str]],
        edges: list[dict[str, str]] | None = None,
        payload_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """TAP-2003: Fire a rich KG event via ``brain_record_event`` (best-effort).

        Use for structured events with multiple entities and typed edges:
        - quality gate failures: file entity + rule entity + ``violates`` edge
        - dependency tracking
        - audit telemetry

        Args:
            event_type: Brain event type string (e.g. ``"quality_gate_fail"``).
            entities: List of ``{"entity_type": <str>, "canonical_name": <str>}``
                dicts (``EntitySpec`` on the brain side). Legacy ``type``/``id``
                shorthands are not reliably upserted — prefer canonical names.
            edges: Optional list of edge specs. Brain ``EdgeSpec`` requires
                pre-resolved entity UUIDs; omit edges when payload alone suffices
                (e.g. ``quality_metric`` telemetry).
            payload_data: Optional dict of scalar metadata stored on
                ``experience_events.payload`` (scores, thresholds, etc.).

        Payload reads (dashboard, stats) require ``brain_query_events`` once
        shipped; ``brain_get_neighbors`` returns KG structure only, not payloads.
        """
        event_payload: dict[str, Any] = {
            "event_type": event_type,
            "entities": entities,
        }
        if edges:
            event_payload["edges"] = edges
        if payload_data:
            event_payload["payload"] = payload_data

        args = {
            "event_type": event_type,
            "payload_json": json.dumps(event_payload),
        }
        result = await self._http_mcp_call("brain_record_event", args)
        return result if isinstance(result, dict) else {"recorded": True}

    # -------------------------------------------------------------------------
    # KG semantic upsert shims (TAP-1947)
    #
    # Thin verbs over :meth:`record_kg_event` — no second write path. Entity
    # IDs are derived deterministically (TAP-1949) so a re-run upserts the
    # same row instead of inserting a duplicate, and the caller learns the id
    # without a round-trip (even when the write is queued offline).
    # -------------------------------------------------------------------------

    def _resolve_project_id(self, project_id: str) -> str:
        """Resolve the brain project slug for entity-key derivation.

        Falls back to the bridge's ``X-Project-Id`` header (set by the
        factory from ``TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID``), then the
        ``TAPPS_BRAIN_PROJECT`` env var, so all writers on the same project
        derive identical entity UUIDs.
        """
        if project_id:
            return project_id
        header = self._http_headers.get("X-Project-Id", "")
        return header or os.environ.get("TAPPS_BRAIN_PROJECT", "")

    def _queue_kg_event(
        self,
        event_type: str,
        entities: list[dict[str, str]],
        edges: list[dict[str, str]] | None,
        payload_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Enqueue a KG event for offline drain and return a degraded envelope."""
        queued = self._enqueue_write(
            {
                "_kind": "kg_event",
                "event_type": event_type,
                "entities": entities,
                "edges": edges,
                "payload_data": payload_data,
            }
        )
        return {
            "success": False,
            "degraded": True,
            "reason": "circuit open",
            "queued": queued,
            "queue_depth": self.queue_depth,
        }

    async def upsert_entity(
        self,
        canonical_name: str,
        entity_type: str,
        *,
        aliases: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        project_id: str = "",
    ) -> dict[str, Any]:
        """Idempotently upsert a KG entity; return ``{"entity_id": <uuid>}``.

        Idempotent on ``(canonical_name, entity_type, project_id)`` — the id
        is the deterministic UUIDv5 from :func:`kg_keys.entity_uuid`, so
        repeated upserts of the same entity collapse to one ``kg_entities``
        row. When the circuit is open the event is queued for later drain;
        the returned ``entity_id`` is still valid because it is derived, not
        assigned by the brain.
        """
        pid = self._resolve_project_id(project_id)
        eid = str(entity_uuid(pid, entity_type, canonical_name))
        entities = [{"type": entity_type, "id": eid}]
        payload: dict[str, Any] = {"canonical_name": canonical_name}
        if aliases:
            payload["aliases"] = aliases
        if metadata:
            payload["metadata"] = metadata
        if self.circuit_open:
            envelope = self._queue_kg_event("entity_upsert", entities, None, payload)
            return {"entity_id": eid, **envelope}
        result = await self.record_kg_event("entity_upsert", entities, None, payload)
        return {"entity_id": eid, **result}

    async def upsert_edge(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        *,
        evidence: dict[str, Any],
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        """Upsert a typed edge with a paired evidence row (ADR-012).

        ADR-012 forbids evidence-free edges: ``evidence`` must carry at least
        a ``file_path``. The edge and its evidence are emitted in one atomic
        ``record_kg_event`` call. Raises :class:`ValueError` (validation) when
        evidence is absent.
        """
        if not evidence or not evidence.get("file_path"):
            raise ValueError(
                "upsert_edge requires a paired evidence row with a file_path "
                "(ADR-012: no evidence-free edges)"
            )
        entities = [
            {"type": "node", "id": subject_id},
            {"type": "node", "id": object_id},
        ]
        edges = [{"src": subject_id, "predicate": predicate, "dst": object_id}]
        payload: dict[str, Any] = {"confidence": confidence, "evidence": evidence}
        if self.circuit_open:
            return self._queue_kg_event("edge_upsert", entities, edges, payload)
        return await self.record_kg_event("edge_upsert", entities, edges, payload)

    async def add_evidence(
        self,
        *,
        file_path: str,
        line_range: str,
        commit_sha: str,
        entity_id: str = "",
        edge_id: str = "",
    ) -> dict[str, Any]:
        """Attach an evidence row to exactly one entity OR edge (XOR).

        Stores ``(file_path, line_range, commit_sha)`` against the target.
        Raises :class:`ValueError` (validation) unless exactly one of
        ``entity_id`` / ``edge_id`` is given.
        """
        if bool(entity_id) == bool(edge_id):
            raise ValueError("add_evidence requires exactly one of entity_id or edge_id")
        target_kind = "entity" if entity_id else "edge"
        target_id = entity_id or edge_id
        entities = [{"type": f"{target_kind}_ref", "id": target_id}]
        payload: dict[str, Any] = {
            "target_kind": target_kind,
            "file_path": file_path,
            "line_range": line_range,
            "commit_sha": commit_sha,
        }
        if self.circuit_open:
            return self._queue_kg_event("evidence_add", entities, None, payload)
        return await self.record_kg_event("evidence_add", entities, None, payload)

    async def _replay_queued_write(self, entry: dict[str, Any]) -> None:
        """Route queued KG events back through :meth:`record_kg_event`.

        Save-shaped entries (no ``_kind``) fall through to the base behaviour.
        """
        if entry.get("_kind") == "kg_event":
            await self.record_kg_event(
                entry["event_type"],
                entry["entities"],
                entry.get("edges"),
                entry.get("payload_data"),
            )
            return
        await self.save(**entry)

    async def record_feedback(
        self,
        feedback_type: str,
        edge_id: str = "",
        entry_key: str = "",
        session_id: str = "",
        utility_score: float = 0.0,
        details: dict[str, Any] | None = None,
        agent_id: str = "",
    ) -> dict[str, Any]:
        """TAP-1938: Record feedback for a KG edge or memory entry.

        Routes to the edge-feedback path when ``edge_id`` is set, or the
        memory-feedback path when ``entry_key`` is set (``edge_id`` takes
        precedence server-side).  ``details`` is JSON-serialised to
        ``details_json`` before dispatch.

        Participates in circuit-breaker + retry semantics matching other
        bridge calls.  Does **not** enqueue when the circuit is open —
        feedback loss is preferable to stale queue growth.
        """
        args: dict[str, Any] = {
            "feedback_type": feedback_type,
            "edge_id": edge_id,
            "entry_key": entry_key,
            "session_id": session_id,
            "utility_score": utility_score,
            "details_json": json.dumps(details) if details else "",
        }
        if agent_id:
            args["agent_id"] = agent_id
        result = await self._http_mcp_call("brain_record_feedback", args)
        return result if isinstance(result, dict) else {"recorded": True}

    # -------------------------------------------------------------------------
    # Native session memory (TAP-1633)
    # -------------------------------------------------------------------------

    async def index_session(
        self,
        session_id: str,
        chunks: list[str],
    ) -> dict[str, Any]:
        """Index a session's chunks for later searching (``memory_index_session``).

        Replaces the legacy in-repo BM25-only session index — the brain
        now owns this surface natively with BM25 + embeddings + decay.
        """
        args: dict[str, Any] = {"session_id": session_id, "chunks": chunks}
        result = await self._http_mcp_call("memory_index_session", args)
        return result if isinstance(result, dict) else {"stored": True}

    async def search_sessions(
        self,
        query: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search indexed session chunks (``memory_search_sessions``)."""
        args: dict[str, Any] = {"query": query, "limit": limit}
        result = await self._http_mcp_call("memory_search_sessions", args)
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return {"results": result}
        return {"results": []}

    async def session_end(
        self,
        summary: str,
        *,
        tags: list[str] | None = None,
        daily_note: bool = False,
    ) -> dict[str, Any]:
        """Record a session-end summary (``tapps_brain_session_end``)."""
        args: dict[str, Any] = {"summary": summary, "daily_note": daily_note}
        if tags is not None:
            args["tags"] = tags
        result = await self._http_mcp_call("tapps_brain_session_end", args)
        return result if isinstance(result, dict) else {"recorded": True}

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

    @staticmethod
    def _entry_key(entry: Any) -> str | None:
        """Extract the memory key from a dict or object entry, or ``None``."""
        if hasattr(entry, "key"):
            return str(entry.key) if entry.key else None
        if isinstance(entry, dict):
            raw = entry.get("key")
            return str(raw) if raw else None
        return None

    @staticmethod
    def _entry_agent_scope(entry: Any) -> Any:
        """Read ``agent_scope`` from a dict or object entry."""
        if isinstance(entry, dict):
            return entry.get("agent_scope")
        return getattr(entry, "agent_scope", None)

    async def _propagate_one_entry(
        self, entry: Any, key: str, agent_profile: str, guard: Any
    ) -> tuple[dict[str, Any], bool]:
        """Propagate a single entry; return ``(detail, propagated)``.

        Extracted from :meth:`hive_propagate` (TAP-6736) to cut its
        cyclomatic complexity — pure refactor, no behavior change.
        """
        if self._entry_agent_scope(entry) == "private":
            return {"key": key, "skipped": "private"}, False
        # TAP-2014: check elevation guard before propagating.
        if guard is not None and not guard(key):
            _log().warning(
                "hive_propagate.refused_no_approval",
                memory_key=key,
                hint="Call brain_propose_hive_elevation then brain_approve_hive_elevation",
            )
            return (
                {"key": key, "refused": True, "reason": "elevation_approval_required"},
                False,
            )
        try:
            per = await self._http_mcp_call(
                "hive_propagate",
                {"key": key, "agent_scope": agent_profile or "hive"},
            )
        except Exception as exc:
            return {"key": key, "error": str(exc)}, False
        if isinstance(per, dict):
            return {"key": key, **per}, bool(per.get("propagated") or per.get("success"))
        return {"key": key}, True

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
        #
        # TAP-2014: apply elevation_guard before each propagation call.
        _ = agent_id
        guard = self.elevation_guard
        propagated = 0
        skipped_private = 0
        refused_no_approval = 0
        details: list[dict[str, Any]] = []
        for entry in entries:
            key = self._entry_key(entry)
            if not key:
                continue
            detail, did_propagate = await self._propagate_one_entry(
                entry, key, agent_profile, guard
            )
            details.append(detail)
            if did_propagate:
                propagated += 1
            elif detail.get("skipped") == "private":
                skipped_private += 1
            elif detail.get("refused"):
                refused_no_approval += 1
        return {
            "enabled": True,
            "degraded": False,
            "refused_no_approval": refused_no_approval,
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
        project_id: str | None = None,
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
        result: dict[str, Any] = await self._http_mcp_call(
            "memory_save", args, project_id=project_id
        )
        self._maybe_start_drain()
        return result if isinstance(result, dict) else {"key": key, "success": True}

    async def delete(self, key: str, *, project_id: str | None = None) -> bool:
        result = await self._http_mcp_call("memory_delete", {"key": key}, project_id=project_id)
        if isinstance(result, bool):
            return result
        if isinstance(result, dict):
            return bool(result.get("deleted", result.get("success", False)))
        return False

    async def reinforce(self, key: str, boost: float = 0.1) -> dict[str, Any]:
        result = await self._http_mcp_call(
            "memory_reinforce", {"key": key, "confidence_boost": boost}
        )
        return result if isinstance(result, dict) else {"key": key}

    async def supersede(self, key: str, new_value: str, **kwargs: Any) -> dict[str, Any]:
        args: dict[str, Any] = {"key": key, "new_value": new_value, **kwargs}
        result = await self._http_mcp_call("memory_supersede", args)
        return result if isinstance(result, dict) else {"key": key}

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

        Calls the brain's ``learning_promote`` tool — not present in the
        tapps-brain>=3.28.0,<4 floor pinned by ADR-0033 as of TAP-6701 (no
        ``learning_promote`` registration found in ``tools_memory.py`` /
        ``tools_maintenance.py`` of the installed 3.29.0 package, and
        ``MemoryEntry`` has no ``promotion_signal``/``promoted_by``/``evidence``
        fields yet). This is the client-side half of a staged rollout: the
        call will fail against today's brain until a later wave ships the
        handler and schema; this lane never invokes it for real (SC-6) —
        only against a mocked bridge in tests.
        """
        args: dict[str, Any] = {
            "key": key,
            "value": value,
            "tier": tier,
            "scope": scope,
            "signal": signal,
            "actor": actor,
            "evidence": evidence,
        }
        result = await self._http_mcp_call("learning_promote", args)
        return result if isinstance(result, dict) else {"key": key, "success": bool(result)}

    # -------------------------------------------------------------------------
    # Maintenance (HTTP overrides)
    # -------------------------------------------------------------------------

    async def gc(self, dry_run: bool = False) -> dict[str, Any]:
        # tapps-brain only registers ``maintenance_gc`` (operator profile);
        # ``memory_gc`` was never a registered name. When the brain is
        # reachable on a non-operator profile (``full``/``coder``/…), the
        # call surfaces as a profile-denial McpError (``-32601`` with
        # ``data.error=="tool_not_in_profile"``). Treat that the same way
        # ``consolidate`` treats removal: degraded stub instead of raising.
        try:
            result = await self._http_mcp_call("maintenance_gc", {"dry_run": dry_run})
        except (RuntimeError, BrainBridgeUnavailable) as exc:
            classification = _classify_mcp_error(exc)
            if classification in {"gated", "removed"}:
                return {
                    "archived_count": 0,
                    "degraded": True,
                    "reason": (
                        "maintenance_gc not in active brain profile"
                        if classification == "gated"
                        else "maintenance_gc unavailable on this brain"
                    ),
                    "dry_run": dry_run,
                }
            raise
        return result if isinstance(result, dict) else {"archived_count": 0}

    async def consolidate(self, dry_run: bool = False) -> dict[str, Any]:
        # brain 3.10+ removed ``memory_consolidate``; the replacement is
        # ``maintenance_consolidate``, which lives in the *operator* profile
        # (mcp_profiles.yaml) alongside ``maintenance_gc``. Calling it from a
        # data-plane profile (``full``/``coder``/…) surfaces as a profile
        # denial, so keep the degraded stub for that path — but target the
        # tool that actually exists so operator-profile deployments really
        # consolidate instead of always degrading. Tracked in TAP-800 drift 1.
        try:
            result = await self._http_mcp_call("maintenance_consolidate", {"dry_run": dry_run})
        except (RuntimeError, BrainBridgeUnavailable) as exc:
            classification = _classify_mcp_error(exc)
            if classification in {"gated", "removed"}:
                return {
                    "groups_found": 0,
                    "degraded": True,
                    "reason": (
                        "maintenance_consolidate not in active brain profile"
                        if classification == "gated"
                        else "maintenance_consolidate unavailable on this brain"
                    ),
                    "dry_run": dry_run,
                }
            raise
        return result if isinstance(result, dict) else {"groups_found": 0}

    # -------------------------------------------------------------------------
    # Diagnostics (HTTP overrides)
    # -------------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Return health dict by probing ``{brain_http_url}/health``.

        Uses ``httpx.AsyncClient`` so the call does not block the event loop
        (TAP-1743: the old ``httpx.get`` in an ``async def`` stalled every
        concurrent MCP tool handler for the duration of the round-trip).
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._http_url}/health",
                    timeout=_BRAIN_HEALTH_TIMEOUT_SECONDS,
                )
            response.raise_for_status()
            payload = response.json()
            base = payload if isinstance(payload, dict) else {}
            return {"status": "ok", "postgres": "connected", **base}
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)}

