"""Unit tests for knowledge/providers — base, Context7Provider, LlmsTxtProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.knowledge.providers.base import DocumentationProvider, ProviderResult
from tapps_mcp.knowledge.providers.context7_provider import Context7Provider
from tapps_mcp.knowledge.providers.llms_txt_provider import (
    LlmsTxtProvider,
    _extract_topic,
)

# ---------------------------------------------------------------------------
# ProviderResult defaults
# ---------------------------------------------------------------------------


class TestProviderResult:
    def test_provider_result_defaults(self) -> None:
        result = ProviderResult()
        assert result.content is None
        assert result.provider_name == ""
        assert result.latency_ms == 0.0
        assert result.token_estimate == 0
        assert result.from_cache is False
        assert result.error is None
        assert result.success is False


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_provider_protocol_compliance_context7(self) -> None:
        """Context7Provider satisfies DocumentationProvider protocol."""
        provider = Context7Provider(api_key=None)
        assert isinstance(provider, DocumentationProvider)

    def test_provider_protocol_compliance_llms_txt(self) -> None:
        """LlmsTxtProvider satisfies DocumentationProvider protocol."""
        provider = LlmsTxtProvider()
        assert isinstance(provider, DocumentationProvider)


# ---------------------------------------------------------------------------
# Context7Provider tests
# ---------------------------------------------------------------------------


class TestContext7Provider:
    def test_context7_name(self) -> None:
        provider = Context7Provider()
        assert provider.name() == "context7"

    def test_context7_not_available_no_key(self) -> None:
        provider = Context7Provider(api_key=None)
        assert provider.is_available() is False

    def test_context7_available_with_key(self) -> None:
        mock_key = MagicMock()
        provider = Context7Provider(api_key=mock_key)
        assert provider.is_available() is True

    @pytest.mark.asyncio
    async def test_context7_resolve_success(self) -> None:
        mock_client = AsyncMock()
        mock_match = MagicMock()
        mock_match.id = "/vercel/next.js"
        mock_client.resolve_library.return_value = [mock_match]

        provider = Context7Provider(client=mock_client)
        result = await provider.resolve("nextjs")

        assert result == "/vercel/next.js"
        mock_client.resolve_library.assert_awaited_once_with("nextjs")

    @pytest.mark.asyncio
    async def test_context7_resolve_not_found(self) -> None:
        mock_client = AsyncMock()
        mock_client.resolve_library.return_value = []

        provider = Context7Provider(client=mock_client)
        result = await provider.resolve("nonexistent-lib")

        assert result is None

    @pytest.mark.asyncio
    async def test_context7_fetch_success(self) -> None:
        mock_client = AsyncMock()
        mock_client.fetch_docs.return_value = "# FastAPI Docs\nContent here."

        provider = Context7Provider(client=mock_client)
        result = await provider.fetch("/tiangolo/fastapi", topic="routing")

        assert result == "# FastAPI Docs\nContent here."
        mock_client.fetch_docs.assert_awaited_once_with("/tiangolo/fastapi", topic="routing")

    @pytest.mark.asyncio
    async def test_context7_fetch_empty(self) -> None:
        mock_client = AsyncMock()
        mock_client.fetch_docs.return_value = ""

        provider = Context7Provider(client=mock_client)
        result = await provider.fetch("/some/lib")

        assert result is None

    @pytest.mark.asyncio
    async def test_context7_close(self) -> None:
        mock_client = AsyncMock()
        provider = Context7Provider(client=mock_client)
        await provider.close()
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_context7_close_no_client(self) -> None:
        provider = Context7Provider()
        # Should not raise when no client exists
        await provider.close()


# ---------------------------------------------------------------------------
# LlmsTxtProvider tests
# ---------------------------------------------------------------------------


class TestLlmsTxtProvider:
    def test_llms_txt_name(self) -> None:
        provider = LlmsTxtProvider()
        assert provider.name() == "llms_txt"

    def test_llms_txt_always_available(self) -> None:
        provider = LlmsTxtProvider()
        assert provider.is_available() is True

    @pytest.mark.asyncio
    async def test_llms_txt_resolve_known(self) -> None:
        provider = LlmsTxtProvider()
        result = await provider.resolve("fastapi")
        assert result == "https://fastapi.tiangolo.com/llms.txt"

    @pytest.mark.asyncio
    async def test_llms_txt_resolve_known_case_insensitive(self) -> None:
        provider = LlmsTxtProvider()
        result = await provider.resolve("  FastAPI  ")
        assert result == "https://fastapi.tiangolo.com/llms.txt"

    @pytest.mark.asyncio
    async def test_llms_txt_resolve_unknown(self) -> None:
        """Unknown library tries URL patterns; all fail -> None."""
        provider = LlmsTxtProvider(timeout=1.0)

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("tapps_mcp.knowledge.providers.llms_txt_provider.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.head.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client
            mock_httpx.HTTPError = Exception

            result = await provider.resolve("some-unknown-lib-xyz")
            assert result is None

    @pytest.mark.asyncio
    async def test_llms_txt_fetch_success(self) -> None:
        provider = LlmsTxtProvider()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Library Docs\nSome content here."

        with patch("tapps_mcp.knowledge.providers.llms_txt_provider.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client
            mock_httpx.HTTPError = Exception

            result = await provider.fetch("https://example.com/llms.txt")
            assert result == "# Library Docs\nSome content here."

    @pytest.mark.asyncio
    async def test_llms_txt_fetch_404(self) -> None:
        provider = LlmsTxtProvider()

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("tapps_mcp.knowledge.providers.llms_txt_provider.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client
            mock_httpx.HTTPError = Exception

            result = await provider.fetch("https://example.com/llms.txt")
            assert result is None

    @pytest.mark.asyncio
    async def test_llms_txt_fetch_with_topic(self) -> None:
        provider = LlmsTxtProvider()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Overview\nGeneral info.\n\n# Routing\nRouting details here."

        with patch("tapps_mcp.knowledge.providers.llms_txt_provider.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client
            mock_httpx.HTTPError = Exception

            result = await provider.fetch("https://example.com/llms.txt", topic="routing")
            assert result is not None
            assert "Routing details here." in result


# ---------------------------------------------------------------------------
# _extract_topic tests
# ---------------------------------------------------------------------------


class TestExtractTopic:
    def test_extract_topic_found(self) -> None:
        content = (
            "# Overview\nGeneral info.\n\n# Installation\nInstall steps.\n\n# Usage\nUsage details."
        )
        result = _extract_topic(content, "installation")
        assert "Install steps." in result
        assert "Usage details." not in result

    def test_extract_topic_not_found(self) -> None:
        content = "# Overview\nGeneral info.\n\n# Usage\nUsage details."
        result = _extract_topic(content, "nonexistent")
        # Should return full content when topic not found
        assert result == content

    def test_extract_topic_case_insensitive(self) -> None:
        content = "# Getting Started\nStart here.\n\n# API Reference\nAPIs."
        result = _extract_topic(content, "getting started")
        assert "Start here." in result

    def test_extract_topic_partial_match(self) -> None:
        content = "# Quick Start Guide\nQuick info.\n\n# API\nAPIs."
        result = _extract_topic(content, "quick start")
        assert "Quick info." in result
