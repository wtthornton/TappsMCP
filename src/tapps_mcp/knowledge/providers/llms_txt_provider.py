"""llms.txt provider - zero-dependency fallback using the llms.txt standard."""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger(__name__)

_HTTP_OK = 200

# Map popular Python libraries to their known llms.txt URLs
_KNOWN_LLMS_TXT: dict[str, str] = {
    "fastapi": "https://fastapi.tiangolo.com/llms.txt",
    "pydantic": "https://docs.pydantic.dev/llms.txt",
    "anthropic": "https://docs.anthropic.com/llms.txt",
    "langchain": "https://python.langchain.com/llms.txt",
    "mcp": "https://modelcontextprotocol.io/llms.txt",
    "django": "https://docs.djangoproject.com/llms.txt",
    "flask": "https://flask.palletsprojects.com/llms.txt",
    "sqlalchemy": "https://docs.sqlalchemy.org/llms.txt",
    "docker": "https://docs.docker.com/llms.txt",
    "cloudflare": "https://developers.cloudflare.com/llms.txt",
    "mintlify": "https://mintlify.com/docs/llms.txt",
    "stripe": "https://docs.stripe.com/llms.txt",
}


class LlmsTxtProvider:
    """Documentation provider using the llms.txt web standard."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def name(self) -> str:
        return "llms_txt"

    def is_available(self) -> bool:
        return True  # Always available (just needs internet)

    async def resolve(self, library: str) -> str | None:
        """Resolve library to an llms.txt URL."""
        lib_lower = library.strip().lower()
        if lib_lower in _KNOWN_LLMS_TXT:
            return _KNOWN_LLMS_TXT[lib_lower]
        # Try common URL patterns
        guesses = [
            f"https://docs.{lib_lower}.dev/llms.txt",
            f"https://{lib_lower}.readthedocs.io/en/latest/llms.txt",
        ]
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            for url in guesses:
                try:
                    resp = await client.head(url)
                    if resp.status_code == _HTTP_OK:
                        return url
                except httpx.HTTPError:
                    continue
        return None

    async def fetch(self, library_id: str, topic: str = "overview") -> str | None:
        """Fetch llms.txt content from the resolved URL."""
        # library_id is actually the URL for this provider
        url = library_id
        # Try llms-full.txt first (more content), fall back to llms.txt
        full_url = url.replace("llms.txt", "llms-full.txt")
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            for try_url in [full_url, url]:
                try:
                    resp = await client.get(try_url)
                    if resp.status_code == _HTTP_OK:
                        content = resp.text
                        if topic != "overview":
                            content = _extract_topic(content, topic)
                        return content if content else None
                except httpx.HTTPError:
                    continue
        return None


def _extract_topic(content: str, topic: str) -> str:
    """Extract a specific section from llms.txt Markdown by heading."""
    lines = content.splitlines()
    section_lines: list[str] = []
    in_section = False
    topic_lower = topic.lower()

    for line in lines:
        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
            if topic_lower in heading:
                in_section = True
                section_lines.append(line)
                continue
            elif in_section:
                break  # hit next heading, stop
        if in_section:
            section_lines.append(line)

    return "\n".join(section_lines) if section_lines else content
