"""Concise MCP tool descriptions for docs-mcp (TAP-1963).

Long-form guidance lives in AGENTS.md and handler docstrings. These strings
are the wire catalog only.
"""

from __future__ import annotations

MEDIAN_MAX_CHARS = 200
HARD_MAX_CHARS = 500

TOOL_DESCRIPTIONS: dict[str, str] = {
    "docs_session_start": (
        "First call each session: detect project type, scan docs, return recommendations."
    ),
    "docs_project_scan": (
        "Audit documentation state with completeness scoring and gap recommendations."
    ),
    "docs_config": ("View or update DocsMCP configuration (.docsmcp.yaml)."),
    "docs_module_map": ("Build hierarchical module tree with public API counts."),
    "docs_api_surface": (
        "Analyze public API surface of a source file (Python, TS, Go, Rust)."
    ),
    "docs_git_summary": (
        "Summarize git history with conventional commits and version boundaries."
    ),
    "docs_generate_readme": (
        "Generate or smart-merge README.md (minimal/standard/comprehensive)."
    ),
    "docs_generate_changelog": ("Generate CHANGELOG.md from git tags and commits."),
    "docs_generate_release_notes": ("Generate structured release notes for one version."),
    "docs_generate_api": (
        "Generate API reference documentation from Python source (markdown/mkdocs/sphinx)."
    ),
    "docs_generate_adr": ("Create an auto-numbered Architecture Decision Record."),
    "docs_generate_onboarding": ("Generate a getting-started / onboarding guide."),
    "docs_generate_contributing": ("Generate CONTRIBUTING.md with dev setup and PR workflow."),
    "docs_generate_prd": ("Generate a Product Requirements Document with phased requirements."),
    "docs_generate_diagram": (
        "Generate Mermaid, PlantUML, or D2 diagrams from code analysis."
    ),
    "docs_generate_architecture": (
        "Generate a self-contained HTML architecture report with SVG diagrams."
    ),
    "docs_generate_epic": (
        "Generate an epic planning document with stories and acceptance criteria."
    ),
    "docs_generate_story": (
        "Generate a user story document with tasks and acceptance criteria."
    ),
    "docs_generate_prompt": ("Generate a reusable LLM prompt artifact from project context."),
    "docs_check_drift": ("Detect code changes not yet reflected in documentation."),
    "docs_check_completeness": (
        "Score documentation completeness across critical categories (0-100)."
    ),
    "docs_check_links": ("Validate internal links across markdown documentation files."),
    "docs_check_freshness": (
        "Classify documentation freshness from file modification times."
    ),
    "docs_validate_epic": ("Validate an epic document for required sections and consistency."),
    "docs_generate_llms_txt": ("Generate machine-readable llms.txt project summary."),
    "docs_generate_frontmatter": ("Add or update YAML frontmatter in a markdown file."),
    "docs_check_diataxis": ("Analyze Diataxis quadrant balance across project docs."),
    "docs_generate_interactive_diagrams": (
        "Generate an interactive HTML page with pan/zoom Mermaid diagrams."
    ),
    "docs_generate_purpose": ("Generate a purpose/intent architecture template."),
    "docs_generate_doc_index": ("Generate a documentation index/map with auto-categorization."),
    "docs_check_cross_refs": (
        "Validate cross-references: orphans, broken refs, and missing backlinks."
    ),
    "docs_check_style": (
        "Deterministic markdown style checks: passive voice, jargon, headings, length."
    ),
    "docs_lint_linear_issue": (
        "Lint one Linear issue payload against the agent-issue template (9 rules)."
    ),
    "docs_validate_linear_issue": (
        "Pre-create gate: return agent_ready verdict for a Linear issue payload."
    ),
    "docs_linear_triage": (
        "Batch-triage N Linear issues: label proposals and parent groupings (read-only)."
    ),
    "docs_save_linear_issue": (
        "Pre-save gate: verify docs_validate_linear_issue ran before save_issue."
    ),
    "docs_generate_release_update": (
        "Generate a Linear project update document for a version release."
    ),
    "docs_validate_release_update": (
        "Validate a release-update document body before posting to Linear."
    ),
    "docs_release_gate": (
        "Aggregate pre-release docs gate: drift + freshness + links in one verdict."
    ),
    "docs_kg_query": ("Query the brain knowledge graph for entities and relations."),
}
