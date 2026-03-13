# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in the docs-mcp package.

## What is DocsMCP?

DocsMCP is a **documentation MCP server** -- a companion to TappsMCP that provides deterministic documentation generation, validation, and analysis tools via structured MCP tool calls. It extracts code structure, analyzes git history, generates docs (README, changelog, API reference, ADRs, guides, diagrams), and validates documentation freshness, completeness, drift, and links. Any MCP-capable client can use it. If you are a consuming project, see [AGENTS.md](AGENTS.md) instead.

## Package location

DocsMCP lives at `packages/docs-mcp/` within the TappsMCP uv workspace monorepo. It depends on `tapps-core` for shared infrastructure (config, security, logging).

## Repository structure

```
packages/docs-mcp/
├── pyproject.toml
├── src/docs_mcp/
│   ├── __init__.py, cli.py, py.typed
│   ├── server.py              # FastMCP instance + docs_session_start, docs_project_scan, docs_config
│   ├── server_helpers.py      # Response builders, settings singleton
│   ├── server_analysis.py     # docs_module_map, docs_api_surface
│   ├── server_git_tools.py    # docs_git_summary
│   ├── server_gen_tools.py    # docs_generate_readme, _changelog, _release_notes, _api, _adr, _onboarding, _contributing, _diagram, _prd, _purpose, _doc_index, _llms_txt, _frontmatter, _interactive_diagrams
│   ├── server_val_tools.py    # docs_check_drift, _completeness, _links, _freshness, _diataxis, _cross_refs
│   ├── config/
│   │   ├── settings.py        # DocsMCPSettings (Pydantic), load_docs_settings()
│   │   └── default.yaml
│   ├── extractors/            # AST-based Python source extraction
│   │   ├── base.py, models.py
│   │   ├── python.py, generic.py
│   │   ├── docstring_parser.py, type_annotations.py
│   ├── analyzers/             # Code and git analysis
│   │   ├── module_map.py      # Hierarchical module tree builder
│   │   ├── api_surface.py     # Public API surface analyzer
│   │   ├── dependency.py      # Import dependency analysis
│   │   ├── git_history.py     # Git commit log reader
│   │   ├── commit_parser.py   # Conventional commit parser
│   │   └── version_detector.py # Semver tag detector
│   ├── generators/            # Documentation content generators
│   │   ├── metadata.py        # Project metadata extraction
│   │   ├── readme.py          # README generation (3 styles)
│   │   ├── smart_merge.py     # Merge generated with existing README
│   │   ├── changelog.py       # CHANGELOG generation
│   │   ├── release_notes.py   # Per-version release notes
│   │   ├── api_docs.py        # API reference docs (markdown/mkdocs/sphinx_rst)
│   │   ├── adr.py             # Architecture Decision Records (MADR/Nygard)
│   │   ├── guides.py          # Onboarding + contributing guides
│   │   ├── specs.py           # Product Requirements Documents (PRD)
│   │   ├── diagrams.py        # Mermaid/PlantUML diagrams (8 types incl. C4, sequence)
│   │   ├── interactive_html.py # Interactive HTML viewer with Mermaid.js
│   │   ├── architecture.py    # Self-contained HTML architecture report with SVG
│   │   ├── epics.py           # Epic planning docs with expert enrichment
│   │   ├── stories.py         # User story docs with expert enrichment
│   │   ├── llms_txt.py        # llms.txt machine-readable project summary
│   │   ├── frontmatter.py     # YAML frontmatter injection/update
│   │   ├── purpose.py         # Purpose/intent architecture template
│   │   └── doc_index.py       # Documentation index/map generator
│   ├── analyzers/             # Code and git analysis (continued)
│   │   └── diataxis.py        # Diataxis content classifier
│   ├── validators/            # Documentation quality checks
│   │   ├── drift.py           # Code-vs-docs drift detection
│   │   ├── completeness.py    # Documentation completeness scoring
│   │   ├── link_checker.py    # Internal link validation
│   │   ├── freshness.py       # File age classification
│   │   ├── diataxis.py        # Diataxis coverage validation
│   │   └── cross_ref.py       # Cross-reference validation
│   └── integrations/
│       └── tapps.py           # Optional TappsMCP enrichment reader
└── tests/
    ├── conftest.py
    ├── unit/
    └── integration/
```

## Development commands

```bash
# Install all packages (from repo root)
uv sync --all-packages

# Run docs-mcp tests
uv run pytest packages/docs-mcp/tests/ -v

# Run a single test file
uv run pytest packages/docs-mcp/tests/unit/test_readme.py -v

# Run a single test by name
uv run pytest packages/docs-mcp/tests/unit/test_readme.py -k "test_generate_standard" -v

# Type checking
uv run mypy --strict packages/docs-mcp/src/docs_mcp/

# Linting and formatting
uv run ruff check packages/docs-mcp/src/
uv run ruff format --check packages/docs-mcp/src/

# Run the server (stdio)
uv run docsmcp serve

# Run the server (HTTP / Streamable HTTP)
uv run docsmcp serve --transport http --port 8000

# CLI utilities
uv run docsmcp doctor     # check config and dependencies
uv run docsmcp scan       # inventory documentation files
uv run docsmcp version    # print version
```

## Architecture

### Data flow

```
Source Code  -->  Extractors  -->  Analyzers  -->  Generators  -->  Output
    |                                  |                              |
    |          Git History  ---------->|                              |
    |                                                                |
    +----  Validators  <---------------------------------------------+
```

1. **Extractors** parse Python source files via AST to extract functions, classes, constants, docstrings, and type annotations.
2. **Analyzers** build higher-level views: module maps, API surfaces, dependency graphs, git history, and version boundaries.
3. **Generators** produce documentation content (README, changelog, API docs, ADRs, guides, diagrams) from analyzed data.
4. **Validators** check existing documentation for drift, completeness, broken links, and staleness.

### Server module split

The MCP server is split across five tool files sharing the same `mcp` FastMCP instance created in `server.py`:

- **`server.py`** -- Creates `FastMCP("DocsMCP")` and registers `docs_session_start`, `docs_project_scan`, `docs_config`. Imports the other four modules at the bottom.
- **`server_analysis.py`** -- `docs_module_map`, `docs_api_surface`
- **`server_git_tools.py`** -- `docs_git_summary`
- **`server_gen_tools.py`** -- `docs_generate_readme`, `docs_generate_changelog`, `docs_generate_release_notes`, `docs_generate_api`, `docs_generate_adr`, `docs_generate_onboarding`, `docs_generate_contributing`, `docs_generate_prd`, `docs_generate_diagram`, `docs_generate_architecture`, `docs_generate_epic`, `docs_generate_story`, `docs_generate_prompt`, `docs_generate_llms_txt`, `docs_generate_frontmatter`, `docs_generate_interactive_diagrams`, `docs_generate_purpose`, `docs_generate_doc_index`
- **`server_val_tools.py`** -- `docs_check_drift`, `docs_check_completeness`, `docs_check_links`, `docs_check_freshness`, `docs_validate_epic`, `docs_check_diataxis`, `docs_check_cross_refs`
- **`server_helpers.py`** -- Response builders (`error_response`, `success_response`), settings singleton (`_get_settings`)

### Configuration

Config is loaded by `config/settings.py` with this precedence:
1. Environment variables (`DOCS_MCP_*`)
2. Project-level `.docsmcp.yaml`
3. Built-in defaults

Settings are cached via `load_docs_settings()`. Reset with `_reset_docs_settings_cache()` in tests.

### TappsMCP integration

`integrations/tapps.py` provides optional enrichment by reading TappsMCP export data from `.tapps-mcp/docsmcp-export.json`. When TappsMCP data is available, `docs_project_scan` and `docs_check_drift` include quality scores and project profile information. All integration methods return safe defaults when TappsMCP data is unavailable.

### Tool registration flow

To add a new MCP tool:
1. Add the handler in the appropriate `server_*.py` file using `@mcp.tool()`
2. Call `_record_call("tool_name")` at the top of the handler
3. Use `_get_settings()` from `server_helpers.py` for configuration
4. Use `error_response()` and `success_response()` for return values
5. Add tests in `packages/docs-mcp/tests/unit/`

## The 31 MCP tools

| Category | Tool | Description |
|---|---|---|
| Session | `docs_session_start` | Project detection, doc inventory, recommendations |
| Session | `docs_config` | View or update DocsMCP configuration |
| Analysis | `docs_project_scan` | Comprehensive documentation state audit |
| Analysis | `docs_module_map` | Hierarchical Python module tree |
| Analysis | `docs_api_surface` | Public API surface of a Python file |
| Analysis | `docs_git_summary` | Git history with conventional commit parsing |
| Generation | `docs_generate_readme` | README with smart merge (minimal/standard/comprehensive) |
| Generation | `docs_generate_changelog` | CHANGELOG from git tags/commits |
| Generation | `docs_generate_release_notes` | Per-version release notes |
| Generation | `docs_generate_api` | API reference docs (markdown/mkdocs/sphinx_rst) |
| Generation | `docs_generate_adr` | Architecture Decision Records (MADR/Nygard) |
| Generation | `docs_generate_onboarding` | Getting-started guide |
| Generation | `docs_generate_contributing` | CONTRIBUTING.md |
| Generation | `docs_generate_prd` | Product Requirements Document (standard/comprehensive, auto-populate, SmartMerger) |
| Generation | `docs_generate_diagram` | Mermaid/PlantUML diagrams (dependency/class/module/ER/C4/sequence) |
| Generation | `docs_generate_architecture` | Self-contained HTML architecture report with SVG diagrams |
| Generation | `docs_generate_epic` | Epic planning docs with stories, AC, expert enrichment |
| Generation | `docs_generate_story` | User story docs with tasks, AC, expert enrichment |
| Generation | `docs_generate_prompt` | Generate reusable prompt templates from project context |
| Generation | `docs_generate_llms_txt` | Machine-readable llms.txt project summary (compact/full) |
| Generation | `docs_generate_frontmatter` | YAML frontmatter injection/update for markdown files |
| Generation | `docs_generate_interactive_diagrams` | Interactive HTML viewer with pan/zoom for Mermaid diagrams |
| Generation | `docs_generate_purpose` | Purpose/intent architecture template with inferred principles |
| Generation | `docs_generate_doc_index` | Documentation index/map with auto-categorization |
| Validation | `docs_validate_epic` | Validate epic documents for completeness and consistency |
| Validation | `docs_check_drift` | Detect code changes not reflected in docs |
| Validation | `docs_check_completeness` | Score documentation completeness (0-100) |
| Validation | `docs_check_links` | Validate internal links in markdown files |
| Validation | `docs_check_freshness` | Score documentation freshness (fresh/aging/stale/ancient) |
| Validation | `docs_check_diataxis` | Diataxis quadrant coverage analysis and balance scoring |
| Validation | `docs_check_cross_refs` | Cross-reference validation (orphans, broken refs, backlinks) |

## Code conventions

- **Python 3.12+** -- `from __future__ import annotations` at the top of every file
- **Type annotations everywhere** -- `mypy --strict` must pass
- **`structlog`** for logging -- never `print()` or `logging` directly
- **`pathlib.Path`** for all file paths
- **Pydantic v2** models for configuration and data structures
- **`ruff`** for linting and formatting (line length: 100)
- **Async/await** for all tool handlers
- All file write operations through `tapps_core.security.path_validator.PathValidator`

## Known gotchas

- **mypy + `@mcp.tool()`**: The mcp SDK decorator is untyped. Needs `disallow_untyped_decorators = false` override.
- **Settings cache**: `load_docs_settings()` caches the no-arg case. Pass explicit `project_root` to bypass. Reset via `_reset_docs_settings_cache()` in tests.
- **Server module import order**: The `server_*.py` modules are imported at the bottom of `server.py` to avoid circular imports. They must import `mcp` from `server.py`.
- **TappsMCP integration**: Always optional. Never import TappsMCP modules at module level -- use try/except inside tool handlers.
- **Smart merge markers**: README generation uses `<!-- docsmcp:begin:section -->` / `<!-- docsmcp:end:section -->` markers. Human-written content outside markers is preserved.

## Self-hosted quality pipeline

When TappsMCP's MCP server is available in your session, use it on this codebase:

1. Call `tapps_session_start` first
2. Use `tapps_quick_check` after editing Python files
3. Use `tapps_validate_changed` before declaring work complete
4. Call `tapps_checklist(task_type="feature")` before finishing
