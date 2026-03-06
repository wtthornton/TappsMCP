"""Context7 API client — async HTTP client for documentation lookup.

Endpoints (v2):
  - ``GET /api/v2/search?query={library}`` — resolve library name to ID
  - ``GET /api/v2/docs/{mode}/{library_id}?type=json&topic={topic}`` — fetch docs

Uses ``httpx`` with HTTP/2 and connection pooling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import structlog

from tapps_core.knowledge.models import LibraryMatch

if TYPE_CHECKING:
    from pydantic import SecretStr

logger = structlog.get_logger(__name__)

CONTEXT7_BASE_URL = "https://context7.com"
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_TOKENS = 5000


class Context7Error(Exception):
    """Raised when the Context7 API returns an error."""


class Context7Client:
    """Async HTTP client for the Context7 documentation API."""

    def __init__(
        self,
        api_key: SecretStr | None = None,
        *,
        base_url: str = CONTEXT7_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily create the httpx client."""
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {
                "User-Agent": "TappsMCP/0.8.4",
                "Accept": "application/json",
            }
            if self._api_key is not None:
                headers["Authorization"] = f"Bearer {self._api_key.get_secret_value()}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def resolve_library(self, query: str) -> list[LibraryMatch]:
        """Resolve a library name query to a list of library matches.

        Args:
            query: Library name or search term.

        Returns:
            List of ``LibraryMatch`` objects, best match first.

        Raises:
            Context7Error: On API failure.
        """
        client = await self._get_client()
        try:
            resp = await client.get("/api/v2/search", params={"query": query})
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "context7_resolve_error",
                query=query,
                status=exc.response.status_code,
            )
            raise Context7Error(f"Context7 API error: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.warning("context7_resolve_network_error", query=query, error=str(exc))
            raise Context7Error(f"Context7 network error: {exc}") from exc

        data = resp.json()
        results: list[LibraryMatch] = []

        # The API returns a list of library objects
        items = data if isinstance(data, list) else data.get("results", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append(
                LibraryMatch(
                    id=str(item.get("id", "")),
                    title=str(item.get("title", item.get("name", ""))),
                    description=str(item.get("description", "")),
                )
            )

        logger.debug("context7_resolved", query=query, match_count=len(results))
        return results

    async def fetch_docs(
        self,
        library_id: str,
        *,
        topic: str = "overview",
        mode: str = "code",
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """Fetch documentation for a resolved library.

        Args:
            library_id: Context7 library ID (e.g., ``"/vercel/next.js"``).
            topic: Documentation topic.
            mode: ``"code"`` for API references, ``"info"`` for conceptual guides.
            max_tokens: Maximum tokens in response.

        Returns:
            Documentation content as a markdown string.

        Raises:
            Context7Error: On API failure or empty response.
        """
        client = await self._get_client()
        # library_id may have leading slash; strip for URL construction
        lib_path = library_id.strip("/")
        url = f"/api/v2/docs/{mode}/{lib_path}"
        params: dict[str, str | int] = {
            "type": "json",
            "topic": topic,
            "tokens": max_tokens,
        }

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "context7_fetch_error",
                library_id=library_id,
                topic=topic,
                status=exc.response.status_code,
            )
            raise Context7Error(f"Context7 fetch error: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "context7_fetch_network_error",
                library_id=library_id,
                error=str(exc),
            )
            raise Context7Error(f"Context7 network error: {exc}") from exc

        data = resp.json()
        content = self._extract_content(data)

        if not content:
            raise Context7Error(f"No documentation found for {library_id} topic={topic}")

        logger.debug(
            "context7_fetched",
            library_id=library_id,
            topic=topic,
            content_length=len(content),
        )
        return content

    @staticmethod
    def _snippet_title(snippet: dict[str, object]) -> list[str]:
        """Extract title line from a snippet dict."""
        title = snippet.get("codeTitle", "")
        if isinstance(title, str) and title.strip():
            return [f"### {title.strip()}"]
        return []

    @staticmethod
    def _snippet_description(snippet: dict[str, object]) -> list[str]:
        """Extract description line from a snippet dict."""
        desc = snippet.get("codeDescription", "") or snippet.get("content", "")
        if isinstance(desc, str) and desc.strip():
            return [desc.strip()]
        return []

    @staticmethod
    def _snippet_code_parts(snippet: dict[str, object]) -> list[str]:
        """Extract code blocks from a snippet's codeList."""
        code_list = snippet.get("codeList", [])
        if not isinstance(code_list, list):
            return []
        parts: list[str] = []
        for code in code_list:
            if isinstance(code, str) and code.strip():
                parts.append(f"```\n{code.strip()}\n```")
            elif isinstance(code, dict):
                lang = code.get("language", "")
                code_text = code.get("code", "")
                if isinstance(code_text, str) and code_text.strip():
                    parts.append(f"```{lang}\n{code_text.strip()}\n```")
        return parts

    @staticmethod
    def _extract_content(data: object) -> str:
        """Extract markdown content from the Context7 JSON response."""
        if isinstance(data, str):
            return data

        if not isinstance(data, dict):
            return ""

        # Direct content field
        if data.get("content"):
            return str(data["content"])

        # Snippets array
        snippets = data.get("snippets", [])
        if not isinstance(snippets, list):
            return ""

        parts: list[str] = []
        for snippet in snippets:
            if not isinstance(snippet, dict):
                continue
            parts.extend(Context7Client._snippet_title(snippet))
            parts.extend(Context7Client._snippet_description(snippet))
            parts.extend(Context7Client._snippet_code_parts(snippet))

        return "\n\n".join(parts)
