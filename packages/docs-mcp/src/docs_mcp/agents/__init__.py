"""Agent matching infrastructure for DocsMCP.

Provides hybrid keyword + embedding matching for agent routing,
catalog management, and deduplication scoring.
"""

from __future__ import annotations

from docs_mcp.agents.catalog import AgentCatalog
from docs_mcp.agents.matcher import HybridMatcher, MatchResult
from docs_mcp.agents.models import AgentConfig, MemoryProfile

__all__ = [
    "AgentCatalog",
    "AgentConfig",
    "HybridMatcher",
    "MatchResult",
    "MemoryProfile",
]
