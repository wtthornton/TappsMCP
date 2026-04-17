"""Unit tests for documentation providers (LlmsTxtProvider, etc.)."""

from __future__ import annotations

import pytest

from tapps_core.knowledge.providers.base import DocumentationProvider
from tapps_core.knowledge.providers.llms_txt_provider import (
    _KNOWN_LLMS_TXT,
    LlmsTxtProvider,
)

# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProviderProtocolCompliance:
    def test_llms_txt_satisfies_protocol(self) -> None:
        assert isinstance(LlmsTxtProvider(), DocumentationProvider)


# ---------------------------------------------------------------------------
# LlmsTxtProvider
# ---------------------------------------------------------------------------


class TestLlmsTxtProvider:
    def test_is_available_always_true(self) -> None:
        assert LlmsTxtProvider().is_available() is True

    def test_name(self) -> None:
        assert LlmsTxtProvider().name() == "llms_txt"


class TestKnownLlmsTxtAliases:
    """Verify new library aliases are in the _KNOWN_LLMS_TXT dict."""

    @pytest.mark.parametrize(
        "library,expected_url_fragment",
        [
            ("pytest", "docs.pytest.org"),
            ("github-actions", "docs.github.com"),
            ("httpx", "python-httpx.org"),
            ("uvicorn", "uvicorn.org"),
            ("ruff", "docs.astral.sh/ruff"),
            ("uv", "docs.astral.sh/uv"),
            # Existing entries still present
            ("docker", "docs.docker.com"),
            ("fastapi", "fastapi.tiangolo.com"),
        ],
    )
    def test_library_in_known_llms_txt(self, library: str, expected_url_fragment: str) -> None:
        assert library in _KNOWN_LLMS_TXT
        assert expected_url_fragment in _KNOWN_LLMS_TXT[library]

    @pytest.mark.asyncio
    async def test_resolve_returns_known_url(self) -> None:
        provider = LlmsTxtProvider()
        url = await provider.resolve("pytest")
        assert url is not None
        assert "docs.pytest.org" in url

    @pytest.mark.asyncio
    async def test_resolve_case_insensitive(self) -> None:
        provider = LlmsTxtProvider()
        url = await provider.resolve("  PyTest  ")
        assert url is not None
        assert "docs.pytest.org" in url
