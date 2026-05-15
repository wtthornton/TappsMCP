"""Lookup orchestration — ties cache, fuzzy matcher, providers, and circuit breaker.

Lookup flow:
  1. Cache check (exact match)
  2. Fuzzy match against cached libraries
  3. Provider chain (Context7 if key, LlmsTxt always) — multi-backend with automatic fallback
  4. RAG safety check on retrieved content
  5. Cache store
  6. Stale fallback if API fails

Background refresh: stale cache entries return immediately and queue an
async background refresh.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from typing import TYPE_CHECKING

import structlog

from tapps_core.knowledge.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    get_context7_circuit_breaker,
)
from tapps_core.knowledge.context7_client import Context7Client, Context7Error
from tapps_core.knowledge.fuzzy_matcher import did_you_mean, fuzzy_match_library
from tapps_core.knowledge.models import CacheEntry, LookupResult
from tapps_core.knowledge.rag_safety import check_content_safety
from tapps_core.knowledge.url_guard import (
    UrlGuardConfig,
    UrlGuardError,
    validate_doc_source_url,
)

if TYPE_CHECKING:
    from pydantic import SecretStr

    from tapps_core.config.settings import TappsMCPSettings
    from tapps_core.knowledge.cache import KBCache
    from tapps_core.knowledge.providers.registry import ProviderRegistry

logger = structlog.get_logger(__name__)

# Libraries where expert knowledge is preferred over Context7 for operational topics.
# These typically return generic API reference from Context7 instead of operational patterns.
_OPS_FIRST_LIBRARIES: frozenset[str] = frozenset(
    {
        "docker",
        "docker-compose",
        "kubernetes",
        "github-actions",
        "ci",
    }
)

# Minimum prose characters to consider content substantive (not just a TOC).
_TOC_PROSE_THRESHOLD = 500
# Minimum ratio of link/heading lines to total lines to be considered TOC-like.
_TOC_LINK_RATIO_THRESHOLD = 0.5

# Pattern matching markdown links: [text](url) or bare URLs
_LINK_RE = re.compile(r"\[.*?\]\(.*?\)|https?://\S+")
# Pattern matching markdown headings
_HEADING_RE = re.compile(r"^#{1,6}\s+")


def _is_toc_only(content: str) -> bool:
    """Check if content is mostly a table-of-contents with little prose.

    Returns ``True`` when the content is dominated by markdown links and
    headings with fewer than ``_TOC_PROSE_THRESHOLD`` characters of actual
    prose text.
    """
    lines = content.splitlines()
    prose_chars = 0
    link_or_heading_lines = 0
    total_lines = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        total_lines += 1
        if _HEADING_RE.match(stripped) or _LINK_RE.search(stripped):
            link_or_heading_lines += 1
        else:
            prose_chars += len(stripped)

    if total_lines == 0:
        return True

    # Content is TOC-only when prose is thin AND most lines are links/headings
    link_ratio = link_or_heading_lines / total_lines if total_lines else 0.0
    return prose_chars < _TOC_PROSE_THRESHOLD and link_ratio > _TOC_LINK_RATIO_THRESHOLD


def _build_provider_registry(
    api_key: SecretStr | None = None,
    *,
    settings: TappsMCPSettings | None = None,
) -> ProviderRegistry:
    """Build provider registry: Context7 (if key), LlmsTxt (always)."""
    from tapps_core.knowledge.providers.context7_provider import Context7Provider
    from tapps_core.knowledge.providers.llms_txt_provider import LlmsTxtProvider
    from tapps_core.knowledge.providers.registry import ProviderRegistry

    registry: ProviderRegistry = ProviderRegistry()
    context7_key = settings.context7_api_key if settings else api_key

    if context7_key is not None:
        registry.register(Context7Provider(api_key=context7_key))
    registry.register(LlmsTxtProvider())
    return registry


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
        registry: ProviderRegistry | None = None,
        settings: TappsMCPSettings | None = None,
    ) -> None:
        self._cache = cache
        self._api_key = api_key if settings is None else settings.context7_api_key
        self._breaker = circuit_breaker or get_context7_circuit_breaker()
        self._client = client or Context7Client(api_key=self._api_key)
        self._registry = registry or (
            _build_provider_registry(settings=settings)
            if settings
            else _build_provider_registry(api_key=api_key)
        )
        self._settings = settings
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def close(self) -> None:
        """Shut down the client and cancel background tasks."""
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._background_tasks.clear()
        await self._client.close()

    async def lookup(
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
        cache_result = self._check_exact_cache(lib_clean, topic, mode, start)
        if cache_result is not None:
            return cache_result

        # 2. Fuzzy match against cached libraries
        cached_entries = self._cache.list_entries()
        known_libs = list({e.library for e in cached_entries})
        fuzzy_result = self._check_fuzzy_cache(lib_clean, topic, known_libs, start)
        if fuzzy_result is not None:
            return fuzzy_result

        # 2b. Custom doc sources (take priority over providers)
        custom_result = await self._check_custom_doc_source(lib_clean, topic, start)
        if custom_result is not None:
            return custom_result

        # 2c. Ops-first routing — for operational libraries, try expert system first
        if lib_clean in _OPS_FIRST_LIBRARIES:
            ops_result = await self._try_expert_first(lib_clean, topic, start)
            if ops_result is not None:
                return ops_result

        # 3. API resolve + fetch — try provider chain first, then legacy Context7
        content, provider_source = await self._fetch_from_providers(lib_clean, topic, mode, start)
        if isinstance(content, LookupResult):
            # Provider step returned an error result (circuit breaker / API error)
            return content

        if content is None:
            return self._not_found_result(lib_clean, topic, known_libs, start)

        # 4. RAG safety check + TOC detection
        safety_result = self._apply_rag_safety(content, lib_clean, topic, start)
        if isinstance(safety_result, LookupResult):
            return safety_result
        safe_content, toc_warning = safety_result

        # 5. Store in cache and return
        return self._cache_and_return(
            lib_clean, topic, safe_content, provider_source, toc_warning, start
        )

    def _check_exact_cache(
        self,
        lib_clean: str,
        topic: str,
        mode: str,
        start: float,
    ) -> LookupResult | None:
        """Return a cached result if an exact match exists (fresh or stale)."""
        entry = self._cache.get(lib_clean, topic)
        if entry is None or not entry.content:
            return None

        elapsed = (time.monotonic() - start) * 1000

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

    def _check_fuzzy_cache(
        self,
        lib_clean: str,
        topic: str,
        known_libs: list[str],
        start: float,
    ) -> LookupResult | None:
        """Return a cached result for the best fuzzy library match, if any."""
        fuzzy_results = fuzzy_match_library(lib_clean, known_libs, threshold=0.7)
        if not fuzzy_results:
            return None

        best = fuzzy_results[0]
        cached = self._cache.get(best.library, topic)
        if cached is None or not cached.content:
            return None

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

    async def _fetch_from_providers(
        self,
        lib_clean: str,
        topic: str,
        mode: str,
        start: float,
    ) -> tuple[str | LookupResult | None, str | None]:
        """Fetch content via the provider chain then legacy Context7.

        Returns ``(content, provider_source)`` on success, or a ``LookupResult``
        error packed in the first element when a circuit-breaker / API error occurs.
        """
        content: str | None = None
        provider_source: str | None = None

        # 3a. Multi-provider chain (Context7 + llms.txt fallback)
        healthy = self._registry.healthy_providers()
        if healthy:
            result = await self._registry.lookup(lib_clean, topic)
            if result.success and result.content:
                content = result.content
                provider_source = result.provider_name or "provider"

        # 3b. Legacy Context7 path (when no provider succeeded and API key set)
        if content is None and self._api_key is not None:
            legacy_result = await self._fetch_legacy_context7(lib_clean, topic, mode, start)
            if isinstance(legacy_result, LookupResult):
                return legacy_result, None
            if legacy_result is not None:
                content = legacy_result
                provider_source = "context7"

        return content, provider_source

    async def _fetch_legacy_context7(
        self,
        lib_clean: str,
        topic: str,
        mode: str,
        start: float,
    ) -> str | LookupResult | None:
        """Call the legacy Context7 circuit breaker and handle its errors.

        Returns the raw content string on success, a ``LookupResult`` on a
        recoverable error (circuit open or API error), or ``None`` if not fetched.
        """
        try:
            result: str | LookupResult | None = await self._breaker.call(
                self._resolve_and_fetch,
                lib_clean,
                topic,
                mode,
            )
            return result
        except CircuitBreakerOpenError:
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

    def _not_found_result(
        self,
        lib_clean: str,
        topic: str,
        known_libs: list[str],
        start: float,
    ) -> LookupResult:
        """Build a failure result with optional 'did you mean?' suggestions."""
        elapsed = (time.monotonic() - start) * 1000
        suggestions = did_you_mean(lib_clean, known_libs)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        return LookupResult(
            success=False,
            library=lib_clean,
            topic=topic,
            error=f"No documentation found.{hint}",
            response_time_ms=round(elapsed, 1),
        )

    def _apply_rag_safety(
        self,
        content: str,
        lib_clean: str,
        topic: str,
        start: float,
    ) -> LookupResult | tuple[str, str | None]:
        """Run the RAG safety check and TOC-only detection on fetched content.

        Returns a ``LookupResult`` error if content is blocked, otherwise a
        ``(safe_content, toc_warning)`` tuple.
        """
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

        safe_content = safety.sanitised_content or content
        toc_warning: str | None = safety.warning

        if _is_toc_only(safe_content):
            toc_msg = (
                "Generic table-of-contents only; consider "
                "tapps_lookup_docs with a more specific topic for operational questions."
            )
            toc_warning = f"{toc_warning} {toc_msg}" if toc_warning else toc_msg
            logger.info("toc_only_content", library=lib_clean, topic=topic)

        return safe_content, toc_warning

    def _cache_and_return(
        self,
        lib_clean: str,
        topic: str,
        safe_content: str,
        provider_source: str | None,
        toc_warning: str | None,
        start: float,
    ) -> LookupResult:
        """Store content in cache and build the final success result."""
        self._cache.put(
            CacheEntry(
                library=lib_clean,
                topic=topic,
                content=safe_content,
                token_count=len(safe_content) // 4,  # rough estimate
                provider_source=provider_source,
            )
        )
        elapsed = (time.monotonic() - start) * 1000
        return LookupResult(
            success=True,
            content=safe_content,
            source=provider_source or "api",
            library=lib_clean,
            topic=topic,
            response_time_ms=round(elapsed, 1),
            cache_hit=False,
            warning=toc_warning,
        )

    async def _try_expert_first(
        self,
        library: str,
        topic: str,
        start: float,
    ) -> LookupResult | None:
        """Expert system removed (EPIC-94). Always returns None."""
        return None

    async def _check_custom_doc_source(
        self,
        library: str,
        topic: str,
        start: float,
    ) -> LookupResult | None:
        """Check if a custom doc source is configured for the library.

        Custom sources (local file or URL) take priority over Context7/LlmsTxt.
        Returns a LookupResult if found, None otherwise.
        """
        if self._settings is None:
            return None

        doc_config = self._settings.doc_sources.get(library)
        if doc_config is None:
            return None

        content: str | None = None
        source_label = "custom_doc_source"

        # Try local file first
        if doc_config.file:
            try:
                from pathlib import Path

                file_path = self._settings.project_root / Path(doc_config.file)
                if file_path.exists() and file_path.is_file():
                    content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
                    source_label = "custom_file"
                    logger.debug(
                        "custom_doc_source_file",
                        library=library,
                        path=str(file_path),
                    )
                else:
                    logger.warning(
                        "custom_doc_source_file_missing",
                        library=library,
                        path=str(file_path),
                    )
            except (OSError, ValueError) as exc:
                logger.warning(
                    "custom_doc_source_file_error",
                    library=library,
                    error=str(exc),
                )

        # Try URL if no file content
        if content is None and doc_config.url:
            content = await self._fetch_custom_doc_url(library, doc_config.url)
            if content is not None:
                source_label = "custom_url"

        if content is None:
            return None

        # RAG safety check
        safety = check_content_safety(content)
        if not safety.safe:
            elapsed = (time.monotonic() - start) * 1000
            return LookupResult(
                success=False,
                library=library,
                topic=topic,
                error=f"Custom doc content blocked by safety filter: {safety.warning}",
                response_time_ms=round(elapsed, 1),
            )

        safe_content = safety.sanitised_content or content

        # Cache the custom content
        self._cache.put(
            CacheEntry(
                library=library,
                topic=topic,
                content=safe_content,
                token_count=len(safe_content) // 4,
                provider_source=source_label,
            )
        )

        elapsed = (time.monotonic() - start) * 1000
        return LookupResult(
            success=True,
            content=safe_content,
            source=source_label,
            library=library,
            topic=topic,
            response_time_ms=round(elapsed, 1),
            cache_hit=False,
        )

    async def _fetch_custom_doc_url(self, library: str, url: str) -> str | None:
        """Fetch a custom doc-source URL with SSRF + size guards (TAP-1791)."""
        import httpx

        assert self._settings is not None  # guarded by caller
        guard = UrlGuardConfig(
            allow_http=self._settings.doc_sources_allow_http,
            allow_private_hosts=frozenset(
                h.lower() for h in self._settings.doc_sources_allow_private_hosts
            ),
            max_bytes=self._settings.doc_sources_max_bytes,
        )

        try:
            await asyncio.to_thread(validate_doc_source_url, url, guard)
        except UrlGuardError as exc:
            logger.warning(
                "custom_doc_source_url_blocked",
                library=library,
                url=url,
                error=str(exc),
            )
            return None

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    declared = resp.headers.get("content-length")
                    if declared is not None:
                        try:
                            if int(declared) > guard.max_bytes:
                                logger.warning(
                                    "custom_doc_source_url_too_large",
                                    library=library,
                                    url=url,
                                    declared_bytes=int(declared),
                                    max_bytes=guard.max_bytes,
                                )
                                return None
                        except ValueError:
                            pass
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > guard.max_bytes:
                            logger.warning(
                                "custom_doc_source_url_too_large",
                                library=library,
                                url=url,
                                received_bytes=total,
                                max_bytes=guard.max_bytes,
                            )
                            return None
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    encoding = resp.encoding or "utf-8"
            content = body.decode(encoding, errors="replace")
            logger.debug(
                "custom_doc_source_url",
                library=library,
                url=url,
                bytes=len(body),
            )
            return content
        except Exception as exc:
            logger.warning(
                "custom_doc_source_url_error",
                library=library,
                url=url,
                error=str(exc),
            )
            return None

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
            except (Context7Error, asyncio.CancelledError, ValueError) as e:
                logger.debug(
                    "background_refresh_failed",
                    library=library,
                    topic=topic,
                    error=str(e),
                )

        task = asyncio.create_task(_refresh())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
