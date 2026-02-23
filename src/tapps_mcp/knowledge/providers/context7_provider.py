"""Context7 documentation provider - wraps the existing Context7Client."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pydantic import SecretStr

    from tapps_mcp.knowledge.context7_client import Context7Client

logger = structlog.get_logger(__name__)


class Context7Provider:
    """Documentation provider backed by the Context7 API."""

    def __init__(
        self,
        api_key: SecretStr | None = None,
        client: Context7Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._resolved_ids: dict[str, str] = {}  # cache: library -> id

    def name(self) -> str:
        return "context7"

    def is_available(self) -> bool:
        return self._api_key is not None

    async def resolve(self, library: str) -> str | None:
        client = self._get_client()
        matches = await client.resolve_library(library)
        if not matches:
            return None
        best = matches[0]
        self._resolved_ids[library] = best.id
        return best.id

    async def fetch(self, library_id: str, topic: str = "overview") -> str | None:
        client = self._get_client()
        content = await client.fetch_docs(library_id, topic=topic)
        return content if content else None

    def _get_client(self) -> Context7Client:
        if self._client is None:
            from tapps_mcp.knowledge.context7_client import (
                Context7Client as _Context7Client,
            )

            self._client = _Context7Client(api_key=self._api_key)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
