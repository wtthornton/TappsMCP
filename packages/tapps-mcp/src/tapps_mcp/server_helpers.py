"""Helper functions extracted from server.py to reduce complexity and duplication."""

from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

    from tapps_core.knowledge.lookup import LookupEngine as _LookupEngineType
    from tapps_core.memory.store import MemoryStore as _MemoryStoreType
    from tapps_mcp.scoring.scorer import CodeScorer as _CodeScorerType


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
# MemoryStore singleton — avoids re-instantiating on every tool call.
# ---------------------------------------------------------------------------

_memory_store: _MemoryStoreType | None = None


def _get_memory_store() -> _MemoryStoreType:
    """Return a lazily-initialized :class:`MemoryStore` singleton."""
    global _memory_store
    if _memory_store is None:
        from tapps_core.config.settings import load_settings
        from tapps_core.memory.store import MemoryStore

        settings = load_settings()
        _memory_store = MemoryStore(settings.project_root)
    return _memory_store


def _reset_memory_store_cache() -> None:
    """Reset the cached :class:`MemoryStore` singleton (for testing)."""
    global _memory_store
    _memory_store = None


# ---------------------------------------------------------------------------
# MCP Context notification helpers
# ---------------------------------------------------------------------------


async def emit_ctx_info(
    ctx: Any,
    message: str,
) -> None:
    """Send a ``ctx.info()`` log notification (best-effort, never raises).

    Follows the defensive access pattern:
    1. ``ctx is None`` — no-op (tool called without context).
    2. ``getattr`` check — graceful on older MCP SDK versions.
    3. ``contextlib.suppress`` — network/protocol errors never crash the tool.
    """
    if ctx is None:
        return
    info_fn = getattr(ctx, "info", None)
    if not callable(info_fn):
        return
    with contextlib.suppress(Exception):
        await info_fn(message)


def error_response(tool_name: str, code: str, message: str) -> dict[str, Any]:
    """Build a standard error response envelope."""
    return {
        "tool": tool_name,
        "success": False,
        "elapsed_ms": 0,
        "error": {"code": code, "message": message},
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

    mark_session_initialized({
        "project_root": str(settings.project_root),
        "quality_preset": settings.quality_preset,
        "auto_initialized": True,
        "project_profile": profile_data,
    })


def ensure_session_initialized_sync() -> None:
    """Lightweight auto-init for sync tool handlers.

    Performs only sync-safe initialization (settings loading).  Does NOT
    run project profiling which requires ``asyncio.to_thread``.
    """
    if _session_initialized:
        return

    from tapps_core.config.settings import load_settings

    settings = load_settings()
    mark_session_initialized({
        "project_root": str(settings.project_root),
        "quality_preset": settings.quality_preset,
        "auto_initialized": True,
        "sync_only": True,
    })
