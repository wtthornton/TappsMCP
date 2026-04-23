# DocsMCP - instructions for AI assistants

When the **DocsMCP** MCP server is configured in your host (Claude Code, Cursor, VS Code Copilot, etc.), you have access to tools that provide **deterministic documentation generation, validation, and code analysis**. DocsMCP analyzes your codebase and git history to produce accurate, up-to-date documentation without hallucination.

---

## What DocsMCP is

DocsMCP is an MCP server that provides 35 tools for:

- **Code analysis** -- module maps, API surface extraction, dependency analysis via AST parsing
- **Git analysis** -- commit history with conventional commit parsing, version detection from tags
- **Documentation generation** -- README, CHANGELOG, release notes, API reference, ADRs, onboarding guides, contributing guides, PRDs, epics, stories, prompt templates, diagrams (Mermaid/PlantUML/D2), interactive HTML diagrams, llms.txt, frontmatter, architecture templates, doc index
- **Documentation validation** -- drift detection, completeness scoring, link checking, freshness classification, Diataxis coverage analysis, cross-reference validation, epic validation, deterministic style/tone checks
- **Linear-issue quality tooling** (v3.0.0+) -- lint, validate, and batch-triage Linear issue payloads against the 5-section agent-issue template (What / Where / Why / Acceptance / Refs) defined in `docs/linear/AGENT_ISSUES.md`. Read-only; the agent fetches issue payloads via the Linear MCP plugin and passes them here for scoring.
- **Configuration** -- view and update DocsMCP settings per-project
- **TappsMCP integration** -- optional quality score enrichment when TappsMCP is also available

You only see these tools when the host has started the DocsMCP server and attached it to your session.

**File paths:** For tools that take `project_root` or file paths, use paths relative to the project root. Most tools auto-detect the project root from configuration or CWD.

---

## Tool inventory

| Tool | Purpose |
|------|---------|
| **docs_session_start** | Detect project type, scan existing docs, return config and recommendations |
| **docs_project_scan** | Comprehensive documentation state audit with completeness scoring |
| **docs_config** | View or update DocsMCP configuration (`.docsmcp.yaml`) |
| **docs_module_map** | Build hierarchical module tree with public API counts and docstrings |
| **docs_api_surface** | Analyze public API of a Python file (functions, classes, constants, coverage) |
| **docs_git_summary** | Git history analysis with conventional commit parsing and version boundaries |
| **docs_generate_readme** | Generate or update README.md with smart merge (preserves human sections) |
| **docs_generate_changelog** | Generate CHANGELOG.md from git tags and commits |
| **docs_generate_release_notes** | Generate structured release notes for a specific version |
| **docs_generate_api** | Generate API reference docs from Python source (markdown/mkdocs/sphinx_rst) |
| **docs_generate_adr** | Create auto-numbered Architecture Decision Records (MADR/Nygard) |
| **docs_generate_onboarding** | Generate getting-started / onboarding guide |
| **docs_generate_contributing** | Generate CONTRIBUTING.md with dev setup and PR workflow |
| **docs_generate_prd** | Generate Product Requirements Documents (standard/comprehensive, auto-populate, SmartMerger) |
| **docs_generate_diagram** | Generate Mermaid/PlantUML/D2 diagrams (dependency/class/module/ER/C4/sequence, D2 themes) |
| **docs_generate_architecture** | Self-contained HTML architecture report with SVG diagrams |
| **docs_generate_epic** | Epic planning docs with stories, AC, expert enrichment |
| **docs_generate_story** | User story docs with tasks, AC, expert enrichment |
| **docs_generate_prompt** | Generate reusable prompt templates from project context |
| **docs_generate_llms_txt** | Machine-readable llms.txt project summary (compact/full) |
| **docs_generate_frontmatter** | YAML frontmatter injection/update for markdown files |
| **docs_generate_interactive_diagrams** | Interactive HTML viewer with pan/zoom for Mermaid diagrams |
| **docs_generate_purpose** | Purpose/intent architecture template with inferred principles |
| **docs_generate_doc_index** | Documentation index/map with auto-categorization |
| **docs_validate_epic** | Validate epic documents for completeness and consistency |
| **docs_check_drift** | Detect documentation drift -- code changes not reflected in docs |
| **docs_check_completeness** | Check documentation completeness across multiple categories |
| **docs_check_links** | Validate internal links in markdown documentation files |
| **docs_check_freshness** | Score documentation freshness (fresh/aging/stale/ancient) |
| **docs_check_diataxis** | Diataxis quadrant coverage analysis and balance scoring |
| **docs_check_cross_refs** | Cross-reference validation (orphans, broken refs, backlinks) |
| **docs_check_style** | Deterministic style/tone checks for markdown (passive voice, jargon, headings, sentence length, tense consistency) |
| **docs_lint_linear_issue** | Lint a Linear issue payload against the agent-issue template (9 rules, agent-readiness label) |
| **docs_validate_linear_issue** | Pre-create gate: HIGH-severity findings only, returns `{agent_ready, score, missing, issues}` |
| **docs_linear_triage** | Batch triage of N issue payloads — label proposals, parent groupings, metadata gaps |

---

## When to use each tool

| Tool | When to use it |
|------|----------------|
| **docs_session_start** | **First call in every session** -- returns project info, existing docs inventory, and recommendations for missing docs. |
| **docs_project_scan** | When you need a **comprehensive audit** of documentation state with completeness scoring (0-100). |
| **docs_config** | To **view current settings** (`action="view"`) or **update a setting** (`action="set"`, `key="..."`, `value="..."`). |
| **docs_module_map** | When you need to **understand project structure** -- module hierarchy, package layout, entry points. |
| **docs_api_surface** | When you need to **document a specific file** -- shows functions, classes, constants, and which are missing docstrings. |
| **docs_git_summary** | When you need **commit history context** for changelogs, release notes, or understanding recent changes. |
| **docs_generate_readme** | When the project **needs a README** or the existing one needs updating. Uses smart merge to preserve human-written sections. |
| **docs_generate_changelog** | When you need to **create or update a CHANGELOG**. Supports keep-a-changelog and conventional formats. |
| **docs_generate_release_notes** | When **preparing a release** and need structured notes with highlights, breaking changes, and contributors. |
| **docs_generate_api** | When you need **API reference documentation** from source code. Supports markdown, mkdocs, and sphinx_rst output. |
| **docs_generate_adr** | When **recording an architecture decision**. Auto-numbers by scanning existing ADRs. |
| **docs_generate_onboarding** | When a project **needs a getting-started guide** for new developers. |
| **docs_generate_contributing** | When a project **needs contribution guidelines**. |
| **docs_generate_prd** | When planning a **new feature or product** -- generates structured PRD with phased requirements and Gherkin acceptance criteria. |
| **docs_generate_diagram** | When you need a **visual overview** of dependencies, class hierarchies, module structure, data models, C4 architecture, or sequence flows. Supports Mermaid, PlantUML, and D2 formats. |
| **docs_generate_architecture** | When you need a **self-contained HTML architecture report** with SVG diagrams. |
| **docs_generate_epic** | When **planning a new epic** -- generates structured epic docs with stories, acceptance criteria, and expert enrichment. |
| **docs_generate_story** | When **writing user stories** -- generates structured story docs with tasks, acceptance criteria, and expert enrichment. |
| **docs_generate_prompt** | When you need to **create reusable prompt templates** from project context. |
| **docs_generate_llms_txt** | When creating **machine-readable project summaries** for LLMs (llms.txt format). |
| **docs_generate_frontmatter** | When **injecting or updating YAML frontmatter** in markdown files. |
| **docs_generate_interactive_diagrams** | When you need **interactive, zoomable diagrams** in an HTML viewer with Mermaid.js. |
| **docs_generate_purpose** | When you need a **purpose/intent architecture template** with auto-inferred principles. |
| **docs_generate_doc_index** | When you need a **documentation index/map** with auto-categorization. |
| **docs_validate_epic** | When **reviewing an epic document** -- validates completeness and consistency. |
| **docs_check_drift** | After **code changes** -- detects public API names missing from documentation. |
| **docs_check_completeness** | During **documentation review** -- scores completeness across critical docs, API docs, guides, ADRs. |
| **docs_check_links** | Before **publishing or merging** -- catches broken internal links. |
| **docs_check_freshness** | During **documentation audit** -- identifies stale docs that may need updating. |
| **docs_check_diataxis** | When assessing **documentation balance** across Diataxis quadrants (tutorials, how-to, reference, explanation). |
| **docs_check_cross_refs** | When validating **cross-references** between documentation files -- finds orphans and broken refs. |
| **docs_check_style** | When reviewing **writing quality** in markdown -- flags jargon, passive voice, long sentences, heading case, and tense mixing. Use `output_format="vale"` for Vale-shaped output. |
| **docs_lint_linear_issue** | When the user hands you a Linear issue to prep for agent work -- scores against 9 rules (autolink mangle, UUID refs, title length, missing file anchor / Acceptance, fenced-block anchoring, priority / estimate). Returns score, findings, suggested agent-readiness label, and reclaimable-noise byte count. |
| **docs_validate_linear_issue** | **Pre-create gate** before saving an issue via the Linear plugin -- returns `{agent_ready, score, missing, issues, suggested_label}`. Only HIGH-severity findings surface in `missing[]`; medium/low stay with the lint tool. |
| **docs_linear_triage** | When auditing a **backlog or batch** of Linear issues -- aggregates label proposals, clusters issues sharing file paths into parent-grouping candidates, summarizes metadata gaps. Read-only, takes N issue payloads as input. |

---

## Recommended workflow

### 1. Start session

Call `docs_session_start` to discover existing documentation and get recommendations.

### 2. Discover (analysis tools)

Use analysis tools to understand the codebase before generating docs:

- `docs_project_scan` -- full documentation inventory and completeness score
- `docs_module_map` -- understand package/module structure
- `docs_api_surface` -- inspect a specific file's public API
- `docs_git_summary` -- review recent changes and version history

### 3. Generate (generation tools)

Generate or update documentation based on analysis:

- `docs_generate_readme` -- start here for new projects
- `docs_generate_api` -- API reference from source code
- `docs_generate_changelog` -- changelog from git history
- `docs_generate_release_notes` -- release notes for a version
- `docs_generate_adr` -- record architecture decisions
- `docs_generate_onboarding` -- developer onboarding guide
- `docs_generate_contributing` -- contribution guidelines
- `docs_generate_prd` -- product requirements documents
- `docs_generate_diagram` -- visual diagrams (Mermaid/PlantUML/D2, 8 types, D2 themes)
- `docs_generate_architecture` -- HTML architecture report
- `docs_generate_interactive_diagrams` -- interactive HTML viewer with pan/zoom
- `docs_generate_epic` -- epic planning docs
- `docs_generate_story` -- user story docs
- `docs_generate_prompt` -- reusable prompt templates
- `docs_generate_llms_txt` -- machine-readable llms.txt
- `docs_generate_frontmatter` -- YAML frontmatter injection
- `docs_generate_purpose` -- architecture purpose/intent template
- `docs_generate_doc_index` -- documentation index/map

### 4. Validate (validation tools)

Check documentation quality after generation or code changes:

- `docs_validate_epic` -- validate epic completeness and consistency
- `docs_check_drift` -- code changes not reflected in docs
- `docs_check_completeness` -- documentation coverage score
- `docs_check_links` -- broken internal links
- `docs_check_freshness` -- stale documentation files
- `docs_check_diataxis` -- Diataxis quadrant coverage analysis
- `docs_check_cross_refs` -- cross-reference validation
- `docs_check_style` -- style and tone (deterministic rules)

### 5. Configure

Use `docs_config` to adjust settings:

- `docs_config(action="view")` -- see current configuration
- `docs_config(action="set", key="default_style", value="comprehensive")` -- change a setting

---

## Task-specific workflows

### Bootstrap documentation for a new project

1. `docs_session_start` -- see what exists and what is missing
2. `docs_module_map` -- understand the project structure
3. `docs_generate_readme(style="standard")` -- create the README
4. `docs_generate_contributing` -- create contribution guidelines
5. `docs_generate_onboarding` -- create getting-started guide
6. `docs_check_completeness` -- verify documentation coverage

### Update documentation after code changes

1. `docs_check_drift` -- find where docs lag behind code
2. `docs_api_surface(source_path="changed_file.py")` -- inspect new/changed APIs
3. `docs_generate_readme(merge=True)` -- update README preserving human sections
4. `docs_generate_api(source_path="...")` -- regenerate API docs for changed modules
5. `docs_check_links` -- verify no broken links

### Audit documentation staleness

1. `docs_session_start` -- inventory existing docs
2. `docs_check_freshness` -- classify docs by age (fresh/aging/stale/ancient)
3. `docs_check_completeness` -- score overall documentation health
4. `docs_check_drift` -- find code-doc mismatches
5. `docs_check_links` -- find broken references

### Prepare a release

1. `docs_git_summary(include_versions=True)` -- review commits and version history
2. `docs_generate_changelog` -- update or create CHANGELOG.md
3. `docs_generate_release_notes(version="1.2.0")` -- generate notes for the release
4. `docs_generate_diagram(diagram_type="dependency")` -- update architecture diagram
5. `docs_check_links` -- final link check before publishing

### Record an architecture decision

1. `docs_generate_adr(title="Use MCP protocol", context="...", decision="...", consequences="...")`
2. The ADR is auto-numbered and written to `docs/decisions/`

### Generate visual diagrams

- `docs_generate_diagram(diagram_type="dependency")` -- module import graph
- `docs_generate_diagram(diagram_type="class_hierarchy")` -- class inheritance
- `docs_generate_diagram(diagram_type="module_map")` -- package architecture
- `docs_generate_diagram(diagram_type="er_diagram")` -- entity-relationship from models
- `docs_generate_diagram(diagram_type="c4_context")` -- C4 System Context diagram
- `docs_generate_diagram(diagram_type="c4_container")` -- C4 Container diagram
- `docs_generate_diagram(diagram_type="c4_component")` -- C4 Component diagram
- `docs_generate_diagram(diagram_type="sequence")` -- sequence diagram (auto-detect or manual flow_spec)

Use `format="mermaid"` (default) for GitHub-rendered diagrams, `format="plantuml"` for PlantUML toolchains, or `format="d2"` for D2 diagrams. D2 supports themes: `theme="default"`, `theme="sketch"`, or `theme="terminal"`.

---

## Integration with TappsMCP

When both DocsMCP and TappsMCP servers are available in the same session:

- `docs_project_scan` enriches results with TappsMCP project profile (project type, tech stack, CI, test frameworks) and may include `style_summary` when `style_include_in_project_scan` is true
- `docs_check_drift` enriches results with quality scores for files with documentation drift
- Use TappsMCP's `tapps_quick_check` and `tapps_validate_changed` on DocsMCP's own source files after edits

The integration is always optional -- DocsMCP works fully independently when TappsMCP is not available.

---

## Configuration reference

Settings can be viewed/changed via `docs_config` or set in `.docsmcp.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `output_dir` | `docs` | Directory for generated documentation |
| `default_style` | `standard` | README style: minimal, standard, comprehensive |
| `default_format` | `markdown` | Output format: markdown, rst, plain |
| `include_toc` | `true` | Include table of contents |
| `include_badges` | `true` | Include badges in README |
| `changelog_format` | `keep-a-changelog` | Changelog format: keep-a-changelog, conventional |
| `adr_format` | `madr` | ADR template: madr, nygard |
| `diagram_format` | `mermaid` | Diagram format: mermaid, plantuml, d2 |
| `git_log_limit` | `500` | Maximum git commits to analyze |
| `style_enabled_rules` | *(see default.yaml)* | Rules for `docs_check_style`: passive_voice, jargon, sentence_length, heading_consistency, tense_consistency |
| `style_heading` | `sentence` | Heading case: `sentence` or `title` |
| `style_max_sentence_words` | `40` | Flag sentences longer than this |
| `style_custom_terms` | `[]` | Terms allowed in headings / excluded from jargon checks |
| `style_jargon_terms` | `[]` | Custom jargon list (non-empty overrides built-in jargon list) |
| `style_include_in_project_scan` | `true` | When true, `docs_project_scan` includes `style_summary` |
| `style_auto_detect_terms` | `false` | When true, scan `*.py` for class/def names and merge into custom terms (bounded) |
| `style_auto_detect_max_files` | `120` | Max Python files to read for auto-detect |
| `style_auto_detect_max_terms` | `80` | Max terms to add from auto-detect |
| `enabled_tools` | *(none)* | Allow list: only these tools are exposed. Empty/missing = all tools. Env: `DOCS_MCP_ENABLED_TOOLS` (comma-separated). |
| `disabled_tools` | `[]` | Deny list: excluded from the exposed set. Ignored when `enabled_tools` is set. Env: `DOCS_MCP_DISABLED_TOOLS`. |
| `tool_preset` | *(none)* | Preset: `full` (all 32 tools, default) or `core` (6 tools: session_start, project_scan, check_drift, generate_readme, check_completeness, check_links). Env: `DOCS_MCP_TOOL_PRESET`. |

Environment variables use the `DOCS_MCP_` prefix (e.g., `DOCS_MCP_OUTPUT_DIR`).

### Reducing tool count (Epic 79.2)

When using DocsMCP with TappsMCP or in environments where the combined tool count should stay within recommended limits (~30 tools), you can restrict which DocsMCP tools are exposed:

- **enabled_tools** (allow list): when non-empty, only these tools are registered. Comma-separated in env: `DOCS_MCP_ENABLED_TOOLS=docs_session_start,docs_project_scan,docs_check_drift`.
- **disabled_tools** (deny list): tools to exclude from the full set. Applied when `enabled_tools` is not set. Env: `DOCS_MCP_DISABLED_TOOLS`.
- **tool_preset**: `full` (all tools, default when unset) or `core` (6 essential tools). Env: `DOCS_MCP_TOOL_PRESET=core`.

Empty or missing = all 32 tools (backward compatible). Invalid tool names in `enabled_tools` are ignored and logged. See tool-count best practices in the repo planning docs (Epic 79).
