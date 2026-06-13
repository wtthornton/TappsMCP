"""Brain-central library doc lookup helpers (ADR-0014 consumer path)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from tapps_core.knowledge.models import LookupResult

if TYPE_CHECKING:
    from tapps_core.brain_bridge import BrainBridge
    from tapps_core.config.settings import TappsMCPSettings

logger = structlog.get_logger(__name__)

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})
_BRAIN_DOCS_WARM_MARKER = ".brain-docs-warm-marker"


def brain_docs_warm_marker_path(project_root: Path) -> Path:
    """Return the throttle marker path for brain ``docs_warm`` (ADR-0014)."""
    return project_root / ".tapps-mcp" / _BRAIN_DOCS_WARM_MARKER


def apply_docs_via_brain_mcp_env(env: dict[str, str]) -> dict[str, str]:
    """Strip consumer Context7 and enable brain doc routing in MCP env blocks."""
    if not docs_via_brain_enabled():
        return env
    updated = dict(env)
    updated.pop("TAPPS_MCP_CONTEXT7_API_KEY", None)
    updated["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    return updated


def docs_via_brain_enabled(settings: TappsMCPSettings | None = None) -> bool:
    """Return True when library docs should route through tapps-brain."""
    env_val = os.environ.get("TAPPS_MCP_DOCS_VIA_BRAIN", "").strip().lower()
    if env_val in _TRUTHY:
        return True
    if env_val in _FALSY:
        return False
    if settings is not None:
        return bool(getattr(settings, "docs_via_brain", False))
    return False


def lookup_result_from_brain_payload(
    payload: dict[str, Any],
    *,
    start: float,
) -> LookupResult:
    """Map a brain ``docs_lookup`` JSON payload to :class:`LookupResult`."""
    elapsed = (time.monotonic() - start) * 1000
    content = payload.get("content")
    return LookupResult(
        success=bool(payload.get("success", bool(content))),
        content=str(content) if content is not None else None,
        source=str(payload.get("source") or "brain"),
        library=payload.get("library"),
        topic=payload.get("topic"),
        context7_id=payload.get("context7_id"),
        error=payload.get("error"),
        response_time_ms=round(elapsed, 1),
        cache_hit=bool(payload.get("cache_hit", False)),
        fuzzy_score=payload.get("fuzzy_score"),
        warning=payload.get("warning"),
    )


def _brain_docs_unavailable(exc: BaseException) -> bool:
    """True when brain does not yet expose doc tools (pre-cutover fallback)."""
    from tapps_core.brain_bridge import ToolNotInProfileError

    if isinstance(exc, ToolNotInProfileError):
        return True
    msg = str(exc)
    return "Unknown tool" in msg or (
        "docs_lookup" in msg and "not available" in msg
    )


async def lookup_via_brain(
    bridge: BrainBridge,
    library: str,
    topic: str,
    *,
    mode: str = "code",
    start: float | None = None,
) -> LookupResult | None:
    """Call brain ``docs_lookup``; return None when the tool is not deployed yet."""
    t0 = start if start is not None else time.monotonic()
    try:
        payload = await bridge.docs_lookup(library=library, topic=topic, mode=mode)
    except Exception as exc:
        if _brain_docs_unavailable(exc):
            logger.info("brain_docs_lookup_fallback", library=library, topic=topic)
            return None
        raise
    if not isinstance(payload, dict):
        return None
    return lookup_result_from_brain_payload(payload, start=t0)


async def warm_via_brain(bridge: BrainBridge, libraries: list[str]) -> dict[str, Any] | None:
    """Call brain ``docs_warm``; return None when the tool is not deployed yet."""
    if not libraries:
        return {"warmed": 0, "libraries": []}
    try:
        result = await bridge.docs_warm(libraries=libraries)
    except Exception as exc:
        if _brain_docs_unavailable(exc):
            logger.info("brain_docs_warm_fallback", count=len(libraries))
            return None
        raise
    return result if isinstance(result, dict) else {"result": result}
