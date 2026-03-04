"""DocsMCP generation tools.

Registers generation tools on the shared ``mcp`` FastMCP instance from
``server.py``: README, changelog, release notes, API docs, ADR,
onboarding/contributing guides, and diagrams.
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


@mcp.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)
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

    return success_response("docs_generate_api", elapsed_ms, data)


@mcp.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)
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

    # Write the ADR file
    write_target = output_path if output_path else filename
    written_path = ""
    try:
        from tapps_core.security.path_validator import PathValidator

        validator = PathValidator(root)
        actual_dir = adr_dir if adr_dir else root / "docs" / "decisions"
        full_path = actual_dir / write_target if not Path(write_target).is_absolute() else Path(
            write_target,
        )
        write_path = validator.validate_write_path(str(full_path))
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(content, encoding="utf-8")
        written_path = str(write_path.relative_to(root)).replace("\\", "/")
    except (ValueError, FileNotFoundError, OSError) as exc:
        return error_response(
            "docs_generate_adr",
            "WRITE_ERROR",
            f"Failed to write ADR: {exc}",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "template": template,
        "filename": filename,
        "written_to": written_path,
        "content": content,
    }

    return success_response("docs_generate_adr", elapsed_ms, data)


@mcp.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)
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

    # Write to file
    target = output_path if output_path else "docs/ONBOARDING.md"
    written_path = ""
    try:
        from tapps_core.security.path_validator import PathValidator

        validator = PathValidator(root)
        write_path = validator.validate_write_path(target)
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(content, encoding="utf-8")
        written_path = str(write_path.relative_to(root)).replace("\\", "/")
    except (ValueError, FileNotFoundError, OSError) as exc:
        return error_response(
            "docs_generate_onboarding",
            "WRITE_ERROR",
            f"Failed to write onboarding guide: {exc}",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "written_to": written_path,
        "content_length": len(content),
        "content": content,
    }

    return success_response("docs_generate_onboarding", elapsed_ms, data)


@mcp.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)
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

    # Write to file
    target = output_path if output_path else "CONTRIBUTING.md"
    written_path = ""
    try:
        from tapps_core.security.path_validator import PathValidator

        validator = PathValidator(root)
        write_path = validator.validate_write_path(target)
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(content, encoding="utf-8")
        written_path = str(write_path.relative_to(root)).replace("\\", "/")
    except (ValueError, FileNotFoundError, OSError) as exc:
        return error_response(
            "docs_generate_contributing",
            "WRITE_ERROR",
            f"Failed to write contributing guide: {exc}",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "written_to": written_path,
        "content_length": len(content),
        "content": content,
    }

    return success_response("docs_generate_contributing", elapsed_ms, data)


@mcp.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)
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

    return success_response(
        "docs_generate_prd",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated PRD and fill in placeholder sections.",
            "Human-written sections (without docsmcp markers) will be preserved on re-generation.",
        ],
    )


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def docs_generate_diagram(
    diagram_type: str = "dependency",
    scope: str = "project",
    depth: int = 2,
    format: str = "",
    direction: str = "TD",
    show_external: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    """Generate Mermaid or PlantUML diagrams from code analysis.

    Diagram types:
    - "dependency": Module import dependency flowchart
    - "class_hierarchy": Class inheritance diagram
    - "module_map": Package/module architecture overview
    - "er_diagram": Entity-relationship diagram from Pydantic/dataclass models

    Args:
        diagram_type: Type of diagram to generate.
        scope: "project" for full project, or a file path for single-file scope.
        depth: Max traversal depth for dependency/module diagrams (default: 2).
        format: Output format - "mermaid" or "plantuml" (default: from config).
        direction: Graph direction - "TD" (top-down) or "LR" (left-right).
        show_external: Include external dependencies in dependency diagrams.
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
