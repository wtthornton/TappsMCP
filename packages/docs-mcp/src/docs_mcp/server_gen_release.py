"""Release-oriented DocsMCP generation tools.

Changelog, per-version release notes, and the structured release-update
document. Split out of ``server_gen_tools.py`` under TAP-5608 — that
module is now a registration facade that re-exports these handlers.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

from docs_mcp.server_gen_helpers import (
    _split_csv,
)
from docs_mcp.server_gen_helpers import (
    get_settings as _get_settings,
)
from docs_mcp.server_gen_helpers import (
    record_call as _record_call,
)
from docs_mcp.server_helpers import (
    error_response,
    finalize_output,
    success_response,
)

logger = structlog.get_logger(__name__)


async def docs_generate_changelog(
    format: str = "keep-a-changelog",
    include_unreleased: bool = True,
    output_path: str = "",
    force: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a CHANGELOG.md from git history.

    Analyzes git tags and commits to produce a structured changelog in either
    Keep-a-Changelog or Conventional format.

    Args:
        format: Changelog format - "keep-a-changelog" or "conventional".
        include_unreleased: Whether to include unreleased changes section.
        output_path: File path to write the changelog (relative to project root).
            When empty, returns the content without writing a file.
        force: When True, overwrite an existing CHANGELOG even if it appears
            hand-crafted. Defaults to False so curated changelogs are never
            silently destroyed.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_changelog")
    start = time.perf_counter_ns()

    if format not in ("keep-a-changelog", "conventional"):
        return error_response(
            "docs_generate_changelog",
            "INVALID_FORMAT",
            f"Invalid format {format!r}. Use 'keep-a-changelog' or 'conventional'.",
        )

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_changelog",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    # Lazy imports for concurrent-safe loading
    from docs_mcp.analyzers.git_history import GitHistoryAnalyzer
    from docs_mcp.analyzers.version_detector import VersionDetector
    from docs_mcp.generators.changelog import ChangelogGenerator

    try:
        detector = VersionDetector()
        versions = detector.detect_versions(root, include_commits=True)

        # Get unreleased commits (commits newer than the latest tag)
        unreleased_commits = None
        if include_unreleased:
            analyzer = GitHistoryAnalyzer(root)
            all_commits = analyzer.get_commits(limit=settings.git_log_limit)
            if versions and all_commits:
                latest_tag_hash = versions[0].commits[0].hash if versions[0].commits else ""
                if latest_tag_hash:
                    unreleased = []
                    for c in all_commits:
                        if c.hash == latest_tag_hash:
                            break
                        unreleased.append(c)
                    unreleased_commits = unreleased or None

        generator = ChangelogGenerator()
        content = generator.generate(
            versions,
            format=format,
            include_unreleased=include_unreleased,
            unreleased_commits=unreleased_commits,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_changelog",
            "GENERATION_ERROR",
            f"Failed to generate changelog: {exc}",
        )

    # Auto-compute output_path when not provided
    target = output_path.strip() or "CHANGELOG.md"

    # Guard: don't silently destroy a hand-crafted CHANGELOG unless force=True
    if not force:
        candidate = root / target
        if candidate.exists():
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            return success_response(
                "docs_generate_changelog",
                elapsed_ms,
                {
                    "format": format,
                    "version_count": len(versions),
                    "output_path": target,
                    "content": content,
                    "content_length": len(content),
                    "warning": (
                        f"{target} already exists and was not overwritten. "
                        "Review the generated content above and pass force=True to overwrite, "
                        "or manually merge the changes you want."
                    ),
                },
            )

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_changelog",
        content,
        target,
        root,
        description="CHANGELOG file.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "format": format,
        "version_count": len(versions),
        **out,
    }

    return success_response("docs_generate_changelog", elapsed_ms, data)


async def docs_generate_release_notes(
    version: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate release notes for a specific version.

    Analyzes git history to produce structured release notes with highlights,
    breaking changes, features, fixes, and contributor information.

    Args:
        version: Version string to generate notes for (e.g. "1.2.0").
            When empty, generates for the latest version.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_release_notes")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_release_notes",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.analyzers.version_detector import VersionDetector
    from docs_mcp.generators.release_notes import ReleaseNotesGenerator

    try:
        detector = VersionDetector()
        versions = detector.detect_versions(root, include_commits=True)

        if not versions:
            return error_response(
                "docs_generate_release_notes",
                "NO_VERSIONS",
                "No semver tags found in the repository.",
            )

        generator = ReleaseNotesGenerator()
        notes = generator.generate_from_versions(versions, version=version)

        if notes is None:
            return error_response(
                "docs_generate_release_notes",
                "VERSION_NOT_FOUND",
                f"Version {version!r} not found. Available: "
                + ", ".join(v.version for v in versions[:10]),
            )

        markdown = generator.render_markdown(notes)
    except Exception as exc:
        return error_response(
            "docs_generate_release_notes",
            "GENERATION_ERROR",
            f"Failed to generate release notes: {exc}",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "version": notes.version,
        "date": notes.date,
        "highlights": notes.highlights,
        "breaking_changes": notes.breaking_changes,
        "features": notes.features,
        "fixes": notes.fixes,
        "other_changes": notes.other_changes,
        "contributors": notes.contributors,
        "markdown": markdown,
    }

    return success_response("docs_generate_release_notes", elapsed_ms, data)


async def docs_generate_release_update(
    version: str,
    prev_version: str,
    bump_type: str = "",
    highlights: str = "",
    issues_closed: str = "",
    breaking_changes: str = "",
    links: str = "",
    health: str = "On Track",
    release_date: str = "",
) -> dict[str, Any]:
    """Generate a Linear project update document for a version release.

    Template sections: version header, health, highlights, issues closed,
    breaking changes (minor/major only), links.

    Args:
        version: New release version, e.g. "1.5.0".
        prev_version: Previous version, e.g. "1.4.2".
        bump_type: "patch", "minor", or "major". Inferred from semver delta if blank.
        highlights: Comma-separated highlight bullets.
        issues_closed: Comma-separated "TAP-123: title" entries.
        breaking_changes: Comma-separated breaking change descriptions (minor/major only).
        links: Comma-separated "Label=URL" pairs, e.g. "Changelog=https://...".
        health: "On Track", "At Risk", or "Off Track".
        release_date: ISO date override (YYYY-MM-DD). Defaults to today.
    """
    _record_call("docs_generate_release_update")
    start = time.perf_counter_ns()

    from docs_mcp.generators.release_update import (
        ReleaseUpdateConfig,
        ReleaseUpdateGenerator,
        infer_bump_type,
    )

    if not version.strip():
        return error_response(
            "docs_generate_release_update",
            "MISSING_VERSION",
            "Parameter 'version' is required.",
        )
    if not prev_version.strip():
        return error_response(
            "docs_generate_release_update",
            "MISSING_PREV_VERSION",
            "Parameter 'prev_version' is required.",
        )

    effective_bump = bump_type.strip() or infer_bump_type(version, prev_version)

    def _parse_links(raw: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in _split_csv(raw):
            if "=" in item:
                label, _, url = item.partition("=")
                result[label.strip()] = url.strip()
        return result

    config = ReleaseUpdateConfig(
        version=version.strip(),
        prev_version=prev_version.strip(),
        bump_type=effective_bump,
        highlights=_split_csv(highlights),
        issues_closed=_split_csv(issues_closed),
        breaking_changes=_split_csv(breaking_changes),
        links=_parse_links(links),
        health=health,
        release_date=release_date.strip(),
    )

    body = ReleaseUpdateGenerator().generate(config)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response(
        "docs_generate_release_update",
        elapsed_ms,
        {
            "body": body,
            "version": config.version,
            "prev_version": config.prev_version,
            "bump_type": effective_bump,
            "content_length": len(body),
        },
    )
