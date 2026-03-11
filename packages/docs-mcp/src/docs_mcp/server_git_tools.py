"""DocsMCP git analysis tools -- docs_git_summary.

This module registers on the shared ``mcp`` FastMCP instance from
``server.py`` and provides git history analysis for documentation generation.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any

from docs_mcp.server import _ANNOTATIONS_READ_ONLY, _record_call, mcp
from docs_mcp.server_helpers import _get_settings, error_response, success_response


async def docs_git_summary(
    limit: int = 50,
    since: str = "",
    path: str = "",
    include_versions: bool = True,
    project_root: str = "",
) -> dict[str, Any]:
    """Analyze git history for documentation generation.

    Returns recent commits (parsed via conventional commit format), version
    boundaries from tags, commit type distribution, and active contributors.

    Args:
        limit: Maximum number of recent commits to return (default 50).
        since: ISO date string -- only include commits after this date.
        path: If given, only commits touching this file/directory.
        include_versions: Whether to detect version boundaries from tags.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_git_summary")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_git_summary",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.analyzers.commit_parser import classify_commit
    from docs_mcp.analyzers.git_history import GitHistoryAnalyzer
    from docs_mcp.analyzers.version_detector import VersionDetector

    analyzer = GitHistoryAnalyzer(root)

    # Fetch commits
    commits = analyzer.get_commits(
        limit=limit,
        since=since if since else None,
        path=path if path else None,
    )

    # Parse each commit
    parsed_commits: list[dict[str, Any]] = []
    type_counter: Counter[str] = Counter()
    author_counter: Counter[str] = Counter()

    for commit in commits:
        parsed = classify_commit(commit.message)
        type_counter[parsed.type] += 1
        author_counter[commit.author] += 1
        parsed_commits.append({
            "hash": commit.short_hash,
            "author": commit.author,
            "date": commit.date,
            "message": commit.message,
            "type": parsed.type,
            "scope": parsed.scope,
            "breaking": parsed.breaking,
            "is_conventional": parsed.is_conventional,
            "files_changed": commit.files_changed,
            "insertions": commit.insertions,
            "deletions": commit.deletions,
        })

    # Version boundaries
    versions_data: list[dict[str, Any]] = []
    if include_versions:
        detector = VersionDetector()
        boundaries = detector.detect_versions(root, include_commits=False)
        for boundary in boundaries:
            versions_data.append({
                "version": boundary.version,
                "tag": boundary.tag,
                "date": boundary.date,
                "commit_count": boundary.commit_count,
            })

    # Active contributors (sorted by commit count descending)
    contributors: list[dict[str, Any]] = [
        {"name": name, "commits": count}
        for name, count in author_counter.most_common()
    ]

    # Type distribution (sorted by count descending)
    type_distribution: dict[str, int] = dict(type_counter.most_common())

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "project_root": str(root),
        "total_commits": len(parsed_commits),
        "commits": parsed_commits,
        "type_distribution": type_distribution,
        "contributors": contributors,
        "versions": versions_data,
    }

    return success_response("docs_git_summary", elapsed_ms, data)


# ---------------------------------------------------------------------------
# Registration (Epic 79.2: conditional)
# ---------------------------------------------------------------------------


def register(mcp_instance: "FastMCP", allowed_tools: frozenset[str]) -> None:
    """Register git tools on the shared mcp instance (Epic 79.2: conditional)."""
    if "docs_git_summary" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_git_summary)
