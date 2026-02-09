"""Lookup orchestration — ties cache, fuzzy matcher, client, and circuit breaker.

Lookup flow:
  1. Cache check (exact match)
  2. Fuzzy match against cached libraries
  3. Context7 API resolve + fetch (with circuit breaker)
  4. RAG safety check on retrieved content
  5. Cache store
  6. Stale fallback if API fails

Background refresh: stale cache entries return immediately and queue an
async background refresh.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from tapps_mcp.knowledge.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    get_context7_circuit_breaker,
)
from tapps_mcp.knowledge.context7_client import Context7Client, Context7Error
from tapps_mcp.knowledge.fuzzy_matcher import fuzzy_match_library
from tapps_mcp.knowledge.models import CacheEntry, LookupResult
from tapps_mcp.knowledge.rag_safety import check_content_safety

if TYPE_CHECKING:
    from pydantic import SecretStr

    from tapps_mcp.knowledge.cache import KBCache

logger = structlog.get_logger(__name__)


class LookupEngine:
    """Documentation lookup engine with cache-first architecture.

    Args:
        cache: KB cache instance.
        api_key: Context7 API key (optional — degrades to cache-only).
        circuit_breaker: Optional circuit breaker override.
        client: Optional Context7 client override (for testing).
    """

    def __init__(
        self,
        cache: KBCache,
        api_key: SecretStr | None = None,
        *,
        circuit_breaker: CircuitBreaker | None = None,
        client: Context7Client | None = None,
    ) -> None:
        self._cache = cache
        self._api_key = api_key
        self._breaker = circuit_breaker or get_context7_circuit_breaker()
        self._client = client or Context7Client(api_key=api_key)
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def close(self) -> None:
        """Shut down the client and cancel background tasks."""
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()
        await self._client.close()

    async def lookup(  # noqa: PLR0911
        self,
        library: str,
        topic: str = "overview",
        *,
        mode: str = "code",
    ) -> LookupResult:
        """Look up documentation for *library* / *topic*.

        Args:
            library: Library name (fuzzy-matched).
            topic: Documentation topic.
            mode: ``"code"`` or ``"info"``.

        Returns:
            ``LookupResult`` with content, source info, and timing.
        """
        start = time.monotonic()
        lib_clean = library.strip().lower()

        # 1. Exact cache hit
        entry = self._cache.get(lib_clean, topic)
        if entry is not None and entry.content:
            elapsed = (time.monotonic() - start) * 1000

            # Check staleness — if stale, return cached but trigger background refresh
            if self._cache.is_stale(lib_clean, topic):
                self._schedule_background_refresh(lib_clean, topic, mode)
                return LookupResult(
                    success=True,
                    content=entry.content,
                    source="stale_fallback",
                    library=entry.library,
                    topic=entry.topic,
                    context7_id=entry.context7_id,
                    response_time_ms=round(elapsed, 1),
                    cache_hit=True,
                    warning="Returning stale cached content; background refresh queued.",
                )

            return LookupResult(
                success=True,
                content=entry.content,
                source="cache",
                library=entry.library,
                topic=entry.topic,
                context7_id=entry.context7_id,
                response_time_ms=round(elapsed, 1),
                cache_hit=True,
            )

        # 2. Fuzzy match against cached libraries
        cached_entries = self._cache.list_entries()
        known_libs = list({e.library for e in cached_entries})
        fuzzy_results = fuzzy_match_library(lib_clean, known_libs, threshold=0.7)

        if fuzzy_results:
            best = fuzzy_results[0]
            cached = self._cache.get(best.library, topic)
            if cached is not None and cached.content:
                elapsed = (time.monotonic() - start) * 1000
                return LookupResult(
                    success=True,
                    content=cached.content,
                    source="fuzzy_match",
                    library=cached.library,
                    topic=cached.topic,
                    context7_id=cached.context7_id,
                    response_time_ms=round(elapsed, 1),
                    cache_hit=True,
                    fuzzy_score=best.score,
                )

        # 3. API resolve + fetch (with circuit breaker)
        if self._api_key is None:
            elapsed = (time.monotonic() - start) * 1000
            return LookupResult(
                success=False,
                library=lib_clean,
                topic=topic,
                error="No Context7 API key configured. Cache miss.",
                response_time_ms=round(elapsed, 1),
            )

        try:
            content = await self._breaker.call(
                self._resolve_and_fetch,
                lib_clean,
                topic,
                mode,
            )
        except CircuitBreakerOpenError:
            # Circuit is open — try stale fallback
            stale = self._cache.get(lib_clean, topic)
            elapsed = (time.monotonic() - start) * 1000
            if stale is not None and stale.content:
                return LookupResult(
                    success=True,
                    content=stale.content,
                    source="stale_fallback",
                    library=stale.library,
                    topic=stale.topic,
                    response_time_ms=round(elapsed, 1),
                    cache_hit=True,
                    warning="Circuit breaker open; returning stale cached content.",
                )
            return LookupResult(
                success=False,
                library=lib_clean,
                topic=topic,
                error="Context7 API unavailable (circuit breaker open).",
                response_time_ms=round(elapsed, 1),
            )
        except (Context7Error, TimeoutError) as exc:
            # API failed — try stale fallback
            stale = self._cache.get(lib_clean, topic)
            elapsed = (time.monotonic() - start) * 1000
            if stale is not None and stale.content:
                return LookupResult(
                    success=True,
                    content=stale.content,
                    source="stale_fallback",
                    library=stale.library,
                    topic=stale.topic,
                    response_time_ms=round(elapsed, 1),
                    cache_hit=True,
                    warning=f"API error: {exc}; returning stale cached content.",
                )
            return LookupResult(
                success=False,
                library=lib_clean,
                topic=topic,
                error=f"Context7 API error: {exc}",
                response_time_ms=round(elapsed, 1),
            )

        if content is None:
            elapsed = (time.monotonic() - start) * 1000
            return LookupResult(
                success=False,
                library=lib_clean,
                topic=topic,
                error="No documentation found.",
                response_time_ms=round(elapsed, 1),
            )

        # 4. RAG safety check
        safety = check_content_safety(content)
        if not safety.safe:
            elapsed = (time.monotonic() - start) * 1000
            return LookupResult(
                success=False,
                library=lib_clean,
                topic=topic,
                error=f"Content blocked by RAG safety filter: {safety.warning}",
                response_time_ms=round(elapsed, 1),
            )

        # Use sanitised content if available
        safe_content = safety.sanitised_content or content

        # 5. Store in cache
        self._cache.put(
            CacheEntry(
                library=lib_clean,
                topic=topic,
                content=safe_content,
                token_count=len(safe_content) // 4,  # rough estimate
            )
        )

        elapsed = (time.monotonic() - start) * 1000
        return LookupResult(
            success=True,
            content=safe_content,
            source="api",
            library=lib_clean,
            topic=topic,
            response_time_ms=round(elapsed, 1),
            cache_hit=False,
            warning=safety.warning,
        )

    async def _resolve_and_fetch(
        self,
        library: str,
        topic: str,
        mode: str,
    ) -> str | None:
        """Resolve library name via API and fetch documentation."""
        # Resolve
        matches = await self._client.resolve_library(library)
        if not matches:
            return None

        best_match = matches[0]

        # Fetch docs
        content = await self._client.fetch_docs(
            best_match.id,
            topic=topic,
            mode=mode,
        )
        return content if content else None

    def _schedule_background_refresh(
        self,
        library: str,
        topic: str,
        mode: str,
    ) -> None:
        """Schedule a background cache refresh (fire-and-forget)."""
        if self._api_key is None:
            return

        async def _refresh() -> None:
            try:
                content = await self._resolve_and_fetch(library, topic, mode)
                if content:
                    safety = check_content_safety(content)
                    if safety.safe:
                        safe_content = safety.sanitised_content or content
                        self._cache.put(
                            CacheEntry(
                                library=library,
                                topic=topic,
                                content=safe_content,
                                token_count=len(safe_content) // 4,
                            )
                        )
                        logger.info(
                            "background_refresh_complete",
                            library=library,
                            topic=topic,
                        )
            except Exception:
                logger.debug(
                    "background_refresh_failed",
                    library=library,
                    topic=topic,
                    exc_info=True,
                )

        task = asyncio.create_task(_refresh())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
