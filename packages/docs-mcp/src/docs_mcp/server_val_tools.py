"""DocsMCP validation tools -- docs_check_drift, docs_check_completeness,
docs_check_links, docs_check_freshness.

These tools register on the shared ``mcp`` FastMCP instance from
``server.py`` and provide documentation validation capabilities.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from docs_mcp.validators.style import StyleReport

_logger = structlog.get_logger(__name__)

from docs_mcp.server import _ANNOTATIONS_READ_ONLY, _record_call
from docs_mcp.server_helpers import (
    _get_settings,
    build_custom_terms_for_style,
    error_response,
    success_response,
)


async def docs_check_drift(
    since: str = "",
    doc_dirs: str = "",
    source_files: str = "",
    search_names: str = "",
    max_items: int = 0,
    project_root: str = "",
    docstring_coverage_counts: bool = True,
    ignore_patterns: str = "",
) -> dict[str, Any]:
    """Detect documentation drift -- code changes not reflected in docs.

    Compares public API names in Python source files against documentation
    content. Reports undocumented additions and stale references.

    The returned ``drift_score`` is on a 0-100 scale (higher = more drift;
    0 = no drift, 100 = severe drift), matching the ``DriftReport`` model.

    Args:
        since: Reserved for future use (git ref or date filter).
        doc_dirs: Comma-separated list of documentation directories to search.
            When empty, scans the entire project for doc files.
        source_files: Comma-separated list of source file paths to limit drift
            analysis to. Paths are relative to project root (e.g.
            ``"server.py,upgrade.py"``). When empty, scans all Python files.
        search_names: Comma-separated list of public names (functions, classes)
            to search for in drift items. Only items containing at least one
            matching name are returned.
        max_items: Maximum number of drift items to return. 0 means unlimited
            (default). Summary counts always reflect the unfiltered totals.
        project_root: Override project root path (default: configured root).
        docstring_coverage_counts: When True (default), a symbol's own module
            or class/function docstring can mark it as "covered" even if the
            external prose doesn't mention it. Set False for a strict pass.
        ignore_patterns: Comma-separated fnmatch globs on fully-qualified
            symbol names (e.g. ``"mypkg.cli.*"``) that should never be flagged
            as drifted. The literal string ``"defaults"`` opts into a built-in
            list covering private/test names.
    """
    _record_call("docs_check_drift")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_drift",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.validators.drift import DriftDetector

    detector = DriftDetector()
    dirs_list: list[str] | None = None
    if doc_dirs.strip():
        dirs_list = [d.strip() for d in doc_dirs.split(",") if d.strip()]

    # Parse source_files filter
    source_filter: list[str] | None = None
    if source_files.strip():
        source_filter = [f.strip() for f in source_files.split(",") if f.strip()]

    # Parse ignore_patterns: "defaults" sentinel, empty, or comma-separated globs.
    ignore_arg: list[str] | str | None
    stripped_ignore = ignore_patterns.strip()
    if not stripped_ignore:
        ignore_arg = None
    elif stripped_ignore == "defaults":
        ignore_arg = "defaults"
    else:
        ignore_arg = [p.strip() for p in stripped_ignore.split(",") if p.strip()]

    report = detector.check(
        root,
        since=since if since.strip() else None,
        doc_dirs=dirs_list,
        docstring_coverage_counts=docstring_coverage_counts,
        ignore_patterns=ignore_arg,
    )

    # Apply post-filters on the report items
    items = report.items
    total_unfiltered = len(items)

    if source_filter:
        normalised = {sf.replace("\\", "/").lower() for sf in source_filter}
        items = [it for it in items if any(it.file_path.lower().endswith(sf) for sf in normalised)]

    if search_names.strip():
        names_lower = {n.strip().lower() for n in search_names.split(",") if n.strip()}
        items = [
            it for it in items
            if any(nm in sym.lower() for nm in names_lower for sym in it.symbols)
        ]

    total_filtered = len(items)

    if max_items > 0:
        items = items[:max_items]

    data: dict[str, Any] = {
        "total_items": total_filtered,
        "total_unfiltered": total_unfiltered,
        "showing": len(items),
        "items": [it.model_dump() for it in items],
        "drift_score": report.drift_score,
        "drift_fraction": getattr(report, "drift_fraction", None),
        "checked_files": report.checked_files,
    }

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
    except Exception as exc:
        _logger.debug("tapps_enrichment_failed", error=str(exc))

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_check_drift", elapsed_ms, data)


async def docs_check_completeness(
    project_root: str = "",
    exclude: str = "",
    respect_gitignore: bool = True,
) -> dict[str, Any]:
    """Check documentation completeness across multiple categories.

    Evaluates essential docs (README, LICENSE), development docs
    (CONTRIBUTING, CHANGELOG), API documentation coverage, inline
    docstrings, and project docs directory presence.

    Args:
        project_root: Override project root path (default: configured root).
        exclude: Comma-separated glob patterns to skip during scanning, on top
            of the built-in baseline (``.git``, ``__pycache__``, ``node_modules``,
            ``.venv*``, ``dist``, ``build``, etc.). Example:
            ``"vendored/**/*,third_party/**/*"``.
        respect_gitignore: When True (default), honor patterns in the project's
            root ``.gitignore``. Pass False to restore pre-2.10 behavior.
    """
    _record_call("docs_check_completeness")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_completeness",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.validators.completeness import CompletenessChecker

    exclude_list: list[str] | None = None
    if exclude.strip():
        exclude_list = [e.strip() for e in exclude.split(",") if e.strip()]

    checker = CompletenessChecker()
    report = checker.check(root, exclude=exclude_list, respect_gitignore=respect_gitignore)

    data: dict[str, Any] = report.model_dump()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_check_completeness", elapsed_ms, data)


async def docs_check_links(
    files: str = "",
    project_root: str = "",
    summary_only: bool = False,
    max_items: int = 200,
    broken_only: bool = False,
    include_backtick_refs: bool = True,
) -> dict[str, Any]:
    """Validate internal links in documentation files.

    Scans markdown files for internal links and verifies that referenced
    files and anchors exist. Does NOT check external HTTP links.

    Large projects can produce huge responses; use ``summary_only`` for
    dashboards and ``max_items`` to cap the detail lists. ``broken_only``
    drops OK/warning items, and ``include_backtick_refs=False`` removes the
    "missing backtick ref" entries from the main lists (they remain counted
    in ``missing_backtick_ref_count``).

    Args:
        files: Comma-separated list of specific files to check (relative or
            absolute paths). When empty, scans all documentation files.
        project_root: Override project root path (default: configured root).
        summary_only: When True, return only counts + score; omit detail lists.
        max_items: Cap on total detail items returned across all lists. When
            the cap is hit, ``truncated=True`` and ``total_available_*``
            fields report the pre-cap totals.
        broken_only: When True, omit OK links and warnings from the detail lists.
        include_backtick_refs: When False, exclude backtick-ref items from the
            detail lists. The scalar count remains accurate.
    """
    _record_call("docs_check_links")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_links",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    files_list: list[str] | None = None
    if files.strip():
        files_list = [f.strip() for f in files.split(",") if f.strip()]

    from docs_mcp.validators.link_checker import LinkChecker

    checker = LinkChecker()
    report = checker.check(
        root,
        files=files_list,
        summary_only=summary_only,
        max_items=max_items,
        broken_only=broken_only,
        include_backtick_refs=include_backtick_refs,
    )

    data: dict[str, Any] = report.model_dump()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_check_links", elapsed_ms, data)


_FRESHNESS_DEFAULT_MAX = 50
_FRESHNESS_VALID_CATEGORIES = frozenset({"fresh", "aging", "stale", "ancient"})


async def docs_check_freshness(
    project_root: str = "",
    path: str = "",
    max_items: int = 0,
    summary_only: bool = False,
    freshness: str = "",
    exclude: str = "",
    respect_gitignore: bool = True,
) -> dict[str, Any]:
    """Score documentation freshness based on file modification times.

    Classifies each doc file as fresh (<30d), aging (30-90d),
    stale (90-365d), or ancient (>365d) and calculates an overall
    freshness score (0-100). Items are sorted stalest-first.

    Args:
        project_root: Override project root path (default: configured root).
        path: Subdirectory to scope the scan to (relative to project root).
            When empty, scans the entire project.
        max_items: Maximum number of items to return. 0 means use default
            (50). Applies after any freshness category filter.
        summary_only: When True, return only aggregate scores and category
            counts without per-file items. Ideal for dashboards.
        freshness: Comma-separated freshness categories to filter by
            (e.g. ``"stale,ancient"``). Only items matching one of the
            listed categories are returned. Empty means all categories.
        exclude: Comma-separated glob patterns to skip during scanning, on top
            of the built-in baseline. Example: ``"vendored/**/*"``.
        respect_gitignore: When True (default), honor the project's root
            ``.gitignore``. Pass False to restore pre-2.10 behavior.
    """
    _record_call("docs_check_freshness")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_freshness",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    # Resolve scoped path
    scan_root = root
    if path.strip():
        scan_root = root / path.strip()
        if not scan_root.is_dir():
            return error_response(
                "docs_check_freshness",
                "INVALID_PATH",
                f"Scoped path does not exist: {scan_root}",
            )

    from docs_mcp.validators.freshness import FreshnessChecker

    exclude_list: list[str] | None = None
    if exclude.strip():
        exclude_list = [e.strip() for e in exclude.split(",") if e.strip()]

    checker = FreshnessChecker()
    report = checker.check(
        scan_root,
        relative_to=root,
        exclude=exclude_list,
        respect_gitignore=respect_gitignore,
    )

    # Items are already sorted stalest-first by the checker
    items = report.items
    total_unfiltered = len(items)

    # Apply freshness category filter
    if freshness.strip():
        categories = {
            c.strip().lower()
            for c in freshness.split(",")
            if c.strip().lower() in _FRESHNESS_VALID_CATEGORIES
        }
        if categories:
            items = [it for it in items if it.freshness in categories]

    total_filtered = len(items)

    # Apply max_items truncation
    effective_max = max_items if max_items > 0 else _FRESHNESS_DEFAULT_MAX
    if not summary_only:
        items = items[:effective_max]

    # Build summary string
    cc = report.category_counts
    summary = (
        f"{total_unfiltered} docs scanned: "
        f"{cc.get('fresh', 0)} fresh, {cc.get('aging', 0)} aging, "
        f"{cc.get('stale', 0)} stale, {cc.get('ancient', 0)} ancient "
        f"(score: {report.freshness_score}/100)"
    )

    data: dict[str, Any] = {
        "summary": summary,
        "total_unfiltered": total_unfiltered,
        "total_items": total_filtered,
        "showing": 0 if summary_only else len(items),
        "items": [] if summary_only else [it.model_dump() for it in items],
        "average_age_days": report.average_age_days,
        "freshness_score": report.freshness_score,
        "category_counts": report.category_counts,
    }

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_check_freshness", elapsed_ms, data)


async def docs_validate_epic(
    file_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Validate the structure of an epic planning document.

    Checks required sections (Goal, Motivation, Acceptance Criteria, Stories),
    story completeness (points, size, AC, tasks, files), point/size consistency,
    dependency cycles in Implementation Order, and Files Affected coverage.

    Args:
        file_path: Path to the epic markdown file (absolute or relative to
            project_root). Required.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_validate_epic")
    start = time.perf_counter_ns()

    if not file_path.strip():
        return error_response(
            "docs_validate_epic",
            "MISSING_FILE",
            "Parameter 'file_path' is required.",
        )

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    fp = Path(file_path)
    if not fp.is_absolute():
        fp = root / fp

    if not fp.exists():
        return error_response(
            "docs_validate_epic",
            "FILE_NOT_FOUND",
            f"Epic file does not exist: {fp}",
        )

    from docs_mcp.validators.epic_validator import EpicValidator

    validator = EpicValidator()
    report = validator.validate(fp)

    data: dict[str, Any] = report.model_dump()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_validate_epic", elapsed_ms, data)


# ---------------------------------------------------------------------------
# Epic 82: Diataxis balance validation
# ---------------------------------------------------------------------------


async def docs_check_diataxis(
    project_root: str = "",
    max_unclassified_samples: int = 20,
) -> dict[str, Any]:
    """Check Diataxis content balance across project documentation.

    Classifies all markdown files into the four Diataxis quadrants (Tutorial,
    How-to, Reference, Explanation) and scores the overall balance. Returns
    per-file classifications, coverage percentages, and recommendations for
    underrepresented quadrants.

    Prefer ``adjusted_balance_score`` over ``balance_score`` when classification
    coverage is low — the raw balance can look "perfect" on a small sample of
    actually-classified files while most of the project went unscored.

    Args:
        project_root: Override project root path (default: configured root).
        max_unclassified_samples: Cap on the number of unclassified file paths
            returned as samples (default 20). Does not affect counts.
    """
    _record_call("docs_check_diataxis")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_diataxis",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.validators.diataxis import DiataxisValidator

    try:
        validator = DiataxisValidator()
        coverage = validator.validate(root, max_unclassified_samples=max_unclassified_samples)
    except Exception as exc:
        return error_response(
            "docs_check_diataxis",
            "VALIDATION_ERROR",
            f"Failed to check Diataxis balance: {exc}",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "balance_score": coverage.balance_score,
        "adjusted_balance_score": coverage.adjusted_balance_score,
        "classification_coverage": coverage.classification_coverage,
        "scoring_note": coverage.scoring_note,
        "coverage": {
            "tutorial": coverage.tutorial_pct,
            "how_to": coverage.howto_pct,
            "reference": coverage.reference_pct,
            "explanation": coverage.explanation_pct,
        },
        "total_files": coverage.total_files,
        "total_scanned": coverage.total_scanned,
        "classified_files": coverage.classified_files,
        "classified_count": coverage.classified_count,
        "unclassified_count": coverage.unclassified_count,
        "unclassified_files": coverage.unclassified_files,
        "per_file": [r.model_dump() for r in coverage.per_file[:50]],
        "recommendations": coverage.recommendations,
    }

    return success_response(
        "docs_check_diataxis",
        elapsed_ms,
        data,
        next_steps=[
            "Address missing content types identified in recommendations.",
            "Use docs_generate_readme or docs_generate_adr to fill gaps.",
            "Run docs_check_completeness for a broader documentation health check.",
        ],
    )


# ---------------------------------------------------------------------------
# docs_check_cross_refs (Epic 85.4)
# ---------------------------------------------------------------------------


async def docs_check_cross_refs(
    doc_dirs: str = "",
    check_backlinks: bool = True,
    project_root: str = "",
    group_by_source: bool = False,
) -> dict[str, Any]:
    """Validate cross-references between documentation files.

    Checks for orphan documents (not linked from any other doc),
    broken references (links to non-existent files), and missing
    backlinks (A links to B but B does not link back).

    Scoring uses a per-file mean so a single autogenerated bad file does not
    tank the whole project. ``legacy_score`` preserves the prior formula for
    downstream tooling still calibrated against it. ``patterns`` surfaces
    repeated broken-prefix patterns to help diagnose bulk misconfigurations.

    Args:
        doc_dirs: Comma-separated list of directories to scan.
            When empty, scans the entire project.
        check_backlinks: Whether to check for missing backlinks.
            Defaults to True.
        project_root: Path to the project root. Defaults to configured root.
        group_by_source: When True, omit the flat ``issues`` list from the
            response and return only grouped-by-source + patterns data. Big
            response-size win on projects where broken refs cluster in a few
            files.
    """
    _record_call("docs_check_cross_refs")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else settings.project_root

    if not root.is_dir():
        return error_response(
            "docs_check_cross_refs",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.validators.cross_ref import CrossRefValidator

    dirs_list: list[str] | None = None
    if doc_dirs:
        dirs_list = [d.strip() for d in doc_dirs.split(",") if d.strip()]

    try:
        validator = CrossRefValidator()
        report = validator.validate(
            root,
            doc_dirs=dirs_list,
            check_backlinks=check_backlinks,
            group_by_source=group_by_source,
        )
    except Exception as exc:
        return error_response(
            "docs_check_cross_refs",
            "VALIDATION_ERROR",
            f"Failed to validate cross-references: {exc}",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "score": report.score,
        "legacy_score": report.legacy_score,
        "scoring_method": report.scoring_method,
        "total_files": report.total_files,
        "total_refs": report.total_refs,
        "orphan_count": report.orphan_count,
        "broken_count": report.broken_count,
        "missing_backlink_count": report.missing_backlink_count,
        "groups": [g.model_dump() for g in report.groups],
        "patterns": [p.model_dump() for p in report.patterns],
        "issues": [] if group_by_source else [i.model_dump() for i in report.issues[:50]],
    }

    return success_response(
        "docs_check_cross_refs",
        elapsed_ms,
        data,
        next_steps=[
            "Fix broken references to improve documentation navigation.",
            "Add links to orphan documents from relevant parent docs.",
            "Run docs_generate_doc_index to create a documentation map.",
        ],
    )


# ---------------------------------------------------------------------------
# Epic 84: Style & tone validation
# ---------------------------------------------------------------------------


def _read_style_settings(settings: Any) -> tuple[list[str], str, int, list[str]]:
    """Read style settings safely, guarding against mocks with missing or wrong-typed attrs."""
    s_rules: list[str] = getattr(settings, "style_enabled_rules", []) or []
    s_heading: str = getattr(settings, "style_heading", "") or ""
    s_max_words: int = getattr(settings, "style_max_sentence_words", 0) or 0
    s_jargon: list[str] = getattr(settings, "style_jargon_terms", []) or []

    # Guard against mocks returning wrong types
    if not isinstance(s_rules, list):
        s_rules = []
    if not isinstance(s_heading, str):
        s_heading = ""
    if not isinstance(s_max_words, int):
        s_max_words = 0
    if not isinstance(s_jargon, list):
        s_jargon = []

    return s_rules, s_heading, s_max_words, s_jargon


def _build_style_config(
    rules: str,
    heading_style: str,
    max_sentence_words: int,
    custom_terms: str,
    root: Path,
    settings: Any,
) -> Any:
    """Build a StyleConfig from explicit params (override) + settings (fallback)."""
    from docs_mcp.validators.style import StyleConfig

    s_rules, s_heading, s_max_words, s_jargon = _read_style_settings(settings)
    config_kwargs: dict[str, Any] = {}

    # Rules: explicit param > settings > default
    if rules.strip():
        config_kwargs["enabled_rules"] = [r.strip() for r in rules.split(",") if r.strip()]
    elif s_rules:
        config_kwargs["enabled_rules"] = s_rules

    # Heading style: explicit param > settings
    if heading_style.strip() in ("sentence", "title"):
        config_kwargs["heading_style"] = heading_style.strip()
    elif s_heading in ("sentence", "title"):
        config_kwargs["heading_style"] = s_heading

    # Max sentence words: explicit param > settings
    if max_sentence_words > 0:
        config_kwargs["max_sentence_words"] = max_sentence_words
    elif s_max_words > 0:
        config_kwargs["max_sentence_words"] = s_max_words

    # Custom terms: param + settings + .docsmcp-terms.txt
    extra: list[str] | None = None
    if custom_terms.strip():
        extra = [t.strip() for t in custom_terms.split(",") if t.strip()]
    merged_terms = build_custom_terms_for_style(root, settings, extra_terms=extra)
    if merged_terms:
        config_kwargs["custom_terms"] = merged_terms

    if s_jargon:
        config_kwargs["jargon_terms"] = s_jargon

    return StyleConfig(**config_kwargs)


def _run_style_check_files(
    checker: Any,
    file_list: list[str],
    root: Path,
) -> tuple[Any, list[str]]:
    """Run style check on a specific list of files and return a StyleReport.

    Returns:
        A tuple of ``(StyleReport, missing_files)`` where *missing_files*
        contains paths that were requested but could not be resolved.
    """
    from docs_mcp.validators.style import FileStyleResult, StyleReport

    results: list[FileStyleResult] = []
    missing: list[str] = []
    for file_str in file_list:
        fp = Path(file_str)
        if not fp.is_absolute():
            fp = root / fp
        if fp.exists():
            results.append(checker.check_file(fp, relative_to=root))
        else:
            missing.append(file_str)

    total_issues = sum(len(r.issues) for r in results)
    agg_score = sum(r.score for r in results) / len(results) if results else 0.0
    issue_counts: dict[str, int] = {}
    for r in results:
        for issue in r.issues:
            issue_counts[issue.rule] = issue_counts.get(issue.rule, 0) + 1

    report = StyleReport(
        total_files=len(results),
        total_issues=total_issues,
        files=results,
        aggregate_score=round(agg_score, 1),
        issue_counts=issue_counts,
    )
    return report, missing


async def docs_check_style(
    files: str = "",
    rules: str = "",
    heading_style: str = "",
    max_sentence_words: int = 0,
    custom_terms: str = "",
    output_format: str = "",
    project_root: str = "",
    summary_only: bool = False,
    max_items: int = 300,
    rule_filter: str = "",
    file_filter: str = "",
) -> dict[str, Any]:
    """Check documentation style and tone for writing quality issues.

    Applies deterministic regex/pattern rules to detect passive voice,
    jargon, long sentences, heading inconsistency, and tense mixing.
    Returns per-file issues with severity, location, and fix suggestions.

    Large projects can produce huge responses; use ``summary_only`` for
    dashboards and ``max_items`` to cap detail items. ``rule_filter`` and
    ``file_filter`` narrow what appears in the detail list; aggregate counts
    always reflect the pre-filter universe so dashboards stay stable.

    Args:
        files: Comma-separated list of specific files to check (relative or
            absolute paths). When empty, scans all documentation files.
        rules: Comma-separated list of rules to enable. Available rules:
            passive_voice, jargon, sentence_length, heading_consistency,
            tense_consistency. When empty, uses all rules.
        heading_style: Heading case style to enforce: ``"sentence"`` (default)
            or ``"title"``. Only applies when heading_consistency rule is active.
        max_sentence_words: Maximum words per sentence before flagging (default: 40).
            Only applies when sentence_length rule is active.
        custom_terms: Comma-separated list of project-specific terms to exclude
            from jargon checks and allow in headings (e.g. ``"FastMCP,DocsMCP"``).
        output_format: Output format: ``""`` (default structured) or ``"vale"``
            for Vale-compatible output.
        project_root: Override project root path (default: configured root).
        summary_only: When True, return only aggregate_score + issue counts;
            detail list is emptied. Counts remain accurate.
        max_items: Cap on total detail items returned across all files.
        rule_filter: Comma-separated list of rule ids; detail items are
            filtered to only these rules. Counts are not filtered.
        file_filter: Comma-separated list of posix-relative file paths; detail
            items are filtered to only these files. Counts are not filtered.
    """
    _record_call("docs_check_style")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root.strip() else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_check_style",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.validators.style import StyleChecker

    config = _build_style_config(
        rules, heading_style, max_sentence_words, custom_terms, root, settings
    )
    checker = StyleChecker(config)

    rule_filter_list: list[str] | None = None
    if rule_filter.strip():
        rule_filter_list = [r.strip() for r in rule_filter.split(",") if r.strip()]
    file_filter_list: list[str] | None = None
    if file_filter.strip():
        file_filter_list = [f.strip() for f in file_filter.split(",") if f.strip()]

    if files.strip():
        file_list = [f.strip() for f in files.split(",") if f.strip()]
        report, missing = _run_style_check_files(checker, file_list, root)

        if missing and report.total_files == 0:
            return error_response(
                "docs_check_style",
                "NO_FILES_FOUND",
                f"No files could be resolved: {', '.join(missing)}",
                extra={"requested_files": missing, "project_root": str(root)},
            )
    else:
        report = checker.check_project(
            root,
            summary_only=summary_only,
            max_items=max_items,
            rule_filter=rule_filter_list,
            file_filter=file_filter_list,
        )
        missing = []

    if output_format.strip().lower() == "vale":
        data = _style_report_vale(report)
    else:
        data = _style_report_structured(report)

    if missing:
        data["warnings"] = [f"File not found: {f}" for f in missing]

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response(
        "docs_check_style",
        elapsed_ms,
        data,
        next_steps=[
            "Fix high-severity style issues (errors first, then warnings).",
            "Add project-specific terms to custom_terms to reduce false positives.",
            "Run docs_check_completeness for a broader documentation health check.",
        ],
    )


def _style_report_structured(report: StyleReport) -> dict[str, Any]:
    """Build structured response data from a StyleReport."""
    files_data: list[dict[str, Any]] = []
    for fr in report.files:
        if fr.issues:
            files_data.append(
                {
                    "file_path": fr.file_path,
                    "score": fr.score,
                    "issue_count": len(fr.issues),
                    "issues": [i.model_dump() for i in fr.issues[:20]],
                }
            )

    return {
        "total_files": report.total_files,
        "total_issues": report.total_issues,
        "aggregate_score": report.aggregate_score,
        "issue_counts": report.issue_counts,
        "top_issues": report.top_issues,
        "file_issue_counts": getattr(report, "file_issue_counts", {}),
        "truncated": getattr(report, "truncated", False),
        "total_available": getattr(report, "total_available", 0),
        "files": files_data,
    }


def _style_report_vale(report: StyleReport) -> dict[str, Any]:
    """Build Vale-compatible output from a StyleReport."""
    vale_output: dict[str, list[dict[str, Any]]] = {}
    for fr in report.files:
        if fr.issues:
            vale_output[fr.file_path] = [
                {
                    "Check": f"DocsMCP.{i.rule}",
                    "Severity": i.severity,
                    "Line": i.line,
                    "Span": [i.column, i.column],
                    "Message": i.message,
                    "Action": {"Name": "suggest", "Params": [i.suggestion]} if i.suggestion else {},
                }
                for i in fr.issues
            ]

    return {
        "format": "vale",
        "total_files": report.total_files,
        "total_issues": report.total_issues,
        "aggregate_score": report.aggregate_score,
        "results": vale_output,
    }


async def docs_validate_release_update(
    body: str = "",
) -> dict[str, Any]:
    """Validate a release update document body before posting to Linear.

    Returns ``agent_ready=true`` when the body passes all HIGH-severity rules.
    Use before calling ``save_document`` to confirm template compliance.

    Args:
        body: The markdown body produced by ``docs_generate_release_update``.
    """
    _record_call("docs_validate_release_update")
    start = time.perf_counter_ns()

    from docs_mcp.validators.release_update import validate_release_update

    if not body.strip():
        return error_response(
            "docs_validate_release_update",
            "MISSING_BODY",
            "Parameter 'body' is required.",
        )

    report = validate_release_update(body)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response(
        "docs_validate_release_update",
        elapsed_ms,
        {
            "agent_ready": report.agent_ready,
            "score": report.score,
            "findings": [f.model_dump() for f in report.findings],
        },
    )


# ---------------------------------------------------------------------------
# Registration (Epic 79.2: conditional)
# ---------------------------------------------------------------------------


def register(mcp_instance: "FastMCP", allowed_tools: frozenset[str]) -> None:  # noqa: UP037
    """Register validation tools on the shared mcp instance (Epic 79.2: conditional)."""
    if "docs_check_drift" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_check_drift)
    if "docs_check_completeness" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_check_completeness)
    if "docs_check_links" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_check_links)
    if "docs_check_freshness" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_check_freshness)
    if "docs_validate_epic" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_validate_epic)
    if "docs_check_diataxis" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_check_diataxis)
    if "docs_check_cross_refs" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_check_cross_refs)
    if "docs_check_style" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_check_style)
    if "docs_validate_release_update" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_validate_release_update)
