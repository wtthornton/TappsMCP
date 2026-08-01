"""Answer-level research recall with freshness tiers (TAP-5366 / ADR-0030).

Persists successful web/fetch findings as pattern-tier memories tagged with
``volatile`` or ``evergreen`` freshness, and recalls them before calling brain
``web_research`` / ``research_fetch``. Stale volatile answers are skipped.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from tapps_mcp.tools.research import ResearchRoute, VALID_FRESHNESS

logger = structlog.get_logger(__name__)

_ANSWER_KEY_PREFIX = "research-answer"
_ANSWER_TAG = "research-answer"
_MAX_MEMORY_VALUE_CHARS = 4000


def research_answer_memory_key(
    *,
    route: ResearchRoute,
    query: str = "",
    url: str = "",
) -> str:
    """Stable pattern-tier key for a research answer (TAP-5366)."""
    if route == "fetch":
        material = f"fetch\0{(url or query).strip().lower()}"
    else:
        material = f"web\0{query.strip().lower()}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"{_ANSWER_KEY_PREFIX}:{route}:{digest}"


def research_answer_tags(*, freshness: str, route: ResearchRoute) -> list[str]:
    """Tags stored with answer-level research memories."""
    return [
        _ANSWER_TAG,
        f"freshness:{freshness}",
        f"route:{route}",
        "tapps-mcp",
        "auto-captured",
    ]


def _truncate_results(results: Any, *, max_chars: int) -> Any:
    if not isinstance(results, list):
        return results
    kept: list[Any] = []
    used = 2  # []
    for item in results:
        chunk = json.dumps(item, ensure_ascii=False, default=str)
        if used + len(chunk) + 1 > max_chars:
            break
        kept.append(item)
        used += len(chunk) + 1
    return kept


def build_answer_memory_value(
    payload: dict[str, Any],
    *,
    freshness: str,
    route: ResearchRoute,
    query: str = "",
    url: str = "",
    saved_at: datetime | None = None,
) -> str:
    """Serialize a compact, freshness-tagged answer for pattern-tier memory."""
    stamp = (saved_at or datetime.now(UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    answer_body: dict[str, Any] = {
        "success": bool(payload.get("success", True)),
        "provider": payload.get("provider"),
        "cache_hit": payload.get("cache_hit"),
    }
    for field in ("answer", "content", "summary", "markdown"):
        if payload.get(field):
            answer_body[field] = payload[field]
            break
    if "results" in payload:
        answer_body["results"] = _truncate_results(payload.get("results"), max_chars=2800)
    compact = {
        "freshness": freshness,
        "route": route,
        "query": query,
        "url": url,
        "saved_at": stamp,
        "answer": answer_body,
    }
    text = json.dumps(compact, ensure_ascii=False, default=str)
    if len(text) > _MAX_MEMORY_VALUE_CHARS:
        text = text[:_MAX_MEMORY_VALUE_CHARS]
    return text


def parse_answer_memory_value(value: Any) -> dict[str, Any] | None:
    """Parse a stored research answer value; return None if malformed."""
    if isinstance(value, dict):
        raw = value
    elif isinstance(value, str):
        text = value.strip()
        if not text.startswith("{"):
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        raw = parsed
    else:
        return None
    freshness = str(raw.get("freshness") or "").lower()
    if freshness not in VALID_FRESHNESS:
        return None
    if not isinstance(raw.get("answer"), dict):
        return None
    return raw


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def answer_saved_at(entry: dict[str, Any], parsed: dict[str, Any]) -> datetime | None:
    """Prefer embedded saved_at, then memory entry timestamps."""
    for candidate in (
        parsed.get("saved_at"),
        entry.get("updated_at"),
        entry.get("created_at"),
        entry.get("timestamp"),
    ):
        stamp = _parse_timestamp(candidate)
        if stamp is not None:
            return stamp
    return None


def is_answer_fresh(
    *,
    freshness: str,
    saved_at: datetime,
    now: datetime | None = None,
    volatile_ttl_hours: int = 24,
    evergreen_ttl_days: int = 30,
) -> bool:
    """Return True when a recalled answer is still within its freshness TTL."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    age = current - saved_at.astimezone(UTC)
    if age < timedelta(0):
        return True
    if freshness == "volatile":
        return age <= timedelta(hours=max(1, volatile_ttl_hours))
    return age <= timedelta(days=max(1, evergreen_ttl_days))


def wrap_memory_hit_payload(
    parsed: dict[str, Any],
    *,
    memory_key: str,
    elapsed_ms: int,
) -> dict[str, Any]:
    """Build a tapps_research success envelope from a fresh memory hit."""
    route = str(parsed.get("route") or "web")
    if route not in {"web", "fetch"}:
        route = "web"
    answer = parsed.get("answer") if isinstance(parsed.get("answer"), dict) else {}
    data: dict[str, Any] = {
        "route": route,
        "source": "memory-hit",
        "memory_hit": True,
        "memory_key": memory_key,
        "freshness": parsed.get("freshness"),
        "query": parsed.get("query") or "",
        "url": parsed.get("url") or "",
        "saved_at": parsed.get("saved_at"),
        **answer,
    }
    data["source"] = "memory-hit"
    return {
        "tool": "tapps_research",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": data,
    }


def _fresh_parsed_answer(
    entry: dict[str, Any],
    *,
    key: str,
    freshness: str,
    volatile_ttl_hours: int,
    evergreen_ttl_days: int,
    now: datetime | None,
) -> dict[str, Any] | None:
    """Validate and freshness-gate a memory entry; return parsed value or None."""
    parsed = parse_answer_memory_value(entry.get("value"))
    if parsed is None:
        return None
    stored_freshness = str(parsed.get("freshness") or "").lower()
    if stored_freshness != freshness:
        logger.debug(
            "research_answer_recall_freshness_mismatch",
            key=key,
            stored=stored_freshness,
            requested=freshness,
        )
        return None
    saved = answer_saved_at(entry, parsed)
    if saved is None:
        return None
    if not is_answer_fresh(
        freshness=stored_freshness,
        saved_at=saved,
        now=now,
        volatile_ttl_hours=volatile_ttl_hours,
        evergreen_ttl_days=evergreen_ttl_days,
    ):
        logger.debug(
            "research_answer_recall_stale",
            key=key,
            freshness=stored_freshness,
            saved_at=saved.isoformat(),
        )
        return None
    return parsed


async def recall_research_answer(
    bridge: Any,
    *,
    route: ResearchRoute,
    query: str = "",
    url: str = "",
    freshness: str,
    volatile_ttl_hours: int = 24,
    evergreen_ttl_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Recall a fresh pattern-tier research answer, or None on miss/stale.

    Stale volatile (and expired evergreen) entries are treated as misses so the
    caller can refetch. Never raises.
    """
    if route not in {"web", "fetch"}:
        return None
    key = research_answer_memory_key(route=route, query=query, url=url)
    try:
        entry = await bridge.get(key)
    except Exception:
        logger.debug("research_answer_recall_get_failed", key=key, exc_info=True)
        return None
    if not isinstance(entry, dict):
        return None
    parsed = _fresh_parsed_answer(
        entry,
        key=key,
        freshness=freshness,
        volatile_ttl_hours=volatile_ttl_hours,
        evergreen_ttl_days=evergreen_ttl_days,
        now=now,
    )
    if parsed is None:
        return None
    return wrap_memory_hit_payload(parsed, memory_key=key, elapsed_ms=0)


async def save_research_answer(
    bridge: Any,
    payload: dict[str, Any],
    *,
    route: ResearchRoute,
    query: str = "",
    url: str = "",
    freshness: str,
) -> str | None:
    """Persist a successful web/fetch answer as pattern-tier memory. Never raises."""
    if route not in {"web", "fetch"} or not payload.get("success", False):
        return None
    key = research_answer_memory_key(route=route, query=query, url=url)
    value = build_answer_memory_value(
        payload,
        freshness=freshness,
        route=route,
        query=query,
        url=url,
    )
    tags = research_answer_tags(freshness=freshness, route=route)
    try:
        await bridge.save(
            key=key,
            value=value,
            tier="pattern",
            source="agent",
            source_agent="tapps-mcp",
            scope="project",
            tags=tags,
            skip_consolidation=True,
        )
        logger.debug("research_answer_save_ok", key=key, freshness=freshness, route=route)
        return key
    except Exception:
        logger.debug("research_answer_save_failed", key=key, exc_info=True)
        return None


async def maybe_recall_research_answer(
    bridge: Any,
    *,
    route: ResearchRoute,
    query: str,
    url: str,
    freshness: str,
    memory_enabled: bool,
    auto_save_quality: bool,
    volatile_ttl_hours: int,
    evergreen_ttl_days: int,
    elapsed_ms: int,
) -> dict[str, Any] | None:
    """Recall-first gate used by ``tapps_research`` when M4.1 is enabled."""
    if not (memory_enabled and auto_save_quality):
        return None
    recalled = await recall_research_answer(
        bridge,
        route=route,
        query=query,
        url=url,
        freshness=freshness,
        volatile_ttl_hours=volatile_ttl_hours,
        evergreen_ttl_days=evergreen_ttl_days,
    )
    if recalled is None:
        return None
    recalled["elapsed_ms"] = elapsed_ms
    if isinstance(recalled.get("data"), dict):
        recalled["data"]["elapsed_ms"] = elapsed_ms
    return recalled


async def maybe_save_research_answer(
    bridge: Any,
    payload: dict[str, Any],
    *,
    route: ResearchRoute,
    query: str,
    url: str,
    freshness: str,
    memory_enabled: bool,
    auto_save_quality: bool,
    response_data: dict[str, Any] | None,
) -> None:
    """Best-effort pattern-tier save after a successful web/fetch result."""
    if not (memory_enabled and auto_save_quality and payload.get("success")):
        return
    await save_research_answer(
        bridge,
        payload,
        route=route,
        query=query,
        url=url,
        freshness=freshness,
    )
    if response_data is not None:
        response_data["freshness"] = freshness
