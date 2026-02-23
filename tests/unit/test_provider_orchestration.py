"""Unit tests for knowledge/providers/registry.py — ProviderRegistry orchestration."""

from __future__ import annotations

import time

import pytest

from tapps_mcp.knowledge.providers.base import DocumentationProvider
from tapps_mcp.knowledge.providers.registry import (
    _FAILURE_THRESHOLD,
    _RECOVERY_SECONDS,
    ProviderRegistry,
    _ProviderState,
)

# ---------------------------------------------------------------------------
# Mock provider for testing
# ---------------------------------------------------------------------------


class MockProvider:
    """Mock documentation provider for testing."""

    def __init__(
        self,
        name_val: str,
        available: bool = True,
        content: str | None = "docs",
    ) -> None:
        self._name = name_val
        self._available = available
        self._content = content
        self._should_fail = False

    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return self._available

    async def resolve(self, library: str) -> str | None:
        if self._should_fail:
            raise RuntimeError("provider error")
        if self._content is None:
            return None
        return f"{library}-id"

    async def fetch(self, library_id: str, topic: str = "overview") -> str | None:
        if self._should_fail:
            raise RuntimeError("provider error")
        return self._content


# ---------------------------------------------------------------------------
# Protocol check for MockProvider
# ---------------------------------------------------------------------------


class TestMockProviderProtocol:
    def test_mock_satisfies_protocol(self) -> None:
        assert isinstance(MockProvider("test"), DocumentationProvider)


# ---------------------------------------------------------------------------
# _ProviderState
# ---------------------------------------------------------------------------


class TestProviderState:
    def test_new_state_is_healthy(self) -> None:
        state = _ProviderState()
        assert state.is_healthy is True

    def test_state_unhealthy_after_threshold(self) -> None:
        state = _ProviderState()
        for _ in range(_FAILURE_THRESHOLD):
            state.record_failure()
        assert state.is_healthy is False

    def test_state_healthy_after_recovery(self) -> None:
        state = _ProviderState()
        for _ in range(_FAILURE_THRESHOLD):
            state.record_failure()
        # Simulate time passing beyond recovery window
        state.last_failure = time.monotonic() - _RECOVERY_SECONDS - 1
        assert state.is_healthy is True

    def test_record_success_resets_failures(self) -> None:
        state = _ProviderState()
        state.record_failure()
        state.record_failure()
        state.record_success()
        assert state.failures == 0
        assert state.total_calls == 3
        assert state.total_successes == 1


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    @pytest.mark.asyncio
    async def test_registry_empty(self) -> None:
        """Lookup on empty registry returns failure."""
        registry = ProviderRegistry()
        result = await registry.lookup("fastapi")
        assert result.success is False
        assert result.error is not None
        assert "All providers failed" in result.error

    @pytest.mark.asyncio
    async def test_registry_single_provider(self) -> None:
        """One provider, successful lookup."""
        registry = ProviderRegistry()
        registry.register(MockProvider("test", content="# FastAPI Docs"))

        result = await registry.lookup("fastapi")
        assert result.success is True
        assert result.content == "# FastAPI Docs"
        assert result.provider_name == "test"
        assert result.latency_ms >= 0
        assert result.token_estimate > 0

    @pytest.mark.asyncio
    async def test_registry_fallback(self) -> None:
        """First provider fails, second succeeds."""
        failing = MockProvider("failing")
        failing._should_fail = True
        succeeding = MockProvider("succeeding", content="# Backup Docs")

        registry = ProviderRegistry()
        registry.register(failing)
        registry.register(succeeding)

        result = await registry.lookup("fastapi")
        assert result.success is True
        assert result.content == "# Backup Docs"
        assert result.provider_name == "succeeding"

    @pytest.mark.asyncio
    async def test_registry_all_fail(self) -> None:
        """All providers fail, returns error."""
        p1 = MockProvider("p1")
        p1._should_fail = True
        p2 = MockProvider("p2")
        p2._should_fail = True

        registry = ProviderRegistry()
        registry.register(p1)
        registry.register(p2)

        result = await registry.lookup("fastapi")
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_registry_skips_unhealthy(self) -> None:
        """Provider with 3+ failures is skipped."""
        unhealthy = MockProvider("unhealthy", content="# Should not see")
        healthy = MockProvider("healthy", content="# Healthy docs")

        registry = ProviderRegistry()
        registry.register(unhealthy)
        registry.register(healthy)

        # Manually mark unhealthy
        state = registry._states["unhealthy"]
        for _ in range(_FAILURE_THRESHOLD):
            state.record_failure()

        result = await registry.lookup("fastapi")
        assert result.success is True
        assert result.provider_name == "healthy"

    @pytest.mark.asyncio
    async def test_registry_recovery(self) -> None:
        """Unhealthy provider recovers after recovery window."""
        provider = MockProvider("recovering", content="# Recovered")

        registry = ProviderRegistry()
        registry.register(provider)

        # Mark as unhealthy
        state = registry._states["recovering"]
        for _ in range(_FAILURE_THRESHOLD):
            state.record_failure()
        assert state.is_healthy is False

        # Simulate time passing
        state.last_failure = time.monotonic() - _RECOVERY_SECONDS - 1
        assert state.is_healthy is True

        result = await registry.lookup("fastapi")
        assert result.success is True
        assert result.provider_name == "recovering"

    @pytest.mark.asyncio
    async def test_registry_stats(self) -> None:
        """get_stats returns per-provider metrics."""
        registry = ProviderRegistry()
        registry.register(MockProvider("p1"))
        registry.register(MockProvider("p2"))

        await registry.lookup("fastapi")

        stats = registry.get_stats()
        assert "p1" in stats
        assert "p2" in stats
        assert stats["p1"]["total_calls"] == 1
        assert stats["p1"]["total_successes"] == 1
        assert stats["p1"]["is_healthy"] is True

    @pytest.mark.asyncio
    async def test_healthy_providers_filters_unavailable(self) -> None:
        """Unavailable providers are excluded from healthy list."""
        available = MockProvider("available", available=True)
        unavailable = MockProvider("unavailable", available=False)

        registry = ProviderRegistry()
        registry.register(available)
        registry.register(unavailable)

        healthy = registry.healthy_providers()
        names = [p.name() for p in healthy]
        assert "available" in names
        assert "unavailable" not in names

    @pytest.mark.asyncio
    async def test_resolve_returns_none_skips(self) -> None:
        """Provider whose resolve returns None is skipped to try the next one."""
        no_resolve = MockProvider("no-resolve", content=None)
        has_content = MockProvider("has-content", content="# Found it!")

        registry = ProviderRegistry()
        registry.register(no_resolve)
        registry.register(has_content)

        result = await registry.lookup("fastapi")
        assert result.success is True
        assert result.content == "# Found it!"
        assert result.provider_name == "has-content"

    @pytest.mark.asyncio
    async def test_providers_property(self) -> None:
        """Providers property returns a copy of the list."""
        registry = ProviderRegistry()
        p1 = MockProvider("p1")
        registry.register(p1)

        providers = registry.providers
        assert len(providers) == 1
        assert providers[0].name() == "p1"
        # Modifying the returned list should not affect the registry
        providers.clear()
        assert len(registry.providers) == 1
