"""Backward-compatible re-export."""

from __future__ import annotations

from tapps_core.knowledge.circuit_breaker import CircuitBreaker as CircuitBreaker
from tapps_core.knowledge.circuit_breaker import (
    CircuitBreakerConfig as CircuitBreakerConfig,
)
from tapps_core.knowledge.circuit_breaker import (
    CircuitBreakerOpenError as CircuitBreakerOpenError,
)
from tapps_core.knowledge.circuit_breaker import (
    CircuitBreakerStats as CircuitBreakerStats,
)
from tapps_core.knowledge.circuit_breaker import CircuitState as CircuitState
from tapps_core.knowledge.circuit_breaker import (
    get_context7_circuit_breaker as get_context7_circuit_breaker,
)
