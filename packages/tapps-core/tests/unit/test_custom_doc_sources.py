"""Unit tests for custom documentation sources (Epic 54.3).

Tests local file and URL doc sources in LookupEngine, priority over
providers, error handling, and DocSourceConfig model.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_core.config.settings import DocSourceConfig, TappsMCPSettings
from tapps_core.knowledge.lookup import LookupEngine
from tapps_core.knowledge.models import CacheEntry


def _make_cache(tmp_path: Path) -> MagicMock:
    """Create a mock KBCache that returns no hits."""
    cache = MagicMock()
    cache.get.return_value = None
    cache.list_entries.return_value = []
    cache.is_stale.return_value = False
    return cache


def _make_settings(
    tmp_path: Path,
    doc_sources: dict[str, DocSourceConfig] | None = None,
) -> TappsMCPSettings:
    """Create settings with custom doc sources."""
    return TappsMCPSettings(
        project_root=tmp_path,
        doc_sources=doc_sources or {},
    )


class TestLocalFileDocSource:
    """Custom doc source from a local file."""

    @pytest.mark.asyncio
    async def test_file_source_returns_content(self, tmp_path: Path) -> None:
        doc_file = tmp_path / "docs" / "my-lib.md"
        doc_file.parent.mkdir(parents=True)
        doc_file.write_text("# My Library\n\nUsage guide.", encoding="utf-8")

        settings = _make_settings(
            tmp_path,
            doc_sources={"my-lib": DocSourceConfig(file="docs/my-lib.md")},
        )
        cache = _make_cache(tmp_path)
        engine = LookupEngine(cache, settings=settings)

        result = await engine.lookup("my-lib", "overview")
        await engine.close()

        assert result.success
        assert "My Library" in (result.content or "")
        assert result.source == "custom_file"
        assert not result.cache_hit

    @pytest.mark.asyncio
    async def test_file_source_cached_after_first_lookup(self, tmp_path: Path) -> None:
        doc_file = tmp_path / "custom-docs.md"
        doc_file.write_text("Custom content", encoding="utf-8")

        settings = _make_settings(
            tmp_path,
            doc_sources={"mylib": DocSourceConfig(file="custom-docs.md")},
        )
        cache = _make_cache(tmp_path)
        engine = LookupEngine(cache, settings=settings)

        await engine.lookup("mylib", "overview")
        await engine.close()

        # Verify cache.put was called
        cache.put.assert_called_once()
        entry = cache.put.call_args[0][0]
        assert isinstance(entry, CacheEntry)
        assert entry.library == "mylib"

    @pytest.mark.asyncio
    async def test_missing_file_falls_through(self, tmp_path: Path) -> None:
        settings = _make_settings(
            tmp_path,
            doc_sources={"mylib": DocSourceConfig(file="nonexistent.md")},
        )
        cache = _make_cache(tmp_path)

        # Mock the provider chain to return no content and disable legacy path
        engine = LookupEngine(cache, settings=settings)
        engine._registry = MagicMock()
        engine._registry.healthy_providers.return_value = []
        engine._api_key = None  # disable legacy Context7 fallback

        result = await engine.lookup("mylib", "overview")
        await engine.close()

        # Should fall through to "no docs found"
        assert not result.success

    @pytest.mark.asyncio
    async def test_file_read_error_falls_through(self, tmp_path: Path) -> None:
        # Create a directory where a file is expected
        bad_path = tmp_path / "is-a-dir.md"
        bad_path.mkdir()

        settings = _make_settings(
            tmp_path,
            doc_sources={"mylib": DocSourceConfig(file="is-a-dir.md")},
        )
        cache = _make_cache(tmp_path)
        engine = LookupEngine(cache, settings=settings)
        engine._registry = MagicMock()
        engine._registry.healthy_providers.return_value = []
        engine._api_key = None  # disable legacy Context7 fallback

        result = await engine.lookup("mylib", "overview")
        await engine.close()

        # Should not crash, falls through
        assert not result.success


class TestUrlDocSource:
    """Custom doc source from a URL."""

    @pytest.mark.asyncio
    async def test_url_source_returns_content(self, tmp_path: Path) -> None:
        import httpx as real_httpx

        settings = _make_settings(
            tmp_path,
            doc_sources={"remote-lib": DocSourceConfig(url="https://example.com/docs.md")},
        )
        cache = _make_cache(tmp_path)
        engine = LookupEngine(cache, settings=settings)

        mock_response = MagicMock()
        mock_response.text = "# Remote Docs\n\nContent from URL."
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(real_httpx, "AsyncClient", return_value=mock_client):
            result = await engine.lookup("remote-lib", "overview")
        await engine.close()

        assert result.success
        assert "Remote Docs" in (result.content or "")
        assert result.source == "custom_url"

    @pytest.mark.asyncio
    async def test_url_error_falls_through(self, tmp_path: Path) -> None:
        import httpx as real_httpx

        settings = _make_settings(
            tmp_path,
            doc_sources={"remote-lib": DocSourceConfig(url="https://example.com/bad")},
        )
        cache = _make_cache(tmp_path)
        engine = LookupEngine(cache, settings=settings)
        engine._registry = MagicMock()
        engine._registry.healthy_providers.return_value = []
        engine._api_key = None  # disable legacy Context7 fallback

        with patch.object(real_httpx, "AsyncClient", side_effect=Exception("Connection failed")):
            result = await engine.lookup("remote-lib", "overview")
        await engine.close()

        assert not result.success


class TestCustomSourcePriority:
    """Custom sources take priority over Context7/LlmsTxt providers."""

    @pytest.mark.asyncio
    async def test_custom_file_beats_providers(self, tmp_path: Path) -> None:
        doc_file = tmp_path / "override.md"
        doc_file.write_text("Custom override content", encoding="utf-8")

        settings = _make_settings(
            tmp_path,
            doc_sources={"react": DocSourceConfig(file="override.md")},
        )
        cache = _make_cache(tmp_path)
        engine = LookupEngine(cache, settings=settings)

        # Even though providers would succeed, custom source should be used
        result = await engine.lookup("react", "overview")
        await engine.close()

        assert result.success
        assert result.source == "custom_file"
        assert "Custom override" in (result.content or "")

    @pytest.mark.asyncio
    async def test_no_custom_source_uses_providers(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path, doc_sources={})
        cache = _make_cache(tmp_path)
        engine = LookupEngine(cache, settings=settings)

        # No custom source, falls through to provider chain
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.content = "Provider content"
        mock_result.provider_name = "context7"
        engine._registry = MagicMock()
        engine._registry.healthy_providers.return_value = [MagicMock()]
        engine._registry.lookup = AsyncMock(return_value=mock_result)

        result = await engine.lookup("some-lib", "overview")
        await engine.close()

        assert result.success
        assert result.source == "context7"


class TestDocSourceConfigModel:
    """DocSourceConfig Pydantic model validation."""

    def test_default_format_is_markdown(self) -> None:
        config = DocSourceConfig()
        assert config.format == "markdown"

    def test_file_only(self) -> None:
        config = DocSourceConfig(file="docs/api.md")
        assert config.file == "docs/api.md"
        assert config.url is None

    def test_url_only(self) -> None:
        config = DocSourceConfig(url="https://example.com/docs")
        assert config.url == "https://example.com/docs"
        assert config.file is None

    def test_both_file_and_url(self) -> None:
        config = DocSourceConfig(file="local.md", url="https://example.com/docs")
        assert config.file == "local.md"
        assert config.url == "https://example.com/docs"


class TestTechStackBoostSetting:
    """Verify tech_stack_boost field in TappsMCPSettings."""

    def test_default_boost(self, tmp_path: Path) -> None:
        settings = TappsMCPSettings(project_root=tmp_path)
        assert settings.tech_stack_boost == 1.2

    def test_custom_boost(self, tmp_path: Path) -> None:
        settings = TappsMCPSettings(project_root=tmp_path, tech_stack_boost=1.5)
        assert settings.tech_stack_boost == 1.5

    def test_boost_minimum_is_one(self, tmp_path: Path) -> None:
        with pytest.raises(Exception):
            TappsMCPSettings(project_root=tmp_path, tech_stack_boost=0.5)

    def test_boost_maximum_is_three(self, tmp_path: Path) -> None:
        with pytest.raises(Exception):
            TappsMCPSettings(project_root=tmp_path, tech_stack_boost=5.0)
