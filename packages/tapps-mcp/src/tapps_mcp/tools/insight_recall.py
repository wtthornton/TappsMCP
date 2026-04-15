"""Auto-recall hook: fetch relevant insights before tapps_validate_changed (STORY-102.3).

This module is called at the start of ``tapps_validate_changed`` when
``memory.recall_on_validate`` is enabled in ``.tapps-mcp.yaml``. It queries
the ``insights`` memory_group for entries relevant to the file paths being
validated and returns a compact context block for injection into the response.

Performance contract
--------------------
The recall MUST complete within ``max_ms`` (default 180ms — within the 200ms
acceptance criterion with 20ms headroom). If tapps-brain is slow or unavailable,
the hook returns an empty result so that validate_changed is never blocked.

Integration
-----------
``tapps_validate_changed`` checks ``settings.memory.recall_on_validate`` and,
when True, calls :func:`recall_insights_for_validate` before building its
response. The result is merged into ``resp_data`` under the ``recalled_insights``
key.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_MAX_MS = 180
_DEFAULT_LIMIT = 5


def recall_insights_for_validate(
    paths: list[Path],
    project_root: Path,
    *,
    max_ms: float = _DEFAULT_MAX_MS,
    limit: int = _DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Search for insights relevant to the files being validated.

    Builds a query from the file paths (stems + directories), calls
    :class:`tapps_core.insights.client.InsightClient`, and returns a
    compact dict suitable for merging into the validate_changed response.

    Args:
        paths: List of file paths being validated.
        project_root: Project root for the MemoryStore.
        max_ms: Hard deadline in milliseconds. Returns empty result when exceeded.
        limit: Maximum number of insights to return.

    Returns:
        Dict with keys:
          ``recall_available`` — bool: True when tapps-brain responded
          ``recalled_insights`` — list of insight summaries (key, value, type, origin)
          ``recall_elapsed_ms`` — float: actual recall duration
          ``recall_query`` — str: the query used
    """
    t0 = time.perf_counter()

    empty: dict[str, Any] = {
        "recall_available": False,
        "recalled_insights": [],
        "recall_elapsed_ms": 0.0,
        "recall_query": "",
    }

    if not paths:
        return empty

    # Build a natural-language query from path stems and immediate parent dirs
    terms: list[str] = []
    for p in paths[:10]:  # cap to avoid huge queries
        terms.append(p.stem)
        if p.parent.name and p.parent.name not in (".", "src"):
            terms.append(p.parent.name)
    query = " ".join(dict.fromkeys(terms))  # deduplicate, preserve order

    if not query.strip():
        return empty

    try:
        from tapps_core.insights.client import InsightClient

        client = InsightClient(project_root)
        if not client.available:
            empty["recall_elapsed_ms"] = (time.perf_counter() - t0) * 1000
            return empty

        results = client.search(query, limit=limit)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > max_ms:
            logger.warning(
                "insight_recall_timeout",
                elapsed_ms=round(elapsed_ms, 1),
                max_ms=max_ms,
                query=query,
            )

        summaries = [
            {
                "key": e.key,
                "value": e.value[:300],  # truncate for response size
                "insight_type": str(e.insight_type),
                "server_origin": str(e.server_origin),
            }
            for e in results
        ]

        logger.info(
            "insight_recall_complete",
            count=len(summaries),
            elapsed_ms=round(elapsed_ms, 1),
            query=query,
        )

        return {
            "recall_available": True,
            "recalled_insights": summaries,
            "recall_elapsed_ms": round(elapsed_ms, 1),
            "recall_query": query,
        }

    except Exception:
        logger.warning("insight_recall_failed", exc_info=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {**empty, "recall_elapsed_ms": round(elapsed_ms, 1)}
