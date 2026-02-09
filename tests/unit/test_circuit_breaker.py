"""Unit tests for knowledge/circuit_breaker.py."""

from __future__ import annotations

import asyncio

import pytest

from tapps_mcp.knowledge.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    get_context7_circuit_breaker,
)


class TestCircuitBreakerStates:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_reset(self):
        cb = CircuitBreaker()
        cb.force_open("test")
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_force_open(self):
        cb = CircuitBreaker()
        cb.force_open("quota exceeded")
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerTransitions:
    @pytest.mark.asyncio
    async def test_closed_to_open_after_failures(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker(config)

        async def failing():
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(failing)

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_rejects_calls(self):
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(config)

        async def failing():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await cb.call(failing)

        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(failing)

    @pytest.mark.asyncio
    async def test_open_returns_fallback(self):
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(config)

        async def failing():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await cb.call(failing)

        result = await cb.call(failing, fallback="default")
        assert result == "default"

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=1, reset_timeout_seconds=0.01)
        cb = CircuitBreaker(config)

        async def failing():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await cb.call(failing)
        assert cb.state == CircuitState.OPEN

        await asyncio.sleep(0.02)

        async def succeeding():
            return "ok"

        result = await cb.call(succeeding)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_half_open_to_closed(self):
        config = CircuitBreakerConfig(
            failure_threshold=1, success_threshold=2, reset_timeout_seconds=0.01
        )
        cb = CircuitBreaker(config)

        async def failing():
            raise ValueError("fail")

        async def succeeding():
            return "ok"

        with pytest.raises(ValueError):
            await cb.call(failing)

        await asyncio.sleep(0.02)

        await cb.call(succeeding)
        await cb.call(succeeding)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self):
        config = CircuitBreakerConfig(failure_threshold=1, reset_timeout_seconds=0.01)
        cb = CircuitBreaker(config)

        async def failing():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await cb.call(failing)

        await asyncio.sleep(0.02)

        with pytest.raises(ValueError):
            await cb.call(failing)
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerStats:
    @pytest.mark.asyncio
    async def test_stats_track_calls(self):
        cb = CircuitBreaker()

        async def succeeding():
            return "ok"

        await cb.call(succeeding)
        await cb.call(succeeding)

        stats = cb.stats
        assert stats.total_requests == 2
        assert stats.successful_requests == 2
        assert stats.failed_requests == 0


class TestCircuitBreakerTimeout:
    @pytest.mark.asyncio
    async def test_timeout_counts_as_failure(self):
        config = CircuitBreakerConfig(timeout_seconds=0.01, failure_threshold=1)
        cb = CircuitBreaker(config)

        async def slow():
            await asyncio.sleep(1.0)
            return "ok"

        with pytest.raises(TimeoutError):
            await cb.call(slow)

        assert cb.stats.failed_requests == 1


class TestSingleton:
    def test_returns_same_instance(self):
        a = get_context7_circuit_breaker()
        b = get_context7_circuit_breaker()
        assert a is b
