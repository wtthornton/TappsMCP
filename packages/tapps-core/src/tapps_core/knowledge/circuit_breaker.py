"""Circuit breaker — fail-fast wrapper for external API calls.

Prevents cascading failures by tracking consecutive failures and
opening the circuit (fast-failing) when the failure threshold is reached.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Fast-fail mode
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerOpenError(Exception):
    """Raised when circuit is open and call is rejected."""


@dataclass
class CircuitBreakerConfig:
    """Configuration for the circuit breaker."""

    failure_threshold: int = 3
    success_threshold: int = 2
    timeout_seconds: float = 10.0
    reset_timeout_seconds: float = 30.0
    name: str = "context7"


@dataclass
class CircuitBreakerStats:
    """Runtime statistics for the circuit breaker."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    state: CircuitState = CircuitState.CLOSED
    last_failure_time: float | None = None
    last_state_change: float | None = None


class CircuitBreaker:
    """Async circuit breaker for external API calls.

    State transitions:
      CLOSED → OPEN: consecutive_failures >= failure_threshold
      OPEN → HALF_OPEN: reset_timeout_seconds elapsed
      HALF_OPEN → CLOSED: consecutive_successes >= success_threshold
      HALF_OPEN → OPEN: any failure
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self._stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._stats.state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Current statistics."""
        return self._stats

    def _check_state_transition(self) -> None:
        """Transition OPEN → HALF_OPEN if reset timeout has elapsed."""
        if self._stats.state != CircuitState.OPEN:
            return
        if self._stats.last_failure_time is None:
            return
        elapsed = time.time() - self._stats.last_failure_time
        if elapsed >= self.config.reset_timeout_seconds:
            self._stats.state = CircuitState.HALF_OPEN
            self._stats.consecutive_failures = 0
            self._stats.consecutive_successes = 0
            self._stats.last_state_change = time.time()
            logger.info(
                "circuit_breaker_half_open",
                name=self.config.name,
                elapsed_s=round(elapsed, 1),
            )

    def _record_success(self) -> None:
        self._stats.total_requests += 1
        self._stats.successful_requests += 1
        self._stats.consecutive_successes += 1
        self._stats.consecutive_failures = 0

        if (
            self._stats.state == CircuitState.HALF_OPEN
            and self._stats.consecutive_successes >= self.config.success_threshold
        ):
            self._stats.state = CircuitState.CLOSED
            self._stats.last_state_change = time.time()
            logger.info("circuit_breaker_closed", name=self.config.name)

    def _record_failure(self) -> None:
        self._stats.total_requests += 1
        self._stats.failed_requests += 1
        self._stats.consecutive_failures += 1
        self._stats.consecutive_successes = 0
        self._stats.last_failure_time = time.time()

        if self._stats.state == CircuitState.HALF_OPEN:
            self._stats.state = CircuitState.OPEN
            self._stats.last_state_change = time.time()
            logger.warning(
                "circuit_breaker_reopened",
                name=self.config.name,
            )
        elif self._stats.state == CircuitState.CLOSED:
            if self._stats.consecutive_failures >= self.config.failure_threshold:
                self._stats.state = CircuitState.OPEN
                self._stats.last_state_change = time.time()
                logger.warning(
                    "circuit_breaker_opened",
                    name=self.config.name,
                    failures=self._stats.consecutive_failures,
                )

    def force_open(self, reason: str = "") -> None:
        """Force the circuit open (e.g., on quota exceeded)."""
        self._stats.state = CircuitState.OPEN
        self._stats.last_failure_time = time.time()
        self._stats.last_state_change = time.time()
        logger.warning(
            "circuit_breaker_forced_open",
            name=self.config.name,
            reason=reason,
        )

    def reset(self) -> None:
        """Reset to initial closed state."""
        self._stats = CircuitBreakerStats()

    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,  # noqa: ANN401
        fallback: Any = None,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Execute *func* with circuit breaker protection.

        Args:
            func: Async callable to execute.
            *args: Positional arguments for *func*.
            fallback: Value to return when circuit is open or call fails.
            **kwargs: Keyword arguments for *func*.

        Returns:
            Result of *func* or *fallback*.

        Raises:
            CircuitBreakerOpenError: If circuit is open and no fallback provided.
        """
        async with self._lock:
            self._check_state_transition()

            if self._stats.state == CircuitState.OPEN:
                self._stats.rejected_requests += 1
                if fallback is not None:
                    return fallback
                raise CircuitBreakerOpenError(f"Circuit breaker [{self.config.name}] is OPEN")

        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout_seconds,
            )
            async with self._lock:
                self._record_success()
            return result
        except TimeoutError:
            async with self._lock:
                self._record_failure()
            if fallback is not None:
                return fallback
            raise
        except asyncio.CancelledError:
            raise
        except Exception:
            async with self._lock:
                self._record_failure()
            if fallback is not None:
                return fallback
            raise


# ---------------------------------------------------------------------------
# Singleton (thread-safe)
# ---------------------------------------------------------------------------

_context7_breaker: CircuitBreaker | None = None
_singleton_lock = threading.Lock()


def get_context7_circuit_breaker() -> CircuitBreaker:
    """Return the global Context7 circuit breaker singleton."""
    global _context7_breaker  # noqa: PLW0603
    if _context7_breaker is None:
        with _singleton_lock:
            if _context7_breaker is None:
                _context7_breaker = CircuitBreaker(CircuitBreakerConfig(name="context7"))
    return _context7_breaker
