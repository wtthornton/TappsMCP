"""MCP resources and workflow prompts for DocsMCP.

Registers MCP resources (docs://status, docs://config, docs://coverage) and
workflow prompts (docs_workflow_overview, docs_workflow) on the shared ``mcp``
FastMCP instance from ``server.py``.
"""

from __future__ import annotations

import structlog

from docs_mcp.server import mcp

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("docs://status")
def _docs_status() -> str:
    """Current documentation state summary.

    Scans the project for documentation files and returns a markdown summary
    of what exists, what is missing, and a completeness score.
    """
    from docs_mcp.config.settings import load_docs_settings
    from docs_mcp.server import _calculate_completeness, _scan_doc_files

    settings = load_docs_settings()
    root = settings.project_root

    all_docs = _scan_doc_files(root)

    # Categorize
    categories: dict[str, list[dict[str, object]]] = {
        "readme": [],
        "changelog": [],
        "contributing": [],
        "license": [],
        "security": [],
        "code_of_conduct": [],
        "api_docs": [],
        "adr": [],
        "guides": [],
        "other": [],
    }
    for doc in all_docs:
        cat = doc.get("category", "other")
        if cat not in categories:
            cat = "other"
        categories[cat].append(doc)

    # Critical docs check
    from docs_mcp.server import _CRITICAL_DOCS

    existing_basenames = {
        d["path"].rsplit("/", 1)[-1].lower() for d in all_docs  # type: ignore[union-attr]
    }
    existing_paths = {d["path"].lower() for d in all_docs}  # type: ignore[union-attr]

    critical_docs: dict[str, dict[str, object]] = {}
    for doc_name in _CRITICAL_DOCS:
        doc_lower = doc_name.lower()
        name_no_ext = doc_lower.rsplit(".", 1)[0] if "." in doc_lower else doc_lower
        found = (
            doc_lower in existing_paths
            or doc_lower in existing_basenames
            or name_no_ext in existing_basenames
        )
        critical_docs[doc_name] = {"exists": found}

    score = _calculate_completeness(categories, critical_docs, all_docs)  # type: ignore[arg-type]

    # Build markdown summary
    lines = [
        "# Documentation Status",
        "",
        f"**Project root:** `{root}`",
        f"**Total docs:** {len(all_docs)}",
        f"**Completeness score:** {score}/100",
        "",
        "## Critical Documents",
        "",
    ]
    for name, info in critical_docs.items():
        status = "present" if info["exists"] else "MISSING"
        lines.append(f"- {name}: {status}")

    lines.append("")
    lines.append("## Categories")
    lines.append("")
    for cat, docs in categories.items():
        if docs:
            lines.append(f"- **{cat}**: {len(docs)} file(s)")

    return "\n".join(lines)


@mcp.resource("docs://config")
def _docs_config_resource() -> str:
    """Active DocsMCP configuration.

    Returns the current settings as a markdown-formatted summary.
    """
    from docs_mcp.config.settings import load_docs_settings

    settings = load_docs_settings()

    lines = [
        "# DocsMCP Configuration",
        "",
        f"- **project_root:** `{settings.project_root}`",
        f"- **output_dir:** {settings.output_dir}",
        f"- **default_style:** {settings.default_style}",
        f"- **default_format:** {settings.default_format}",
        f"- **include_toc:** {settings.include_toc}",
        f"- **include_badges:** {settings.include_badges}",
        f"- **changelog_format:** {settings.changelog_format}",
        f"- **adr_format:** {settings.adr_format}",
        f"- **diagram_format:** {settings.diagram_format}",
        f"- **git_log_limit:** {settings.git_log_limit}",
        f"- **log_level:** {settings.log_level}",
        f"- **log_json:** {settings.log_json}",
    ]
    return "\n".join(lines)


@mcp.resource("docs://coverage")
def _docs_coverage_resource() -> str:
    """Documentation coverage report.

    Runs the completeness checker and returns a markdown-formatted coverage
    report with per-category scores and recommendations.
    """
    from docs_mcp.config.settings import load_docs_settings
    from docs_mcp.validators.completeness import CompletenessChecker

    settings = load_docs_settings()
    root = settings.project_root

    checker = CompletenessChecker()
    report = checker.check(root)

    lines = [
        "# Documentation Coverage Report",
        "",
        f"**Overall score:** {report.overall_score:.0f}/100",
        "",
        "## Categories",
        "",
    ]
    for cat in report.categories:
        pct = cat.score * 100
        present_str = ", ".join(cat.present) if cat.present else "none"
        missing_str = ", ".join(cat.missing) if cat.missing else "none"
        lines.append(f"### {cat.name} ({pct:.0f}%)")
        lines.append(f"- Present: {present_str}")
        lines.append(f"- Missing: {missing_str}")
        lines.append("")

    if report.recommendations:
        lines.append("## Recommendations")
        lines.append("")
        for rec in report.recommendations:
            lines.append(f"- {rec}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workflow prompts
# ---------------------------------------------------------------------------

_TOOL_REFERENCE = """\
## DocsMCP Tool Reference (18 tools)

### Discovery & Setup
- **docs_session_start** - Initialize a session; detects project type, scans existing docs, returns config and recommendations
- **docs_project_scan** - Comprehensive documentation audit with completeness scoring and category breakdown
- **docs_config** - View or update DocsMCP configuration (output_dir, style, format, etc.)
- **docs_module_map** - Build a hierarchical module map of a Python project via AST parsing
- **docs_api_surface** - Extract the public API surface (functions, classes, constants) from source code
- **docs_git_summary** - Analyze git history: recent commits, version boundaries, contributor stats

### Generation
- **docs_generate_readme** - Generate or update README.md with project metadata, install instructions, and API overview
- **docs_generate_api** - Generate API reference documentation from source code
- **docs_generate_changelog** - Generate CHANGELOG.md from git history (Keep-a-Changelog or Conventional)
- **docs_generate_release_notes** - Generate release notes for a specific version or tag range
- **docs_generate_adr** - Generate an Architecture Decision Record (MADR or Nygard format)
- **docs_generate_onboarding** - Generate an onboarding/getting-started guide
- **docs_generate_contributing** - Generate a CONTRIBUTING.md with project-specific guidelines
- **docs_generate_diagram** - Generate architecture diagrams (dependency, module, class, sequence) in Mermaid or PlantUML

### Validation
- **docs_check_drift** - Detect documentation drift: code changes not reflected in docs
- **docs_check_completeness** - Check documentation completeness across categories with scoring
- **docs_check_links** - Validate links in documentation files (internal cross-references)
- **docs_check_freshness** - Check documentation freshness based on last-modified dates vs code changes
"""

_WORKFLOW_OVERVIEW = f"""\
# DocsMCP Workflow Guide

DocsMCP provides 18 MCP tools organized into three phases: Discovery, Generation, and Validation. Follow this workflow for comprehensive documentation management.

## Recommended Workflow

### Phase 1: Discovery
Start every session by understanding the current state of documentation.

1. **docs_session_start** - Always call first. Returns project type, existing docs, config, and recommendations.
2. **docs_project_scan** - Deep audit of documentation state with completeness score and category breakdown.
3. **docs_module_map** / **docs_api_surface** - Understand code structure before generating docs.
4. **docs_git_summary** - Review recent changes for changelogs and release notes.

### Phase 2: Generation
Generate or update documentation based on discovery findings.

5. **docs_generate_readme** - Create or update the project README.
6. **docs_generate_api** - Generate API reference from source code.
7. **docs_generate_changelog** / **docs_generate_release_notes** - Create version history docs.
8. **docs_generate_adr** - Record architectural decisions.
9. **docs_generate_onboarding** / **docs_generate_contributing** - Create contributor guides.
10. **docs_generate_diagram** - Visualize architecture and dependencies.

### Phase 3: Validation
Verify documentation quality after generation or code changes.

11. **docs_check_drift** - Ensure docs reflect current code.
12. **docs_check_completeness** - Verify all categories are covered.
13. **docs_check_links** - Validate internal cross-references.
14. **docs_check_freshness** - Flag stale documentation.

{_TOOL_REFERENCE}"""

_TASK_WORKFLOWS: dict[str, str] = {
    "bootstrap": """\
# DocsMCP Workflow: Bootstrap

Bootstrap documentation for a project from scratch.

## Steps

1. **docs_session_start** - Detect project type and scan for any existing docs.
2. **docs_project_scan** - Get a full inventory and completeness score (likely low).
3. **docs_module_map** - Understand the code structure.
4. **docs_api_surface** - Identify public APIs that need documentation.
5. **docs_generate_readme** - Create the project README first (most important doc).
6. **docs_generate_api** - Generate API reference from source code.
7. **docs_generate_contributing** - Add contributor guidelines.
8. **docs_generate_onboarding** - Create a getting-started guide.
9. **docs_generate_changelog** - Initialize changelog from git history.
10. **docs_generate_diagram** - Add architecture diagrams.
11. **docs_check_completeness** - Verify coverage and identify remaining gaps.
""",
    "update": """\
# DocsMCP Workflow: Update

Update existing documentation after code changes.

## Steps

1. **docs_session_start** - Re-scan current documentation state.
2. **docs_check_drift** - Identify where docs have fallen behind code changes.
3. **docs_check_freshness** - Find stale documents that need attention.
4. **docs_git_summary** - Review what changed since the last update.
5. **docs_generate_readme** - Update README if project structure changed.
6. **docs_generate_api** - Regenerate API docs to reflect new/changed APIs.
7. **docs_generate_changelog** - Update changelog with new entries.
8. **docs_check_completeness** - Verify nothing was missed.
9. **docs_check_links** - Ensure all cross-references are still valid.
""",
    "audit": """\
# DocsMCP Workflow: Audit

Perform a comprehensive documentation quality audit.

## Steps

1. **docs_session_start** - Initialize and get current config.
2. **docs_project_scan** - Full inventory with completeness scoring.
3. **docs_check_drift** - Detect code-doc mismatches.
4. **docs_check_completeness** - Score documentation coverage by category.
5. **docs_check_links** - Find broken internal references.
6. **docs_check_freshness** - Identify stale or outdated documents.
7. **docs_api_surface** - Compare public API against what is documented.
8. Review findings and prioritize fixes based on completeness score and drift severity.
""",
    "release": """\
# DocsMCP Workflow: Release

Prepare documentation for a release.

## Steps

1. **docs_session_start** - Initialize session.
2. **docs_git_summary** - Analyze commits and version boundaries since last release.
3. **docs_generate_changelog** - Update changelog with new version section.
4. **docs_generate_release_notes** - Generate release notes for the new version.
5. **docs_generate_readme** - Update README with any version-specific changes.
6. **docs_check_drift** - Ensure all recent code changes are documented.
7. **docs_check_completeness** - Final completeness check before release.
8. **docs_check_links** - Validate all links are working.
""",
}


@mcp.prompt("docs_workflow_overview")
def _docs_workflow_overview() -> str:
    """Full DocsMCP workflow guide explaining all 18 tools and recommended usage order."""
    return _WORKFLOW_OVERVIEW


@mcp.prompt("docs_workflow")
def _docs_workflow(task_type: str = "bootstrap") -> str:
    """Task-specific DocsMCP workflow.

    Args:
        task_type: One of "bootstrap", "update", "audit", or "release".
    """
    if task_type not in _TASK_WORKFLOWS:
        valid = ", ".join(sorted(_TASK_WORKFLOWS))
        return (
            f"Unknown task type: {task_type!r}. "
            f"Valid types: {valid}.\n\n"
            "Use docs_workflow_overview for the full workflow guide."
        )
    return _TASK_WORKFLOWS[task_type]
