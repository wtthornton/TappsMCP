# docs-mcp

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)  ![License](https://img.shields.io/badge/license-MIT-green)  ![Version](https://img.shields.io/badge/version-2.4.0-blue)

MCP server for automated documentation generation, validation, and maintenance

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Development](#development)
- [License](#license)

## Features

- Python project with modern packaging (pyproject.toml)
- Test suite included
- Docker support
- Documentation included
- 73 modules with 279 public APIs
- CLI entry points: src/docs_mcp/cli.py, docsmcp = docs_mcp.cli:cli
- Click CLI framework
- Pydantic data validation
- pytest testing framework

## Installation

```bash
pip install docs-mcp
```

## Usage

### `docsmcp`

```bash
docsmcp
```


## Architecture

### Project Structure

```
+ agents/  # Agent matching infrastructure for DocsMCP.

Provides hybrid keyword + embedding matching for agent routing,
catalog management, deduplication scoring, and lifecycle governance.
  - catalog  # Agent catalog loader for DocsMCP.

Reads AGENT.md files from a directory and parses YAML frontmatter into
AgentConfig instances.
  - dedup  # Embedding-based deduplication gate for agent proposals.

Checks whether a proposed new agent overlaps with existing agents
in the catalog using embedding cosine similarity. When overlap is
detected, returns the overlapping agents instead of allowing creation.
  - embeddings  # Embedding backend abstraction for DocsMCP agent matching.

Provides a pluggable interface for computing text embeddings, with
a local sentence-transformers implementation and a stub for testing.
Includes disk-based caching keyed by content hash.
  - health  # Catalog health analysis for agent governance.

Computes pairwise similarity between all agents and identifies
potential overlaps that may indicate redundant agents needing
merge or cleanup.
  - keyword_matcher  # Keyword-based agent matching for DocsMCP.

Provides a simple TF-IDF-inspired overlap scorer as the baseline
matching strategy and fallback when embeddings are unavailable.
  - lifecycle  # Agent lifecycle management for catalog governance.

Handles soft-delete (deprecation) and cleanup of agents that have
been deprecated beyond the retention period.
  - matcher  # Hybrid agent matcher combining keyword and embedding scores.

Routes prompts to the best-matching agent using a weighted combination
of keyword overlap and embedding cosine similarity.
  - merge  # Capability merge suggestion generator for agent catalog governance.

When the dedup gate detects overlap between a proposed agent and an
existing one, this module generates structured merge suggestions:
which keywords/capabilities to add to the existing agent to cover
the proposed functionality.
  - models  # Agent configuration models for DocsMCP.
  - overlap_guard  # Proposer overlap guard for agent catalog governance.

Before creating a new agent, the overlap guard identifies the top-N
most similar existing agents. This context can be injected into a
proposer prompt or presented to a human reviewer to reduce
redundant agent creation.
+ analyzers/  # Code analysis engines for DocsMCP.
  - api_surface  # Public API surface detector for source modules (Python + multi-language).
  - commit_parser  # Conventional commit parser and heuristic classifier for DocsMCP.

Parses commit messages that follow the Conventional Commits specification
(``type(scope): description``). For non-conventional messages, falls back
to keyword-based heuristic classification.
  - dependency  # Import dependency graph builder for Python projects.
  - diataxis  # Diataxis content classification for documentation files.

Classifies markdown documents into the four Diataxis quadrants:
- Tutorial (learning-oriented, practical)
- How-to Guide (task-oriented, practical)
- Reference (information-oriented, theoretical)
- Explanation (understanding-oriented, theoretical)

Uses deterministic heuristics (heading patterns, content indicators,
structural analysis) -- no LLM calls.
  - git_history  # Git log parser for DocsMCP.

Wraps ``gitpython`` to extract commit history, tags, and per-file
last-modified timestamps. All methods return empty/degraded results
when the directory is not a Git repository.
  - models  # Data models for code analysis results.
  - module_map  # Module structure analyzer that builds a hierarchical map of a project.

Supports Python (AST-based) and multi-language files (TypeScript, Go,
Rust, Java) when tree-sitter is installed.
  - version_detector  # Tag/version boundary detection for DocsMCP.

Detects semver tags in a Git repository, groups commits between
version boundaries, and sorts by version number.
- cli  # DocsMCP CLI - documentation MCP server management.
+ config/  # DocsMCP configuration system.
  - settings  # DocsMCP configuration system.

Precedence (highest to lowest):
    1. Environment variables (``DOCS_MCP_*``)
    2. Project-level ``.docsmcp.yaml``
    3. Built-in defaults
- constants  # Shared constants for the docs_mcp package.
+ extractors/  # Code extraction engines for DocsMCP.
  - base  # Base protocol for source code extractors.
  - dispatcher  # Extractor dispatcher -- selects the best extractor for a given file.
  - docstring_parser  # Docstring parser supporting Google, NumPy, and Sphinx styles.

Parses Python docstrings into structured data models without external
dependencies. Handles style auto-detection and graceful fallback for
malformed input.
  - generic  # Regex-based fallback extractor for any text-based source file.
  - models  # Data models for code extraction results.
  - python  # Python AST-based source code extractor.
  - treesitter_base  # Base class for tree-sitter powered source code extractors.
  - treesitter_go  # Tree-sitter based Go extractor.
  - treesitter_java  # Tree-sitter based Java extractor.
  - treesitter_rust  # Tree-sitter based Rust extractor.
  - treesitter_typescript  # Tree-sitter based TypeScript/TSX extractor.
  - type_annotations  # Type annotation extraction and resolution for Python AST nodes.

Resolves Python type annotations from AST nodes and string representations
into structured, human-readable TypeInfo objects with normalization to
modern Python typing conventions.
+ generators/  # DocsMCP generators - README generation, metadata extraction, and smart merge.
  - adr  # Architecture Decision Record (ADR) generation in MADR and Nygard formats.
  - api_docs  # Per-module API reference documentation generator.

Generates structured API reference docs from Python source files using
the existing PythonExtractor and docstring parser infrastructure.
Supports markdown, mkdocs, and Sphinx RST output formats.
  - architecture  # Architecture document generator — produces a comprehensive, visually rich
HTML architecture report for any Python project.

Combines module map analysis, dependency graph analysis, API surface analysis,
and project metadata into a single self-contained HTML document with embedded
SVG diagrams, CSS styling, and detailed prose descriptions.
  - changelog  # Changelog generation in Keep-a-Changelog and Conventional formats.

Generates structured changelogs from git version boundaries and commits.
Uses Jinja2 templates for rendering, with fallback to programmatic
generation if templates are unavailable.
  - diagrams  # Diagram generation for Python project structures.

Generates Mermaid and PlantUML diagrams from project analysis results,
including dependency graphs, class hierarchies, module maps, and ER diagrams.
  - doc_index  # Documentation index generator (Epic 85.2).

Scans a project for documentation files and generates a structured
index/map with categories, descriptions, and freshness indicators.
  - epics  # Epic document generation with stories, acceptance criteria, and risk assessment.
  - expert_utils  # Shared helpers for expert guidance extraction and filtering in epic/story generators.

Used by EpicGenerator and StoryGenerator to:
- Extract the first substantive paragraph from consultation answers (skipping
  boilerplate like "Based on domain knowledge...").
- Filter guidance by confidence and content quality (Epic 18.3).
  - frontmatter  # Structured YAML frontmatter injection and update for markdown files.

Adds or updates YAML frontmatter metadata in existing markdown documents,
preserving existing fields while merging auto-detected values.
  - guides  # Onboarding and contributing guide generation.
  - interactive_html  # Interactive HTML diagram renderer using Mermaid.js (Epic 81.3).

Wraps Mermaid diagram content in a self-contained HTML file with
interactive pan/zoom controls via Mermaid.js and panzoom.js.
  - invest_assessor  # INVEST checklist auto-assessment from story configuration signals.
  - llms_txt  # llms.txt generator for machine-readable project documentation.

Generates llms.txt files following the emerging standard for AI-readable
project summaries. Supports compact (llms.txt) and detailed (llms-full.txt)
output modes.
  - metadata  # Project metadata extraction from pyproject.toml, package.json, and Cargo.toml.
  - prompts  # Prompt artifact generation (Epic 75). PromptConfig + PromptGenerator for LLM-facing prompt docs.
  - purpose  # Purpose/Intent architecture template generator (Epic 85.1).

Generates a purpose-and-intent section for architecture documentation,
including project purpose, design principles, key decisions, and
intended audience. Uses project metadata and module map analysis.
  - readme  # README generation with Jinja2 templates and section generators.
  - release_notes  # Release notes generation for a specific version.

Extracts highlights, breaking changes, features, fixes, contributors,
and other changes from a version boundary's commits and renders
structured release notes as markdown.
  - risk_classifier  # Risk auto-classification from keywords with ISO 31000 3x3 matrix scoring.
  - smart_merge  # Smart merge engine for preserving human-written README sections.
  - specs  # Product Requirements Document (PRD) generation with phased requirements.
  - stories  # User story document generation with acceptance criteria and task breakdown.
  - test_deriver  # Derive test case names from acceptance criteria when none are provided.
+ integrations/  # DocsMCP integrations - optional enrichment from external tools.
  - tapps  # TappsMCP integration for optional quality enrichment in DocsMCP.

Reads shared file artifacts produced by TappsMCP to enrich documentation
with quality scores, project profiles, and dependency data. All methods
return safe defaults when TappsMCP data is unavailable - DocsMCP never
fails due to missing TappsMCP data.
- server  # DocsMCP MCP server entry point.

Creates the FastMCP server instance, registers tools, and provides
``run_server()`` for the CLI.
- server_analysis  # DocsMCP analysis tools — docs_module_map and docs_api_surface.

These tools register on the shared ``mcp`` FastMCP instance from
``server.py`` and provide code structure analysis capabilities.
- server_gen_tools  # DocsMCP generation tools.

Registers generation tools on the shared ``mcp`` FastMCP instance from
``server.py``: README, changelog, release notes, API docs, ADR,
onboarding/contributing guides, diagrams, architecture reports, epics,
and user stories.
- server_git_tools  # DocsMCP git analysis tools -- docs_git_summary.

This module registers on the shared ``mcp`` FastMCP instance from
``server.py`` and provides git history analysis for documentation generation.
- server_helpers  # Helper functions for DocsMCP server — response builders and singleton caches.
- server_resources  # MCP resources and workflow prompts for DocsMCP.

Registers MCP resources (docs://status, docs://config, docs://coverage) and
workflow prompts (docs_workflow_overview, docs_workflow) on the shared ``mcp``
FastMCP instance from ``server.py``.
- server_val_tools  # DocsMCP validation tools -- docs_check_drift, docs_check_completeness,
docs_check_links, docs_check_freshness.

These tools register on the shared ``mcp`` FastMCP instance from
``server.py`` and provide documentation validation capabilities.
+ validators/  # Documentation validation engine for DocsMCP.

Provides drift detection, completeness checking, link validation,
freshness scoring, epic structure validation, and style/tone checking
for project documentation.
  - completeness  # Documentation completeness checker.
  - cross_ref  # Cross-reference validator for documentation files (Epic 85.4).

Validates that cross-references between documentation files are
consistent and bidirectional. Detects orphan docs, missing backlinks,
and broken inter-doc references.
  - diataxis  # Diataxis balance validator for project documentation.

Scans all markdown files in a project, classifies each into Diataxis
quadrants, and produces a coverage report with balance scoring and
recommendations for underrepresented quadrants.
  - drift  # Drift detection: identify code changes not reflected in documentation.
  - epic_validator  # Structural validator for epic planning documents.

Parses markdown epic files and checks for required sections, story
completeness, point/size consistency, dependency cycles, and
files-affected coverage.
  - freshness  # Documentation freshness scoring based on file modification times.
  - identifier_terms  # Collect likely project-specific terms from Python source identifiers (Epic 84.3).

Deterministic, bounded scan: no LLM, no network. Used to reduce false positives
in style rules (jargon, heading case) for names that legitimately appear in docs.
  - link_checker  # Internal link validator for documentation files.
  - style  # Documentation style and tone validation engine.

Provides deterministic, regex/pattern-based style checking for markdown
documentation.  Each rule receives parsed content and returns issues with
severity, location, and fix suggestions.

Epic 84 -- Doc Style & Tone Validation.
```

## API Reference

See the [API documentation](docs/api.md) for detailed reference.

## Development

```bash
# Clone the repository
git clone https://github.com/wtthornton/TappsMCP.git
cd docs-mcp

# Install dependencies
pip install -e '.[dev]'

# Run tests
pytest
```

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -am 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT license.
