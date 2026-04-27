"""Tests for startup diagnostics module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from tapps_mcp.common.models import (
    CacheDiagnostic,
    Context7Diagnostic,
    KnowledgeBaseDiagnostic,
    StartupDiagnostics,
)
from tapps_mcp.diagnostics import (
    check_cache,
    check_context7,
    check_knowledge_base,
    collect_diagnostics,
)


class TestCheckContext7:
    def test_with_api_key_set(self) -> None:
        result = check_context7(SecretStr("sk-test-key-123"))
        assert result.api_key_set is True
        assert result.status == "available"

    def test_with_none_key(self) -> None:
        result = check_context7(None)
        assert result.api_key_set is False
        assert result.status == "no_key"

    def test_with_empty_key(self) -> None:
        result = check_context7(SecretStr(""))
        assert result.api_key_set is False
        assert result.status == "no_key"

    def test_returns_context7_diagnostic(self) -> None:
        result = check_context7(None)
        assert isinstance(result, Context7Diagnostic)


class TestCheckCache:
    def test_existing_writable_dir(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = check_cache(cache_dir)
        assert result.exists is True
        assert result.writable is True
        assert result.entry_count == 0
        assert result.total_size_bytes == 0
        assert result.stale_count == 0
        assert result.cache_dir == str(cache_dir)

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "nonexistent"
        result = check_cache(cache_dir)
        assert result.exists is False
        assert result.writable is False
        assert result.entry_count == 0
        assert result.total_size_bytes == 0
        assert result.stale_count == 0

    def test_dir_with_cached_entries(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        from tapps_mcp.knowledge.cache import KBCache
        from tapps_mcp.knowledge.models import CacheEntry

        cache = KBCache(cache_dir)
        cache.put(
            CacheEntry(
                library="fastapi",
                topic="overview",
                content="# FastAPI docs\nSome content here.",
                snippet_count=1,
                token_count=10,
            )
        )

        result = check_cache(cache_dir)
        assert result.exists is True
        assert result.writable is True
        assert result.entry_count == 1
        assert result.total_size_bytes > 0

    def test_returns_cache_diagnostic(self, tmp_path: Path) -> None:
        result = check_cache(tmp_path / "missing")
        assert isinstance(result, CacheDiagnostic)


class TestCheckKnowledgeBase:
    def test_expert_system_removed(self) -> None:
        """Expert system removed (EPIC-94) — knowledge base returns zero counts."""
        result = check_knowledge_base()
        assert result.expected_domains == 0
        assert result.total_domains == 0
        assert result.missing_domains == []
        assert result.total_files == 0

    def test_returns_empty_domains_list(self) -> None:
        result = check_knowledge_base()
        assert result.domains == []

    def test_returns_knowledge_base_diagnostic(self) -> None:
        result = check_knowledge_base()
        assert isinstance(result, KnowledgeBaseDiagnostic)


class TestCollectDiagnostics:
    def test_returns_all_sections(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = collect_diagnostics(api_key=None, cache_dir=cache_dir)
        assert isinstance(result, StartupDiagnostics)
        assert isinstance(result.context7, Context7Diagnostic)
        assert isinstance(result.cache, CacheDiagnostic)
        assert isinstance(result.knowledge_base, KnowledgeBaseDiagnostic)

    def test_model_dump_is_serializable(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = collect_diagnostics(api_key=None, cache_dir=cache_dir)
        dumped = result.model_dump()
        serialized = json.dumps(dumped)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert "context7" in parsed
        assert "cache" in parsed
        assert "knowledge_base" in parsed

    def test_with_api_key(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = collect_diagnostics(api_key=SecretStr("test-key"), cache_dir=cache_dir)
        assert result.context7.api_key_set is True
        assert result.context7.status == "available"


class TestServerInfoDiagnostics:
    def setup_method(self) -> None:
        from tapps_mcp.tools.checklist import CallTracker

        CallTracker.reset()

    @pytest.mark.asyncio
    async def test_includes_diagnostics_key(self) -> None:
        from tapps_mcp.server import tapps_server_info

        result = await tapps_server_info()
        assert "diagnostics" in result["data"]

    @pytest.mark.asyncio
    async def test_diagnostics_has_all_sections(self) -> None:
        from tapps_mcp.server import tapps_server_info

        result = await tapps_server_info()
        diag = result["data"]["diagnostics"]
        assert "context7" in diag
        assert "cache" in diag
        assert "knowledge_base" in diag

    @pytest.mark.asyncio
    async def test_diagnostics_context7_reports_status(self) -> None:
        from tapps_mcp.server import tapps_server_info

        result = await tapps_server_info()
        ctx7 = result["data"]["diagnostics"]["context7"]
        assert "api_key_set" in ctx7
        assert "status" in ctx7
        assert ctx7["status"] in ("available", "no_key")

    @pytest.mark.asyncio
    async def test_diagnostics_knowledge_base_reports_domains(self) -> None:
        """Expert system removed (EPIC-94) — knowledge base returns zero counts."""
        from tapps_mcp.server import tapps_server_info

        result = await tapps_server_info()
        kb = result["data"]["diagnostics"]["knowledge_base"]
        assert kb["expected_domains"] == 0
        assert kb["total_files"] == 0
        assert isinstance(kb["domains"], list)
