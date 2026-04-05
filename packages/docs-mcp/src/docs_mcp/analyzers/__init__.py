"""Code analysis engines for DocsMCP."""

from __future__ import annotations

from docs_mcp.analyzers.commit_parser import (
    ParsedCommit,
    classify_commit,
    parse_conventional_commit,
)
from docs_mcp.analyzers.dependency import ImportEdge, ImportGraph, ImportGraphBuilder
from docs_mcp.analyzers.git_history import CommitInfo, GitHistoryAnalyzer, TagInfo
from docs_mcp.analyzers.models import ModuleMap, ModuleNode
from docs_mcp.analyzers.module_map import ModuleMapAnalyzer
from docs_mcp.analyzers.version_detector import VersionBoundary, VersionDetector

__all__ = [
    "CommitInfo",
    "GitHistoryAnalyzer",
    "ImportEdge",
    "ImportGraph",
    "ImportGraphBuilder",
    "ModuleMap",
    "ModuleMapAnalyzer",
    "ModuleNode",
    "ParsedCommit",
    "TagInfo",
    "VersionBoundary",
    "VersionDetector",
    "classify_commit",
    "parse_conventional_commit",
]
