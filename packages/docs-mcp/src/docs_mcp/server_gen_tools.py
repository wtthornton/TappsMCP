"""DocsMCP generation tools.

Registers generation tools on the shared ``mcp`` FastMCP instance from
``server.py``: README, changelog, release notes, API docs, ADR,
onboarding/contributing guides, diagrams, architecture reports, epics,
and user stories.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from docs_mcp.server import (
    _ANNOTATIONS_READ_ONLY,
    _ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
    _record_call,
)
from docs_mcp.server_helpers import (
    _get_settings,
    build_generator_manifest,
    can_write_to_project,
    error_response,
    success_response,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = structlog.get_logger(__name__)


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

    # Optionally write to file (or content-return in Docker mode)
    written_path = ""
    if output_path and can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(output_path)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
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
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_changelog", content, output_path,
            description="CHANGELOG file.",
        )

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


async def docs_generate_readme(
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
            existing = await asyncio.to_thread(out.read_text, encoding="utf-8")
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

    # Write output (or content-return in Docker mode)
    if out.is_relative_to(root):
        rel_path = str(out.relative_to(root)).replace("\\", "/")
    else:
        rel_path = str(out)

    written = False
    if can_write_to_project(root):
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(out.write_text, final_content, encoding="utf-8")
            written = True
        except OSError as exc:
            return error_response("docs_generate_readme", "WRITE_ERROR", str(exc))

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "output_path": rel_path,
        "style": style,
        "content_length": len(final_content),
        "content": final_content,
        **merge_stats,
    }
    if not written:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_readme", final_content, rel_path,
            description="Project README.",
        )

    return success_response(
        "docs_generate_readme",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated README and customize sections as needed.",
            "Human-written sections (without docsmcp markers) will be preserved on re-generation.",
        ],
    )


async def docs_generate_api(
    source_path: str = "",
    format: str = "markdown",
    depth: str = "public",
    include_examples: bool = True,
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate API reference documentation from Python source files.

    Produces structured per-module documentation with classes, functions,
    parameters, return types, and usage examples extracted from tests.

    Args:
        source_path: File or directory to document (relative to project root).
            When empty, documents the entire project source.
        format: Output format - "markdown", "mkdocs", or "sphinx_rst".
        depth: Visibility depth - "public", "protected", or "all".
        include_examples: Whether to extract usage examples from test files.
        output_path: File path to write output (relative to project root).
            When empty, returns the content without writing a file.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_api")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_api",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.api_docs import APIDocGenerator

    generator = APIDocGenerator()

    # Resolve source path
    src = root / source_path if source_path else root
    if not src.exists():
        return error_response(
            "docs_generate_api",
            "SOURCE_NOT_FOUND",
            f"Source path does not exist: {src}",
        )

    try:
        content = generator.generate(
            src,
            project_root=root,
            output_format=format,
            depth=depth,
            include_examples=include_examples,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_api",
            "GENERATION_ERROR",
            f"Failed to generate API docs: {exc}",
        )

    if not content:
        return error_response(
            "docs_generate_api",
            "NO_CONTENT",
            "No documentable content found in the source path.",
        )

    # Optionally write to file (or content-return in Docker mode)
    written_path = ""
    if output_path and can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(output_path)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_api",
                "WRITE_ERROR",
                f"Failed to write API docs: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "format": format,
        "depth": depth,
        "content_length": len(content),
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_api", content, output_path,
            description="API reference documentation.",
        )

    return success_response("docs_generate_api", elapsed_ms, data)


async def docs_generate_adr(
    title: str,
    template: str = "madr",
    context: str = "",
    decision: str = "",
    consequences: str = "",
    status: str = "proposed",
    adr_directory: str = "",
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Create an Architecture Decision Record (ADR).

    Auto-numbers the ADR by scanning existing records in the ADR directory.
    Supports MADR and Nygard template formats.

    Args:
        title: Title of the decision (e.g. "Use MCP protocol").
        template: ADR template format - "madr" or "nygard".
        context: Context and problem statement.
        decision: The decision that was made.
        consequences: Consequences of this decision.
        status: Decision status - "proposed", "accepted", "deprecated",
            or "superseded".
        adr_directory: Directory for ADR files (default: docs/decisions/).
        output_path: Override output file path. When empty, auto-generates
            from title and number.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_adr")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_adr",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.adr import ADRGenerator

    generator = ADRGenerator()
    adr_dir = root / adr_directory if adr_directory else None

    try:
        content, filename = generator.generate(
            title,
            template=template,
            context=context,
            decision=decision,
            consequences=consequences,
            status=status,
            adr_dir=adr_dir,
            project_root=root,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_adr",
            "GENERATION_ERROR",
            f"Failed to generate ADR: {exc}",
        )

    # Write the ADR file (or content-return in Docker mode)
    write_target = output_path if output_path else filename
    written_path = ""
    if can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            actual_dir = adr_dir if adr_dir else root / "docs" / "decisions"
            full_path = (
                actual_dir / write_target
                if not Path(write_target).is_absolute()
                else Path(write_target)
            )
            write_path = validator.validate_write_path(str(full_path))
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_adr",
                "WRITE_ERROR",
                f"Failed to write ADR: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    # Build relative path for content-return mode
    adr_rel = write_target
    if not written_path and not Path(write_target).is_absolute():
        adr_base = "docs/decisions" if not adr_dir else str(adr_dir)
        adr_rel = f"{adr_base}/{write_target}"

    data: dict[str, Any] = {
        "template": template,
        "filename": filename,
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    else:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_adr", content, adr_rel,
            description=f"Architecture Decision Record: {title}",
        )

    return success_response("docs_generate_adr", elapsed_ms, data)


async def docs_generate_onboarding(
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a getting-started / onboarding guide for the project.

    Creates a developer onboarding document with prerequisites, installation,
    project structure, and first steps based on project analysis.

    Args:
        output_path: Output file path (default: docs/ONBOARDING.md).
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_onboarding")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_onboarding",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.guides import OnboardingGuideGenerator

    try:
        generator = OnboardingGuideGenerator()
        content = generator.generate(root)
    except Exception as exc:
        return error_response(
            "docs_generate_onboarding",
            "GENERATION_ERROR",
            f"Failed to generate onboarding guide: {exc}",
        )

    if not content:
        return error_response(
            "docs_generate_onboarding",
            "NO_CONTENT",
            "Could not generate onboarding content for this project.",
        )

    # Write to file (or content-return in Docker mode)
    target = output_path if output_path else "docs/ONBOARDING.md"
    written_path = ""
    if can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(target)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_onboarding",
                "WRITE_ERROR",
                f"Failed to write onboarding guide: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "content_length": len(content),
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    else:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_onboarding", content, target,
            description="Getting-started / onboarding guide.",
        )

    return success_response("docs_generate_onboarding", elapsed_ms, data)


async def docs_generate_contributing(
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a CONTRIBUTING.md file for the project.

    Creates a contribution guide with development setup, coding standards,
    testing, and PR workflow based on project analysis.

    Args:
        output_path: Output file path (default: CONTRIBUTING.md in project root).
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_contributing")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_contributing",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.guides import ContributingGuideGenerator

    try:
        generator = ContributingGuideGenerator()
        content = generator.generate(root)
    except Exception as exc:
        return error_response(
            "docs_generate_contributing",
            "GENERATION_ERROR",
            f"Failed to generate contributing guide: {exc}",
        )

    if not content:
        return error_response(
            "docs_generate_contributing",
            "NO_CONTENT",
            "Could not generate contributing content for this project.",
        )

    # Write to file (or content-return in Docker mode)
    target = output_path if output_path else "CONTRIBUTING.md"
    written_path = ""
    if can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(target)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_contributing",
                "WRITE_ERROR",
                f"Failed to write contributing guide: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "content_length": len(content),
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    else:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_contributing", content, target,
            description="Contribution guide with development setup and PR workflow.",
        )

    return success_response("docs_generate_contributing", elapsed_ms, data)


async def docs_generate_prd(
    title: str,
    problem: str = "",
    personas: str = "",
    phases: str = "",
    constraints: str = "",
    non_goals: str = "",
    style: str = "standard",
    auto_populate: bool = False,
    existing_content: str = "",
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a Product Requirements Document (PRD) with phased requirements.

    Creates a structured PRD with Executive Summary, Problem Statement, User
    Personas, Solution Overview, Phased Requirements, Acceptance Criteria
    (Gherkin), Technical Constraints, and Non-Goals.

    The ``comprehensive`` style adds a Boundary System ("Always do" /
    "Ask first" / "Never do") and Architecture Overview section.

    When ``auto_populate=True``, enriches sections from project analyzers
    (module map, tech stack, quality scores, git history).

    When ``existing_content`` is provided, uses SmartMerger to preserve
    hand-edited sections (identified by ``<!-- docsmcp:start:section -->``
    markers).

    Args:
        title: Title for the PRD (e.g. "User Authentication System").
        problem: Problem statement text.
        personas: Comma-separated list of user personas.
        phases: JSON array of phase objects with keys: name, description,
            requirements. Example: [{"name": "MVP", "requirements": ["Login"]}]
        constraints: Comma-separated list of technical constraints.
        non_goals: Comma-separated list of non-goals / out-of-scope items.
        style: PRD style - "standard" or "comprehensive".
        auto_populate: Enrich from project analyzers (ModuleMap, Metadata, etc).
        existing_content: Existing PRD markdown to merge with (preserves edits).
        output_path: File path to write the PRD (relative to project root).
            When empty, returns the content without writing a file.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_prd")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_prd",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.specs import PRDConfig, PRDGenerator, PRDPhase

    # Parse comma-separated lists
    persona_list = [p.strip() for p in personas.split(",") if p.strip()] if personas else []
    constraint_list = (
        [c.strip() for c in constraints.split(",") if c.strip()] if constraints else []
    )
    non_goal_list = [n.strip() for n in non_goals.split(",") if n.strip()] if non_goals else []

    # Parse phases JSON
    phase_list: list[PRDPhase] = []
    if phases:
        try:
            phase_list = PRDGenerator.parse_phases_json(phases)
        except ValueError as exc:
            return error_response(
                "docs_generate_prd",
                "INVALID_PHASES",
                str(exc),
            )

    config = PRDConfig(
        title=title,
        problem=problem,
        personas=persona_list,
        phases=phase_list,
        constraints=constraint_list,
        non_goals=non_goal_list,
        style=style,
        existing_content=existing_content,
    )

    generator = PRDGenerator()

    try:
        content = generator.generate(
            config,
            project_root=root if auto_populate else None,
            auto_populate=auto_populate,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_prd",
            "GENERATION_ERROR",
            f"Failed to generate PRD: {exc}",
        )

    # SmartMerger integration when existing content is provided
    merge_stats: dict[str, Any] = {}
    if existing_content.strip():
        from docs_mcp.generators.smart_merge import SmartMerger

        try:
            merger = SmartMerger()
            result = merger.merge(existing_content, content)
            content = result.content
            merge_stats = {
                "merged": True,
                "sections_preserved": result.sections_preserved,
                "sections_updated": result.sections_updated,
                "sections_added": result.sections_added,
            }
        except Exception as exc:
            return error_response(
                "docs_generate_prd",
                "MERGE_ERROR",
                f"Failed to merge with existing content: {exc}",
            )
    else:
        merge_stats = {"merged": False}

    # Optionally write to file (or content-return in Docker mode)
    written_path = ""
    if output_path and can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(output_path)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_prd",
                "WRITE_ERROR",
                f"Failed to write PRD: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "title": title,
        "style": style,
        "auto_populated": auto_populate,
        "content_length": len(content),
        "content": content,
        **merge_stats,
    }
    if written_path:
        data["written_to"] = written_path
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_prd", content, output_path,
            description=f"Product Requirements Document: {title}",
        )

    return success_response(
        "docs_generate_prd",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated PRD and fill in placeholder sections.",
            "Human-written sections (without docsmcp markers) will be preserved on re-generation.",
        ],
    )


async def docs_generate_diagram(
    diagram_type: str = "dependency",
    scope: str = "project",
    depth: int = 2,
    format: str = "",
    direction: str = "TD",
    show_external: bool = False,
    flow_spec: str = "",
    theme: str = "default",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate Mermaid, PlantUML, or D2 diagrams from code analysis.

    Diagram types:
    - "dependency": Module import dependency flowchart
    - "class_hierarchy": Class inheritance diagram
    - "module_map": Package/module architecture overview
    - "er_diagram": Entity-relationship diagram from Pydantic/dataclass models
    - "c4_context": C4 System Context diagram showing external actors
    - "c4_container": C4 Container diagram showing high-level building blocks
    - "c4_component": C4 Component diagram showing internal components
    - "sequence": Sequence diagram showing request flows and call chains

    Args:
        diagram_type: Type of diagram to generate.
        scope: "project" for full project, or a file path for single-file scope.
            For c4_component, scope can be a package path to focus on.
        depth: Max traversal depth for dependency/module/sequence diagrams (default: 2).
        format: Output format - "mermaid", "plantuml", or "d2" (default: from config).
        direction: Graph direction - "TD" (top-down) or "LR" (left-right).
        show_external: Include external dependencies in dependency diagrams.
        flow_spec: JSON string defining a manual sequence flow. When provided with
            diagram_type="sequence", uses this spec instead of auto-detection.
            Expected: {"participants": [...], "messages": [{"from": ..., "to": ...,
            "label": ...}]}. Optional fields: "title", "notes", "groups".
        theme: D2 theme - "default", "sketch", or "terminal". Ignored for
            mermaid/plantuml formats.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_diagram")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_diagram",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.diagrams import DiagramGenerator

    output_format = format if format else getattr(settings, "diagram_format", "mermaid")

    generator = DiagramGenerator()
    try:
        result = generator.generate(
            root,
            diagram_type=diagram_type,
            output_format=output_format,
            scope=scope,
            depth=depth,
            direction=direction,
            show_external=show_external,
            flow_spec=flow_spec,
            theme=theme,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_diagram",
            "GENERATION_ERROR",
            f"Failed to generate diagram: {exc}",
        )

    if not result.content:
        return error_response(
            "docs_generate_diagram",
            "NO_CONTENT",
            f"No content generated for diagram type '{diagram_type}'.",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "diagram_type": result.diagram_type,
        "format": result.format,
        "node_count": result.node_count,
        "edge_count": result.edge_count,
        "content": result.content,
    }

    return success_response("docs_generate_diagram", elapsed_ms, data)


async def docs_generate_architecture(
    title: str = "",
    subtitle: str = "",
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a comprehensive, self-contained HTML architecture report.

    Produces a visually rich document with embedded SVG diagrams, detailed
    component descriptions, dependency flow visualizations, and API surface
    summary. The output is a single HTML file with no external dependencies.

    Sections included:
    - Project purpose and executive summary with key metrics
    - High-level architecture diagram (SVG with gradient-styled component boxes)
    - Component deep-dive with per-package descriptions and module listings
    - Dependency flow diagram (SVG with curved arrows showing import relationships)
    - Public API surface (classes, methods, docstrings)
    - Technology stack (runtime and development dependencies)

    Args:
        title: Custom report title (default: project name from metadata).
        subtitle: Custom subtitle / tagline (default: project description).
        output_path: File path to write the HTML report to. If empty, content
            is returned in the response without writing to disk.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_architecture")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_architecture",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.architecture import ArchitectureGenerator

    generator = ArchitectureGenerator()
    try:
        result = generator.generate(
            root,
            title=title,
            subtitle=subtitle,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_architecture",
            "GENERATION_ERROR",
            f"Failed to generate architecture report: {exc}",
        )

    if not result.content:
        return error_response(
            "docs_generate_architecture",
            "NO_CONTENT",
            "No content generated for architecture report.",
        )

    # Optionally write to disk (or content-return in Docker mode)
    written_path = ""
    if output_path and can_write_to_project(root):
        try:
            out = Path(output_path)
            if not out.is_absolute():
                out = root / out
            out.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(out.write_text, result.content, encoding="utf-8")
            written_path = str(out)
        except Exception as exc:
            return error_response(
                "docs_generate_architecture",
                "WRITE_ERROR",
                f"Failed to write architecture report: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "format": result.format,
        "package_count": result.package_count,
        "module_count": result.module_count,
        "edge_count": result.edge_count,
        "class_count": result.class_count,
        "content": result.content,
    }
    if written_path:
        data["written_to"] = written_path
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_architecture", result.content, output_path,
            description="Architecture report (HTML with SVG diagrams).",
        )

    return success_response(
        "docs_generate_architecture",
        elapsed_ms,
        data,
        next_steps=[
            "Open the HTML file in a browser for the full visual experience",
            "Use docs_generate_diagram for additional specific diagram types",
        ],
    )


async def docs_generate_epic(
    title: str,
    number: int = 0,
    purpose_and_intent: str = "",
    goal: str = "",
    motivation: str = "",
    status: str = "Proposed",
    priority: str = "",
    estimated_loe: str = "",
    dependencies: str = "",
    blocks: str = "",
    acceptance_criteria: str = "",
    stories: str = "",
    technical_notes: str = "",
    risks: str = "",
    non_goals: str = "",
    success_metrics: str = "",
    stakeholders: str = "",
    references: str = "",
    files: str = "",
    link_stories: bool = False,
    style: str = "standard",
    auto_populate: bool = False,
    quick_start: bool = False,
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate an Epic planning document with stories and acceptance criteria.

    Creates a structured epic document following agile best practices with
    metadata block, goal, motivation, acceptance criteria (checkbox list),
    numbered story stubs, technical notes, and out-of-scope items.

    The ``comprehensive`` style adds success metrics, stakeholders, references,
    implementation order, risk assessment with auto-classification, and files
    affected table with aggregated paths from stories.

    When ``auto_populate=True``, enriches sections from project analyzers
    (module map, tech stack, git history).

    When ``files`` is provided, generates a detailed Files Affected table
    with per-file analysis (line counts, recent git commits, public symbols)
    and a Related Epics section cross-referencing existing epics that mention
    the same files.

    Args:
        title: Epic title (e.g. "User Authentication System").
        number: Epic number for story numbering (e.g. 23 gives stories 23.1, 23.2).
        purpose_and_intent: Required per Epic 75.3. One paragraph: "We are doing this so that …".
        goal: One-paragraph description of what the epic achieves.
        motivation: Why this work matters.
        status: Epic status - "Proposed", "In Progress", "Complete",
            "Blocked", or "Cancelled".
        priority: Priority label (e.g. "P0 - Critical", "P1 - High").
        estimated_loe: Level of effort estimate (e.g. "~2-3 weeks (1 developer)").
        dependencies: Comma-separated list of dependencies (e.g. "Epic 0, Epic 4").
        blocks: Comma-separated list of epics this blocks.
        acceptance_criteria: Comma-separated list of acceptance criteria.
        stories: JSON array of story objects with keys: title, points, description,
            tasks, ac_count.
            Example: [{"title": "Data Models", "points": 3}]
        technical_notes: Comma-separated list of technical notes.
        risks: Comma-separated list of risks (comprehensive style only).
        non_goals: Comma-separated list of out-of-scope items.
        success_metrics: Comma-separated or pipe-delimited success metrics
            (comprehensive only). Example: "MTTR|4h|1h|PagerDuty"
        stakeholders: Comma-separated or pipe-delimited stakeholders
            (comprehensive only). Example: "Owner|Alice|Implementation"
        references: Comma-separated OKR/roadmap references (comprehensive only).
        files: Comma-separated file paths the epic affects. When provided with
            auto_populate, generates per-file analysis (line counts, git history,
            public symbols) and cross-references related epics.
        link_stories: When True, story stubs link to full story files.
        style: Epic style - "minimal", "standard", "comprehensive", or "auto".
            "auto" selects the style based on input complexity (stories, risks,
            files, success_metrics).
        auto_populate: Enrich from project analyzers (ModuleMap, Metadata, etc).
            Default False. On large projects this adds latency (module map
            walk, 8 expert consultations, git history). A 15 s wall-clock
            budget is enforced; steps that exceed it are skipped and partial
            results returned.
        quick_start: When True, infer defaults from the title alone -- goal,
            motivation, 3 story stubs, acceptance criteria, and priority are
            filled in automatically. Explicit parameters always override
            quick-start defaults. Style defaults to "auto" in quick-start mode.
        output_path: File path to write the epic (relative to project root).
            When empty, returns the content without writing a file.
        project_root: Override project root path (default: configured root).

    Returns:
        On success, ``data`` includes ``timing_ms`` (per-phase milliseconds:
        ``render_ms``, ``total_ms``, and when ``auto_populate=True``,
        ``metadata_ms``, ``module_map_ms``, ``git_ms``, ``experts_ms``,
        ``auto_populate_ms``).
    """
    _record_call("docs_generate_epic")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_epic",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.epics import EpicConfig, EpicGenerator, EpicStoryStub

    # Parse comma-separated lists
    dep_list = [d.strip() for d in dependencies.split(",") if d.strip()] if dependencies else []
    blocks_list = [b.strip() for b in blocks.split(",") if b.strip()] if blocks else []
    ac_list = (
        [a.strip() for a in acceptance_criteria.split(",") if a.strip()]
        if acceptance_criteria
        else []
    )
    notes_list = (
        [n.strip() for n in technical_notes.split(",") if n.strip()]
        if technical_notes
        else []
    )
    risks_list = [r.strip() for r in risks.split(",") if r.strip()] if risks else []
    ng_list = [n.strip() for n in non_goals.split(",") if n.strip()] if non_goals else []
    sm_list = (
        [s.strip() for s in success_metrics.split(",") if s.strip()]
        if success_metrics
        else []
    )
    sh_list = (
        [s.strip() for s in stakeholders.split(",") if s.strip()]
        if stakeholders
        else []
    )
    ref_list = (
        [r.strip() for r in references.split(",") if r.strip()]
        if references
        else []
    )

    # Parse stories JSON
    story_list: list[EpicStoryStub] = []
    if stories:
        try:
            story_list = EpicGenerator.parse_stories_json(stories)
        except ValueError as exc:
            return error_response(
                "docs_generate_epic",
                "INVALID_STORIES",
                str(exc),
            )

    # Parse files list
    files_list = (
        [f.strip() for f in files.split(",") if f.strip()] if files else []
    )

    config = EpicConfig(
        title=title,
        number=number,
        purpose_and_intent=purpose_and_intent.strip(),
        goal=goal,
        motivation=motivation,
        status=status,
        priority=priority,
        estimated_loe=estimated_loe,
        dependencies=dep_list,
        blocks=blocks_list,
        acceptance_criteria=ac_list,
        stories=story_list,
        technical_notes=notes_list,
        risks=risks_list,
        non_goals=ng_list,
        success_metrics=sm_list,
        stakeholders=sh_list,
        references=ref_list,
        files=files_list,
        link_stories=link_stories,
        style=style,
    )

    generator = EpicGenerator()

    # Pass project_root when auto_populate or files are provided
    needs_root = auto_populate or bool(files_list)

    try:
        content, timing_ms = generator.generate_with_timing(
            config,
            project_root=root if needs_root else None,
            auto_populate=auto_populate,
            quick_start=quick_start,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_epic",
            "GENERATION_ERROR",
            f"Failed to generate epic: {exc}",
        )

    # Optionally write to file (or content-return in Docker mode)
    written_path = ""
    if output_path and can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(output_path)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_epic",
                "WRITE_ERROR",
                f"Failed to write epic: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "title": title,
        "number": number,
        "style": style,
        "story_count": len(story_list),
        "auto_populated": auto_populate,
        "quick_start": quick_start,
        "content_length": len(content),
        "content": content,
        "timing_ms": timing_ms,
    }
    if written_path:
        data["written_to"] = written_path
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_epic", content, output_path,
            description=f"Epic planning document: {title}",
        )

    return success_response(
        "docs_generate_epic",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated epic and fill in placeholder sections.",
            "Use docs_generate_story to expand individual story stubs into full documents.",
            "Human-written sections (without docsmcp markers) will be preserved on re-generation.",
        ],
    )


async def docs_generate_story(
    title: str,
    epic_number: int = 0,
    story_number: int = 0,
    purpose_and_intent: str = "",
    role: str = "",
    want: str = "",
    so_that: str = "",
    description: str = "",
    points: int = 0,
    size: str = "",
    tasks: str = "",
    acceptance_criteria: str = "",
    test_cases: str = "",
    dependencies: str = "",
    files: str = "",
    technical_notes: str = "",
    criteria_format: str = "checkbox",
    style: str = "standard",
    inherit_context: bool = True,
    epic_path: str = "",
    auto_populate: bool = False,
    quick_start: bool = False,
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a User Story document with acceptance criteria and task breakdown.

    Creates a structured user story with "As a / I want / So that" statement,
    sizing, task checklist, acceptance criteria, and definition of done.

    The ``comprehensive`` style adds test cases, technical notes, dependencies,
    and an INVEST checklist.

    Acceptance criteria support two formats:
    - ``checkbox``: Checkbox list (default, best for technical stories)
    - ``gherkin``: Given/When/Then Gherkin format (best for user-facing behavior)

    When ``auto_populate=True``, enriches sections from project analyzers.
    When ``quick_start=True``, infers defaults from the title alone.

    Args:
        title: Story title (e.g. "Add login form validation").
        epic_number: Parent epic number (e.g. 23 for story numbering as 23.1).
        story_number: Story number within the epic (e.g. 1 for 23.1).
        purpose_and_intent: Required per Epic 75.3. One paragraph: "This story exists so that …".
        role: User role for the story statement (e.g. "developer").
        want: Desired capability (e.g. "to validate login credentials").
        so_that: Benefit/reason (e.g. "invalid logins are rejected").
        description: Detailed description of the story.
        points: Story points estimate.
        size: T-shirt size - "S", "M", "L", or "XL".
        tasks: JSON array of task objects with keys: description, file_path.
            Example: [{"description": "Create model", "file_path": "src/models.py"}]
        acceptance_criteria: Comma-separated list of acceptance criteria.
        test_cases: Comma-separated list of test cases (comprehensive style only).
        dependencies: Comma-separated list of dependencies.
        files: Comma-separated list of affected file paths.
        technical_notes: Comma-separated list of technical notes.
        criteria_format: Acceptance criteria format - "checkbox" or "gherkin".
        style: Story style - "standard" or "comprehensive".
        inherit_context: When True, skip project metadata in story (inherit from epic).
        epic_path: Relative path to parent epic file for cross-referencing.
        auto_populate: Enrich from project analyzers (ModuleMap, Metadata).
        quick_start: When True, infer defaults from the title alone -- role, want,
            so_that, points, size, tasks, and acceptance criteria are filled in
            automatically. Explicit parameters always override quick-start defaults.
        output_path: File path to write the story (relative to project root).
            When empty, returns the content without writing a file.
            When set with ``epic_path``, the epic link is rewritten relative to
            this file (e.g. ``../EPIC-99.md`` for stories in a subdirectory).
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_story")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_story",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    import json as json_mod

    from docs_mcp.generators.stories import StoryConfig, StoryGenerator, StoryTask

    # Parse comma-separated lists
    ac_list = (
        [a.strip() for a in acceptance_criteria.split(",") if a.strip()]
        if acceptance_criteria
        else []
    )
    tc_list = (
        [t.strip() for t in test_cases.split(",") if t.strip()] if test_cases else []
    )
    dep_list = [d.strip() for d in dependencies.split(",") if d.strip()] if dependencies else []
    file_list = [f.strip() for f in files.split(",") if f.strip()] if files else []
    notes_list = (
        [n.strip() for n in technical_notes.split(",") if n.strip()]
        if technical_notes
        else []
    )

    # Parse tasks JSON (or pre-parsed list from MCP clients)
    task_list: list[StoryTask] = []
    if tasks:
        try:
            raw: Any = tasks if isinstance(tasks, list) else json_mod.loads(tasks)
            if not isinstance(raw, list):
                return error_response(
                    "docs_generate_story",
                    "INVALID_TASKS",
                    "Tasks JSON must be a list of objects",
                )
            for item in raw:
                if isinstance(item, dict):
                    task_list.append(
                        StoryTask(
                            description=str(item.get("description", "")),
                            file_path=str(item.get("file_path", "")),
                        )
                    )
        except json_mod.JSONDecodeError as exc:
            return error_response(
                "docs_generate_story",
                "INVALID_TASKS",
                f"Invalid JSON for tasks: {exc}",
            )

    config = StoryConfig(
        title=title,
        epic_number=epic_number,
        story_number=story_number,
        purpose_and_intent=purpose_and_intent.strip(),
        role=role,
        want=want,
        so_that=so_that,
        description=description,
        points=points,
        size=size,
        tasks=task_list,
        acceptance_criteria=ac_list,
        test_cases=tc_list,
        dependencies=dep_list,
        files=file_list,
        technical_notes=notes_list,
        criteria_format=criteria_format,
        style=style,
        inherit_context=inherit_context,
        epic_path=epic_path,
    )

    generator = StoryGenerator()

    try:
        content = generator.generate(
            config,
            project_root=root if auto_populate else None,
            auto_populate=auto_populate,
            quick_start=quick_start,
            output_path=output_path or "",
        )
    except Exception as exc:
        return error_response(
            "docs_generate_story",
            "GENERATION_ERROR",
            f"Failed to generate story: {exc}",
        )

    # Optionally write to file (or content-return in Docker mode)
    written_path = ""
    if output_path and can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(output_path)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_story",
                "WRITE_ERROR",
                f"Failed to write story: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "title": title,
        "epic_number": epic_number,
        "story_number": story_number,
        "style": style,
        "criteria_format": criteria_format,
        "task_count": len(task_list),
        "auto_populated": auto_populate,
        "quick_start": quick_start,
        "content_length": len(content),
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_story", content, output_path,
            description=f"User story: {title}",
        )

    return success_response(
        "docs_generate_story",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated story and fill in placeholder sections.",
            "Use docs_generate_epic to create the parent epic if not yet created.",
            "Human-written sections (without docsmcp markers) will be preserved on re-generation.",
        ],
    )


async def docs_generate_prompt(
    name: str,
    when_to_use: str = "",
    purpose_and_intent: str = "",
    task: str = "",
    success_criteria: str = "",
    context_files: str = "",
    reference_notes: str = "",
    rules: str = "",
    conversation_first: bool = False,
    plan_steps: int = 0,
    alignment_required: bool = False,
    allowed_tools: str = "",
    output_format: str = "",
    dont: str = "",
    style: str = "standard",
    compact_llm_view: bool = False,
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a prompt artifact (Epic 75). LLM-facing prompt doc with docsmcp markers.

    Creates a structured prompt with Purpose & Intent (required), task, context files,
    success brief, rules, optional conversation/plan/alignment, allowed tools, output format.
    When compact_llm_view=True, emits a token-efficient view (goal + criteria + steps + rules)
    targeting ≤~1.5K tokens (Epic 75.4).

    Args:
        name: Prompt name (e.g. "quality-gate-workflow").
        when_to_use: When and why this prompt is used.
        purpose_and_intent: Required. One paragraph: "This prompt is for … so that …".
        task: "I want to [TASK] so that [SUCCESS CRITERIA]."
        success_criteria: Definition of success.
        context_files: JSON array of {"path": "...", "description": "..."}.
        reference_notes: Optional reference / blueprint notes.
        rules: Standards, constraints, landmines.
        conversation_first: If True, add "ask clarifying questions first" section.
        plan_steps: Number of plan steps (0 = omit plan section).
        alignment_required: If True, add "Only begin once we've aligned" section.
        allowed_tools: Comma-separated list of MCP tool names.
        output_format: Expected output format (e.g. JSON schema, markdown structure).
        dont: Comma-separated list of "don't" items.
        style: "standard" or "comprehensive".
        compact_llm_view: When True, generate compact view only (≤~1.5K tokens) for LLM context.
        output_path: File path to write (relative to project root). Empty = docs/prompts/{name}.md.
        project_root: Override project root.
    """
    _record_call("docs_generate_prompt")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_prompt",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    import json as json_mod

    from docs_mcp.generators.prompts import (
        ContextFileEntry,
        PromptConfig,
        PromptGenerator,
    )

    if not name.strip():
        return error_response(
            "docs_generate_prompt",
            "INVALID_NAME",
            "name is required",
        )

    purpose = purpose_and_intent.strip() or "This prompt is for the given task so that success criteria are met."

    cf_list: list[ContextFileEntry] = []
    if context_files:
        try:
            raw = json_mod.loads(context_files) if isinstance(context_files, str) else context_files
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        cf_list.append(ContextFileEntry(path=item.get("path", ""), description=item.get("description", "")))
                    else:
                        cf_list.append(ContextFileEntry(path=str(item), description=""))
        except (json_mod.JSONDecodeError, TypeError):
            pass

    tools_list = [t.strip() for t in allowed_tools.split(",") if t.strip()] if allowed_tools else []
    dont_list = [d.strip() for d in dont.split(",") if d.strip()] if dont else []

    config = PromptConfig(
        name=name.strip(),
        when_to_use=when_to_use.strip(),
        purpose_and_intent=purpose,
        task=task.strip(),
        success_criteria=success_criteria.strip(),
        context_files=cf_list,
        reference_notes=reference_notes.strip(),
        success_brief=None,
        rules=rules.strip(),
        conversation_first=conversation_first,
        plan_steps=plan_steps if plan_steps else False,
        alignment_required=alignment_required,
        allowed_tools=tools_list,
        output_format=output_format.strip(),
        dont=dont_list,
        style=style if style in ("standard", "comprehensive") else "standard",
    )

    gen = PromptGenerator()
    content = (
        gen.generate_compact(config) if compact_llm_view else gen.generate(config)
    )

    written_path = ""
    slug = name.strip().replace(" ", "-").lower()
    if not slug.endswith(".md"):
        slug += ".md"
    rel = output_path.strip() or f"docs/prompts/{slug}"
    if not rel.endswith(".md"):
        rel += ".md"
    if can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(rel)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_prompt",
                "WRITE_ERROR",
                f"Failed to write prompt: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    data: dict[str, Any] = {
        "name": name,
        "style": style,
        "content_length": len(content),
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    else:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_prompt", content, rel,
            description=f"Prompt template: {name}",
        )

    return success_response(
        "docs_generate_prompt",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated prompt and refine Purpose & Intent and rules.",
            "Use as context for the LLM or register as an MCP prompt template.",
        ],
    )


# ---------------------------------------------------------------------------
# Epic 83: llms.txt & Frontmatter tools
# ---------------------------------------------------------------------------


async def docs_generate_llms_txt(
    mode: str = "compact",
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate an llms.txt file for AI-readable project documentation.

    Produces a structured machine-readable summary of the project including
    tech stack, entry points, key files, and documentation map. Follows the
    emerging llms.txt standard for AI coding assistant consumption.

    Args:
        mode: Output mode - "compact" (default) or "full" (includes API summary
            and project structure).
        output_path: File path to write (relative to project root). Typically
            "llms.txt" or "llms-full.txt". When empty, returns content only.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_llms_txt")
    start = time.perf_counter_ns()

    if mode not in ("compact", "full"):
        return error_response(
            "docs_generate_llms_txt",
            "INVALID_MODE",
            f"Invalid mode {mode!r}. Use 'compact' or 'full'.",
        )

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_llms_txt",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.llms_txt import LlmsTxtGenerator

    try:
        # Optionally get module map for full mode
        module_map = None
        if mode == "full":
            try:
                from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

                analyzer = ModuleMapAnalyzer()
                module_map = analyzer.analyze(root)
            except Exception:
                pass  # Degrade gracefully

        generator = LlmsTxtGenerator(mode=mode)
        result = generator.generate(root, module_map=module_map)
        content = result.content
    except Exception as exc:
        return error_response(
            "docs_generate_llms_txt",
            "GENERATION_ERROR",
            f"Failed to generate llms.txt: {exc}",
        )

    # Optionally write to file
    written_path = ""
    if output_path and can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(output_path)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_llms_txt",
                "WRITE_ERROR",
                f"Failed to write llms.txt: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "mode": result.mode,
        "section_count": result.section_count,
        "project_name": result.project_name,
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_llms_txt", content, output_path,
            description="Machine-readable llms.txt project summary for AI assistants.",
        )

    return success_response(
        "docs_generate_llms_txt",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated llms.txt and verify project details are accurate.",
            "Commit llms.txt to the repository root for AI assistant discovery.",
        ],
    )


async def docs_generate_frontmatter(
    file_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Add or update YAML frontmatter in a markdown file.

    Auto-detects title, description, tags, and Diataxis content type from the
    document content. Preserves existing frontmatter fields while merging new
    auto-detected values.

    Args:
        file_path: Path to the markdown file (relative to project root).
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_frontmatter")
    start = time.perf_counter_ns()

    if not file_path:
        return error_response(
            "docs_generate_frontmatter",
            "MISSING_PATH",
            "file_path is required.",
        )

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_frontmatter",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    target = (root / file_path).resolve()
    if not target.exists():
        return error_response(
            "docs_generate_frontmatter",
            "FILE_NOT_FOUND",
            f"File not found: {file_path}",
        )

    if target.suffix.lower() not in (".md", ".mdx", ".markdown"):
        return error_response(
            "docs_generate_frontmatter",
            "INVALID_FILE_TYPE",
            "Only markdown files (.md, .mdx, .markdown) are supported.",
        )

    from docs_mcp.generators.frontmatter import FrontmatterGenerator

    try:
        original = await asyncio.to_thread(target.read_text, encoding="utf-8")
        generator = FrontmatterGenerator()
        result = generator.generate(original, file_path=target)
        content = result.content
    except Exception as exc:
        return error_response(
            "docs_generate_frontmatter",
            "GENERATION_ERROR",
            f"Failed to generate frontmatter: {exc}",
        )

    # Write back if we can
    written_path = ""
    if can_write_to_project(root):
        try:
            await asyncio.to_thread(target.write_text, content, encoding="utf-8")
            written_path = str(target.relative_to(root)).replace("\\", "/")
        except OSError as exc:
            return error_response(
                "docs_generate_frontmatter",
                "WRITE_ERROR",
                f"Failed to write frontmatter: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "file_path": file_path,
        "fields_added": result.fields_added,
        "fields_preserved": result.fields_preserved,
        "had_existing": result.had_existing,
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    elif not can_write_to_project(root):
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_frontmatter", content, file_path,
            description=f"Markdown file with updated YAML frontmatter: {file_path}",
        )

    return success_response(
        "docs_generate_frontmatter",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated frontmatter fields for accuracy.",
            "Run docs_check_completeness to see improved documentation scoring.",
        ],
    )


# ---------------------------------------------------------------------------
# Epic 81.3: Interactive HTML diagrams
# ---------------------------------------------------------------------------


async def docs_generate_interactive_diagrams(
    diagram_types: str = "dependency,module_map",
    title: str = "",
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate an interactive HTML page with Mermaid.js diagrams.

    Creates a self-contained HTML file with pan/zoom controls, diagram
    toggling, and a table of contents. Each requested diagram type is
    generated in Mermaid format and embedded in the interactive viewer.

    Args:
        diagram_types: Comma-separated diagram types to include.
            Valid types: dependency, class_hierarchy, module_map, er_diagram,
            c4_context, c4_container, c4_component.
        title: Page title (default: project name + " Architecture").
        output_path: File path to write HTML (relative to project root).
            When empty, returns content only.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_interactive_diagrams")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_interactive_diagrams",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.diagrams import DiagramGenerator
    from docs_mcp.generators.interactive_html import InteractiveHtmlGenerator

    types_list = [t.strip() for t in diagram_types.split(",") if t.strip()]
    if not types_list:
        return error_response(
            "docs_generate_interactive_diagrams",
            "NO_TYPES",
            "At least one diagram_type is required.",
        )

    # Generate each diagram in Mermaid format
    diagram_gen = DiagramGenerator()
    diagrams: list[tuple[str, str]] = []
    type_labels = {
        "dependency": "Dependency Graph",
        "class_hierarchy": "Class Hierarchy",
        "module_map": "Module Map",
        "er_diagram": "ER Diagram",
        "c4_context": "C4 System Context",
        "c4_container": "C4 Container",
        "c4_component": "C4 Component",
    }

    for dt in types_list:
        if dt not in DiagramGenerator.VALID_TYPES:
            continue
        try:
            result = diagram_gen.generate(
                root, diagram_type=dt, output_format="mermaid"
            )
            if result.content:
                label = type_labels.get(dt, dt.replace("_", " ").title())
                diagrams.append((label, result.content))
        except Exception:
            logger.debug("interactive_diagram_failed", diagram_type=dt)

    if not diagrams:
        return error_response(
            "docs_generate_interactive_diagrams",
            "NO_DIAGRAMS",
            "No diagrams could be generated for the requested types.",
        )

    # Build interactive HTML
    page_title = title or f"{root.name} Architecture"
    html_gen = InteractiveHtmlGenerator()
    html_result = html_gen.generate(
        diagrams, title=page_title, subtitle=f"Generated from {root.name}"
    )
    content = html_result.content

    # Optionally write to file
    written_path = ""
    if output_path and can_write_to_project(root):
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(output_path)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_interactive_diagrams",
                "WRITE_ERROR",
                f"Failed to write interactive diagrams: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "diagram_count": html_result.diagram_count,
        "title": html_result.title,
        "content_length": len(content),
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_interactive_diagrams", content, output_path,
            description="Interactive HTML architecture diagrams with Mermaid.js.",
        )

    return success_response(
        "docs_generate_interactive_diagrams",
        elapsed_ms,
        data,
        next_steps=[
            "Open the HTML file in a browser to explore the interactive diagrams.",
            "Use the zoom and toggle controls to navigate complex architectures.",
        ],
    )


# ---------------------------------------------------------------------------
# docs_generate_purpose (Epic 85.1)
# ---------------------------------------------------------------------------


async def docs_generate_purpose(
    project_root: str = "",
    output_path: str = "",
    project_name: str = "",
) -> dict[str, Any]:
    """Generate a purpose/intent architecture template for a project.

    Produces a structured markdown template covering project purpose,
    design principles, key architectural decisions, intended audience,
    and quality attributes. Principles and decisions are inferred from
    project dependencies and structure.

    Args:
        project_root: Path to the project root. Defaults to configured root.
        output_path: Optional output file path (relative to project root).
            When empty, content is returned without writing.
        project_name: Override the project name in the template.
    """
    _record_call("docs_generate_purpose")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else settings.project_root

    if not root.is_dir():
        return error_response(
            "docs_generate_purpose",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.purpose import PurposeGenerator

    try:
        gen = PurposeGenerator()
        result = gen.generate(root, project_name=project_name)
    except Exception as exc:
        return error_response(
            "docs_generate_purpose",
            "GENERATION_ERROR",
            f"Failed to generate purpose template: {exc}",
        )

    if not result.content:
        return error_response(
            "docs_generate_purpose",
            "NO_CONTENT",
            "No content generated for purpose template.",
        )

    content = result.content
    written_path = ""

    if output_path and can_write_to_project(root):
        write_path = root / output_path
        try:
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_purpose",
                "WRITE_ERROR",
                f"Failed to write purpose template: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "sections": result.sections,
        "degraded": result.degraded,
        "content_length": len(content),
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_purpose", content, output_path,
            description="Architecture purpose/intent template.",
        )

    return success_response(
        "docs_generate_purpose",
        elapsed_ms,
        data,
        next_steps=[
            "Fill in the [placeholder] sections with project-specific details.",
            "Generate ADRs with docs_generate_adr for key decisions.",
            "Run docs_check_completeness to verify documentation coverage.",
        ],
    )


# ---------------------------------------------------------------------------
# docs_generate_doc_index (Epic 85.2)
# ---------------------------------------------------------------------------


async def docs_generate_doc_index(
    doc_dirs: str = "",
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a documentation index/map for a project.

    Scans for documentation files, extracts titles and descriptions,
    categorizes them, and produces a structured markdown index with
    category groupings and freshness indicators.

    Args:
        doc_dirs: Comma-separated list of directories to scan.
            When empty, scans the entire project.
        output_path: Optional output file path (relative to project root).
            When empty, content is returned without writing.
        project_root: Path to the project root. Defaults to configured root.
    """
    _record_call("docs_generate_doc_index")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else settings.project_root

    if not root.is_dir():
        return error_response(
            "docs_generate_doc_index",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.doc_index import DocIndexGenerator

    dirs_list: list[str] | None = None
    if doc_dirs:
        dirs_list = [d.strip() for d in doc_dirs.split(",") if d.strip()]

    try:
        gen = DocIndexGenerator()
        result = gen.generate(root, doc_dirs=dirs_list)
    except Exception as exc:
        return error_response(
            "docs_generate_doc_index",
            "GENERATION_ERROR",
            f"Failed to generate doc index: {exc}",
        )

    content = result.content
    written_path = ""

    if output_path and can_write_to_project(root):
        write_path = root / output_path
        try:
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            written_path = str(write_path.relative_to(root)).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(
                "docs_generate_doc_index",
                "WRITE_ERROR",
                f"Failed to write doc index: {exc}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "total_files": result.total_files,
        "categories": result.categories,
        "content_length": len(content),
        "content": content,
    }
    if written_path:
        data["written_to"] = written_path
    elif output_path:
        data["content_return"] = True
        data["file_manifest"] = build_generator_manifest(
            "docs_generate_doc_index", content, output_path,
            description="Documentation index/map.",
        )

    return success_response(
        "docs_generate_doc_index",
        elapsed_ms,
        data,
        next_steps=[
            "Review the index for orphan or uncategorized documents.",
            "Run docs_check_cross_refs to validate cross-references between documents.",
            "Use docs_check_completeness for a broader documentation health check.",
        ],
    )


# ---------------------------------------------------------------------------
# Registration (Epic 79.2: conditional)
# ---------------------------------------------------------------------------


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register generation tools on the shared mcp instance (Epic 79.2: conditional)."""
    if "docs_generate_changelog" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_changelog)
    if "docs_generate_release_notes" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_generate_release_notes)
    if "docs_generate_readme" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_readme)
    if "docs_generate_api" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_api)
    if "docs_generate_adr" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_adr)
    if "docs_generate_onboarding" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_onboarding)
    if "docs_generate_contributing" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_contributing)
    if "docs_generate_prd" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_prd)
    if "docs_generate_diagram" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_generate_diagram)
    if "docs_generate_architecture" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_architecture)
    if "docs_generate_epic" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_epic)
    if "docs_generate_story" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_story)
    if "docs_generate_prompt" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_prompt)
    if "docs_generate_llms_txt" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_llms_txt)
    if "docs_generate_frontmatter" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_frontmatter)
    if "docs_generate_interactive_diagrams" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_interactive_diagrams)
    if "docs_generate_purpose" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_purpose)
    if "docs_generate_doc_index" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(docs_generate_doc_index)
