"""Cache warming — pre-fetch documentation for project dependencies.

On server startup, detects project libraries and queues background
cache warming.  Does not block server startup.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from tapps_core.knowledge.context7_client import Context7Client, Context7Error
from tapps_core.knowledge.library_detector import detect_libraries
from tapps_core.knowledge.rag_safety import check_content_safety

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import SecretStr

    from tapps_core.knowledge.cache import KBCache

logger = structlog.get_logger(__name__)

# Maximum libraries to warm in a single session
MAX_WARM_LIBRARIES = 20

# Delay between API calls during warming (seconds)
WARM_DELAY_SECONDS = 0.5


async def warm_cache(
    project_root: Path,
    cache: KBCache,
    api_key: SecretStr | None = None,
    *,
    libraries: list[str] | None = None,
    max_libraries: int = MAX_WARM_LIBRARIES,
) -> int:
    """Detect project dependencies and pre-fetch their documentation.

    Args:
        project_root: Project root to scan for dependency files.
        cache: KB cache instance.
        api_key: Context7 API key (skips warming if ``None``).
        libraries: Optional explicit list of library names. If provided, uses
            this instead of detecting from project manifest files.
        max_libraries: Maximum number of libraries to warm.

    Returns:
        Number of libraries successfully warmed.
    """
    if api_key is None:
        logger.warning("cache_warming_skipped", reason="no_api_key")
        return 0

    libs = libraries if libraries is not None else detect_libraries(project_root)
    if not libs:
        logger.info("cache_warming_skipped", reason="no_dependencies_detected")
        return 0

    # Filter out already-cached (non-stale) libraries
    to_warm = [lib for lib in libs[:max_libraries] if not cache.has(lib) or cache.is_stale(lib)]

    if not to_warm:
        logger.info("cache_warming_skipped", reason="all_cached")
        return 0

    logger.info(
        "cache_warming_started",
        total_detected=len(libs),
        to_warm=len(to_warm),
    )

    client = Context7Client(api_key=api_key)
    warmed = 0

    try:
        for lib in to_warm:
            try:
                warmed += await _warm_one(lib, client, cache)
            except (Context7Error, TimeoutError):
                logger.debug("cache_warming_failed", library=lib, exc_info=True)

            # Rate limiting
            await asyncio.sleep(WARM_DELAY_SECONDS)
    finally:
        await client.close()

    logger.info("cache_warming_complete", warmed=warmed, attempted=len(to_warm))
    return warmed


async def _warm_one(
    library: str,
    client: Context7Client,
    cache: KBCache,
) -> int:
    """Warm a single library.  Returns 1 on success, 0 on failure."""
    from tapps_core.knowledge.models import CacheEntry as CacheEntryModel

    # Resolve library name
    matches = await client.resolve_library(library)
    if not matches:
        return 0

    best = matches[0]

    # Fetch documentation
    try:
        content = await client.fetch_docs(best.id, topic="overview")
    except Context7Error:
        return 0

    if not content:
        return 0

    # RAG safety check
    safety = check_content_safety(content)
    if not safety.safe:
        logger.info("cache_warming_blocked_unsafe", library=library)
        return 0

    safe_content = safety.sanitised_content or content

    # Store in cache
    cache.put(
        CacheEntryModel(
            library=library.lower(),
            topic="overview",
            content=safe_content,
            context7_id=best.id,
            token_count=len(safe_content) // 4,
        )
    )

    logger.debug("cache_warming_warmed", library=library, context7_id=best.id)
    return 1
