"""HTTP memory CRUD + KG-read mixin for :class:`HttpBrainBridge`.

Split out of ``brain_bridge_http_ops.py`` (TAP-6736, further split). No
behavior change: each method body below is moved byte-for-byte. Composed as
``_HttpMemoryMixin`` alongside ``_HttpKgHiveMixin``, the HTTP transport
mixins, and ``BrainBridge`` into the public ``HttpBrainBridge`` class in the
facade module.
"""

from __future__ import annotations

import json
from typing import Any

from tapps_core.knowledge.kg_keys import entity_spec


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


class _HttpMemoryMixin:
    """Memory search/get/list/recall, KG reads, docs/research, and profile CRUD."""

    async def search(
        self,
        query: str,
        limit: int = 10,
        tier: str | None = None,
        *,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"query": query, "limit": limit}
        if tier is not None:
            args["tier"] = tier
        result = await self._http_mcp_call("memory_search", args, project_id=project_id)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("results") or result.get("entries") or []
        return []

    async def recall(
        self,
        query: str,
        max_results: int = 10,
        *,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Relevance-ranked recall carrying a wire ``score`` per hit (TAP-6701).

        Calls the ``brain_recall`` MCP tool rather than ``memory_search``.
        ``brain_recall`` (tapps-brain ``mcp_server/tools_brain.py::brain_recall``)
        and the REST ``POST /v1/recall`` (``http_adapter.py:1961``) are both thin
        transports over the same ``services.memory_service.brain_recall``
        (``memory_service.py:220``), which since TAP-6696 serializes a composite
        ``score`` per result, sorted desc, before truncating to ``max_results``.
        ``memory_search`` (``memory_service.py:1180``) is a distinct, unranked
        structured-filter search that never computes a score — that is why
        :meth:`search` cannot be reused for this. ``brain_recall`` is present in
        the ``reviewer`` profile (``mcp_profiles.yaml:277``), the same
        least-privilege profile ``memory_search`` uses, so no profile widening
        is required to call it from read-only auto-recall.
        """
        args: dict[str, Any] = {"query": query, "max_results": max_results}
        result = await self._http_mcp_call("brain_recall", args, project_id=project_id)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("results") or result.get("entries") or []
        return []

    async def get(
        self,
        key: str,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any] | None:
        result = await self._http_mcp_call("memory_get", {"key": key}, project_id=project_id)
        if isinstance(result, dict) and result.get("key") and not result.get("error"):
            return result
        return None

    async def list_memories(
        self,
        limit: int = 20,
        tier: str | None = None,
        *,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"limit": limit}
        if tier is not None:
            args["tier"] = tier
        result = await self._http_mcp_call("memory_list", args, project_id=project_id)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("entries") or result.get("results") or []
        return []

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

    async def docs_lookup(
        self,
        library: str,
        topic: str = "overview",
        mode: str = "code",
    ) -> dict[str, Any]:
        """Fetch library docs from brain ``docs_lookup`` (ADR-0014)."""
        result = await self._http_mcp_call(
            "docs_lookup",
            {"library": library, "topic": topic, "mode": mode},
        )
        return result if isinstance(result, dict) else {"content": str(result)}

    async def docs_warm(self, libraries: list[str]) -> dict[str, Any]:
        """Batch-warm library docs via brain ``docs_warm`` (ADR-0014)."""
        result = await self._http_mcp_call("docs_warm", {"libraries": libraries})
        return result if isinstance(result, dict) else {"warmed": result}

    async def web_research(
        self,
        query: str,
        *,
        source: str = "auto",
        freshness: str = "volatile",
        max_results: int = 5,
    ) -> dict[str, Any]:
        """Run brain ``web_research`` (ADR-0030 / TAP-5364 contract)."""
        result = await self._http_mcp_call(
            "web_research",
            {
                "query": query,
                "source": source,
                "freshness": freshness,
                "max_results": max_results,
            },
        )
        return result if isinstance(result, dict) else {"content": str(result)}

    async def research_fetch(
        self,
        url: str,
        *,
        freshness: str = "evergreen",
    ) -> dict[str, Any]:
        """Run brain ``research_fetch`` (ADR-0030 / TAP-5364 contract)."""
        result = await self._http_mcp_call(
            "research_fetch",
            {"url": url, "freshness": freshness},
        )
        return result if isinstance(result, dict) else {"content": str(result)}

    # -------------------------------------------------------------------------
    # Knowledge graph (TAP-1630)
    # -------------------------------------------------------------------------

    async def find_related(
        self,
        key: str,
        max_hops: int = 2,
        *,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Walk the knowledge graph from *key* outward and return related entries.

        Maps to the brain's ``memory_find_related`` tool.
        """
        args: dict[str, Any] = {"key": key, "max_hops": max_hops}
        result = await self._http_mcp_call("memory_find_related", args, project_id=project_id)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            entries = result.get("entries") or result.get("results") or []
            return entries if isinstance(entries, list) else []
        return []

    async def entry_relations(self, key: str) -> list[dict[str, Any]]:
        """Return all relations attached to a single entry (``memory_relations``)."""
        result = await self._http_mcp_call("memory_relations", {"key": key})
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            relations = result.get("relations") or result.get("results") or []
            return relations if isinstance(relations, list) else []
        return []

    async def query_relations(
        self,
        *,
        subject: str = "",
        predicate: str = "",
        object_entity: str = "",
    ) -> list[dict[str, Any]]:
        """Query relations matching an SPO triple (any field may be empty).

        Maps to the brain's ``memory_query_relations`` tool. At least one of
        *subject* / *predicate* / *object_entity* should be non-empty for a
        useful query; the brain will return all relations otherwise.
        """
        args: dict[str, Any] = {}
        if subject:
            args["subject"] = subject
        if predicate:
            args["predicate"] = predicate
        if object_entity:
            args["object_entity"] = object_entity
        result = await self._http_mcp_call("memory_query_relations", args)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            relations = result.get("relations") or result.get("results") or []
            return relations if isinstance(relations, list) else []
        return []

    async def get_neighbors(
        self,
        entity_ids: list[str],
        *,
        hops: int = 1,
        limit: int = 20,
        predicate_filter: str = "",
    ) -> dict[str, Any]:
        """Return the k-hop neighborhood of *entity_ids* (``brain_get_neighbors``).

        The brain expects ``entity_ids_json`` as a JSON-encoded array of
        string ids on the wire; this method takes a Python list and serialises.
        """
        args: dict[str, Any] = {
            "entity_ids_json": json.dumps(entity_ids),
            "hops": hops,
            "limit": limit,
        }
        if predicate_filter:
            args["predicate_filter"] = predicate_filter
        result = await self._http_mcp_call("brain_get_neighbors", args)
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return {"neighbors": result}
        return {"neighbors": []}

    async def query_events(
        self,
        event_type: str,
        *,
        since: str | None = None,
        until: str | None = None,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query recorded KG events by type (TAP-1997 phase-2).

        Returns an empty list when the brain does not expose
        ``brain_query_events`` yet (see ``docs/handoff/BRAIN-wave2-capabilities.md``).
        """
        args: dict[str, Any] = {"event_type": event_type, "limit": limit}
        if since:
            args["since"] = since
        if until:
            args["until"] = until
        if entity_id:
            args["entity_id"] = entity_id
        try:
            result = await self._http_mcp_call("brain_query_events", args)
        except Exception:
            _log().debug("brain_query_events_unavailable", event_type=event_type, exc_info=True)
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            events = result.get("events") or result.get("results") or []
            return events if isinstance(events, list) else []
        return []

    async def memory_profile_info(self) -> dict[str, Any]:
        """Return the active memory profile, layers, and scoring config.

        Brain tool ``profile_info`` (``full`` profile). Distinct from
        :meth:`profile_get`, which reads profile-scoped learned KV data.
        """
        result = await self._http_mcp_call("profile_info", {})
        return result if isinstance(result, dict) else {"ok": False}

    async def memory_profile_switch(self, name: str) -> dict[str, Any]:
        """Switch to a different built-in memory profile (brain ``profile_switch``)."""
        result = await self._http_mcp_call("profile_switch", {"name": name})
        return result if isinstance(result, dict) else {"ok": False}

    async def profile_get(self, profile: str, key: str) -> dict[str, Any]:
        """Read profile-scoped learned data (TAP-1998 / EPIC-074)."""
        result = await self._http_mcp_call(
            "brain_profile_get",
            {"profile": profile, "key": key},
        )
        return result if isinstance(result, dict) else {"ok": False}

    async def profile_set(self, profile: str, key: str, value_json: str) -> dict[str, Any]:
        """Persist profile-scoped learned data (TAP-1998 / EPIC-075)."""
        result = await self._http_mcp_call(
            "brain_profile_set",
            {"profile": profile, "key": key, "value_json": value_json},
        )
        return result if isinstance(result, dict) else {"ok": False}

    async def explain_connection(
        self,
        subject_id: str,
        object_id: str,
        *,
        max_hops: int = 3,
    ) -> dict[str, Any]:
        """Explain how *subject_id* connects to *object_id* in the graph.

        Maps to ``brain_explain_connection``. Returns the structured path /
        explanation dict the brain produces.
        """
        args: dict[str, Any] = {
            "subject_id": subject_id,
            "object_id": object_id,
            "max_hops": max_hops,
        }
        result = await self._http_mcp_call("brain_explain_connection", args)
        if isinstance(result, dict):
            return result
        return {"explanation": result}

    # -------------------------------------------------------------------------
    # Batch operations (TAP-1631)
    # -------------------------------------------------------------------------

    async def save_many(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Single-round-trip bulk save via ``memory_save_many`` (TAP-1631).

        Overrides the base :meth:`BrainBridge.save_many` loop with a real
        batched call. Each entry must include ``key`` and ``value``; other
        per-entry fields (``tier``, ``scope``, ``tags``, ``source``, …) flow
        through verbatim. Returns the brain's aggregate dict, normalised so
        callers always see ``saved`` / ``failed`` / ``total`` keys.
        """
        if not entries:
            return {"saved": 0, "failed": 0, "total": 0, "entries": []}
        result = await self._http_mcp_call("memory_save_many", {"entries": entries})
        if not isinstance(result, dict):
            return {"saved": len(entries), "failed": 0, "total": len(entries)}
        # Normalise: brain returns shape varies between releases; collapse to
        # the saved/failed/total triad the agent expects.
        saved = int(
            result.get("saved")
            or result.get("saved_count")
            or len(result.get("entries", []) if result.get("entries") else [])
        )
        failed = int(result.get("failed") or result.get("failed_count") or 0)
        total = int(result.get("total") or saved + failed or len(entries))
        return {**result, "saved": saved, "failed": failed, "total": total}

    async def recall_many(self, queries: list[str]) -> dict[str, Any]:
        """Batch recall via ``memory_recall_many``.

        Issues *queries* as a single call instead of N separate
        ``memory_recall`` round-trips. Returns the brain response dict
        unchanged (typically ``{"results": [{"query": ..., "hits": [...]}, ...]}``).
        """
        if not queries:
            return {"results": []}
        result = await self._http_mcp_call("memory_recall_many", {"queries": queries})
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return {"results": result}
        return {"results": []}

    async def reinforce_many(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Batch confidence boost via ``memory_reinforce_many``.

        Each entry must have a ``key`` and may include a ``confidence_boost``
        float (defaults are applied server-side when omitted).
        """
        if not entries:
            return {"reinforced": 0, "failed": 0, "total": 0}
        result = await self._http_mcp_call("memory_reinforce_many", {"entries": entries})
        if not isinstance(result, dict):
            return {"reinforced": len(entries), "failed": 0, "total": len(entries)}
        reinforced = int(
            result.get("reinforced")
            or result.get("reinforced_count")
            or len(result.get("entries", []) if result.get("entries") else [])
        )
        failed = int(result.get("failed") or result.get("failed_count") or 0)
        total = int(result.get("total") or reinforced + failed or len(entries))
        return {**result, "reinforced": reinforced, "failed": failed, "total": total}

    # -------------------------------------------------------------------------
    # Feedback flywheel + brain-quality diagnostics (TAP-1632)
    # -------------------------------------------------------------------------

    async def feedback_rate(
        self,
        entry_key: str,
        *,
        rating: str = "helpful",
        session_id: str = "",
        details_json: str = "",
    ) -> dict[str, Any]:
        """Score how useful a recalled entry was (``feedback_rate``).

        *rating* is server-defined (typically ``"helpful"`` / ``"unhelpful"`` /
        ``"misleading"``). ``details_json`` is an optional structured payload
        the brain stores alongside the rating for later analysis.
        """
        args: dict[str, Any] = {"entry_key": entry_key, "rating": rating}
        if session_id:
            args["session_id"] = session_id
        if details_json:
            args["details_json"] = details_json
        result = await self._http_mcp_call("feedback_rate", args)
        return result if isinstance(result, dict) else {"recorded": True}

    async def feedback_gap(
        self,
        query: str,
        *,
        session_id: str = "",
        details_json: str = "",
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Record an unmet-recall signal — the agent searched and got nothing.

        Drives the flywheel: the brain counts these gaps and surfaces them
        via ``flywheel_report``.
        """
        args: dict[str, Any] = {"query": query}
        if session_id:
            args["session_id"] = session_id
        if details_json:
            args["details_json"] = details_json
        result = await self._http_mcp_call("feedback_gap", args, project_id=project_id)
        return result if isinstance(result, dict) else {"recorded": True}

    async def flywheel_report(self, period_days: int = 7) -> dict[str, Any]:
        """Summary of feedback signal collected over the last *period_days*."""
        result = await self._http_mcp_call("flywheel_report", {"period_days": period_days})
        return result if isinstance(result, dict) else {"summary": result}

    async def flywheel_process(self, since: str = "") -> dict[str, Any]:
        """Process feedback events since *since* (ISO-8601 timestamp) via the flywheel.

        TAP-2005: called at session end so brain reconciles session events into
        adaptive weight updates. *since* should be the session-start ISO timestamp;
        empty string means "all unprocessed events".
        """
        args: dict[str, Any] = {}
        if since:
            args["since"] = since
        result = await self._http_mcp_call("flywheel_process", args)
        return result if isinstance(result, dict) else {"processed": True}

    async def diagnostics_report(self, record_history: bool = True) -> dict[str, Any]:
        """Brain-quality snapshot (decay, coverage, contradiction load)."""
        result = await self._http_mcp_call("diagnostics_report", {"record_history": record_history})
        return result if isinstance(result, dict) else {"report": result}

    async def record_event(
        self,
        event_type: str,
        entity_id: str,
    ) -> dict[str, Any]:
        """TAP-1992: Fire a KG event via ``brain_record_event`` (best-effort).

        Designed for deprecation-usage telemetry: pass ``event_type`` (e.g.
        ``"deprecated_tool_call"``) and ``entity_id`` (e.g.
        ``"tapps_memory:save"``) to capture a KG edge that can later be
        queried via ``brain_get_neighbors``.

        The brain stores the event as a KG entity + edge. Results are
        queryable via ``brain_get_neighbors(entity_ids=["tapps_memory:save"])``.
        """
        payload = {
            "event_type": event_type,
            "entities": [entity_spec("tool", entity_id)],
        }
        args = {
            "event_type": event_type,
            "payload_json": json.dumps(payload),
        }
        result = await self._http_mcp_call("brain_record_event", args)
        return result if isinstance(result, dict) else {"recorded": True}

