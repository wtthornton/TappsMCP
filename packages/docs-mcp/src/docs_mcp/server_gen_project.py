"""Project-level DocsMCP generation tools.

README, API reference, ADRs, llms.txt, frontmatter, doc index, and the
purpose/intent template. Split out of ``server_gen_tools.py`` under
TAP-5608 — that module is now a registration facade that re-exports
these handlers.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import structlog

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

    # Resolve relative path for output
    if out.is_relative_to(root):
        rel_path = str(out.relative_to(root)).replace("\\", "/")
    else:
        rel_path = str(out)

    # Three-tier output: write-first / inline / manifest
    out_result = await finalize_output(
        "docs_generate_readme",
        final_content,
        rel_path,
        root,
        description="Project README.",
    )
    if not out_result.get("success", True):
        return out_result

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "style": style,
        **merge_stats,
        **out_result,
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

    # Auto-compute output_path when not provided
    if output_path.strip():
        target = output_path.strip()
    else:
        # Derive from source_path: docs/api/{source}.md
        slug = Path(source_path).stem if source_path else "reference"
        ext = ".rst" if format == "sphinx_rst" else ".md"
        target = f"docs/api/{slug}{ext}"

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_api",
        content,
        target,
        root,
        description="API reference documentation.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "format": format,
        "depth": depth,
        **out,
    }

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

    # Resolve the target path
    write_target = output_path or filename
    if not Path(write_target).is_absolute():
        adr_base = str(adr_dir) if adr_dir else "docs/decisions"
        adr_rel = f"{adr_base}/{write_target}"
    else:
        adr_rel = write_target

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_adr",
        content,
        adr_rel,
        root,
        description=f"Architecture Decision Record: {title}",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "template": template,
        "filename": filename,
        **out,
    }

    return success_response("docs_generate_adr", elapsed_ms, data)


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

    # Auto-compute output_path when not provided
    if output_path.strip():
        target = output_path.strip()
    else:
        target = "llms-full.txt" if mode == "full" else "llms.txt"

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_llms_txt",
        content,
        target,
        root,
        description="Machine-readable llms.txt project summary for AI assistants.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "mode": result.mode,
        "project_name": result.project_name,
        **out,
    }

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

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_frontmatter",
        content,
        file_path,
        root,
        description=f"Markdown file with updated YAML frontmatter: {file_path}",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "file_path": file_path,
        "fields_added": result.fields_added,
        "fields_preserved": result.fields_preserved,
        "had_existing": result.had_existing,
        **out,
    }

    return success_response(
        "docs_generate_frontmatter",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated frontmatter fields for accuracy.",
            "Run docs_check_completeness to see improved documentation scoring.",
        ],
    )


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

    # Auto-compute output_path when not provided
    target = output_path.strip() or "docs/PURPOSE.md"

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_purpose",
        content,
        target,
        root,
        description="Architecture purpose/intent template.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "sections": result.sections,
        "degraded": result.degraded,
        **out,
    }

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

    # Auto-compute output_path when not provided
    target = output_path.strip() or "docs/INDEX.md"

    try:
        gen = DocIndexGenerator()
        result = gen.generate(root, doc_dirs=dirs_list, output_path=target)
    except Exception as exc:
        return error_response(
            "docs_generate_doc_index",
            "GENERATION_ERROR",
            f"Failed to generate doc index: {exc}",
        )

    content = result.content

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_doc_index",
        content,
        target,
        root,
        description="Documentation index/map.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "total_files": result.total_files,
        "categories": result.categories,
        **out,
    }

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
