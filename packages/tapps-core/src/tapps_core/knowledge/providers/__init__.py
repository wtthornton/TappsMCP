"""Documentation provider abstraction for multi-backend lookup."""

from __future__ import annotations

from tapps_core.knowledge.providers.base import DocumentationProvider, ProviderResult
from tapps_core.knowledge.providers.registry import ProviderRegistry

__all__ = ["DocumentationProvider", "ProviderRegistry", "ProviderResult"]
