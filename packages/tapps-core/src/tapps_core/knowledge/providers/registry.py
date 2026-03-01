"""Provider registry with fallback chain and per-provider circuit breakers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from tapps_core.knowledge.providers.base import ProviderResult

if TYPE_CHECKING:
    from tapps_core.knowledge.providers.base import DocumentationProvider

logger = structlog.get_logger(__name__)

# Simple per-provider failure tracking (lightweight circuit breaker)
_FAILURE_THRESHOLD = 3
_RECOVERY_SECONDS = 60.0


@dataclass
class _ProviderState:
    failures: int = 0
    last_failure: float = 0.0
    total_calls: int = 0
    total_successes: int = 0

    @property
    def is_healthy(self) -> bool:
        if self.failures < _FAILURE_THRESHOLD:
            return True
        return (time.monotonic() - self.last_failure) > _RECOVERY_SECONDS

    def record_success(self) -> None:
        self.failures = 0
        self.total_calls += 1
        self.total_successes += 1

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure = time.monotonic()
        self.total_calls += 1


class ProviderRegistry:
    """Ordered registry of documentation providers with health tracking."""

    def __init__(self) -> None:
        self._providers: list[DocumentationProvider] = []
        self._states: dict[str, _ProviderState] = {}

    def register(self, provider: DocumentationProvider) -> None:
        """Add a provider to the registry (appended at end = lowest priority)."""
        self._providers.append(provider)
        self._states[provider.name()] = _ProviderState()

    @property
    def providers(self) -> list[DocumentationProvider]:
        return list(self._providers)

    def healthy_providers(self) -> list[DocumentationProvider]:
        """Return available providers that are healthy."""
        return [
            p
            for p in self._providers
            if p.is_available() and self._states.get(p.name(), _ProviderState()).is_healthy
        ]

    async def lookup(
        self,
        library: str,
        topic: str = "overview",
    ) -> ProviderResult:
        """Try providers in priority order until one succeeds."""
        for provider in self.healthy_providers():
            state = self._states.get(provider.name(), _ProviderState())
            start = time.monotonic()
            try:
                library_id = await provider.resolve(library)
                if library_id is None:
                    continue  # not an error, just not found

                content = await provider.fetch(library_id, topic)
                if content is None:
                    continue

                elapsed = (time.monotonic() - start) * 1000
                state.record_success()
                logger.info(
                    "provider_lookup_success",
                    provider=provider.name(),
                    library=library,
                    latency_ms=round(elapsed, 1),
                )
                return ProviderResult(
                    content=content,
                    provider_name=provider.name(),
                    latency_ms=round(elapsed, 1),
                    token_estimate=len(content) // 4,
                    success=True,
                )
            except Exception as exc:
                elapsed = (time.monotonic() - start) * 1000
                state.record_failure()
                logger.warning(
                    "provider_lookup_failed",
                    provider=provider.name(),
                    library=library,
                    error=str(exc),
                    latency_ms=round(elapsed, 1),
                )
                continue

        return ProviderResult(
            error=f"All providers failed for library '{library}'",
            success=False,
        )

    def get_stats(self) -> dict[str, dict[str, object]]:
        """Per-provider call stats."""
        return {
            name: {
                "total_calls": s.total_calls,
                "total_successes": s.total_successes,
                "current_failures": s.failures,
                "is_healthy": s.is_healthy,
            }
            for name, s in self._states.items()
        }
