"""Agent matching infrastructure for DocsMCP.

Provides hybrid keyword + embedding matching for agent routing,
catalog management, deduplication scoring, and lifecycle governance.
"""

from __future__ import annotations

from docs_mcp.agents.catalog import AgentCatalog
from docs_mcp.agents.dedup import DedupMatch, DedupResult, check_dedup
from docs_mcp.agents.health import CatalogHealthReport, analyze_catalog_health
from docs_mcp.agents.lifecycle import (
    CleanupResult,
    DeprecationResult,
    cleanup_deprecated,
    deprecate_agent,
    restore_agent,
)
from docs_mcp.agents.matcher import HybridMatcher, MatchResult
from docs_mcp.agents.merge import MergeReport, MergeSuggestion, generate_merge_suggestion
from docs_mcp.agents.models import AgentConfig, MemoryProfile
from docs_mcp.agents.overlap_guard import OverlapContext, get_overlap_context

__all__ = [
    "AgentCatalog",
    "AgentConfig",
    "CatalogHealthReport",
    "CleanupResult",
    "DedupMatch",
    "DedupResult",
    "DeprecationResult",
    "HybridMatcher",
    "MatchResult",
    "MemoryProfile",
    "MergeReport",
    "MergeSuggestion",
    "OverlapContext",
    "analyze_catalog_health",
    "check_dedup",
    "cleanup_deprecated",
    "deprecate_agent",
    "generate_merge_suggestion",
    "get_overlap_context",
    "restore_agent",
]
