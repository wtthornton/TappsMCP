"""Unit tests for documentation providers (DeepconProvider, DocforkProvider, etc.)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from tapps_mcp.knowledge.providers.base import DocumentationProvider
from tapps_mcp.knowledge.providers.deepcon_provider import DeepconProvider
from tapps_mcp.knowledge.providers.docfork_provider import DocforkProvider
from tapps_mcp.knowledge.providers.llms_txt_provider import LlmsTxtProvider


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProviderProtocolCompliance:
    def test_deepcon_satisfies_protocol(self) -> None:
        assert isinstance(DeepconProvider(api_key=SecretStr("x")), DocumentationProvider)

    def test_docfork_satisfies_protocol(self) -> None:
        assert isinstance(DocforkProvider(api_key=SecretStr("x")), DocumentationProvider)

    def test_llms_txt_satisfies_protocol(self) -> None:
        assert isinstance(LlmsTxtProvider(), DocumentationProvider)


# ---------------------------------------------------------------------------
# DeepconProvider
# ---------------------------------------------------------------------------


class TestDeepconProviderAvailability:
    def test_is_available_with_key(self) -> None:
        p = DeepconProvider(api_key=SecretStr("test"))
        assert p.is_available() is True

    def test_is_available_without_key(self) -> None:
        p = DeepconProvider(api_key=None)
        assert p.is_available() is False

    def test_name(self) -> None:
        assert DeepconProvider(api_key=None).name() == "deepcon"


class TestDeepconProviderResolve:
    @pytest.mark.asyncio
    async def test_resolve_returns_id_from_response(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"id": "fastapi"}]}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("tapps_mcp.knowledge.providers.deepcon_provider.httpx.AsyncClient", return_value=mock_client):
            p = DeepconProvider(api_key=SecretStr("key"))
            result = await p.resolve("fastapi")
        assert result == "fastapi"

    @pytest.mark.asyncio
    async def test_resolve_returns_none_without_key(self) -> None:
        p = DeepconProvider(api_key=None)
        result = await p.resolve("fastapi")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_returns_none_empty_results(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("tapps_mcp.knowledge.providers.deepcon_provider.httpx.AsyncClient", return_value=mock_client):
            p = DeepconProvider(api_key=SecretStr("key"))
            result = await p.resolve("fastapi")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_raises_on_429(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Rate limited", request=MagicMock(), response=mock_resp
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("tapps_mcp.knowledge.providers.deepcon_provider.httpx.AsyncClient", return_value=mock_client):
            p = DeepconProvider(api_key=SecretStr("key"))
            with pytest.raises(httpx.HTTPStatusError):
                await p.resolve("fastapi")


class TestDeepconProviderFetch:
    @pytest.mark.asyncio
    async def test_fetch_returns_content(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": "# FastAPI docs"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("tapps_mcp.knowledge.providers.deepcon_provider.httpx.AsyncClient", return_value=mock_client):
            p = DeepconProvider(api_key=SecretStr("key"))
            result = await p.fetch("fastapi", "overview")
        assert result == "# FastAPI docs"

    @pytest.mark.asyncio
    async def test_fetch_returns_none_without_key(self) -> None:
        p = DeepconProvider(api_key=None)
        result = await p.fetch("fastapi")
        assert result is None


# ---------------------------------------------------------------------------
# DocforkProvider
# ---------------------------------------------------------------------------


class TestDocforkProviderAvailability:
    def test_is_available_with_key(self) -> None:
        p = DocforkProvider(api_key=SecretStr("test"))
        assert p.is_available() is True

    def test_is_available_without_key(self) -> None:
        p = DocforkProvider(api_key=None)
        assert p.is_available() is False

    def test_name(self) -> None:
        assert DocforkProvider(api_key=None).name() == "docfork"


class TestDocforkProviderResolve:
    @pytest.mark.asyncio
    async def test_resolve_returns_library_as_id(self) -> None:
        p = DocforkProvider(api_key=SecretStr("key"))
        result = await p.resolve("fastapi")
        assert result == "fastapi"

    @pytest.mark.asyncio
    async def test_resolve_returns_none_without_key(self) -> None:
        p = DocforkProvider(api_key=None)
        result = await p.resolve("fastapi")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_normalizes_to_lower(self) -> None:
        p = DocforkProvider(api_key=SecretStr("key"))
        result = await p.resolve("  FastAPI  ")
        assert result == "fastapi"


class TestDocforkProviderFetch:
    @pytest.mark.asyncio
    async def test_fetch_returns_content(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": "# Docfork docs"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("tapps_mcp.knowledge.providers.docfork_provider.httpx.AsyncClient", return_value=mock_client):
            p = DocforkProvider(api_key=SecretStr("key"))
            result = await p.fetch("fastapi", "overview")
        assert result == "# Docfork docs"

    @pytest.mark.asyncio
    async def test_fetch_returns_none_without_key(self) -> None:
        p = DocforkProvider(api_key=None)
        result = await p.fetch("fastapi")
        assert result is None


# ---------------------------------------------------------------------------
# LlmsTxtProvider
# ---------------------------------------------------------------------------


class TestLlmsTxtProvider:
    def test_is_available_always_true(self) -> None:
        assert LlmsTxtProvider().is_available() is True

    def test_name(self) -> None:
        assert LlmsTxtProvider().name() == "llms_txt"
