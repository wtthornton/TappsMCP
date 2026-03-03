"""DocsMCP validation tools -- docs_check_drift, docs_check_completeness,
docs_check_links, docs_check_freshness.

These tools register on the shared ``mcp`` FastMCP instance from
``server.py`` and provide documentation validation capabilities.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from docs_mcp.server import _ANNOTATIONS_READ_ONLY, _record_call, mcp
from docs_mcp.server_helpers import _get_settings, error_response, success_response


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def docs_check_drift(
    since: str = "",
    doc_dirs: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Detect documentation drift -- code changes not reflected in docs.

    Compares public API names in Python source files against documentation
    content. Reports undocumented additions and stale references.

    Args:
        since: Reserved for future use (git ref or date filter).
        doc_dirs: Comma-separated list of documentation directories to search.
            When empty, scans the entire project for doc files.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_check_drift")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_drift", "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.validators.drift import DriftDetector

    detector = DriftDetector()
    dirs_list: list[str] | None = None
    if doc_dirs.strip():
        dirs_list = [d.strip() for d in doc_dirs.split(",") if d.strip()]

    report = detector.check(
        root,
        since=since if since.strip() else None,
        doc_dirs=dirs_list,
    )

    data: dict[str, Any] = report.model_dump()

    # Optional TappsMCP enrichment
    try:
        from docs_mcp.integrations.tapps import (
            _SCORE_THRESHOLD_MEDIUM,
            TappsIntegration,
        )

        integration = TappsIntegration(root)
        if integration.is_available:
            enrichment = integration.load_enrichment()
            if enrichment.quality_scores:
                data["tapps_enrichment"] = {
                    "available": True,
                    "scored_files": len(enrichment.quality_scores),
                    "low_quality_files": [
                        s.file_path
                        for s in enrichment.quality_scores
                        if s.overall_score < _SCORE_THRESHOLD_MEDIUM
                    ],
                }
    except Exception:  # noqa: S110 — TappsMCP enrichment is optional
        pass

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_check_drift", elapsed_ms, data)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def docs_check_completeness(
    project_root: str = "",
) -> dict[str, Any]:
    """Check documentation completeness across multiple categories.

    Evaluates essential docs (README, LICENSE), development docs
    (CONTRIBUTING, CHANGELOG), API documentation coverage, inline
    docstrings, and project docs directory presence.

    Args:
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_check_completeness")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_completeness", "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.validators.completeness import CompletenessChecker

    checker = CompletenessChecker()
    report = checker.check(root)

    data: dict[str, Any] = report.model_dump()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_check_completeness", elapsed_ms, data)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def docs_check_links(
    files: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Validate internal links in documentation files.

    Scans markdown files for internal links and verifies that referenced
    files and anchors exist. Does NOT check external HTTP links.

    Args:
        files: Comma-separated list of specific files to check (relative or
            absolute paths). When empty, scans all documentation files.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_check_links")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_links", "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    files_list: list[str] | None = None
    if files.strip():
        files_list = [f.strip() for f in files.split(",") if f.strip()]

    from docs_mcp.validators.link_checker import LinkChecker

    checker = LinkChecker()
    report = checker.check(root, files=files_list)

    data: dict[str, Any] = report.model_dump()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_check_links", elapsed_ms, data)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def docs_check_freshness(
    project_root: str = "",
) -> dict[str, Any]:
    """Score documentation freshness based on file modification times.

    Classifies each doc file as fresh (<30d), aging (30-90d),
    stale (90-365d), or ancient (>365d) and calculates an overall
    freshness score (0-100).

    Args:
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_check_freshness")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_freshness", "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.validators.freshness import FreshnessChecker

    checker = FreshnessChecker()
    report = checker.check(root)

    data: dict[str, Any] = report.model_dump()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_check_freshness", elapsed_ms, data)
