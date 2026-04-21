"""Helper functions extracted from server.py to reduce complexity and duplication."""

from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

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
    """Return a lazily-initialized brain bridge singleton.

    Returns an :class:`~tapps_core.brain_bridge.HttpBrainBridge` when
    ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` is set, a plain
    :class:`~tapps_core.brain_bridge.BrainBridge` when
    ``TAPPS_BRAIN_DATABASE_URL`` is set, or ``None`` when neither is
    configured.
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


def _peek_brain_bridge() -> _BrainBridgeType | None:
    """Return the cached :class:`BrainBridge` without forcing init (TAP-517).

    Used by read-only consumers like ``tapps_server_info`` that need to
    report bridge state but must not incur a Postgres connection just to
    answer a diagnostics query.
    """
    return _brain_bridge


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
#
# TAP-572: tapps-mcp is a *client* of tapps-brain. Hive lives server-side,
# behind the BrainBridge / brain MCP surface. We no longer instantiate a
# local Postgres-backed Hive backend from this process; session-level Hive
# status is obtained via ``BrainBridge.hive_status``. ``_reset_hive_store_cache``
# is retained as a no-op compat shim for the test conftest autouse fixture.
# ---------------------------------------------------------------------------


def _agent_teams_env_enabled() -> bool:
    """True when Claude Code Agent Teams experimental flag is set."""
    return bool(os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"))


def _reset_hive_store_cache() -> None:
    """Compat no-op (TAP-572 removed client-side Hive singletons).

    Kept so ``packages/tapps-mcp/tests/conftest.py`` continues to import
    and call it from the autouse cache-reset fixture without needing a
    coordinated change.
    """
    return None


def initial_session_hive_status() -> dict[str, Any]:
    """Baseline ``hive_status`` before :func:`collect_session_hive_status` runs.

    Used by session-start when collection is skipped or raises.
    """
    return {"enabled": False}


async def collect_session_hive_status(settings: TappsMCPSettings) -> dict[str, Any]:
    """Build ``hive_status`` payload for :func:`tapps_session_start`.

    TAP-572: tapps-mcp is a **client** of tapps-brain — Hive lives server-side.
    This helper no longer probes a Postgres DSN directly; it asks the
    :class:`BrainBridge` for Hive status (``bridge.hive_status``) and reports
    whatever the brain says. When the bridge is not available (brain not
    configured / unreachable), we report ``enabled: "unknown"`` rather than
    fabricating a client-side DSN error — per the memory rule *"no client-side
    mirror of server-enforced rules"*.

    Behavior:

    * ``CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`` unset -> ``{"enabled": False}``.
    * Agent Teams on, bridge unavailable -> ``enabled: "unknown"``,
      ``degraded: true``, message points at brain connectivity
      (``TAPPS_BRAIN_BASE_URL`` / ``TAPPS_BRAIN_AUTH_TOKEN`` /
      ``TAPPS_BRAIN_DATABASE_URL`` on the brain server) — not a local DSN.
    * Agent Teams on, bridge available -> pass through
      ``bridge.hive_status(...)`` result, with ``agent_id`` surfaced for the
      session-start payload.

    Propagation tier rules (``auto_propagate_tiers`` / ``private_tiers``) are
    intentionally not mirrored here: tapps-brain's ``PropagationEngine``
    enforces them server-side on every ``hive_propagate`` / ``hive_push`` call.
    """
    if not _agent_teams_env_enabled():
        return initial_session_hive_status()

    from tapps_core.agent_identity import get_stable_agent_id

    bridge = _get_brain_bridge()
    agent_id = get_stable_agent_id(settings)
    if bridge is None:
        return {
            "enabled": "unknown",
            "degraded": True,
            "message": (
                "Hive status unknown: tapps-brain not reachable from this "
                "MCP server. Configure TAPPS_BRAIN_BASE_URL / "
                "TAPPS_BRAIN_AUTH_TOKEN (remote brain) or "
                "TAPPS_BRAIN_DATABASE_URL (in-process brain) so the brain "
                "can answer hive queries."
            ),
        }

    agent_name = os.environ.get("CLAUDE_AGENT_NAME", "unnamed")
    active_profile = settings.memory.profile or "repo-brain"
    try:
        result = await bridge.hive_status(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_profile=active_profile,
            project_root=str(settings.project_root),
            register=True,
        )
    except Exception as exc:
        return {
            "enabled": True,
            "degraded": True,
            "message": f"Hive status failed: {exc}",
        }

    # bridge.hive_status returns dict with enabled/degraded/namespaces/agents.
    # Surface agent_id for the session-start payload (clients use it to
    # correlate subsequent hive_push / hive_propagate calls).
    if isinstance(result, dict):
        result.setdefault("agent_id", agent_id)
        agents = result.get("agents")
        if isinstance(agents, list):
            result.setdefault("registered_agents_count", len(agents))
    return result


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
    except Exception as exc:
        import structlog

        structlog.get_logger(__name__).warning(
            "project_profile_detection_failed", error=str(exc), exc_info=True
        )

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
