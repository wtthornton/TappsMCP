"""Session-start helper functions for TappsMCP pipeline tools.

Extracted from ``server_pipeline_tools.py`` for maintainability.
Re-exported from ``server_pipeline_tools`` for backward compatibility.

The session-state flags (``_session_state``, ``_state_lock``, ``_background_tasks``)
live in ``server_pipeline_tools`` to avoid circular imports; this module looks
them up at call time via the host module.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from tapps_brain.models import MemorySnapshot
    from tapps_brain.store import MemoryStore

    from tapps_core.config.settings import TappsMCPSettings

_logger = structlog.get_logger(__name__)


def _maybe_auto_gc(
    store: MemoryStore,
    current_count: int,
    settings: object,
) -> dict[str, Any] | None:
    """Run garbage collection if memory usage exceeds the configured threshold.

    Returns a summary dict when GC ran, or ``None`` if skipped.
    Only runs once per session (guarded by ``_session_state.gc_done``).
    """
    from tapps_mcp import server_pipeline_tools as _host

    if _host._session_state.gc_done:
        return None

    mem_settings = getattr(settings, "memory", None)
    if mem_settings is None:
        return None

    gc_enabled = getattr(mem_settings, "gc_enabled", True)
    if not gc_enabled:
        return None

    max_memories = getattr(mem_settings, "max_memories", 1500)
    threshold = getattr(mem_settings, "gc_auto_threshold", 0.8)
    trigger_count = int(max_memories * threshold)

    if current_count <= trigger_count:
        return None

    _host._session_state.gc_done = True

    try:
        from tapps_brain.decay import DecayConfig
        from tapps_brain.gc import MemoryGarbageCollector

        config = DecayConfig()
        gc = MemoryGarbageCollector(config)

        snapshot = store.snapshot()
        candidates = gc.identify_candidates(snapshot.entries)

        archived_keys: list[str] = []
        for candidate in candidates:
            deleted = store.delete(candidate.key)
            if deleted:
                archived_keys.append(candidate.key)

        remaining = store.count()

        _logger.info(
            "session_auto_gc_completed",
            evicted=len(archived_keys),
            remaining=remaining,
            threshold=threshold,
        )

        return {
            "ran": True,
            "evicted": len(archived_keys),
            "remaining": remaining,
        }
    except Exception:
        _logger.debug("session_auto_gc_failed", exc_info=True)
        return {"ran": False, "error": "auto-gc failed"}


def _enrich_memory_status_hints(
    memory_status: dict[str, Any],
    entries: list[Any],
    settings: TappsMCPSettings,
) -> None:
    """Add consolidation and federation hints to memory_status when applicable (Epic 65.1)."""
    try:
        from tapps_core.metrics.dashboard import DashboardGenerator

        consolidation = DashboardGenerator._compute_consolidation_stats(entries)
        if consolidation.get("consolidation_groups", 0) > 0:
            memory_status["consolidation_hint"] = (
                f"{consolidation['consolidated_count']} groups, "
                f"{consolidation['source_entries_count']} source entries"
            )

        from tapps_brain.federation import load_federation_config

        config = load_federation_config()
        project_root_str = str(settings.project_root)
        if any(p.project_root == project_root_str for p in config.projects):
            synced = sum(1 for e in entries if "federated" in (e.tags or []))
            memory_status["federation_hint"] = f"hub_registered, {synced} synced entries"
    except Exception:
        _logger.debug("memory_status_hints_failed", exc_info=True)


def _enrich_memory_profile_status(
    memory_status: dict[str, Any],
    store: Any,
    settings: TappsMCPSettings,
) -> None:
    """Add active profile name and source to memory_status (Epic M2.4)."""
    try:
        profile = store.profile
        profile_name = profile.name if profile is not None else "repo-brain"

        # Detect source
        project_yaml = settings.project_root / ".tapps-brain" / "profile.yaml"
        if settings.memory.profile:
            source = "settings"
        elif project_yaml.exists():
            source = "project_override"
        else:
            source = "default"

        memory_status["profile"] = profile_name
        memory_status["profile_source"] = source
    except Exception:
        _logger.debug("memory_profile_status_failed", exc_info=True)


def _maybe_consolidation_scan(
    store: MemoryStore,
    settings: TappsMCPSettings,
) -> dict[str, Any] | None:
    """Run periodic memory consolidation scan if enabled and due.

    Returns a summary dict when scan ran, or ``None`` if skipped.
    Only runs once per session (guarded by ``_session_state.consolidation_done``).

    Epic 58, Story 58.3: Periodic consolidation scan at session start.
    """
    from tapps_mcp import server_pipeline_tools as _host

    # Early exit: already ran this session or settings not configured
    if _host._session_state.consolidation_done:
        return None

    mem_settings = getattr(settings, "memory", None)
    consolidation_settings = getattr(mem_settings, "consolidation", None) if mem_settings else None
    scan_enabled = getattr(consolidation_settings, "scan_on_session_start", True)
    if not consolidation_settings or not scan_enabled:
        return None

    _host._session_state.consolidation_done = True

    try:
        from tapps_brain.auto_consolidation import run_periodic_consolidation_scan

        result = run_periodic_consolidation_scan(
            store,
            settings.project_root,
            threshold=consolidation_settings.threshold,
            min_group_size=consolidation_settings.min_entries,
            scan_interval_days=consolidation_settings.scan_interval_days,
        )

        if result.scanned:
            _logger.info(
                "session_consolidation_scan_completed",
                groups_found=result.groups_found,
                entries_consolidated=result.entries_consolidated,
            )
            return result.to_dict()

        if result.skipped_reason:
            _logger.debug(
                "session_consolidation_scan_skipped",
                reason=result.skipped_reason,
            )
            return {"skipped": True, "reason": result.skipped_reason}

        return None
    except Exception:
        _logger.debug("session_consolidation_scan_failed", exc_info=True)
        return {"ran": False, "error": "consolidation scan failed"}


async def call_memory_index_session_start(
    session_id: str,
    project_root: Path,
) -> dict[str, Any]:
    """Index this session's start in the brain-native session store.

    TAP-1999: replaces the legacy ``_process_session_capture`` disk-file
    pattern.  Registers the session with ``memory_index_session`` so it is
    queryable via ``memory_search_sessions`` across sessions.

    Best-effort — brain unavailability must not prevent session start
    from completing.
    """
    try:
        from tapps_mcp.server_helpers import _get_brain_bridge

        bridge = _get_brain_bridge()
    except Exception as exc:
        _logger.debug("memory_index_session_start_bridge_failed", error=str(exc))
        return {"success": False, "skipped": True, "reason": "bridge_unavailable"}

    if bridge is None:
        return {"success": False, "skipped": True, "reason": "bridge_unavailable"}

    if not hasattr(bridge, "index_session"):
        return {"success": False, "skipped": True, "reason": "index_session_not_supported"}

    chunks = [
        f"session_start:{session_id}",
        f"project:{project_root.name}",
    ]

    try:
        result = await bridge.index_session(session_id, chunks)
    except Exception as exc:
        _logger.warning(
            "memory_index_session_start_failed",
            error=str(exc),
            session_id=session_id,
        )
        return {"success": False, "error": str(exc)}

    _logger.info("memory_index_session_start_completed", session_id=session_id)
    return {
        "success": True,
        "session_id": session_id,
        "chunks": len(chunks),
        "result": result,
    }


def _process_session_capture(
    project_root: Path,
    store: MemoryStore,
) -> dict[str, Any] | None:
    """Check for and process a session-capture.json left by the Stop hook.

    If the file exists, reads it, persists the data to memory, deletes
    the capture file, and returns a summary dict.  Returns ``None`` if
    no capture file exists.  Failures are logged and silently ignored.
    """
    import json as _json

    capture_path = project_root / ".tapps-mcp" / "session-capture.json"
    if not capture_path.exists():
        return None

    try:
        raw = capture_path.read_text(encoding="utf-8")
        data = _json.loads(raw)
        date_str = data.get("date", "unknown")
        validated = data.get("validated", False)
        files_edited = data.get("files_edited", 0)

        value = (
            f"Session on {date_str}: "
            f"{'validated' if validated else 'not validated'}, "
            f"{files_edited} Python file(s) edited."
        )
        store.save(
            key=f"session-capture.{date_str}",
            value=value,
            tier="context",
            source="system",
            source_agent="tapps-memory-capture-hook",
            scope="project",
            tags=["session-capture", "auto"],
        )

        capture_path.unlink(missing_ok=True)

        _logger.info(
            "session_capture_processed",
            date=date_str,
            validated=validated,
            files_edited=files_edited,
        )
        return {
            "date": date_str,
            "validated": validated,
            "files_edited": files_edited,
        }
    except Exception:
        _logger.debug("session_capture_processing_failed", exc_info=True)
        # Clean up even on failure to avoid re-processing bad data
        with contextlib.suppress(OSError):
            capture_path.unlink(missing_ok=True)
        return None


async def _check_compaction_rehydration(
    project_root: Path,
) -> dict[str, Any] | None:
    """Check for a compaction-marker written by the PreCompact hook (TAP-2017).

    When ``tapps-pre-compact.sh`` runs before Claude Code compacts the context,
    it calls ``tapps-mcp compact-index`` which:
      1. Writes ``.tapps-mcp/compaction-marker.json`` with the session_id and
         a list of indexable chunks.
      2. Calls ``memory_index_session`` on the brain bridge so the pre-compact
         state is persisted and queryable via ``memory_search_sessions``.

    This function checks for that marker on session start.  If found:
      - Reads the session_id and indexed_in_brain flag.
      - Calls ``bridge.search_sessions()`` to pull back any matching chunks.
      - Deletes the marker so subsequent session-start calls don't re-surface
        stale rehydration data.

    Returns ``None`` when no marker is present or the check is disabled via
    ``TAPPS_MCP_COMPACTION_REHYDRATE=false``.  Failures are silently suppressed
    so a brain outage cannot block session start.
    """
    import json as _json
    import os

    if os.environ.get("TAPPS_MCP_COMPACTION_REHYDRATE", "true").lower() == "false":
        return None

    from tapps_mcp.memory.compact_index import COMPACTION_MARKER_FILENAME

    marker_path = project_root / ".tapps-mcp" / COMPACTION_MARKER_FILENAME
    if not marker_path.exists():
        return None

    try:
        marker: dict[str, Any] = _json.loads(marker_path.read_text(encoding="utf-8"))
    except Exception:
        _logger.debug("compaction_rehydration_marker_read_failed", exc_info=True)
        return None
    finally:
        # Always delete the marker — even on read failure — to avoid infinite
        # rehydration loops on subsequent session starts.
        try:
            marker_path.unlink(missing_ok=True)
        except OSError:
            pass

    session_id = marker.get("session_id", "")
    compacted_at = marker.get("compacted_at", 0.0)
    indexed = marker.get("indexed_in_brain", False)

    result: dict[str, Any] = {
        "session_id": session_id,
        "compacted_at": compacted_at,
        "indexed_in_brain": indexed,
        "prior_chunks": [],
    }

    if not indexed or not session_id:
        return result

    # Attempt to fetch prior context from the brain.
    try:
        from tapps_mcp.server_helpers import (
            _get_brain_bridge as _get_brain_bridge_fn,
        )

        bridge = _get_brain_bridge_fn()
        if bridge is not None and hasattr(bridge, "search_sessions"):
            search_result = await bridge.search_sessions(  # type: ignore[misc]
                f"compaction_boundary:{session_id}", limit=5
            )
            if isinstance(search_result, dict):
                hits = search_result.get("results", [])
                result["prior_chunks"] = [h.get("chunk", "") for h in hits if isinstance(h, dict)]
                result["search_result_count"] = len(hits)
    except Exception as exc:
        _logger.debug(
            "compaction_rehydration_search_failed",
            error=str(exc),
            session_id=session_id,
        )

    _logger.info(
        "compaction_rehydration_check_completed",
        session_id=session_id,
        indexed=indexed,
        prior_chunks=len(result.get("prior_chunks", [])),
    )
    return result


def _cleanup_legacy_learning_dir(project_root: Path) -> bool:
    """One-shot cleanup of the legacy ``.tapps-mcp/learning/`` directory (TAP-2023).

    The directory was created by ``FileOutcomeTracker`` and
    ``FilePerformanceTracker`` in ``tapps-core``, but neither class is
    instantiated in production code — they exist only as backward-compat
    re-exports.  The directory is therefore a cargo-cult artifact; this
    function removes it on the next session start.

    Only removes the directory if it is empty or contains only the two
    known JSONL files (``outcomes.jsonl``, ``expert_performance.jsonl``).
    Leaves unknown files untouched and logs a warning so operators can
    inspect them.

    Returns ``True`` if the directory was removed, ``False`` otherwise.
    """
    learning_dir = project_root / ".tapps-mcp" / "learning"
    if not learning_dir.exists():
        return False

    known_files = {"outcomes.jsonl", "expert_performance.jsonl"}
    try:
        actual = {p.name for p in learning_dir.iterdir()}
    except OSError:
        _logger.debug("legacy_learning_dir_list_failed", exc_info=True)
        return False

    unexpected = actual - known_files
    if unexpected:
        _logger.warning(
            "legacy_learning_dir_has_unknown_files",
            directory=str(learning_dir),
            unexpected=sorted(unexpected),
        )
        return False

    # Remove known files then the directory itself.
    for name in actual & known_files:
        with contextlib.suppress(OSError):
            (learning_dir / name).unlink(missing_ok=True)

    try:
        learning_dir.rmdir()
        _logger.info("legacy_learning_dir_removed", directory=str(learning_dir))
        return True
    except OSError:
        _logger.debug("legacy_learning_dir_rmdir_failed", exc_info=True)
        return False


async def _maybe_validate_memories(
    store: MemoryStore,
    settings: TappsMCPSettings,
) -> dict[str, Any] | None:
    """Validate stale memories against authoritative docs at session start.

    Returns a summary dict when validation ran, or ``None`` if skipped.
    Only runs once per session (guarded by ``_session_state.doc_validation_done``).

    Epic 62, Story 62.6: Session-start validation pass.
    """
    from tapps_mcp import server_pipeline_tools as _host

    mem_settings = getattr(settings, "memory", None)
    doc_val = getattr(mem_settings, "doc_validation", None) if mem_settings else None
    if (
        doc_val is None
        or not getattr(doc_val, "enabled", False)
        or not getattr(doc_val, "validate_on_session_start", True)
    ):
        return None

    async with _host._state_lock:
        if _host._session_state.doc_validation_done:
            return None
        _host._session_state.doc_validation_done = True

    try:
        from tapps_brain.doc_validation import MemoryDocValidator

        from tapps_core.knowledge.cache import KBCache
        from tapps_core.knowledge.lookup import LookupEngine

        _cache = KBCache(settings.project_root / ".tapps-mcp-cache")
        lookup = LookupEngine(_cache, settings=settings)
        validator = MemoryDocValidator(lookup)  # type: ignore[arg-type]  # LookupEngine has extra kwargs vs LookupEngineLike Protocol

        all_entries = store.list_all()
        max_entries = getattr(doc_val, "max_entries_per_session", 5)
        threshold = getattr(doc_val, "confidence_threshold", 0.5)
        dry_run = getattr(doc_val, "dry_run", False)

        report = await validator.validate_stale(
            all_entries,
            confidence_threshold=threshold,
            max_entries=max_entries,
        )

        if not report.entries:
            return {"ran": True, "validated": 0, "skipped": "no stale entries"}

        apply_result = await validator.apply_results(
            report,
            store,
            dry_run=dry_run,
        )

        _logger.info(
            "session_doc_validation_completed",
            validated=report.validated,
            flagged=report.flagged,
            no_docs=report.no_docs,
            dry_run=dry_run,
        )

        return {
            "ran": True,
            "validated": report.validated,
            "flagged": report.flagged,
            "no_docs": report.no_docs,
            "adjustments": apply_result.boosted + apply_result.penalised,
            "dry_run": dry_run,
        }
    except Exception:
        _logger.debug("session_doc_validation_failed", exc_info=True)
        return {"ran": False, "error": "doc validation failed"}


def _schedule_background_maintenance(
    mem_store: MemoryStore,
    snapshot: MemorySnapshot,
    settings: TappsMCPSettings,
) -> None:
    """Schedule heavy memory maintenance ops as fire-and-forget background tasks.

    Moves GC, consolidation scan, doc validation, and session indexing
    off the critical path so ``tapps_session_start`` returns faster.

    Epic 68.2: Session start performance optimization.
    TAP-1999: ``_process_session_capture`` (disk-file) replaced by
    ``call_memory_index_session_start`` (brain-native).

    Looks up ``_maybe_auto_gc``, ``_maybe_consolidation_scan``,
    ``_maybe_validate_memories``, and ``call_memory_index_session_start`` on the
    ``server_pipeline_tools`` module at call time so that tests patching
    those symbols on the host module are honoured.
    """
    from tapps_mcp import server_pipeline_tools as _host

    async def _run_maintenance() -> None:
        """Execute all maintenance ops sequentially in the background."""
        total_count: int = snapshot.total_count
        try:
            _cleanup_legacy_learning_dir(settings.project_root)
        except Exception:
            _logger.debug("background_legacy_learning_cleanup_failed", exc_info=True)

        try:
            _host._maybe_auto_gc(mem_store, total_count, settings)
        except Exception:
            _logger.debug("background_auto_gc_failed", exc_info=True)

        try:
            _host._maybe_consolidation_scan(mem_store, settings)
        except Exception:
            _logger.debug("background_consolidation_scan_failed", exc_info=True)

        try:
            await _host._maybe_validate_memories(mem_store, settings)
        except Exception:
            _logger.debug("background_doc_validation_failed", exc_info=True)

        try:
            from datetime import UTC
            from datetime import datetime as _dt

            _iso = _host._session_state.session_start_iso or _dt.now(UTC).isoformat()
            await _host.call_memory_index_session_start(_iso, settings.project_root)
        except Exception:
            _logger.debug("background_session_index_failed", exc_info=True)

    task = asyncio.create_task(_run_maintenance())
    _host._background_tasks.add(task)
    task.add_done_callback(_host._background_tasks.discard)


def _collect_brain_bridge_health() -> dict[str, Any]:
    """TAP-523: run BrainBridge.health_check() at session start.

    Reports DSN reachability and pool config validity. Non-blocking: probes
    the cached BrainBridge singleton if available, otherwise reports
    ``{enabled: False}``. Failures inside ``health_check`` surface as
    ``ok: false`` with an ``errors`` list.

    TAP-2098: when the bridge supports :meth:`auth_probe` and the probe
    returns an ``out_of_profile`` envelope with ``suggested_profile`` set,
    surface that into ``details`` so operators see "switch to profile X"
    remediation directly in ``brain_bridge_health`` instead of having to dig
    into ``memory_status.auth_probe``.
    """
    try:
        from tapps_mcp.server_helpers import _get_brain_bridge

        bridge = _get_brain_bridge()
    except Exception as exc:
        return {"enabled": False, "error": f"bridge_resolve_failed: {exc}"}
    if bridge is None:
        return {"enabled": False}
    try:
        report = bridge.health_check()
    except Exception as exc:
        return {"enabled": True, "ok": False, "errors": [f"health_check_raised: {exc}"]}
    _enrich_health_with_auth_probe(bridge, report)
    _enrich_health_with_async_native(bridge, report)
    return {"enabled": True, **report}


def _enrich_health_with_async_native(bridge: Any, report: dict[str, Any]) -> None:
    """TAP-1982: surface async-native write status from the brain healthz response.

    The brain's async backend activates when ``TAPPS_BRAIN_DATABASE_URL``
    (or ``TAPPS_BRAIN_HIVE_DSN``) is set in the **brain container** environment.
    There is no client-side flag — the gate is DSN presence at the brain HTTP
    adapter level. When the ``/healthz`` response includes ``db_ok``, we surface
    ``async_native`` so operators can verify the fast write path is active without
    checking the brain container env directly.

    Only meaningful for HTTP bridge mode; in-process BrainBridge does not run
    an HTTP adapter, so ``async_native`` is omitted for that mode.
    """
    if not getattr(bridge, "is_http_mode", False):
        return
    details = report.get("details") or {}
    db_ok = details.get("db_ok")
    if db_ok is True:
        report["async_native"] = True
    elif db_ok is False:
        report["async_native"] = False
    # else: absent (legacy brain, pre-v3.19.0 /healthz) — omit; cannot determine


def _enrich_health_with_auth_probe(bridge: Any, report: dict[str, Any]) -> None:
    """TAP-2098: surface ``suggested_profile`` (and gating context) from a
    fresh ``auth_probe`` into ``report['details']`` when the brain reports
    the probe tool is hidden by the active profile.

    No-ops when the bridge does not expose ``auth_probe`` (e.g. in-process
    mode) or when the probe response carries no ``suggested_profile``.
    """
    if not hasattr(bridge, "auth_probe"):
        return
    try:
        probe = bridge.auth_probe()
    except Exception:
        return
    if not isinstance(probe, dict):
        return
    suggested = probe.get("suggested_profile")
    gated = probe.get("gated")
    if not suggested and not gated:
        return
    details = dict(report.get("details") or {})
    if suggested:
        details["suggested_profile"] = suggested
    if gated:
        details["profile_gated"] = True
        if probe.get("profile"):
            details["active_profile"] = probe["profile"]
        if probe.get("tool"):
            details["denied_tool"] = probe["tool"]
    report["details"] = details


def _memory_status_http_mode(bridge: Any) -> dict[str, Any]:
    """Return status dict for HTTP bridge mode.

    Probes both ``/health`` (unauthenticated) AND a real authenticated MCP
    tool call via :meth:`HttpBrainBridge.auth_probe`. ``degraded`` is true
    if EITHER probe fails — a healthy endpoint with broken auth used to
    report ``degraded=false`` and silently hide 401/403s until the first
    runtime memory operation.
    """
    health = bridge.health_check()
    health_ok = bool(health.get("ok", False))

    auth_probe: dict[str, Any]
    if health_ok and hasattr(bridge, "auth_probe"):
        try:
            auth_probe = bridge.auth_probe()
        except Exception as exc:
            auth_probe = {"ok": False, "error": f"probe_raised: {exc}"}
    else:
        auth_probe = {"ok": False, "skipped": True, "reason": "health_unavailable"}
    auth_ok = bool(auth_probe.get("ok", False))

    return {
        "enabled": health_ok and auth_ok,
        "mode": "http",
        "http_url": str(getattr(bridge, "_http_url", "")),
        "degraded": not (health_ok and auth_ok),
        "health_ok": health_ok,
        "auth_probe": auth_probe,
    }


def _tally_memory_tiers(entries: list[Any]) -> tuple[dict[str, int], list[float]]:
    """Aggregate tier counts and confidence values from memory entries."""
    by_tier: dict[str, int] = {
        "architectural": 0,
        "pattern": 0,
        "procedural": 0,
        "context": 0,
    }
    confidences: list[float] = []
    for entry in entries:
        tier_val = entry.tier if isinstance(entry.tier, str) else entry.tier.value
        by_tier[tier_val] = by_tier.get(tier_val, 0) + 1
        confidences.append(entry.confidence)
    return by_tier, confidences


def _collect_memory_status(settings: Any) -> dict[str, Any]:
    """Collect memory subsystem status for session start."""
    status: dict[str, Any] = {"enabled": False}
    try:
        if not settings.memory.enabled:
            return status

        # HTTP bridge mode: no in-process MemoryStore snapshot is available.
        from tapps_mcp.server_helpers import _get_brain_bridge, _get_memory_store

        bridge = _get_brain_bridge()
        if bridge is not None and getattr(bridge, "is_http_mode", False):
            http_status = _memory_status_http_mode(bridge)
            # TAP-1286: surface the resolved (possibly derived) brain_project_id
            # so the agent can see which slug was used.
            http_status["brain_project_id"] = settings.memory.brain_project_id
            return http_status

        mem_store = _get_memory_store()
        if mem_store is None:
            return status

        snapshot = mem_store.snapshot()
        contradicted_count = sum(1 for entry in snapshot.entries if entry.contradicted)

        by_tier, confidences = _tally_memory_tiers(snapshot.entries)
        avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        max_mem = settings.memory.max_memories
        cap_pct = round((snapshot.total_count / max_mem) * 100, 1) if max_mem > 0 else 0.0

        status = {
            "enabled": True,
            "total": snapshot.total_count,
            "stale": 0,
            "contradicted": contradicted_count,
            "by_tier": by_tier,
            "avg_confidence": avg_conf,
            "capacity_pct": cap_pct,
        }

        _enrich_memory_profile_status(status, mem_store, settings)
        _enrich_memory_status_hints(status, snapshot.entries, settings)
        _schedule_background_maintenance(mem_store, snapshot, settings)
    except Exception:
        _logger.debug("memory_status_check_failed", exc_info=True)
    return status


# ---------------------------------------------------------------------------
# Search-first: proactive "look these up before coding" list (TAP-475)
# ---------------------------------------------------------------------------

# Static mapping: normalised package name → (suggested topic, reason)
# Only libraries with reliable Context7 / tapps_lookup_docs coverage.
_DOCS_COVERED: dict[str, tuple[str, str]] = {
    "pydantic": ("models", "Validate fields, validators, model_config"),
    "fastapi": ("routing", "Path params, deps, request/response models"),
    "fastmcp": ("tools", "MCP tool registration, context, annotations"),
    "mcp": ("server", "FastMCP server, tool handler patterns"),
    "structlog": ("configuration", "Processor chains, bound loggers, async logging"),
    "httpx": ("async client", "AsyncClient, request methods, auth"),
    "requests": ("sessions", "Session, auth, retry, timeout patterns"),
    "sqlalchemy": ("orm", "Session, relationship, async engine patterns"),
    "alembic": ("migrations", "env.py, autogenerate, revision"),
    "pytest": ("fixtures", "Conftest, fixtures, parametrize, async tests"),
    "mypy": ("configuration", "strict mode, type ignore, overrides"),
    "ruff": ("configuration", "rule selectors, per-file ignores, pyproject"),
    "pandas": ("dataframe", "DataFrame, groupby, merge, IO methods"),
    "numpy": ("arrays", "ndarray, broadcasting, vectorised ops"),
    "click": ("commands", "Command, option, argument, groups"),
    "typer": ("commands", "App, argument, option, callbacks"),
    "rich": ("console", "Console, Panel, Table, Progress, Markdown"),
    "jinja2": ("templates", "Environment, Template, filters, macros"),
    "reportlab": ("canvas", "Canvas, Platypus, flowables, PDF generation"),
    "pypdf": ("merging", "PdfReader, PdfWriter, pages, annotations"),
    "document-quality": (
        "pdf output",
        "Thin pages, link annotations, PDF outlines/bookmarks, HTML-to-PDF pitfalls",
    ),
    "aiohttp": ("client", "ClientSession, request, streaming"),
    "celery": ("tasks", "Task, apply_async, beat schedule"),
    "redis": ("commands", "Pipeline, pubsub, async client"),
    "motor": ("async ops", "AsyncIOMotorClient, collection, find"),
    "beanie": ("documents", "Document, find, insert, update"),
    "tortoise": ("models", "Model, fields, Tortoise.init"),
    "django": ("orm", "Model, QuerySet, views, urls"),
    "flask": ("routing", "Blueprint, request, response, app factory"),
    "starlette": ("middleware", "Middleware, routing, TestClient"),
    "uvicorn": ("configuration", "Config, lifespan, SSL, workers"),
    "boto3": ("s3", "S3 client, put_object, presigned URLs"),
    "anthropic": ("messages", "Client, messages.create, prompt caching, streaming"),
    "openai": ("chat", "ChatCompletion, streaming, function calling"),
    "langchain": ("chains", "Chain, LLM, PromptTemplate, memory"),
    "tomllib": ("parsing", "tomllib.loads, tomllib.load — stdlib in 3.11+"),
    "pathlib": ("Path", "Path operations, glob, read_text — stdlib"),
    "asyncio": ("event loop", "gather, create_task, Queue, timeout"),
    "dataclasses": ("fields", "field, dataclass, post_init — stdlib"),
    "typing": ("generics", "Generic, Protocol, TypeVar, Annotated — stdlib"),
}


def _normalise_dep(name: str) -> str:
    """Lowercase and replace hyphens with underscores for uniform lookup."""
    return name.lower().replace("-", "_").split("[")[0].strip()


_VERSION_OP_RE = re.compile(r"[;@<>=!~\[]")


def _strip_version_specifier(dep: str) -> str:
    """Return the package name from a PEP 508 dependency string.

    Handles extras (``pkg[extra]``), environment markers (``pkg; python>=X``),
    URL specs (``pkg @ https://...``), and version ops (``>=``, ``~=``, etc.)
    via :class:`packaging.requirements.Requirement`. Falls back to a regex
    split on the first version/extras/marker delimiter when parsing raises
    (TAP-615).
    """
    try:
        from packaging.requirements import InvalidRequirement, Requirement

        return Requirement(dep).name
    except (InvalidRequirement, ImportError):
        return _VERSION_OP_RE.split(dep, maxsplit=1)[0].strip()


def _load_tomllib() -> Any:
    """Return tomllib module (stdlib in 3.11+, fallback to tomli)."""
    try:
        import tomllib

        return tomllib
    except ImportError:
        try:
            import tomli

            return tomli
        except ImportError:
            return None


def _collect_raw_deps(project_root: Path, tomllib_mod: Any) -> list[str]:
    """Collect dependency names from pyproject.toml and workspace members."""
    pyproject = project_root / "pyproject.toml"
    try:
        with pyproject.open("rb") as fh:
            data = tomllib_mod.load(fh)
    except Exception:
        _logger.debug("search_first_pyproject_parse_failed", exc_info=True)
        return []

    raw_deps: list[str] = []
    project_section = data.get("project", {})
    for dep in project_section.get("dependencies", []):
        raw_deps.append(_strip_version_specifier(dep))

    for group_deps in project_section.get("optional-dependencies", {}).values():
        if isinstance(group_deps, list):
            for dep in group_deps:
                raw_deps.append(_strip_version_specifier(str(dep)))

    for group_deps in data.get("dependency-groups", {}).values():
        if isinstance(group_deps, list):
            for dep in group_deps:
                raw_deps.append(_strip_version_specifier(str(dep)))

    # workspace members — scan their pyproject.tomls too (best-effort)
    ws_members = data.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    for member_glob in ws_members:
        for member_pyproject in project_root.glob(f"{member_glob}/pyproject.toml"):
            try:
                with member_pyproject.open("rb") as fh:
                    member_data = tomllib_mod.load(fh)
                for dep in member_data.get("project", {}).get("dependencies", []):
                    raw_deps.append(_strip_version_specifier(dep))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                _logger.warning(
                    "workspace_pyproject_unreadable",
                    path=str(member_pyproject),
                    error=str(exc),
                )

    return raw_deps


def _build_search_first(project_root: Path) -> dict[str, Any] | None:
    """Parse pyproject.toml deps and return search-first coverage hints.

    Returns None when no pyproject.toml is found so callers can omit the
    field entirely (TAP-475 requirement: omit, not empty list).
    """
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return None

    tomllib_mod = _load_tomllib()
    if tomllib_mod is None:
        return None

    raw_deps = _collect_raw_deps(project_root, tomllib_mod)

    covered: list[dict[str, str]] = []
    unknown: list[str] = []
    seen: set[str] = set()

    for raw in raw_deps:
        norm = _normalise_dep(raw.strip())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        if norm in _DOCS_COVERED:
            topic, reason = _DOCS_COVERED[norm]
            covered.append({"library": norm, "topic": topic, "reason": reason})
        else:
            unknown.append(norm)

    try:
        from tapps_mcp.pipeline.document_judges import is_document_consumer

        if is_document_consumer(project_root):
            topic, reason = _DOCS_COVERED["document-quality"]
            if not any(entry.get("library") == "document-quality" for entry in covered):
                covered.append(
                    {"library": "document-quality", "topic": topic, "reason": reason}
                )
    except Exception:
        _logger.debug("search_first_document_quality_failed", exc_info=True)

    covered.sort(key=lambda x: x["library"])

    result: dict[str, Any] = {"covered": covered}
    if unknown:
        result["unknown_deps"] = sorted(unknown)
    return result


# ---------------------------------------------------------------------------
# CLI fallback map for MCP disconnect recovery (TAP-3587 / ReportLab feedback)
# ---------------------------------------------------------------------------

CLI_FALLBACK: dict[str, str] = {
    "tapps_session_start": "tapps-mcp doctor --quick",
    "tapps_quick_check": "tapps-mcp quick-check --file-path <path>",
    "tapps_validate_changed": (
        "tapps-mcp validate-changed [--file-paths a.py,b.py] [--quick|--full]"
    ),
    "tapps_doctor": "tapps-mcp doctor [--quick]",
    "tapps_lookup_docs": "tapps-mcp lookup-docs --library <name> [--topic TOPIC]",
    "tapps_memory": "tapps-mcp memory <list|save|get|search|delete>",
}

MCP_RECOVERY_HINT = (
    "If MCP tools return 'Not connected' after a host reload, use cli_fallback "
    "CLI commands from the project root or restart the host — see docs/TROUBLESHOOTING.md."
)


def attach_cli_fallback(data: dict[str, Any]) -> None:
    """Attach CLI equivalents and mid-session MCP recovery hint to session_start data."""
    data["cli_fallback"] = dict(CLI_FALLBACK)
    data["mcp_recovery_hint"] = MCP_RECOVERY_HINT


# ---------------------------------------------------------------------------
# TAP-1331: background lookup_docs cache warm on session_start
# ---------------------------------------------------------------------------

_CACHE_WARM_FLAG_NAME = ".cache-warm-marker"
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _schedule_lookup_docs_warm(
    project_root: Path,
    covered: list[dict[str, str]],
) -> dict[str, Any]:
    """Fire-and-forget warm of the lookup_docs cache for top covered libraries.

    Runs once per (CACHE_WARM_TTL) day on session_start. Skips when no
    Context7 API key is configured. Returns a structured status dict so the
    session_start response can surface what happened without blocking.
    """
    if not covered:
        return {"scheduled": False, "skipped": "no_covered_libraries"}

    flag = project_root / ".tapps-mcp-cache" / _CACHE_WARM_FLAG_NAME
    try:
        if flag.exists():
            age = time.time() - flag.stat().st_mtime
            if age < 86_400:  # one day
                return {
                    "scheduled": False,
                    "skipped": "warmed_within_24h",
                    "age_seconds": int(age),
                }
    except Exception:
        _logger.debug("cache_warm_flag_stat_failed", exc_info=True)

    libraries = [c["library"] for c in covered][:10]

    async def _runner() -> None:
        try:
            from tapps_core.config.settings import load_settings as _ls
            from tapps_core.knowledge.cache import KBCache
            from tapps_core.knowledge.warming import warm_cache

            s = _ls()
            api_key = getattr(s, "context7_api_key", None)
            if not api_key or not api_key.get_secret_value():
                return
            cache = KBCache(project_root / ".tapps-mcp-cache")
            await warm_cache(
                project_root,
                cache,
                api_key=api_key,
                libraries=libraries,
                max_libraries=len(libraries),
            )
            try:
                flag.parent.mkdir(parents=True, exist_ok=True)
                flag.write_text(str(int(time.time())))
            except Exception:
                _logger.debug("cache_warm_flag_write_failed", exc_info=True)
        except Exception:
            _logger.debug("cache_warm_runner_failed", exc_info=True)

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_runner())
        # Keep a reference so the task isn't GC'd before completion (RUF006).
        # Background fire-and-forget; we don't await.
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        return {"scheduled": True, "libraries": libraries, "count": len(libraries)}
    except RuntimeError:
        return {"scheduled": False, "skipped": "no_running_loop"}
