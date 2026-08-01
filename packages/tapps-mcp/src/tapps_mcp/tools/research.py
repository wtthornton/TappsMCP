"""Unified research router (ADR-0030 / TAP-5365).

Routes library/API questions to ``lookup_docs`` and open-ended / latest /
URL questions to brain ``web_research`` / ``research_fetch`` via BrainBridge.
Credentials stay brain-side; brain-down never returns silent empty success.
"""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

ResearchRoute = Literal["docs", "web", "fetch"]

VALID_ROUTES: frozenset[str] = frozenset({"auto", "docs", "web", "fetch"})
VALID_FRESHNESS: frozenset[str] = frozenset({"volatile", "evergreen"})
VALID_SOURCES: frozenset[str] = frozenset({"auto", "exa", "tavily", "firecrawl"})

_WEB_HINTS = re.compile(
    r"\b("
    r"latest|news|today|current|as\s+of\s+20\d{2}|what'?s\s+new|"
    r"recent\s+changes|search\s+the\s+web|web\s+search|google|bing"
    r")\b",
    re.IGNORECASE,
)
_DOCS_HINTS = re.compile(
    r"\b("
    r"api|docs?|documentation|signature|how\s+to\s+(use|call|import)|"
    r"fixture|middleware|validator|type\s+hint"
    r")\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def looks_like_url(value: str) -> bool:
    """Return True when *value* is an absolute http(s) URL."""
    text = value.strip()
    if not _URL_RE.match(text):
        return False
    parsed = urlparse(text)
    return bool(parsed.scheme in {"http", "https"} and parsed.netloc)


def classify_research_route(
    query: str,
    *,
    library: str = "",
    url: str = "",
    route: str = "auto",
) -> ResearchRoute:
    """Choose docs vs web vs fetch per ADR-0030 routing heuristics."""
    normalized = (route or "auto").strip().lower() or "auto"
    if normalized in {"docs", "web", "fetch"}:
        return normalized  # type: ignore[return-value]

    if url.strip() or looks_like_url(query):
        return "fetch"
    if library.strip():
        return "docs"
    if _WEB_HINTS.search(query):
        return "web"
    if _DOCS_HINTS.search(query):
        return "docs"
    # Open-ended questions default to the brain web path (ADR-0030).
    return "web"


def telemetry_source_for_docs(*, cache_hit: bool) -> str:
    """Map docs lookup outcome to ADR-0030 ``source`` telemetry."""
    return "cache-hit" if cache_hit else "docs"


def telemetry_source_for_web(payload: dict[str, Any]) -> str:
    """Map brain web/fetch payload to ADR-0030 ``source`` telemetry."""
    if payload.get("cache_hit") is True:
        return "cache-hit"
    source = str(payload.get("source") or "").lower()
    if source in {"cache", "cache-hit"}:
        return "cache-hit"
    if source == "stale_fallback":
        return "web"
    return "web"


def bridge_degraded_response(
    *,
    route: ResearchRoute,
    detail: str,
    reason: str = "brain_bridge_call_failed",
    elapsed_ms: int = 0,
) -> dict[str, Any]:
    """Structured degrade when BrainBridge cannot serve web research."""
    return {
        "tool": "tapps_research",
        "success": False,
        "elapsed_ms": elapsed_ms,
        "degraded": True,
        "retryable": True,
        "data": {
            "route": route,
            "source": "web",
            "error": reason,
            "detail": detail,
            "remediation": (
                "tapps-brain is unreachable or the research tool is unavailable. "
                "Verify memory.brain_http_url / TAPPS_BRAIN_AUTH_TOKEN, ensure "
                "brain ≥ 3.28.0 exposes web_research/research_fetch, then retry."
            ),
            "next_steps": [
                "Check tapps-brain health at memory.brain_http_url",
                "Confirm brain tools/list includes web_research and research_fetch",
                "Retry after ~30s if the circuit breaker is open",
            ],
        },
    }


def wrap_brain_research_payload(
    payload: dict[str, Any],
    *,
    route: ResearchRoute,
    elapsed_ms: int,
) -> dict[str, Any]:
    """Normalize a brain research payload into the tapps_research envelope."""
    success = bool(payload.get("success", False))
    degraded = bool(payload.get("degraded", False)) or not success
    data: dict[str, Any] = {
        "route": route,
        **payload,
    }
    # Prefer router telemetry over brain's provider ``source`` field.
    data["source"] = telemetry_source_for_web(payload)
    response: dict[str, Any] = {
        "tool": "tapps_research",
        "success": success,
        "elapsed_ms": elapsed_ms,
        "data": data,
    }
    if degraded:
        response["degraded"] = True
    if payload.get("retryable") is not None:
        response["retryable"] = bool(payload.get("retryable"))
    elif not success:
        response["retryable"] = True
    return response
