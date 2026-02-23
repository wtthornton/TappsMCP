"""Docfork documentation provider — minimal REST/MCP-based provider.

Docfork is MCP-based at https://mcp.docfork.com/mcp with tools query_docs,
fetch_url. This provider attempts a configurable REST API; if Docfork exposes
one, it will succeed. Otherwise it fails gracefully and the registry falls
through to the next provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import structlog

from tapps_mcp.knowledge.rag_safety import check_content_safety

if TYPE_CHECKING:
    from pydantic import SecretStr

logger = structlog.get_logger(__name__)

DOCFORK_BASE_URL = "https://api.docfork.com"
DOCFORK_TIMEOUT = 30.0


class DocforkProvider:
    """Documentation provider for Docfork — REST API or stub fallback."""

    def __init__(
        self,
        api_key: SecretStr | None = None,
        base_url: str = DOCFORK_BASE_URL,
        timeout: float = DOCFORK_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def name(self) -> str:
        return "docfork"

    def is_available(self) -> bool:
        return self._api_key is not None

    async def resolve(self, library: str) -> str | None:
        """Resolve library to a Docfork ID. Returns library as-id (e.g. fastapi -> fastapi)."""
        if self._api_key is None:
            return None
        # Docfork accepts library names as-is when using REST
        return library.strip().lower()

    async def fetch(self, library_id: str, topic: str = "overview") -> str | None:
        """Fetch documentation via POST to configurable base_url."""
        if self._api_key is None:
            return None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                # Attempt POST with library/topic — Docfork REST shape if available
                resp = await client.post(
                    f"{self._base_url}/v1/query",
                    json={"library": library_id, "topic": topic},
                    headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                )
                if resp.status_code == 429:
                    resp.raise_for_status()
                resp.raise_for_status()
                data = resp.json()
                content = data.get("content") or data.get("docs") or data.get("text") or ""
                if not content:
                    return None
                safety = check_content_safety(content)
                if not safety.safe:
                    return None
                return safety.sanitised_content or content
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    raise
                logger.debug(
                    "docfork_fetch_error",
                    library_id=library_id,
                    status=exc.response.status_code,
                    error=str(exc),
                )
                return None
            except httpx.HTTPError as exc:
                logger.debug("docfork_fetch_error", library_id=library_id, error=str(exc))
                return None
