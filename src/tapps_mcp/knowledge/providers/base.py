"""Base protocol and models for documentation providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class DocumentationProvider(Protocol):
    """Protocol that all documentation backends must implement."""

    def name(self) -> str:
        """Provider name (e.g., 'context7', 'llms_txt')."""
        ...

    def is_available(self) -> bool:
        """Whether this provider is configured and potentially reachable."""
        ...

    async def resolve(self, library: str) -> str | None:
        """Resolve a library name to a provider-specific ID.

        Returns None if library not found.
        """
        ...

    async def fetch(self, library_id: str, topic: str = "overview") -> str | None:
        """Fetch documentation content for a resolved library ID.

        Returns None if not found.
        """
        ...


@dataclass
class ProviderResult:
    """Result from a provider lookup attempt."""

    content: str | None = None
    provider_name: str = ""
    latency_ms: float = 0.0
    token_estimate: int = 0
    from_cache: bool = False
    error: str | None = None
    success: bool = False
