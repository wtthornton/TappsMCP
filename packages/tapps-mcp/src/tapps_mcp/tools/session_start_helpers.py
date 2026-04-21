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
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from tapps_core.config.settings import TappsMCPSettings
    from tapps_core.memory.models import MemorySnapshot
    from tapps_core.memory.store import MemoryStore

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

        from tapps_core.memory.federation import load_federation_config

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
        from tapps_core.knowledge.cache import KBCache
        from tapps_core.knowledge.lookup import LookupEngine
        from tapps_core.memory.doc_validation import MemoryDocValidator

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

    Moves GC, consolidation scan, doc validation, and session capture
    processing off the critical path so ``tapps_session_start`` returns faster.

    Epic 68.2: Session start performance optimization.

    Looks up ``_maybe_auto_gc``, ``_maybe_consolidation_scan``,
    ``_maybe_validate_memories``, and ``_process_session_capture`` on the
    ``server_pipeline_tools`` module at call time so that tests patching
    those symbols on the host module are honoured.
    """
    from tapps_mcp import server_pipeline_tools as _host

    async def _run_maintenance() -> None:
        """Execute all maintenance ops sequentially in the background."""
        total_count: int = snapshot.total_count
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
            _host._process_session_capture(settings.project_root, mem_store)
        except Exception:
            _logger.debug("background_session_capture_failed", exc_info=True)

    task = asyncio.create_task(_run_maintenance())
    _host._background_tasks.add(task)
    task.add_done_callback(_host._background_tasks.discard)


def _collect_brain_bridge_health() -> dict[str, Any]:
    """TAP-523: run BrainBridge.health_check() at session start.

    Reports DSN reachability and pool config validity. Non-blocking: probes
    the cached BrainBridge singleton if available, otherwise reports
    ``{enabled: False}``. Failures inside ``health_check`` surface as
    ``ok: false`` with an ``errors`` list.
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
    return {"enabled": True, **report}


def _memory_status_http_mode(bridge: Any) -> dict[str, Any]:
    """Return status dict for HTTP bridge mode."""
    health = bridge.health_check()
    return {
        "enabled": health.get("ok", False),
        "mode": "http",
        "http_url": str(getattr(bridge, "_http_url", "")),
        "degraded": not health.get("ok", False),
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
            return _memory_status_http_mode(bridge)

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


def _strip_version_specifier(dep: str) -> str:
    """Strip PEP 508 version specifiers from a dependency string."""
    return dep.split(">")[0].split("<")[0].split("=")[0].split("!")[0].split("~")[0]


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

    # workspace members — scan their pyproject.tomls too (best-effort)
    ws_members = data.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    for member_glob in ws_members:
        for member_pyproject in project_root.glob(f"{member_glob}/pyproject.toml"):
            try:
                with member_pyproject.open("rb") as fh:
                    member_data = tomllib_mod.load(fh)
                for dep in member_data.get("project", {}).get("dependencies", []):
                    raw_deps.append(_strip_version_specifier(dep))
            except Exception:
                pass

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

    covered.sort(key=lambda x: x["library"])

    result: dict[str, Any] = {"covered": covered}
    if unknown:
        result["unknown_deps"] = sorted(unknown)
    return result
