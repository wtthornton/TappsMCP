"""Deepcon documentation provider — REST API for doc lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import structlog

from tapps_mcp.knowledge.rag_safety import check_content_safety

if TYPE_CHECKING:
    from pydantic import SecretStr

logger = structlog.get_logger(__name__)

DEEPCON_BASE_URL = "https://api.deepcon.ai"
DEEPCON_TIMEOUT = 30.0


class DeepconProvider:
    """Documentation provider backed by the Deepcon REST API."""

    def __init__(
        self,
        api_key: SecretStr | None = None,
        base_url: str = DEEPCON_BASE_URL,
        timeout: float = DEEPCON_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def name(self) -> str:
        return "deepcon"

    def is_available(self) -> bool:
        return self._api_key is not None

    async def resolve(self, library: str) -> str | None:
        """Resolve library name to a Deepcon ID via /v1/search."""
        if self._api_key is None:
            return None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}/v1/search",
                    json={"query": library, "type": "library"},
                    headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                )
                _raise_on_429(resp)
                resp.raise_for_status()
                data = resp.json()
                # Expected: {"results": [{"id": "fastapi", ...}], ...}
                results = data.get("results") or data.get("matches") or []
                if not results:
                    return None
                first = results[0]
                lib_id = first.get("id") or first.get("library_id") or first.get("name")
                return str(lib_id) if lib_id else None
            except httpx.HTTPStatusError as exc:
                _reraise_429(exc)
                raise
            except httpx.HTTPError as exc:
                logger.debug("deepcon_resolve_error", library=library, error=str(exc))
                return None

    async def fetch(self, library_id: str, topic: str = "overview") -> str | None:
        """Fetch documentation content via /v1/docs."""
        if self._api_key is None:
            return None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/v1/docs",
                    params={"library_id": library_id, "topic": topic},
                    headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                )
                _raise_on_429(resp)
                resp.raise_for_status()
                data = resp.json()
                content = data.get("content") or data.get("docs") or data.get("text") or ""
                if not content:
                    return None
                # RAG safety check on content
                safety = check_content_safety(content)
                if not safety.safe:
                    return None
                return safety.sanitised_content or content
            except httpx.HTTPStatusError as exc:
                _reraise_429(exc)
                raise
            except httpx.HTTPError as exc:
                logger.debug("deepcon_fetch_error", library_id=library_id, error=str(exc))
                return None


def _raise_on_429(resp: httpx.Response) -> None:
    """Raise HTTPStatusError on 429 so registry records failure and does not retry."""
    if resp.status_code == 429:
        resp.raise_for_status()


def _reraise_429(exc: httpx.HTTPStatusError) -> None:
    """Re-raise 429 so it propagates to registry (no retry)."""
    if exc.response.status_code == 429:
        raise exc
