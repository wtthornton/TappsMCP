# DocsMCP - Product Requirements Document

**Version:** 1.0.0-draft
**Date:** 2026-02-28
**Author:** TappsMCP Team
**Status:** Draft

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Market Landscape & Competitive Analysis](#3-market-landscape--competitive-analysis)
4. [Product Vision & Positioning](#4-product-vision--positioning)
5. [Target Users & Personas](#5-target-users--personas)
6. [Core Design Principles](#6-core-design-principles)
7. [Architecture Overview](#7-architecture-overview)
8. [Feature Specification](#8-feature-specification)
9. [MCP Tool Inventory](#9-mcp-tool-inventory)
10. [Integration Points](#10-integration-points)
11. [Technology Stack](#11-technology-stack)
12. [Epic Breakdown](#12-epic-breakdown)
13. [Quality & Testing Strategy](#13-quality--testing-strategy)
14. [Distribution Strategy](#14-distribution-strategy)
15. [Success Metrics](#15-success-metrics)
16. [Risks & Mitigations](#16-risks--mitigations)
17. [Future Roadmap](#17-future-roadmap)
18. [References & Research](#18-references--research)

---

## 1. Executive Summary

**DocsMCP** is a standalone MCP (Model Context Protocol) server that provides deterministic and AI-augmented documentation generation, drift detection, and maintenance tools to LLMs and AI coding assistants. It is the documentation companion to [TappsMCP](https://github.com/your-org/tapps-mcp) (code quality) — where TappsMCP answers "is the code good?", DocsMCP answers "is the documentation complete, accurate, and current?"

DocsMCP exposes its capabilities as MCP tools that any MCP-capable client (Claude Code, Cursor, VS Code Copilot, Windsurf) can invoke. It generates, validates, and maintains project documentation including READMEs, API references, changelogs, architecture decision records, diagrams, and onboarding guides — all grounded in the actual codebase via AST parsing, git history analysis, and import graph traversal.

### Key Differentiators

| Differentiator | Description |
|---|---|
| **MCP-native** | First documentation server built specifically for the MCP protocol, not retrofitted |
| **Hybrid deterministic + generative** | AST analysis and git parsing are deterministic; prose generation uses LLM via the host client |
| **Drift detection** | Identifies when documentation is stale relative to code changes |
| **TappsMCP companion** | Shares architectural patterns, can consume TappsMCP's dependency graph and scoring data |
| **Docs-as-code** | Generates markdown that lives in the repo and follows PR review workflows |
| **Multi-language** | Python-first, with extensible language support (TypeScript, Go, Rust, Java) |

---

## 2. Problem Statement

### The Documentation Gap

Modern AI coding assistants excel at writing and reviewing code but have no structured tooling for documentation. Today's reality:

1. **Documentation is an afterthought** — Developers write code, AI assistants help, but nobody maintains docs
2. **Documentation drifts silently** — Code changes without corresponding doc updates; the gap widens with every PR
3. **No quality gate for docs** — CI pipelines check code quality (lint, type-check, test) but not documentation completeness or accuracy
4. **Manual README maintenance** — READMEs rot, API docs become stale, architecture diagrams become fiction
5. **Changelog friction** — Generating changelogs from git history requires manual tooling setup that most teams skip
6. **Onboarding cost** — New developers spend days deciphering undocumented codebases; AI assistants hallucinate when docs are missing

### Why Existing Tools Fall Short

| Tool Category | Limitation |
|---|---|
| **Sphinx / MkDocs** | Require manual setup, configuration, and maintenance; generate static sites, not in-editor docs |
| **DocuWriter.ai / Swimm** | SaaS-only, no MCP integration, expensive enterprise pricing, closed-source |
| **Mintlify** | Excellent for hosted docs sites but not for in-repo documentation generation |
| **readme-ai** | CLI-only, generates initial README but doesn't maintain it; no drift detection |
| **GitHub Copilot Docs Agent** | Proprietary, limited to PR-triggered updates, not available as a general tool |
| **Context7 / docs-mcp-server** | Read existing docs into LLM context — they don't *generate* docs |
| **DeepDocs** | GitHub-native agent, not MCP-compatible, limited to drift PRs |

### The Opportunity

No MCP server exists that provides structured, tool-based documentation generation and maintenance. DocsMCP fills this gap by giving AI assistants the ability to create, update, validate, and audit project documentation through the same MCP protocol they already use for code quality (TappsMCP), GitHub integration, and other developer tools.

---

## 3. Market Landscape & Competitive Analysis

### 3.1 Documentation Generation Tools (2026)

#### AI-Powered Documentation Platforms

| Tool | Type | Strengths | Weaknesses | MCP Support |
|---|---|---|---|---|
| **Mintlify** | SaaS platform | Beautiful docs, Autopilot agent, MCP server for *reading* docs | Hosted-only, $300+/mo, generates hosted sites not in-repo docs | Read-only MCP |
| **DocuWriter.ai** | SaaS tool | Multi-language, UML diagrams, Swagger gen | Closed-source, SaaS pricing ($19+/mo), no MCP | None |
| **Swimm** | SaaS platform | Code-coupled docs, drift detection, CI integration | Enterprise pricing, closed-source, no MCP | None |
| **DeepDocs** | GitHub agent | Auto-detects drift, proposes PR updates | GitHub-only, not MCP, limited to drift fixes | None |
| **DocuMate** | Open-source | Static analysis + Copilot AI, drift detection | TypeScript/JS/Python only, Copilot-dependent | None |
| **readme-ai** | CLI tool | One-command README generation, multi-LLM | Initial generation only, no maintenance, no MCP | None |
| **ReadmeX** | CLI tool | README + interactive wiki generation | Initial generation only, Chinese-focused | None |

#### Documentation Frameworks

| Framework | Type | Strengths | Weaknesses |
|---|---|---|---|
| **MkDocs + mkdocstrings** | Static site gen | Markdown-native, auto API docs from docstrings, Material theme | Requires manual config, no drift detection, no MCP |
| **Sphinx** | Static site gen | Python ecosystem standard, extensive plugins | reStructuredText friction, complex config, aging ecosystem |
| **Zensical** (alpha) | Next-gen docs | From mkdocs-material creators, modern architecture | Alpha stage, not production-ready until late 2026 |
| **Pydoc-Markdown** | Markdown gen | Parses without executing code, Markdown output | Limited to API docs, no broader documentation |

#### Changelog & Release Tools

| Tool | Type | Strengths | Weaknesses |
|---|---|---|---|
| **git-cliff** | CLI (Rust) | Highly customizable, conventional commits, fast | Changelog only, no MCP |
| **conventional-changelog** | CLI (Node) | Ecosystem standard, GitHub Actions integration | Node dependency, changelog only |
| **standard-version** | CLI (Node) | Versioning + changelog combined | Node dependency, changelog only |
| **commitlint** | Git hook | Enforces commit message standards | Enforcement only, no generation |

#### Diagram Generation

| Tool | Type | Strengths | Weaknesses |
|---|---|---|---|
| **Mermaid.js** | Text-to-diagram | GitHub-native rendering, VS Code plugin with AI generation | Manual diagram authoring, limited auto-generation from code |
| **py2puml** | Python-to-UML | Generates class diagrams from Python code | UML only, no architecture diagrams |
| **pydeps** | Python deps | Generates dependency graphs as images | Dependency graphs only |

### 3.2 MCP Documentation Servers (Current State)

| Server | Purpose | Generates Docs? |
|---|---|---|
| **Context7** (Upstash) | Fetches library docs for LLM context | No — reads existing docs |
| **docs-mcp-server** (arabold) | Personal doc index with semantic search | No — indexes existing docs |
| **Microsoft Learn MCP** | Microsoft docs for LLM context | No — reads existing docs |
| **Mintlify MCP** | Serves hosted docs to LLMs | No — reads existing docs |

**Key insight:** Every existing documentation MCP server is *read-only* — they help LLMs consume existing documentation. None of them *generate* documentation. DocsMCP will be the first MCP server focused on documentation creation and maintenance.

### 3.3 Emerging Trends (2026)

1. **AI-native documentation** — Mintlify's Autopilot, GitHub Copilot Docs Agent, and DeepDocs all represent the shift toward AI-monitored documentation that self-updates
2. **Docs-as-code maturity** — MDX/Markdown in repos, PR-based review, CI validation is now standard practice
3. **Documentation drift as a first-class concern** — IEEE research papers (2025-2026) formalizing drift detection; tools like Swimm and DeepDocs gaining traction
4. **MCP ecosystem explosion** — 70% of MCP servers use FastMCP; protocol becoming the USB-C of AI tool integration
5. **Conventional commits adoption** — Enables automated changelogs; increasingly enforced via CI
6. **Mermaid diagram rendering** — GitHub, GitLab, VS Code all render Mermaid natively; diagram-as-code is mainstream

---

## 4. Product Vision & Positioning

### Vision Statement

> DocsMCP makes project documentation a living, version-controlled artifact that stays in sync with code — generated, validated, and maintained through the same AI-assisted workflow developers already use for coding.

### Positioning

```
For: Development teams using AI coding assistants (Claude Code, Cursor, VS Code Copilot)
Who: Need documentation that stays current with their codebase
DocsMCP is: An MCP server for documentation generation and maintenance
That: Generates, validates, and updates project documentation from code analysis
Unlike: Mintlify (SaaS-only), Swimm (enterprise pricing), readme-ai (one-shot generation)
Our product: Is open-source, MCP-native, drift-aware, and integrates with existing quality pipelines
```

### Relationship to TappsMCP

```
                    AI Coding Assistant (Claude Code / Cursor / Copilot)
                                    |
                          MCP Protocol (2025-11-25)
                           /                    \
                    TappsMCP                  DocsMCP
                  (Code Quality)          (Documentation)
                       |                        |
              "Is the code good?"    "Are the docs complete?"
                       |                        |
              Scores, gates,         README, API docs, changelog,
              security scans,        diagrams, drift detection,
              expert advice          ADRs, onboarding guides
                       \                       /
                        \                     /
                    Shared data flows:
                    - TappsMCP dependency_graph → DocsMCP diagrams
                    - TappsMCP project_profile → DocsMCP tech stack context
                    - TappsMCP score_file → DocsMCP quality badges
                    - DocsMCP drift_score → TappsMCP checklist integration
```

---

## 5. Target Users & Personas

### 5.1 Primary: Solo Developer / Small Team Lead

- Uses Claude Code or Cursor daily
- Maintains 1-5 projects, each with minimal documentation
- Knows docs are important but deprioritizes them under shipping pressure
- **Pain:** README is outdated, no API docs, no changelog, onboarding new contributors is painful
- **Need:** One-command documentation bootstrap and ongoing maintenance

### 5.2 Secondary: Open Source Maintainer

- Manages a public repository with external contributors
- Needs professional-grade README, contributing guide, changelog, and API reference
- Documentation quality directly impacts adoption and contributions
- **Pain:** Contributors ask questions already answered by (missing) docs
- **Need:** Comprehensive documentation generation with drift alerts on PRs

### 5.3 Tertiary: Team Tech Lead / Staff Engineer

- Responsible for architectural documentation across multiple services
- Needs ADRs, system diagrams, API contracts, onboarding guides
- **Pain:** Architecture docs become fiction within weeks of creation
- **Need:** Documentation that auto-updates from code analysis, drift detection in CI

---

## 6. Core Design Principles

### 6.1 Deterministic Where Possible, Generative Where Needed

DocsMCP follows a **hybrid approach**:

| Layer | Approach | Examples |
|---|---|---|
| **Data extraction** | Deterministic (AST, git, imports) | Function signatures, dependency graphs, commit history, module structure |
| **Structure & templates** | Deterministic (templates) | Document scaffolding, section ordering, table formats |
| **Prose generation** | Delegated to host LLM | README descriptions, function explanations, changelog summaries |
| **Validation & drift** | Deterministic (diffing) | Comparing docs against code state, detecting stale sections |

The MCP tool returns structured data (signatures, graphs, diffs) that the host LLM can use to generate prose. DocsMCP does NOT embed an LLM — it provides the structured context that makes LLM-generated documentation accurate and grounded.

### 6.2 Docs-as-Code

- All generated documentation is Markdown (or MDX) that lives in the repository
- Documentation follows the same PR review process as code
- Version-controlled, diffable, portable

### 6.3 Non-Destructive by Default

- Never overwrites existing documentation without explicit confirmation
- Smart-merge: update sections that changed, preserve human-written content
- Drift detection proposes changes, doesn't force them

### 6.4 Language-Agnostic Core, Language-Specific Extractors

- Core documentation engine works with any language
- Language-specific AST parsers extract structured data (Python first, then TypeScript, Go, Rust, Java)
- Plugin architecture for adding new language extractors

### 6.5 MCP Protocol Alignment

- Follow MCP 2025-11-25 specification
- Use FastMCP 3.x decorator patterns
- Tools for actions, Resources for data, Prompts for workflows
- Structured output schemas for all tools
- Streamable HTTP transport support

---

## 7. Architecture Overview

### 7.1 High-Level Architecture

```
DocsMCP Server
├── Core Engine
│   ├── extractors/          # Language-specific AST parsing
│   │   ├── python.py        # Python extractor (ast module)
│   │   ├── typescript.py    # TypeScript extractor (tree-sitter)
│   │   ├── generic.py       # Regex-based fallback for any language
│   │   └── base.py          # Extractor protocol/interface
│   ├── analyzers/           # Cross-language analysis
│   │   ├── module_map.py    # Module structure analyzer
│   │   ├── api_surface.py   # Public API detection
│   │   ├── dependency.py    # Import/dependency graph
│   │   ├── git_history.py   # Git log, blame, diff analysis
│   │   ├── commit_parser.py # Conventional commits parser
│   │   └── coverage.py      # Documentation coverage calculator
│   ├── generators/          # Document generators
│   │   ├── readme.py        # README generation
│   │   ├── api_reference.py # API documentation
│   │   ├── changelog.py     # Changelog from git history
│   │   ├── adr.py           # Architecture Decision Records
│   │   ├── diagram.py       # Mermaid diagram generation
│   │   ├── onboarding.py    # Onboarding / getting-started guide
│   │   ├── contributing.py  # CONTRIBUTING.md generation
│   │   ├── migration.py     # Migration guide generation
│   │   └── release_notes.py # Release notes generation
│   ├── validators/          # Documentation validation
│   │   ├── drift.py         # Drift detection engine
│   │   ├── completeness.py  # Coverage/completeness checker
│   │   ├── link_checker.py  # Internal/external link validation
│   │   ├── freshness.py     # Staleness scoring by section
│   │   └── consistency.py   # Cross-document consistency checks
│   └── templates/           # Document templates (Jinja2)
│       ├── readme/          # README variants (minimal, standard, comprehensive)
│       ├── api/             # API doc templates
│       ├── changelog/       # Changelog formats (keep-a-changelog, conventional)
│       ├── adr/             # ADR templates (MADR, Nygard, custom)
│       └── guides/          # Guide templates
├── MCP Layer
│   ├── server.py            # FastMCP instance, core tools
│   ├── server_gen_tools.py  # Generation tools
│   ├── server_val_tools.py  # Validation tools
│   ├── server_analysis.py   # Analysis/extraction tools
│   ├── server_helpers.py    # Shared utilities
│   └── resources.py         # MCP resources and prompts
├── Config
│   ├── settings.py          # Configuration management
│   └── default.yaml         # Default configuration
├── Security
│   ├── path_validator.py    # File system sandboxing
│   └── content_safety.py    # Generated content safety checks
└── CLI
    └── cli.py               # Click-based CLI (init, doctor, generate)
```

### 7.2 Data Flow

```
Source Code → Extractors → Structured Data → Generators → Markdown Templates → Output Files
                                  ↑                              ↑
                            Git History                    Host LLM (prose)
                            TappsMCP data                  via MCP context
```

### 7.3 Server Module Split Strategy

Following TappsMCP's proven pattern of splitting the server across multiple files to manage complexity:

| Module | Responsibility | Estimated Tools |
|---|---|---|
| `server.py` | FastMCP instance, core tools (session_start, project_scan, doc_status) | 4-5 |
| `server_gen_tools.py` | Generation tools (readme, api_docs, changelog, adr, diagram, guides) | 8-10 |
| `server_val_tools.py` | Validation tools (drift_check, completeness, link_check, freshness) | 5-6 |
| `server_analysis.py` | Analysis tools (module_map, api_surface, git_summary, coverage) | 4-5 |
| `server_helpers.py` | Shared utilities, caches, response builders | 0 (internal) |

---

## 8. Feature Specification

### 8.1 Documentation Generation

#### 8.1.1 README Generation (`docs_generate_readme`)

**Description:** Generates or updates a project README.md from codebase analysis.

**Inputs:**
- `style`: `"minimal"` | `"standard"` | `"comprehensive"` (default: `"standard"`)
- `sections`: Optional list of sections to include/exclude
- `update_mode`: `"create"` | `"update"` | `"smart_merge"` (default: `"smart_merge"`)

**Analysis performed:**
- Project name, description from `pyproject.toml` / `package.json` / `Cargo.toml`
- Tech stack detection (languages, frameworks, dependencies)
- Entry points and CLI commands
- Installation methods (pip, npm, cargo, docker)
- Directory structure analysis
- Test framework detection
- License detection
- CI/CD detection (GitHub Actions, GitLab CI)
- Existing README section preservation (in smart_merge mode)

**Output:** Structured data containing:
- Extracted project metadata (deterministic)
- Suggested section content with placeholders for LLM prose
- Section structure and ordering
- Badge suggestions (CI, coverage, version, license)

**README Sections (standard style):**
1. Title + badges
2. Description (LLM-assisted)
3. Features / highlights
4. Quick start / installation
5. Usage examples
6. Configuration
7. API reference (summary, links to full docs)
8. Development setup
9. Testing
10. Contributing
11. License

#### 8.1.2 API Reference Generation (`docs_generate_api`)

**Description:** Generates API documentation from source code analysis.

**Inputs:**
- `source_path`: File or directory to document
- `format`: `"markdown"` | `"mkdocs"` | `"sphinx_rst"` (default: `"markdown"`)
- `depth`: `"public"` | `"protected"` | `"all"` (default: `"public"`)
- `include_examples`: `bool` (default: `true`)

**Analysis performed:**
- AST parsing of all Python files in scope
- Public API surface detection (functions, classes, methods without `_` prefix)
- Docstring extraction and parsing (Google, NumPy, Sphinx styles)
- Type annotation extraction
- Parameter and return type documentation
- Exception documentation
- Decorator detection (`@property`, `@staticmethod`, `@classmethod`, `@abstractmethod`)
- Cross-reference resolution (imports, inheritance)
- Usage example extraction from tests

**Output:** Per-module structured data:
- Module docstring
- Classes with methods, properties, class variables
- Standalone functions
- Constants and type aliases
- Inheritance hierarchy
- Cross-reference links

#### 8.1.3 Changelog Generation (`docs_generate_changelog`)

**Description:** Generates or updates CHANGELOG.md from git history analysis.

**Inputs:**
- `format`: `"keep-a-changelog"` | `"conventional"` | `"simple"` (default: `"keep-a-changelog"`)
- `from_ref`: Git ref to start from (default: last tag or initial commit)
- `to_ref`: Git ref to end at (default: `"HEAD"`)
- `group_by`: `"type"` | `"scope"` | `"date"` (default: `"type"`)
- `include_breaking`: `bool` (default: `true`)

**Analysis performed:**
- Git log parsing between refs
- Conventional commit message parsing (type, scope, description, body, breaking changes)
- Non-conventional commit classification via heuristics (keywords: fix, add, remove, update, refactor)
- PR/issue reference extraction (`#123`, `GH-123`)
- Author attribution
- Semantic versioning inference from commit types
- Tag-based version boundary detection

**Output:** Structured changelog data:
- Version sections with date and comparison links
- Categorized entries: Added, Changed, Deprecated, Removed, Fixed, Security
- Breaking changes highlighted
- Contributor attribution

#### 8.1.4 Architecture Decision Records (`docs_generate_adr`)

**Description:** Creates or lists Architecture Decision Records.

**Inputs:**
- `action`: `"create"` | `"list"` | `"supersede"`
- `title`: ADR title (for create)
- `template`: `"madr"` | `"nygard"` | `"custom"` (default: `"madr"`)
- `context_files`: Optional list of relevant source files for context extraction

**Analysis performed (for create):**
- Scan referenced files for architectural patterns (imports, class hierarchies, config)
- Extract existing ADR numbering sequence
- Detect related existing ADRs by keyword overlap
- Generate status, context, and consequences sections with code-grounded evidence

**Output:**
- Numbered ADR file in `docs/adr/` or `docs/decisions/`
- Updated ADR index/log
- Cross-references to related ADRs

#### 8.1.5 Diagram Generation (`docs_generate_diagram`)

**Description:** Generates Mermaid diagrams from code analysis.

**Inputs:**
- `diagram_type`: `"dependency"` | `"class"` | `"sequence"` | `"module_map"` | `"architecture"` | `"er"`
- `scope`: File path, directory, or `"project"` (default: `"project"`)
- `depth`: How many levels deep to traverse (default: `2`)
- `format`: `"mermaid"` | `"plantuml"` (default: `"mermaid"`)

**Analysis performed:**
- Import graph construction from AST
- Class inheritance hierarchy extraction
- Module boundary detection
- Public interface identification
- Circular dependency detection
- Package grouping

**Diagram types:**
| Type | Source | Output |
|---|---|---|
| `dependency` | Import analysis | Module dependency flowchart |
| `class` | AST class parsing | Class diagram with inheritance |
| `sequence` | Function call chain analysis | Sequence diagram for key flows |
| `module_map` | Directory + import analysis | High-level architecture overview |
| `architecture` | Package structure + entry points | System architecture diagram |
| `er` | Pydantic/dataclass/ORM models | Entity-relationship diagram |

**Output:** Mermaid (or PlantUML) text that renders natively in GitHub, GitLab, VS Code, and most documentation platforms.

#### 8.1.6 Onboarding Guide (`docs_generate_onboarding`)

**Description:** Generates a getting-started guide for new contributors.

**Inputs:**
- `audience`: `"developer"` | `"contributor"` | `"user"` (default: `"developer"`)
- `depth`: `"quick_start"` | `"full_guide"` (default: `"full_guide"`)

**Analysis performed:**
- Development environment requirements (Python version, Node, etc.)
- Dependency installation commands (from lockfiles)
- Environment variable detection (`.env.example`, config files)
- Test running commands (from `pyproject.toml`, `package.json`, `Makefile`)
- Build/run commands
- Common development tasks from `Makefile` / `justfile` / scripts directory
- Pre-commit hook configuration
- CI pipeline analysis (what CI checks, so devs can run locally)

**Output:** Structured onboarding document with:
- Prerequisites
- Setup steps (clone, install, configure)
- Development workflow (branch, test, lint, commit)
- Architecture overview (links to diagrams)
- Key directories and files
- Common commands reference
- Troubleshooting section

#### 8.1.7 Contributing Guide (`docs_generate_contributing`)

**Description:** Generates CONTRIBUTING.md tailored to the project.

**Analysis performed:**
- Branch strategy detection (git flow, trunk-based)
- Commit message convention detection (conventional commits, etc.)
- PR template analysis
- CI requirements
- Code style tools (linters, formatters)
- Test requirements

#### 8.1.8 Release Notes (`docs_generate_release_notes`)

**Description:** Generates release notes for a specific version or tag.

**Inputs:**
- `version`: Tag or version string
- `previous_version`: Optional (auto-detected from tags)
- `style`: `"detailed"` | `"summary"` | `"user_facing"` (default: `"user_facing"`)

**Analysis performed:**
- Git diff between versions
- Files changed analysis
- Commit categorization
- Breaking change detection
- Migration requirement detection
- Dependency version changes

### 8.2 Documentation Validation

#### 8.2.1 Drift Detection (`docs_check_drift`)

**Description:** Detects documentation that has drifted from the current code state.

**Inputs:**
- `scope`: `"all"` | `"readme"` | `"api"` | `"changelog"` | specific file path
- `base_ref`: Git ref to compare against (default: `"HEAD~10"` or last release tag)
- `sensitivity`: `"low"` | `"medium"` | `"high"` (default: `"medium"`)

**Analysis performed:**
- Code changes since base_ref that affect documented modules
- Function signature changes vs API docs
- New public APIs without documentation
- Removed APIs still documented
- Configuration changes not reflected in docs
- Dependency changes not reflected in setup/install docs
- README sections referencing renamed/deleted files

**Output:**
- Drift score (0-100, 100 = perfectly in sync)
- Per-section drift indicators with evidence
- Suggested updates with code references
- Priority ranking (critical drift vs cosmetic)

#### 8.2.2 Completeness Check (`docs_check_completeness`)

**Description:** Measures documentation coverage across the project.

**Inputs:**
- `scope`: `"project"` | `"module"` | specific path
- `requirements`: `"minimal"` | `"standard"` | `"comprehensive"`

**Checks performed:**
- README exists and has required sections
- API documentation coverage (% of public APIs documented)
- Docstring coverage (% of public functions with docstrings)
- Changelog exists and is current
- Contributing guide exists
- License file exists
- Architecture documentation exists (ADRs, diagrams)
- Configuration documentation exists
- Examples/tutorials exist
- Installation instructions are present

**Output:**
- Overall completeness score (0-100)
- Per-category scores
- Missing documentation items ranked by impact
- Comparison against requirements level

#### 8.2.3 Link Validation (`docs_check_links`)

**Description:** Validates all links in documentation files.

**Inputs:**
- `scope`: `"all"` | specific file path
- `check_external`: `bool` (default: `false` — external link checking is opt-in)
- `check_anchors`: `bool` (default: `true`)

**Checks performed:**
- Internal file references (relative paths)
- Anchor references within and across files
- Code reference validation (file:line references)
- Image/asset references
- External URL validation (when enabled, with rate limiting)

**Output:**
- Broken links with location and suggested fixes
- Orphaned documentation files (not linked from anywhere)
- Missing referenced files

#### 8.2.4 Freshness Score (`docs_check_freshness`)

**Description:** Scores how recently each documentation file was updated relative to the code it documents.

**Inputs:**
- `scope`: `"project"` | specific path

**Analysis performed:**
- Last modification date of each doc file
- Last modification date of code files in corresponding modules
- Git blame analysis to identify most stale sections
- Ratio of doc commits to code commits over time

**Output:**
- Per-file freshness score (0-100)
- Staleness alerts for files not updated in configurable threshold
- Trending: improving or degrading over time

### 8.3 Documentation Analysis

#### 8.3.1 Project Scan (`docs_project_scan`)

**Description:** Comprehensive scan of project documentation state. Called at session start.

**Output:**
- Project metadata (name, version, type, languages)
- Existing documentation inventory
- Documentation gaps
- Quick completeness score
- Recommended next actions

#### 8.3.2 Module Map (`docs_module_map`)

**Description:** Generates a structural map of the project's modules and their relationships.

**Inputs:**
- `depth`: Number of directory levels (default: `3`)
- `include_private`: `bool` (default: `false`)

**Output:**
- Hierarchical module tree with descriptions
- Public API count per module
- Import relationships between modules
- Entry points and CLI commands

#### 8.3.3 API Surface (`docs_api_surface`)

**Description:** Extracts the public API surface of a module or project.

**Inputs:**
- `source_path`: File or directory
- `include_types`: `bool` (default: `true`)

**Output:**
- All public functions, classes, methods
- Type signatures
- Docstring presence/absence
- Decorator information
- Export analysis (`__all__`, `__init__.py` re-exports)

#### 8.3.4 Git Summary (`docs_git_summary`)

**Description:** Summarizes recent git history for documentation context.

**Inputs:**
- `period`: `"week"` | `"month"` | `"release"` | `"all"` (default: `"month"`)
- `format`: `"summary"` | `"detailed"` (default: `"summary"`)

**Output:**
- Commit count and contributor count
- Most changed files/modules
- Conventional commit type distribution
- Key changes narrative (structured for LLM summarization)

### 8.4 Session & Configuration

#### 8.4.1 Session Start (`docs_session_start`)

**Description:** Initializes DocsMCP session, detects project context.

**Output:**
- Server version and capabilities
- Project detection (language, framework, package manager)
- Existing documentation inventory
- Configuration loaded
- Recommended workflow

#### 8.4.2 Documentation Config (`docs_config`)

**Description:** View or update DocsMCP configuration.

**Inputs:**
- `action`: `"get"` | `"set"`
- `key`: Config key (for set)
- `value`: Config value (for set)

**Configuration options:**
- `output_dir`: Where generated docs are written (default: `docs/`)
- `readme_style`: Default README style
- `changelog_format`: Default changelog format
- `adr_template`: Default ADR template
- `diagram_format`: Default diagram format
- `languages`: Languages to analyze (auto-detected)
- `exclude_patterns`: Glob patterns to exclude from analysis
- `drift_sensitivity`: Default drift detection sensitivity
- `completeness_level`: Required completeness level

---

## 9. MCP Tool Inventory

### 9.1 Complete Tool List

| # | Tool Name | Category | Description |
|---|---|---|---|
| 1 | `docs_session_start` | Session | Initialize session, detect project context |
| 2 | `docs_project_scan` | Analysis | Comprehensive documentation state scan |
| 3 | `docs_config` | Config | View/update DocsMCP configuration |
| 4 | `docs_generate_readme` | Generation | Generate or update README.md |
| 5 | `docs_generate_api` | Generation | Generate API reference documentation |
| 6 | `docs_generate_changelog` | Generation | Generate CHANGELOG.md from git history |
| 7 | `docs_generate_adr` | Generation | Create Architecture Decision Records |
| 8 | `docs_generate_diagram` | Generation | Generate Mermaid/PlantUML diagrams |
| 9 | `docs_generate_onboarding` | Generation | Generate getting-started / developer guide |
| 10 | `docs_generate_contributing` | Generation | Generate CONTRIBUTING.md |
| 11 | `docs_generate_release_notes` | Generation | Generate version release notes |
| 12 | `docs_check_drift` | Validation | Detect documentation drift from code |
| 13 | `docs_check_completeness` | Validation | Measure documentation coverage |
| 14 | `docs_check_links` | Validation | Validate documentation links |
| 15 | `docs_check_freshness` | Validation | Score documentation recency |
| 16 | `docs_module_map` | Analysis | Generate project module structure map |
| 17 | `docs_api_surface` | Analysis | Extract public API surface |
| 18 | `docs_git_summary` | Analysis | Summarize git history for docs context |

### 9.2 MCP Resources

| Resource URI | Description |
|---|---|
| `docs://status` | Current documentation state summary |
| `docs://config` | Active configuration |
| `docs://templates/{type}` | Available templates for each doc type |
| `docs://coverage` | Documentation coverage report |

### 9.3 MCP Prompts

| Prompt | Description |
|---|---|
| `docs_workflow_overview` | Full DocsMCP workflow guide |
| `docs_workflow(task_type)` | Task-specific workflow (bootstrap, update, audit, release) |

---

## 10. Integration Points

### 10.1 TappsMCP Integration

DocsMCP can optionally consume TappsMCP data when both servers are available:

| TappsMCP Tool | DocsMCP Usage |
|---|---|
| `tapps_dependency_graph` | Feed into `docs_generate_diagram` for accurate dependency diagrams |
| `tapps_project_profile` | Enrich `docs_project_scan` with tech stack data |
| `tapps_score_file` | Generate quality badges in README |
| `tapps_dead_code` | Exclude dead code from API documentation |
| `tapps_impact_analysis` | Inform drift detection about blast radius |
| `tapps_validate_changed` | Trigger `docs_check_drift` for changed files |

**Implementation:** DocsMCP checks for TappsMCP data in MCP context or environment. When unavailable, it falls back to its own analysis (with `enriched: false` flag).

### 10.2 Git Integration

- Git history analysis for changelogs, release notes, freshness
- Git blame for staleness detection
- Git diff for drift detection
- Conventional commits parsing
- Tag-based version detection

### 10.3 CI/CD Integration

DocsMCP can generate CI workflow steps for documentation validation:

- **GitHub Actions:** Workflow that runs `docs_check_drift` and `docs_check_completeness` on PRs
- **Pre-commit hooks:** Link validation, completeness checks
- **Release automation:** Changelog and release notes generation triggered by tags

### 10.4 Documentation Platforms

Output compatible with:
- **GitHub** — Native Markdown rendering, Mermaid support
- **GitLab** — Markdown + Mermaid rendering
- **MkDocs** — Generate `mkdocs.yml` + Markdown source files
- **Sphinx** — Generate RST output format option
- **Mintlify** — Generate MDX output format option
- **ReadTheDocs** — Compatible with Sphinx/MkDocs output

---

## 11. Technology Stack

### 11.1 Core Dependencies

| Component | Technology | Rationale |
|---|---|---|
| **Runtime** | Python 3.12+ | Matches TappsMCP, rich AST module, ecosystem |
| **MCP Framework** | FastMCP 3.x | Industry standard, decorator-based, typed |
| **Package Manager** | uv | Fast, modern, matches TappsMCP |
| **CLI** | Click | Proven, matches TappsMCP pattern |
| **Configuration** | Pydantic v2 + YAML | Type-safe, matches TappsMCP |
| **Logging** | structlog | JSON-structured, matches TappsMCP |
| **Type Checking** | mypy (strict) | Matches TappsMCP quality bar |
| **Linting** | ruff | Matches TappsMCP |
| **Testing** | pytest + pytest-asyncio | Matches TappsMCP |
| **Templates** | Jinja2 | Industry standard, powerful, well-typed |

### 11.2 Analysis Dependencies

| Component | Technology | Rationale |
|---|---|---|
| **Python AST** | `ast` (stdlib) | Zero-dependency, reliable |
| **TypeScript AST** | tree-sitter (optional) | Multi-language parsing |
| **Git analysis** | `gitpython` or subprocess `git` | Git history, blame, diff |
| **Commit parsing** | Custom conventional commits parser | No heavy dependency |
| **Diagram rendering** | Mermaid text output | No rendering dependency; clients render |
| **Markdown processing** | `mistune` or `markdown-it-py` | Link extraction, section parsing |

### 11.3 Optional Dependencies

| Component | Technology | When Needed |
|---|---|---|
| **tree-sitter** | Multi-lang AST | TypeScript/Go/Rust/Java support |
| **pygments** | Syntax highlighting | HTML report output |
| **jinja2** | Template engine | Document generation |

---

## 12. Epic Breakdown

### Epic 0: Foundation & Security (~1 week)

| Story | Description | LOE |
|---|---|---|
| 0.1 | Project scaffolding (pyproject.toml, src layout, uv setup) | 2h |
| 0.2 | FastMCP server skeleton with `docs_session_start` | 4h |
| 0.3 | Configuration system (Pydantic settings, YAML config, defaults) | 4h |
| 0.4 | Path validation / security sandbox (port from TappsMCP pattern) | 3h |
| 0.5 | CLI skeleton (Click, `docsmcp serve`, `docsmcp doctor`) | 3h |
| 0.6 | Logging setup (structlog) | 1h |
| 0.7 | Test infrastructure (pytest, conftest, fixtures, CI) | 3h |
| 0.8 | CLAUDE.md, AGENTS.md, initial README | 2h |

### Epic 1: Code Extraction Engine (~2 weeks)

| Story | Description | LOE |
|---|---|---|
| 1.1 | Python AST extractor — functions, classes, methods, decorators | 8h |
| 1.2 | Docstring parser (Google, NumPy, Sphinx styles) | 6h |
| 1.3 | Type annotation extractor | 4h |
| 1.4 | Module structure analyzer | 4h |
| 1.5 | Public API surface detector (`__all__`, naming conventions) | 4h |
| 1.6 | Import graph builder | 6h |
| 1.7 | Generic/regex-based fallback extractor | 4h |
| 1.8 | `docs_module_map` and `docs_api_surface` MCP tools | 4h |

### Epic 2: Git Analysis Engine (~1.5 weeks)

| Story | Description | LOE |
|---|---|---|
| 2.1 | Git log parser with structured output | 4h |
| 2.2 | Conventional commits parser (type, scope, breaking changes) | 6h |
| 2.3 | Non-conventional commit classifier (keyword heuristics) | 4h |
| 2.4 | Tag/version boundary detection | 3h |
| 2.5 | Git blame integration for staleness analysis | 4h |
| 2.6 | Git diff analysis for drift detection | 4h |
| 2.7 | `docs_git_summary` MCP tool | 3h |

### Epic 3: README Generation (~1.5 weeks)

| Story | Description | LOE |
|---|---|---|
| 3.1 | Project metadata extraction (pyproject.toml, package.json, Cargo.toml) | 6h |
| 3.2 | README templates (minimal, standard, comprehensive) with Jinja2 | 6h |
| 3.3 | Section generators (installation, usage, development, etc.) | 8h |
| 3.4 | Smart-merge engine (update sections, preserve human content) | 8h |
| 3.5 | Badge generation (CI, coverage, version, license) | 3h |
| 3.6 | `docs_generate_readme` MCP tool | 3h |

### Epic 4: API Documentation Generation (~2 weeks)

| Story | Description | LOE |
|---|---|---|
| 4.1 | API doc template system (Markdown, MkDocs, Sphinx RST) | 6h |
| 4.2 | Module-level documentation generator | 6h |
| 4.3 | Class documentation generator (methods, properties, inheritance) | 8h |
| 4.4 | Function documentation generator (params, returns, exceptions) | 6h |
| 4.5 | Cross-reference resolver | 4h |
| 4.6 | Example extraction from test files | 4h |
| 4.7 | `docs_generate_api` MCP tool | 3h |

### Epic 5: Changelog & Release Notes (~1.5 weeks)

| Story | Description | LOE |
|---|---|---|
| 5.1 | Keep-a-Changelog format generator | 6h |
| 5.2 | Conventional changelog format generator | 4h |
| 5.3 | Version section builder (grouping, attribution, links) | 4h |
| 5.4 | Breaking changes extractor and highlighter | 3h |
| 5.5 | Release notes generator (user-facing narrative) | 4h |
| 5.6 | `docs_generate_changelog` and `docs_generate_release_notes` MCP tools | 4h |

### Epic 6: Diagram Generation (~1.5 weeks)

| Story | Description | LOE |
|---|---|---|
| 6.1 | Mermaid diagram primitives (nodes, edges, subgraphs, styling) | 4h |
| 6.2 | Dependency graph → Mermaid flowchart | 6h |
| 6.3 | Class hierarchy → Mermaid class diagram | 6h |
| 6.4 | Module structure → Mermaid architecture diagram | 4h |
| 6.5 | Pydantic/dataclass → Mermaid ER diagram | 4h |
| 6.6 | PlantUML output option | 3h |
| 6.7 | `docs_generate_diagram` MCP tool | 3h |

### Epic 7: Documentation Validation (~2 weeks)

| Story | Description | LOE |
|---|---|---|
| 7.1 | Drift detection engine (code changes vs doc state) | 8h |
| 7.2 | Completeness checker (coverage scoring across categories) | 6h |
| 7.3 | Link validator (internal references, anchors, file paths) | 6h |
| 7.4 | Freshness scorer (git blame + modification dates) | 4h |
| 7.5 | Consistency checker (cross-document terminology, naming) | 4h |
| 7.6 | `docs_check_drift`, `docs_check_completeness`, `docs_check_links`, `docs_check_freshness` MCP tools | 6h |

### Epic 8: ADR & Guides (~1 week)

| Story | Description | LOE |
|---|---|---|
| 8.1 | ADR templates (MADR, Nygard) | 4h |
| 8.2 | ADR numbering, indexing, and supersession | 3h |
| 8.3 | Onboarding guide generator | 6h |
| 8.4 | Contributing guide generator | 4h |
| 8.5 | `docs_generate_adr`, `docs_generate_onboarding`, `docs_generate_contributing` MCP tools | 4h |

### Epic 9: Project Scan & Workflow (~1 week)

| Story | Description | LOE |
|---|---|---|
| 9.1 | `docs_project_scan` comprehensive documentation audit | 6h |
| 9.2 | MCP resources (status, config, templates, coverage) | 4h |
| 9.3 | MCP prompts (workflow overview, task-specific workflows) | 4h |
| 9.4 | Configuration management (`docs_config` tool) | 3h |
| 9.5 | AGENTS.md generation for consuming projects | 3h |

### Epic 10: Distribution & CLI (~1 week)

| Story | Description | LOE |
|---|---|---|
| 10.1 | PyPI packaging and publishing | 3h |
| 10.2 | CLI commands (`docsmcp serve`, `generate`, `check`, `doctor`) | 6h |
| 10.3 | Docker image | 3h |
| 10.4 | npm wrapper package (for Node-ecosystem users) | 3h |
| 10.5 | CI workflow generator for documentation checks | 4h |

### Epic 11: TappsMCP Integration (~1 week)

| Story | Description | LOE |
|---|---|---|
| 11.1 | TappsMCP data consumption protocol | 4h |
| 11.2 | Dependency graph enrichment for diagrams | 3h |
| 11.3 | Project profile enrichment for scans | 3h |
| 11.4 | Quality badge generation from TappsMCP scores | 2h |
| 11.5 | Drift detection in TappsMCP checklist integration | 3h |

### Epic 12: Multi-Language Support (~2 weeks, post-MVP)

| Story | Description | LOE |
|---|---|---|
| 12.1 | tree-sitter integration for multi-language AST | 8h |
| 12.2 | TypeScript extractor | 6h |
| 12.3 | Go extractor | 6h |
| 12.4 | Rust extractor | 6h |
| 12.5 | Java extractor | 6h |

### Total Estimated LOE

| Phase | Epics | Duration |
|---|---|---|
| **MVP (Epics 0-7)** | Foundation → Validation | ~12 weeks |
| **Full v1.0 (Epics 8-11)** | Guides, Workflow, Distribution, Integration | ~4 weeks |
| **v1.1+ (Epic 12)** | Multi-language | ~2 weeks |

---

## 13. Quality & Testing Strategy

### 13.1 Testing Requirements

| Layer | Target | Tools |
|---|---|---|
| **Unit tests** | 80%+ coverage, all extractors and generators | pytest |
| **Integration tests** | End-to-end tool calls with real codebases | pytest + sample repos |
| **Snapshot tests** | Generated documentation output stability | pytest-snapshot |
| **Property tests** | AST extractor robustness | hypothesis |

### 13.2 Quality Gates

- `ruff check` — zero warnings
- `ruff format --check` — formatted
- `mypy --strict` — type-safe
- `pytest --cov=docsmcp --cov-fail-under=80` — coverage threshold
- TappsMCP `tapps_validate_changed` — if TappsMCP is available in CI

### 13.3 Test Fixtures

- Sample Python projects with known structure (minimal, complex, multi-package)
- Sample git histories with conventional commits
- Sample documentation in various states (complete, drifted, missing)
- Edge cases: empty files, no docstrings, circular imports, monorepos

---

## 14. Distribution Strategy

| Channel | Format | Target Audience |
|---|---|---|
| **PyPI** | `pip install docsmcp` / `uv add docsmcp` | Python developers |
| **npm** | `npx docsmcp` (wrapper) | Node ecosystem users |
| **Docker** | `docker run docsmcp` | CI/CD, containerized environments |
| **GitHub Releases** | Binary + source | Direct download |
| **MCP Registry** | Listed in official MCP server registry | Discovery |

---

## 15. Success Metrics

### 15.1 Adoption Metrics

| Metric | Target (6 months) |
|---|---|
| PyPI monthly downloads | 5,000+ |
| GitHub stars | 500+ |
| MCP registry listing | Listed and discoverable |

### 15.2 Quality Metrics

| Metric | Target |
|---|---|
| Test coverage | 80%+ |
| mypy strict compliance | 100% |
| Tool response time (p95) | < 5s for single-file tools, < 30s for project-wide |

### 15.3 User Impact Metrics

| Metric | Measurement |
|---|---|
| Documentation completeness improvement | Before/after completeness scores on adopting projects |
| Drift reduction | Drift score trends over time |
| README quality | Community feedback, adoption in open-source projects |

---

## 16. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| **AST parsing fails on complex code** | Incomplete extraction | Medium | Graceful degradation with warnings; regex fallback |
| **Git history analysis is slow on large repos** | Poor UX for big projects | Medium | Configurable depth limits; incremental analysis; caching |
| **Generated docs are generic/low quality** | Low adoption | Medium | Rich templates; structured data for LLM prose; quality examples |
| **MCP protocol changes** | Breaking compatibility | Low | Pin to 2025-11-25; follow spec evolution |
| **TappsMCP coupling too tight** | DocsMCP can't standalone | Medium | All TappsMCP integrations are optional with fallbacks |
| **Multi-language support complexity** | Delayed delivery | High | Python-first MVP; other languages are post-v1.0 |
| **Documentation drift detection false positives** | User fatigue | Medium | Configurable sensitivity; evidence-based reporting |
| **Overlap with GitHub Copilot Docs Agent** | Competitive pressure | Medium | Open-source, MCP-native, multi-platform differentiation |

---

## 17. Future Roadmap

### v1.1 — Multi-Language (Epic 12)
- TypeScript, Go, Rust, Java extractors via tree-sitter

### v1.2 — Advanced Diagrams
- Sequence diagrams from runtime traces
- Data flow diagrams
- Infrastructure diagrams (from Terraform/Docker/K8s configs)

### v1.3 — Documentation Site Generation
- MkDocs project generator (full `mkdocs.yml` + theme configuration)
- Sphinx project generator
- Mintlify project generator

### v1.4 — Collaborative Features
- Documentation review workflow (like code review but for docs)
- Documentation ownership (DOCOWNERS file)
- Metrics dashboard (coverage trends, drift trends, contributor docs activity)

### v1.5 — Memory & Learning
- Shared memory system (like TappsMCP's) for documentation decisions
- Style guide learning from existing documentation
- Terminology consistency enforcement

### v2.0 — Agent-to-Agent
- MCP agent-to-agent protocol support (2026 spec extension)
- DocsMCP as a documentation agent that other agents can delegate to
- TappsMCP ↔ DocsMCP bidirectional data sharing

---

## 18. References & Research

### 18.1 MCP Protocol & Ecosystem

| Resource | URL | Notes |
|---|---|---|
| MCP Specification (2025-11-25) | https://modelcontextprotocol.io/specification/2025-11-25 | Current stable spec |
| MCP Official Servers | https://github.com/modelcontextprotocol/servers | Reference implementations |
| FastMCP (Python) | https://github.com/jlowin/fastmcp | Standard Python MCP framework, v3.0+ |
| FastMCP Tutorial | https://www.firecrawl.dev/blog/fastmcp-tutorial-building-mcp-servers-python | Building MCP servers guide |
| IBM MCP Architecture Patterns | https://developer.ibm.com/articles/mcp-architecture-patterns-ai-systems/ | Multi-agent MCP patterns |
| MCP Best Practices (IBM) | https://ibm.github.io/mcp-context-forge/best-practices/developing-your-mcp-server-python/ | Server development best practices |
| MCP State of the Art (Elastic) | https://www.elastic.co/search-labs/blog/mcp-current-state | MCP ecosystem analysis 2025-2026 |
| MCP as USB-C of AI | https://mirilittleme.medium.com/the-model-context-protocol-how-mcp-became-the-usb-c-of-ai-in-just-one-year-11a15e3611d2 | MCP adoption trajectory |
| Awesome MCP Servers | https://github.com/punkpeye/awesome-mcp-servers | Curated MCP server list |

### 18.2 Documentation MCP Servers (Existing)

| Server | URL | Notes |
|---|---|---|
| Context7 (Upstash) | https://github.com/upstash/context7 | Library doc lookup for LLMs (read-only) |
| docs-mcp-server (arabold) | https://github.com/arabold/docs-mcp-server | Personal doc index with semantic search (read-only) |
| Microsoft Learn MCP | https://github.com/MicrosoftDocs/mcp | Microsoft docs for LLMs (read-only) |
| GitHub MCP Server | https://github.com/github/github-mcp-server | GitHub API integration, not docs generation |

### 18.3 AI Documentation Generation Tools

| Tool | URL | Notes |
|---|---|---|
| Mintlify | https://www.mintlify.com/ | AI-native docs platform, Autopilot agent, MCP read server |
| Mintlify Autopilot | https://www.mintlify.com/blog/autopilot | Self-updating docs agent |
| DocuWriter.ai | https://www.docuwriter.ai/ | AI code documentation, UML, Swagger generation |
| Swimm | https://www.docuwriter.ai/compare/docuwriter-swimm-alternative | Code-coupled documentation, drift detection |
| DeepDocs | https://deepdocs.dev/documentation-in-agile-development/ | GitHub-native AI docs agent |
| readme-ai | https://github.com/eli64s/readme-ai | AI-powered README generator CLI |
| ReadmeX | https://github.com/aibox22/readmeX | AI README + wiki generator |
| GitHub Copilot Docs Agent | https://github.blog/changelog/2026-02-13-github-agentic-workflows-are-now-in-technical-preview/ | Agentic workflows for docs (tech preview) |

### 18.4 Documentation Frameworks & Standards

| Resource | URL | Notes |
|---|---|---|
| MkDocs | https://www.mkdocs.org/ | Markdown-based static site generator |
| mkdocstrings | https://github.com/mkdocstrings/mkdocstrings | Auto API docs from docstrings for MkDocs |
| Sphinx | https://www.sphinx-doc.org/ | Python documentation standard |
| Pydoc-Markdown | https://niklasrosenstein.github.io/pydoc-markdown/ | Python API docs in Markdown (parse-only) |
| Zensical (alpha) | N/A | Next-gen from mkdocs-material creators, late 2026 |
| Keep a Changelog | https://keepachangelog.com/ | Changelog format standard |
| Conventional Commits | https://www.conventionalcommits.org/ | Commit message standard |

### 18.5 Changelog & Release Tools

| Tool | URL | Notes |
|---|---|---|
| git-cliff | https://git-cliff.org/ | Highly customizable changelog generator (Rust) |
| conventional-changelog | https://github.com/conventional-changelog/conventional-changelog | Node-based conventional changelog |
| commitlint | https://commitlint.js.org/ | Commit message linting |

### 18.6 Diagram Tools

| Tool | URL | Notes |
|---|---|---|
| Mermaid.js | https://mermaid.js.org/ | Text-to-diagram, GitHub/GitLab native |
| Mermaid VS Code Plugin | https://test-docs.mermaidchart.com/blog/posts/the-essential-guide-to-mermaid-chart-plugin-for-vs-code-08-2025 | AI diagram generation from code |
| dependency-graph-mermaid | https://github.com/power-modules/dependency-graph-mermaid | Dep graph to Mermaid renderer |

### 18.7 Architecture Decision Records

| Resource | URL | Notes |
|---|---|---|
| ADR GitHub Organization | https://adr.github.io/ | ADR standards and tooling |
| ADR Examples | https://github.com/joelparkerhenderson/architecture-decision-record | Templates and examples |
| ADR Tooling | https://adr.github.io/adr-tooling/ | Decision capturing tools |
| AI-Generated ADRs | https://piethein.medium.com/building-an-architecture-decision-record-writer-agent-a74f8f739271 | ADR writer agent pattern |
| log4brains | https://github.com/thomvaill/log4brains | ADR management and publication |

### 18.8 Documentation Drift & Quality

| Resource | URL | Notes |
|---|---|---|
| Documentation Drift (Gaudion) | https://gaudion.dev/blog/documentation-drift | What is drift and how to avoid it |
| DocuMate Drift Detection | https://dev.to/calebyhan/documate-eliminate-documentation-drift-3hhh | Static analysis + AI drift detection |
| IEEE Drift Detection Paper | https://ieeexplore.ieee.org/document/11196773/ | Academic review of drift detection methods |
| AI-Driven Documentation 2026 | https://overcast.blog/ai-driven-documentation-in-2026-f993f0c6d0d6 | Industry trends and practices |

### 18.9 API Documentation Best Practices (2026)

| Resource | URL | Notes |
|---|---|---|
| OpenAPI Documentation Tools | https://treblle.com/blog/best-openapi-documentation-tools | 13 best OpenAPI tools for 2026 |
| API Documentation Best Practices | https://www.theneo.io/blog/api-documentation-best-practices-how-to-simplify-integration-for-developers | Integration simplification guide |
| AI Documentation Generators 2026 | https://www.nxcode.io/resources/news/ai-documentation-generator-2026 | Market overview |
| Software Documentation Tools 2026 | https://ferndesk.com/blog/best-software-documentation-tools | Comprehensive comparison |
| API Documentation Tools Comparison | https://ferndesk.com/blog/best-api-documentation-tools | Deep dive comparison |

### 18.10 TappsMCP (Companion Project)

| Resource | Location | Notes |
|---|---|---|
| TappsMCP Source | `C:\cursor\TappMCP` | Companion code quality MCP server |
| TappsMCP Architecture | `C:\cursor\TappMCP\CLAUDE.md` | Server module split pattern, tool registration |
| TappsMCP Epic Structure | `C:\cursor\TappMCP\docs\planning\epics\` | Epic planning reference |
| TappsMCP Dependency Graph | `tapps_dependency_graph` tool | Consumable by DocsMCP for diagrams |
| TappsMCP Project Profile | `tapps_project_profile` tool | Consumable by DocsMCP for context |

---

## Appendix A: Configuration File Schema

```yaml
# .docsmcp.yaml — DocsMCP project configuration
version: "1.0"

# General settings
output_dir: "docs/"
languages:
  - python
exclude_patterns:
  - "**/__pycache__/**"
  - "**/node_modules/**"
  - "**/.venv/**"

# README generation
readme:
  style: "standard"  # minimal | standard | comprehensive
  badges:
    - ci
    - coverage
    - version
    - license
  custom_sections: []

# API documentation
api:
  format: "markdown"  # markdown | mkdocs | sphinx_rst
  depth: "public"     # public | protected | all
  docstring_style: "google"  # google | numpy | sphinx | auto
  include_examples: true

# Changelog
changelog:
  format: "keep-a-changelog"  # keep-a-changelog | conventional | simple
  group_by: "type"            # type | scope | date
  include_breaking: true

# Architecture Decision Records
adr:
  template: "madr"    # madr | nygard | custom
  directory: "docs/decisions/"

# Diagrams
diagrams:
  format: "mermaid"   # mermaid | plantuml
  default_depth: 2

# Validation
validation:
  drift_sensitivity: "medium"  # low | medium | high
  completeness_level: "standard"  # minimal | standard | comprehensive
  check_external_links: false
  freshness_threshold_days: 30

# TappsMCP integration (optional)
tapps_integration:
  enabled: true  # auto-detected; false if TappsMCP not available
  consume_dependency_graph: true
  consume_project_profile: true
  consume_quality_scores: true
```

## Appendix B: Example Tool Output

### `docs_check_drift` Example Response

```json
{
  "tool": "docs_check_drift",
  "success": true,
  "data": {
    "drift_score": 62,
    "status": "drifted",
    "summary": "Documentation is moderately out of sync with codebase",
    "sections": [
      {
        "file": "README.md",
        "section": "Installation",
        "drift": "high",
        "evidence": "pyproject.toml added 3 new dependencies since README was last updated",
        "last_doc_update": "2026-01-15",
        "last_code_change": "2026-02-25",
        "suggested_action": "Update installation section with new dependencies"
      },
      {
        "file": "README.md",
        "section": "API Reference",
        "drift": "critical",
        "evidence": "4 new public functions added to core module without API documentation",
        "functions": ["process_batch", "validate_config", "export_results", "migrate_schema"],
        "suggested_action": "Generate API documentation for new public functions"
      },
      {
        "file": "docs/architecture.md",
        "section": "Module Diagram",
        "drift": "medium",
        "evidence": "2 new modules (analytics/, reporting/) not shown in architecture diagram",
        "suggested_action": "Regenerate architecture diagram with docs_generate_diagram"
      }
    ],
    "next_steps": [
      "Run docs_generate_api to document new public functions",
      "Run docs_generate_readme(update_mode='smart_merge') to update README",
      "Run docs_generate_diagram(diagram_type='module_map') to update architecture"
    ]
  }
}
```

## Appendix C: Naming Conventions

| Convention | Pattern | Example |
|---|---|---|
| MCP tool names | `docs_{verb}_{noun}` | `docs_generate_readme`, `docs_check_drift` |
| Python modules | `snake_case` | `api_reference.py`, `drift.py` |
| Config keys | `snake_case` | `drift_sensitivity`, `output_dir` |
| Template files | `{type}_{variant}.md.j2` | `readme_standard.md.j2` |
| Test files | `test_{module}.py` | `test_readme.py`, `test_drift.py` |
