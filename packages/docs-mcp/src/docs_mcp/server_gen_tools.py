"""DocsMCP generation tools - README, changelog, and release notes.

These tools register on the shared ``mcp`` FastMCP instance from
``server.py`` and provide documentation generation capabilities.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from docs_mcp.server import (
    _ANNOTATIONS_READ_ONLY,
    _ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
    _record_call,
    mcp,
)
from docs_mcp.server_helpers import _get_settings, error_response, success_response


@mcp.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)
async def docs_generate_changelog(
    format: str = "keep-a-changelog",
    include_unreleased: bool = True,
    output_path: str = "",
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
                    unreleased_commits = unreleased if unreleased else None

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

    # Optionally write to file
    written_path = ""
    if output_path:
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(output_path)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            write_path.write_text(content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_changelog",
                "WRITE_ERROR",
                f"Failed to write changelog: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "format": format,
        "version_count": len(versions),
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path

    return success_response("docs_generate_changelog", elapsed_ms, data)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
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


@mcp.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)
async def docs_generate_readme(  # noqa: PLR0911
    style: str = "standard",
    output_path: str = "",
    merge: bool = True,
    project_root: str = "",
) -> dict[str, Any]:
    """Generate or update a README.md file for the project.

    When ``merge=True`` and a README.md already exists, preserves human-written
    sections and only updates machine-managed sections (wrapped in docsmcp
    markers). When ``merge=False`` or no existing README, generates fresh.

    Args:
        style: README style - "minimal", "standard", or "comprehensive".
        output_path: Output file path (default: README.md in project root).
        merge: Whether to merge with existing README (default: True).
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_readme")
    start = time.perf_counter_ns()

    from docs_mcp.config.settings import load_docs_settings

    try:
        root_override = Path(project_root) if project_root.strip() else None
        settings = load_docs_settings(root_override)
    except Exception as exc:
        return error_response("docs_generate_readme", "CONFIG_ERROR", str(exc))

    root = settings.project_root

    # Validate style
    valid_styles = ("minimal", "standard", "comprehensive")
    if style not in valid_styles:
        return error_response(
            "docs_generate_readme",
            "INVALID_STYLE",
            f"Invalid style '{style}'. Must be one of: {', '.join(valid_styles)}",
        )

    # Determine output path
    if output_path.strip():
        out = Path(output_path)
        if not out.is_absolute():
            out = root / out
    else:
        out = root / "README.md"

    # Validate output path is within project root
    from tapps_core.security.path_validator import PathValidator

    validator = PathValidator(root)
    try:
        out = validator.validate_write_path(str(out))
    except (ValueError, FileNotFoundError) as exc:
        return error_response("docs_generate_readme", "PATH_ERROR", str(exc))

    # Extract metadata and generate content
    from docs_mcp.generators.metadata import MetadataExtractor
    from docs_mcp.generators.readme import ReadmeGenerator

    try:
        extractor = MetadataExtractor()
        metadata = extractor.extract(root)

        generator = ReadmeGenerator(style=style)
        generated = generator.generate(root, metadata=metadata)
    except Exception as exc:
        return error_response("docs_generate_readme", "GENERATION_ERROR", str(exc))

    # Handle merge
    merge_stats: dict[str, Any] = {}
    final_content: str

    if merge and out.exists():
        from docs_mcp.generators.smart_merge import SmartMerger

        try:
            existing = out.read_text(encoding="utf-8")
            merger = SmartMerger()
            result = merger.merge(existing, generated)
            final_content = result.content
            merge_stats = {
                "merged": True,
                "sections_preserved": result.sections_preserved,
                "sections_updated": result.sections_updated,
                "sections_added": result.sections_added,
            }
        except Exception as exc:
            return error_response("docs_generate_readme", "MERGE_ERROR", str(exc))
    else:
        final_content = generated
        merge_stats = {"merged": False}

    # Write output
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(final_content, encoding="utf-8")
    except OSError as exc:
        return error_response("docs_generate_readme", "WRITE_ERROR", str(exc))

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    if out.is_relative_to(root):
        rel_path = str(out.relative_to(root)).replace("\\", "/")
    else:
        rel_path = str(out)

    data: dict[str, Any] = {
        "output_path": rel_path,
        "style": style,
        "content_length": len(final_content),
        "content": final_content,
        **merge_stats,
    }

    return success_response(
        "docs_generate_readme",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated README and customize sections as needed.",
            "Human-written sections (without docsmcp markers) will be preserved on re-generation.",
        ],
    )
