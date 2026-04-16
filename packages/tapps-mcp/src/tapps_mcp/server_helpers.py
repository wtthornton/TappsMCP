"""Helper functions extracted from server.py to reduce complexity and duplication."""

from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context
    from tapps_brain import HiveBackend as _HiveStoreType
    from tapps_brain.backends import AgentRegistry as _HiveAgentRegistryType

    from tapps_core.brain_bridge import BrainBridge as _BrainBridgeType
    from tapps_core.config.settings import TappsMCPSettings
    from tapps_core.knowledge.lookup import LookupEngine as _LookupEngineType
    from tapps_core.memory.store import MemoryStore as _MemoryStoreType
    from tapps_mcp.scoring.scorer import CodeScorer as _CodeScorerType
    from tapps_mcp.scoring.scorer_base import ScorerBase as _ScorerBaseType


# ---------------------------------------------------------------------------
# MCP Context progress helper
# ---------------------------------------------------------------------------


async def emit_ctx_info(ctx: Context[Any, Any, Any] | None, message: str) -> None:
    """Emit a ``ctx.info`` notification if *ctx* is available.

    Defensive: null-checks *ctx*, uses ``getattr`` for ``info``, and
    suppresses all exceptions so callers never fail due to notification
    issues.
    """
    if ctx is None:
        return
    info_fn = getattr(ctx, "info", None)
    if info_fn is None:
        return
    with contextlib.suppress(Exception):
        await info_fn(message)


# ---------------------------------------------------------------------------
# CodeScorer singleton — avoids re-instantiating on every tool call.
# ---------------------------------------------------------------------------

_scorer: _CodeScorerType | None = None


def _get_scorer() -> _CodeScorerType:
    """Return a lazily-initialized :class:`CodeScorer` singleton."""
    global _scorer
    if _scorer is None:
        from tapps_mcp.scoring.scorer import CodeScorer

        _scorer = CodeScorer()
    return _scorer


def _reset_scorer_cache() -> None:
    """Reset the cached :class:`CodeScorer` singleton (for testing)."""
    global _scorer
    _scorer = None


def _get_scorer_for_file(file_path: Path | str) -> _ScorerBaseType | None:
    """Return the appropriate scorer for a file based on its extension.

    Uses the language detector to route to the correct scorer:
    - Python (.py, .pyi) -> CodeScorer
    - TypeScript/JavaScript (.ts, .tsx, .js, .jsx, .mjs, .cjs) -> TypeScriptScorer
    - Go (.go) -> GoScorer
    - Rust (.rs) -> RustScorer

    Returns None if the file's language is not supported for scoring.
    """
    from tapps_mcp.scoring.language_detector import get_scorer

    return get_scorer(file_path)


def _is_scorable_file(file_path: Path | str) -> bool:
    """Check if a file can be scored (has a supported language extension)."""
    from tapps_mcp.scoring.language_detector import detect_language

    return detect_language(file_path) is not None


def _get_supported_extensions() -> frozenset[str]:
    """Return the set of all file extensions that can be scored."""
    from tapps_mcp.scoring.language_detector import get_supported_extensions

    return get_supported_extensions()


# ---------------------------------------------------------------------------
# LookupEngine singleton — avoids re-instantiating on every tool call.
# ---------------------------------------------------------------------------

_lookup_engine: _LookupEngineType | None = None


def _get_lookup_engine() -> _LookupEngineType:
    """Return a lazily-initialized :class:`LookupEngine` singleton."""
    global _lookup_engine
    if _lookup_engine is None:
        from tapps_core.config.settings import load_settings
        from tapps_core.knowledge.cache import KBCache
        from tapps_core.knowledge.lookup import LookupEngine

        settings = load_settings()
        cache = KBCache(settings.project_root / ".tapps-mcp-cache")
        _lookup_engine = LookupEngine(cache, settings=settings)
    return _lookup_engine


def _reset_lookup_engine_cache() -> None:
    """Reset the cached :class:`LookupEngine` singleton (for testing)."""
    global _lookup_engine
    _lookup_engine = None


# ---------------------------------------------------------------------------
# BrainBridge singleton — async-safe wrapper over tapps-brain v3 AgentBrain.
# TAP-408: Replaces the SQLite-backed MemoryStore init with a Postgres-backed
# BrainBridge.  _get_memory_store() is kept as a thin compat shim so that
# existing sync callers continue to work against the same MemoryStore API.
# ---------------------------------------------------------------------------

_brain_bridge: _BrainBridgeType | None = None
_brain_bridge_lock = threading.Lock()


def _get_brain_bridge() -> _BrainBridgeType | None:
    """Return a lazily-initialized :class:`BrainBridge` singleton.

    Returns ``None`` when ``TAPPS_BRAIN_DATABASE_URL`` is not configured,
    which allows callers to gate memory operations gracefully.
    """
    global _brain_bridge
    if _brain_bridge is None:
        with _brain_bridge_lock:
            if _brain_bridge is None:
                from tapps_core.brain_bridge import create_brain_bridge
                from tapps_core.config.settings import load_settings

                _brain_bridge = create_brain_bridge(load_settings())
    return _brain_bridge


def _reset_brain_bridge_cache() -> None:
    """Reset the cached :class:`BrainBridge` singleton (for testing)."""
    global _brain_bridge
    with _brain_bridge_lock:
        if _brain_bridge is not None:
            _brain_bridge.close()
        _brain_bridge = None


def _get_memory_store() -> _MemoryStoreType:
    """Return the Postgres-backed :class:`MemoryStore` from the BrainBridge.

    Raises ``RuntimeError`` when ``TAPPS_BRAIN_DATABASE_URL`` is not set.
    Kept as a compat shim for sync callers; prefer ``_get_brain_bridge()``
    and its async methods in new code.
    """
    bridge = _get_brain_bridge()
    if bridge is None:
        raise RuntimeError(
            "Memory store unavailable: TAPPS_BRAIN_DATABASE_URL is not configured. "
            "Set this environment variable to enable memory operations."
        )
    store: _MemoryStoreType = bridge.store
    return store


def _reset_memory_store_cache() -> None:
    """Compat alias for :func:`_reset_brain_bridge_cache` (for testing)."""
    _reset_brain_bridge_cache()


_IMPACT_MEMORY_CONTEXT_LIMIT = 5
_IMPACT_MEMORY_MIN_CONFIDENCE = 0.3
_IMPACT_MEMORY_SUMMARY_MAX = 200


def build_impact_memory_context(
    resolved_file: Path,
    project_root: Path,
    settings: TappsMCPSettings,
) -> dict[str, Any]:
    """BM25 memory hits for :func:`tapps_impact_analysis` (Epic M4.4).

    Skips when memory is disabled, when ``enrich_impact_analysis`` is false, or
    when the store/search fails (returns empty ``memory_context`` + status fields).
    Relation-graph enrichment is not wired here (only ``MemoryStore.search`` is used);
    graph-boosted recall remains a separate integration path.
    """
    mem = settings.memory
    if not mem.enabled:
        return {
            "memory_context": [],
            "memory_context_enrichment": "skipped",
            "memory_context_skip": "memory_disabled",
        }
    if not mem.enrich_impact_analysis:
        return {
            "memory_context": [],
            "memory_context_enrichment": "skipped",
            "memory_context_skip": "enrich_impact_analysis_disabled",
        }

    try:
        root = project_root.resolve()
        file_resolved = resolved_file.resolve()
        try:
            rel = file_resolved.relative_to(root)
            rel_s = rel.as_posix()
        except ValueError:
            rel_s = resolved_file.name
        query = f"{rel_s} {resolved_file.name}".strip()
    except OSError:
        query = resolved_file.name

    def _tier_str(tier_obj: object) -> str:
        if hasattr(tier_obj, "value"):
            return str(getattr(tier_obj, "value", ""))
        return str(tier_obj)

    try:
        store = _get_memory_store()
        raw = store.search(query)
    except Exception as exc:
        import structlog

        structlog.get_logger(__name__).debug(
            "impact_memory_context_search_failed", query=query, exc_info=True
        )
        return {
            "memory_context": [],
            "memory_context_enrichment": "error",
            "memory_context_error": str(exc),
            "memory_context_query": query,
        }

    min_c = _IMPACT_MEMORY_MIN_CONFIDENCE
    filtered: list[Any] = []
    for entry in raw:
        conf = float(getattr(entry, "confidence", 1.0))
        if conf >= min_c:
            filtered.append(entry)
        if len(filtered) >= _IMPACT_MEMORY_CONTEXT_LIMIT:
            break

    items: list[dict[str, Any]] = []
    for entry in filtered:
        val = str(getattr(entry, "value", "") or "")
        cap = _IMPACT_MEMORY_SUMMARY_MAX
        items.append(
            {
                "key": str(getattr(entry, "key", "")),
                "summary": val[:cap] + ("..." if len(val) > cap else ""),
                "tier": _tier_str(getattr(entry, "tier", "")),
                "confidence": float(getattr(entry, "confidence", 0.0)),
                "source": "memory",
            }
        )

    return {
        "memory_context": items,
        "memory_context_enrichment": "ok",
        "memory_context_query": query,
    }


# ---------------------------------------------------------------------------
# Hive (tapps_brain.hive) — optional; gated by Agent Teams env (Epic M3)
# ---------------------------------------------------------------------------

_hive_store: Any | None = None
_hive_registry: Any | None = None
_hive_import_error: str | None = None
_hive_init_error: str | None = None
_hive_lock = threading.Lock()


def _agent_teams_env_enabled() -> bool:
    """True when Claude Code Agent Teams experimental flag is set."""
    return bool(os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"))


def _reset_hive_store_cache() -> None:
    """Reset Hive singletons and cached error state (for testing)."""
    global _hive_store, _hive_registry, _hive_import_error, _hive_init_error
    with _hive_lock:
        if _hive_store is not None:
            with contextlib.suppress(Exception):
                _hive_store.close()
        _hive_store = None
        _hive_registry = None
        _hive_import_error = None
        _hive_init_error = None


def _ensure_hive_singletons() -> tuple[
    _HiveStoreType | None,
    _HiveAgentRegistryType | None,
    str | None,
]:
    """Lazily construct Hive store and agent registry.

    Returns ``(hive_store, agent_registry, error_message)``. *error_message*
    is populated with an actionable reason when init cannot complete: missing
    tapps-brain import, missing/invalid ``TAPPS_BRAIN_DATABASE_URL``, or a
    ``create_hive_backend`` failure. Backend-init failures are cached so we
    don't retry a known-broken DSN on every call; DSN-missing is *not* cached
    (env may be set later by a fixture or sidecar).
    """
    global _hive_store, _hive_registry, _hive_import_error, _hive_init_error
    if not _agent_teams_env_enabled():
        return None, None, None
    if _hive_import_error is not None:
        return None, None, _hive_import_error
    with _hive_lock:
        if _hive_import_error is not None:
            return None, None, _hive_import_error
        try:
            # tapps-brain v3: AgentRegistry moved from hive to backends.
            # File-backed HiveStore was removed (ADR-007); postgres hive is
            # available via create_hive_backend() when DATABASE_URL is set.
            from tapps_brain.backends import AgentRegistry
        except ImportError as exc:
            _hive_import_error = str(exc)
            return None, None, _hive_import_error
        if _hive_store is None:
            dsn = os.environ.get("TAPPS_BRAIN_DATABASE_URL", "")
            if not dsn:
                return (
                    None,
                    None,
                    (
                        "TAPPS_BRAIN_DATABASE_URL not configured "
                        "(Postgres DSN required for Hive; ADR-007)"
                    ),
                )
            if not dsn.startswith(("postgres://", "postgresql://")):
                scheme = dsn.split("://", 1)[0] if "://" in dsn else "<none>"
                return (
                    None,
                    None,
                    (
                        f"TAPPS_BRAIN_DATABASE_URL scheme '{scheme}' not supported "
                        "(Hive requires postgres:// or postgresql://)"
                    ),
                )
            if _hive_init_error is not None:
                return None, None, _hive_init_error
            try:
                from tapps_brain.backends import create_hive_backend

                _hive_store = create_hive_backend(dsn)
            except Exception as exc:
                _hive_init_error = f"create_hive_backend failed: {exc}"
                return None, None, _hive_init_error
        if _hive_registry is None:
            _hive_registry = AgentRegistry()
    return _hive_store, _hive_registry, None


def _get_hive_store() -> _HiveStoreType | None:
    """Return :class:`HiveStore` singleton when Agent Teams env is set, else None."""
    store, _, _err = _ensure_hive_singletons()
    return store


def _get_hive_registry() -> _HiveAgentRegistryType | None:
    """Return :class:`AgentRegistry` singleton when Agent Teams env is set, else None."""
    _, registry, _err = _ensure_hive_singletons()
    return registry


def initial_session_hive_status() -> dict[str, Any]:
    """Baseline ``hive_status`` before :func:`collect_session_hive_status` runs.

    Used by session-start when collection is skipped or raises.
    """
    return {"enabled": False}


def collect_session_hive_status(settings: TappsMCPSettings) -> dict[str, Any]:
    """Build ``hive_status`` payload for :func:`tapps_session_start`.

    When ``CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`` is unset, returns
    ``{"enabled": False}``. When set, registers this process as a Hive agent
    (best-effort) and returns namespace / agent counts. On failure, returns
    ``degraded: true`` with an actionable message (non-fatal), matching other
    optional tapps-brain integrations.

    Propagation tier rules (``auto_propagate_tiers`` / ``private_tiers``) are
    intentionally not mirrored here: tapps-brain's ``PropagationEngine``
    enforces them server-side on every ``hive_propagate`` / ``hive_push`` call.
    Clients read the propagation outcome from the response, not the rules.
    """
    if not _agent_teams_env_enabled():
        return initial_session_hive_status()

    try:
        store, registry, init_err = _ensure_hive_singletons()
        if init_err or store is None or registry is None:
            reason = init_err or "Hive singletons unavailable"
            return {
                "enabled": True,
                "degraded": True,
                "message": f"Hive unavailable: {reason}",
            }

        from tapps_brain.models import AgentRegistration

        active_profile = settings.memory.profile or "repo-brain"
        agent_id = os.environ.get("CLAUDE_AGENT_ID", f"agent-{os.getpid()}")
        agent_name = os.environ.get("CLAUDE_AGENT_NAME", "unnamed")
        registry.register(
            AgentRegistration(
                id=agent_id,
                name=agent_name,
                profile=active_profile,
                project_root=str(settings.project_root),
            )
        )
        namespaces = store.list_namespaces()
        agents = registry.list_agents()
        return {
            "enabled": True,
            "degraded": False,
            "agent_id": agent_id,
            "namespaces": namespaces,
            "registered_agents_count": len(agents),
        }
    except Exception as exc:
        return {
            "enabled": True,
            "degraded": True,
            "message": f"Hive status failed: {exc}",
        }


# STORY-101.4 — actionable error envelope.
#
# Map of error code -> default (category, retryable, remediation). Keeps
# error envelopes self-describing so agents can branch on category /
# retryable without parsing free-form messages. Callers may override any
# field via ``extra``.
#
# Categories:
#   - user_input:    bad path / missing param / invalid argument
#   - environment:   missing checker, unreachable service, OS limit
#   - timeout:       wall-clock or per-tool budget exceeded
#   - deprecated:    tool/flag removed; alternative is offered
#   - unsupported:   request is well-formed but out of scope (e.g. language)
#   - internal:      unexpected exception inside a tool (default fallback)
_ERROR_METADATA: dict[str, dict[str, Any]] = {
    "path_denied": {
        "category": "user_input",
        "retryable": False,
        "remediation": "Pass an absolute path inside the project root.",
    },
    "file_error": {
        "category": "user_input",
        "retryable": False,
        "remediation": "Verify the file exists and is readable.",
    },
    "missing_params": {
        "category": "user_input",
        "retryable": False,
        "remediation": "Re-call with the required parameter populated.",
    },
    "invalid_library": {
        "category": "user_input",
        "retryable": False,
        "remediation": "Pass a non-empty library name (e.g. 'fastapi').",
    },
    "unsupported_language": {
        "category": "unsupported",
        "retryable": False,
        "remediation": (
            "Use a supported extension: .py/.pyi, .ts/.tsx/.js/.jsx/.mjs/.cjs, .go, .rs."
        ),
    },
    "scoring_failed": {
        "category": "internal",
        "retryable": True,
        "remediation": (
            "Retry once; if it persists, re-run with quick=False to surface the "
            "underlying scorer error."
        ),
    },
    "TOOL_DEPRECATED": {
        "category": "deprecated",
        "retryable": False,
        "remediation": "Switch to the listed alternative tool.",
    },
    "timeout": {
        "category": "timeout",
        "retryable": True,
        "remediation": "Re-run with a smaller scope (explicit file_paths or fewer files).",
    },
}

_DEFAULT_ERROR_METADATA: dict[str, Any] = {
    "category": "internal",
    "retryable": True,
    "remediation": "Retry the call; if it persists, file an issue with the message above.",
}


def error_response(
    tool_name: str,
    code: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard, actionable error response envelope (STORY-101.4).

    Every envelope carries ``category``, ``retryable``, and ``remediation``
    fields derived from the registry above so agents can react without
    parsing the human-readable ``message``. Callers can override any field
    by passing it in ``extra``.

    Args:
        tool_name: Name of the tool that produced the error.
        code: Machine-readable error code (e.g. ``"path_denied"``).
        message: Human-readable error description.
        extra: Optional structured metadata merged into the error object
            (e.g. ``{"alternatives": [...], "deprecated_since": "EPIC-94"}``).
            Wins over registry defaults when keys overlap.
    """
    defaults = _ERROR_METADATA.get(code, _DEFAULT_ERROR_METADATA)
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "category": defaults["category"],
        "retryable": defaults["retryable"],
        "remediation": defaults["remediation"],
    }
    if extra:
        error.update(extra)
    return {
        "tool": tool_name,
        "success": False,
        "elapsed_ms": 0,
        "error": error,
    }


_SENTINEL = object()


def success_response(
    tool_name: str,
    elapsed_ms: int,
    data: dict[str, Any],
    *,
    degraded: bool | object = _SENTINEL,
    next_steps: list[str] | None = None,
    pipeline_progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard success response envelope.

    When *degraded* is explicitly passed (even as False), the key is included
    in the response.  When omitted, the key is absent.

    When *next_steps* is non-empty, it is included in ``data`` so the LLM
    sees actionable guidance.  Same for *pipeline_progress*.
    """
    if next_steps:
        data["next_steps"] = next_steps
    if pipeline_progress:
        data["pipeline_progress"] = pipeline_progress

    result: dict[str, Any] = {
        "tool": tool_name,
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": data,
    }
    if degraded is not _SENTINEL:
        result["degraded"] = degraded
    return result


def serialize_issues(
    issues: list[Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Serialize a list of Pydantic model issues, truncated to *limit*."""
    return [i.model_dump() for i in issues[:limit]]


# ---------------------------------------------------------------------------
# Session auto-initialization state
# ---------------------------------------------------------------------------

_session_lock = threading.Lock()
_session_initialized: bool = False
_session_context: dict[str, Any] = {}


def is_session_initialized() -> bool:
    """Check if the session has been initialized."""
    return _session_initialized


def mark_session_initialized(context: dict[str, Any] | None = None) -> None:
    """Mark the session as initialized with optional context."""
    global _session_initialized
    with _session_lock:
        _session_initialized = True
        if context:
            _session_context.update(context)


def get_session_context() -> dict[str, Any]:
    """Return a copy of the cached session context."""
    with _session_lock:
        return dict(_session_context)


def _reset_session_state() -> None:
    """Reset session state (for testing)."""
    global _session_initialized
    with _session_lock:
        _session_initialized = False
        _session_context.clear()


async def ensure_session_initialized() -> None:
    """Lightweight auto-init for async tool handlers.

    When called before ``tapps_session_start`` has run, loads settings and
    detects the project profile so that tools have project context.  After
    the first successful call this becomes a no-op.
    """
    if _session_initialized:
        return

    import asyncio

    from tapps_core.config.settings import load_settings

    settings = load_settings()
    profile_data: dict[str, Any] = {}

    try:
        from tapps_mcp.project.profiler import detect_project_profile

        profile = await asyncio.to_thread(detect_project_profile, settings.project_root)
        profile_data = {
            "project_type": profile.project_type,
            "has_tests": profile.has_tests,
            "has_docker": profile.has_docker,
            "has_ci": profile.has_ci,
        }
    except Exception:
        pass  # Best-effort; profiling failure should not block session init

    mark_session_initialized(
        {
            "project_root": str(settings.project_root),
            "quality_preset": settings.quality_preset,
            "auto_initialized": True,
            "project_profile": profile_data,
        }
    )


def ensure_session_initialized_sync() -> None:
    """Lightweight auto-init for sync tool handlers.

    Performs only sync-safe initialization (settings loading).  Does NOT
    run project profiling which requires ``asyncio.to_thread``.
    """
    if _session_initialized:
        return

    from tapps_core.config.settings import load_settings

    settings = load_settings()
    mark_session_initialized(
        {
            "project_root": str(settings.project_root),
            "quality_preset": settings.quality_preset,
            "auto_initialized": True,
            "sync_only": True,
        }
    )
