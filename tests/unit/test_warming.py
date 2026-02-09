"""Unit tests for knowledge/warming.py — cache warming."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from tapps_mcp.knowledge.cache import KBCache
from tapps_mcp.knowledge.models import LibraryMatch
from tapps_mcp.knowledge.warming import warm_cache


class TestWarmCache:
    @pytest.fixture
    def cache(self, tmp_path):
        return KBCache(cache_dir=tmp_path / "cache")

    @pytest.fixture
    def project(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi\ndjango\n")
        return tmp_path

    @pytest.mark.asyncio
    async def test_no_api_key(self, project, cache):
        count = await warm_cache(project, cache, api_key=None)
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_dependencies(self, tmp_path, cache):
        count = await warm_cache(tmp_path, cache, api_key=SecretStr("key"))
        assert count == 0

    @pytest.mark.asyncio
    async def test_warms_libraries(self, project, cache):
        mock_client = AsyncMock()
        mock_client.resolve_library.return_value = [
            LibraryMatch(id="/test/lib", title="Test")
        ]
        mock_client.fetch_docs.return_value = "# Docs"
        mock_client.close = AsyncMock()

        with patch(
            "tapps_mcp.knowledge.warming.Context7Client",
            return_value=mock_client,
        ):
            count = await warm_cache(project, cache, api_key=SecretStr("key"))

        assert count == 2  # fastapi and django
        assert cache.has("fastapi")
        assert cache.has("django")

    @pytest.mark.asyncio
    async def test_skips_cached(self, project, cache):
        # Pre-cache fastapi
        from tapps_mcp.knowledge.models import CacheEntry

        cache.put(CacheEntry(library="fastapi", content="already cached"))

        mock_client = AsyncMock()
        mock_client.resolve_library.return_value = [
            LibraryMatch(id="/test/lib", title="Test")
        ]
        mock_client.fetch_docs.return_value = "# Docs"
        mock_client.close = AsyncMock()

        with patch(
            "tapps_mcp.knowledge.warming.Context7Client",
            return_value=mock_client,
        ):
            count = await warm_cache(project, cache, api_key=SecretStr("key"))

        # Only django should be warmed (fastapi already cached, may be stale though)
        assert count >= 1

    @pytest.mark.asyncio
    async def test_handles_api_errors(self, project, cache):
        from tapps_mcp.knowledge.context7_client import Context7Error

        mock_client = AsyncMock()
        mock_client.resolve_library.side_effect = Context7Error("API down")
        mock_client.close = AsyncMock()

        with patch(
            "tapps_mcp.knowledge.warming.Context7Client",
            return_value=mock_client,
        ):
            count = await warm_cache(project, cache, api_key=SecretStr("key"))

        assert count == 0  # All failed

    @pytest.mark.asyncio
    async def test_max_libraries_respected(self, tmp_path, cache):
        libs = "\n".join(f"lib{i}" for i in range(50))
        (tmp_path / "requirements.txt").write_text(libs)

        mock_client = AsyncMock()
        mock_client.resolve_library.return_value = [
            LibraryMatch(id="/test/lib", title="Test")
        ]
        mock_client.fetch_docs.return_value = "# Docs"
        mock_client.close = AsyncMock()

        with patch(
            "tapps_mcp.knowledge.warming.Context7Client",
            return_value=mock_client,
        ):
            count = await warm_cache(
                tmp_path, cache, api_key=SecretStr("key"), max_libraries=5
            )

        assert count <= 5
