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
        # Key-presence alone no longer claims "available" — that requires a
        # live probe. Presence yields "unknown" until probe_context7 runs.
        result = check_context7(SecretStr("sk-test-key-123"))
        assert result.api_key_set is True
        assert result.status == "unknown"

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

    def test_with_api_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # collect_diagnostics now runs the throttled live probe; stub it so the
        # unit test stays offline and deterministic.
        import tapps_mcp.diagnostics as diag_mod

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        def _fake_probe(root: Path, api_key: object, **_: object) -> Context7Diagnostic:
            return Context7Diagnostic(
                api_key_set=True, status="available", reachable=True, http_status=200
            )

        monkeypatch.setattr(diag_mod, "probe_context7", _fake_probe)
        result = collect_diagnostics(api_key=SecretStr("test-key"), cache_dir=cache_dir)
        assert result.context7.api_key_set is True
        assert result.context7.status == "available"

    def test_no_key_skips_network(self, tmp_path: Path) -> None:
        # No key → no_key verdict with no network call (and no marker written).
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = collect_diagnostics(api_key=None, cache_dir=cache_dir)
        assert result.context7.status == "no_key"


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
        assert ctx7["status"] in (
            "available",
            "no_key",
            "unauthorized",
            "unreachable",
            "unknown",
        )

    @pytest.mark.asyncio
    async def test_diagnostics_knowledge_base_reports_domains(self) -> None:
        """Expert system removed (EPIC-94) — knowledge base returns zero counts."""
        from tapps_mcp.server import tapps_server_info

        result = await tapps_server_info()
        kb = result["data"]["diagnostics"]["knowledge_base"]
        assert kb["expected_domains"] == 0
        assert kb["total_files"] == 0
        assert isinstance(kb["domains"], list)


class _FakeClient:
    """Stand-in for Context7Client driving probe outcomes without network."""

    def __init__(self, *, result: object = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.closed = False

    async def resolve_library(self, _query: str) -> object:
        if self._exc is not None:
            raise self._exc
        return self._result

    async def close(self) -> None:
        self.closed = True


def _fresh_breaker() -> object:
    from tapps_core.knowledge.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

    return CircuitBreaker(CircuitBreakerConfig(name="test-context7"))


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    import tapps_core.knowledge.context7_client as c7

    monkeypatch.setattr(c7, "Context7Client", lambda **_: client)


class TestProbeContext7Async:
    @pytest.mark.asyncio
    async def test_no_key_returns_no_key_without_network(self) -> None:
        from tapps_mcp.diagnostics import probe_context7_async

        diag = await probe_context7_async(None)
        assert diag.status == "no_key"
        assert diag.reachable is None

    @pytest.mark.asyncio
    async def test_reachable_returns_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from tapps_mcp.diagnostics import probe_context7_async

        client = _FakeClient(result=[object()])
        _patch_client(monkeypatch, client)
        diag = await probe_context7_async(SecretStr("k"), breaker=_fresh_breaker())
        assert diag.status == "available"
        assert diag.reachable is True
        assert diag.http_status == 200
        assert client.closed is True

    @pytest.mark.asyncio
    async def test_401_returns_unauthorized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from tapps_core.knowledge.context7_client import Context7Error
        from tapps_mcp.diagnostics import probe_context7_async

        client = _FakeClient(exc=Context7Error("Context7 API error: 401"))
        _patch_client(monkeypatch, client)
        diag = await probe_context7_async(SecretStr("bad"), breaker=_fresh_breaker())
        assert diag.status == "unauthorized"
        assert diag.http_status == 401
        assert diag.reachable is True

    @pytest.mark.asyncio
    async def test_network_error_returns_unreachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        from tapps_mcp.diagnostics import probe_context7_async

        client = _FakeClient(exc=httpx.ConnectError("boom"))
        _patch_client(monkeypatch, client)
        diag = await probe_context7_async(SecretStr("k"), breaker=_fresh_breaker())
        assert diag.status == "unreachable"
        assert diag.reachable is False


class TestProbeContext7Throttle:
    def test_fresh_marker_short_circuits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tapps_mcp.diagnostics as diag_mod

        # Seed a fresh marker, then assert the live coroutine is never called.
        seeded = Context7Diagnostic(api_key_set=True, status="available", reachable=True)
        diag_mod._write_probe_marker(tmp_path, seeded)

        def _boom(*_a: object, **_k: object) -> object:
            raise AssertionError("probe_context7_async must not run on a fresh marker")

        monkeypatch.setattr(diag_mod, "probe_context7_async", _boom)
        result = diag_mod.probe_context7(tmp_path, SecretStr("k"))
        assert result.status == "available"

    def test_force_bypasses_marker(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import tapps_mcp.diagnostics as diag_mod

        diag_mod._write_probe_marker(
            tmp_path,
            Context7Diagnostic(api_key_set=True, status="available", reachable=True),
        )
        client = _FakeClient(exc=__import__("httpx").ConnectError("down"))
        _patch_client(monkeypatch, client)
        # force=True must ignore the cached "available" and re-probe live.
        result = diag_mod.probe_context7(tmp_path, SecretStr("k"), force=True)
        assert result.status == "unreachable"

    def test_marker_roundtrip_is_serializable(self, tmp_path: Path) -> None:
        import tapps_mcp.diagnostics as diag_mod

        diag = Context7Diagnostic(
            api_key_set=True, status="unreachable", reachable=False, detail="x"
        )
        diag_mod._write_probe_marker(tmp_path, diag)
        loaded = diag_mod._read_probe_marker(tmp_path)
        assert loaded is not None
        assert loaded.status == "unreachable"
        assert loaded.detail == "x"

    def test_force_probe_from_within_running_event_loop_does_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: tapps_doctor(quick=False) crashed with
        "asyncio.run() cannot be called from a running event loop" because
        probe_context7 called asyncio.run() unconditionally from a sync call
        site that MCP tool dispatch had already entered from a running loop.
        """
        import asyncio

        import tapps_mcp.diagnostics as diag_mod

        client = _FakeClient(result=[object()])
        _patch_client(monkeypatch, client)

        async def _probe_on_loop_thread() -> Context7Diagnostic:
            # Calling the sync probe_context7 directly here reproduces the
            # original crash context: the current thread already has a
            # running event loop when probe_context7's asyncio.run() fires.
            return diag_mod.probe_context7(tmp_path, SecretStr("k"), force=True)

        result = asyncio.run(_probe_on_loop_thread())
        assert result.status == "available"
