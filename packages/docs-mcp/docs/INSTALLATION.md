# DocsMCP Installation Guide

DocsMCP is an MCP server for automated documentation generation, validation, and maintenance. It is **not published to PyPI** — install from a local checkout of the TappsMCP repo.

## Installation

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd TappsMCP
uv tool install -e packages/docs-mcp
```

This puts `docsmcp` on your `$PATH`. To work on docs-mcp itself:

```bash
uv sync --all-packages           # full workspace dev install
uv run docsmcp serve             # run from the checkout
```

## Quick Start

### 1. Verify installation

```bash
docsmcp version
docsmcp doctor
```

### 2. Run the MCP server

```bash
# stdio transport (for local MCP clients)
docsmcp serve

# HTTP transport (for remote/container usage)
docsmcp serve --transport http --host 127.0.0.1 --port 8000
```

### 3. Use via python -m

```bash
python -m docs_mcp serve
```

## MCP Client Configuration

### Claude Code

Add to `.claude/settings.json` or project-level `mcp.json`:

```json
{
  "mcpServers": {
    "docs-mcp": {
      "command": "docsmcp",
      "args": ["serve"],
      "env": {
        "TAPPS_MCP_PROJECT_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

To auto-approve all DocsMCP tools, add to `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__docs-mcp__*"
    ]
  }
}
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "docs-mcp": {
      "command": "docsmcp",
      "args": ["serve"],
      "env": {
        "TAPPS_MCP_PROJECT_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

### VS Code Copilot

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "docs-mcp": {
      "command": "docsmcp",
      "args": ["serve"],
      "env": {
        "TAPPS_MCP_PROJECT_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

## Docker

### Build the image

```bash
cd packages/docs-mcp
docker build -t docs-mcp .
```

### Run with stdio transport

```bash
docker run -i --rm \
  -v /path/to/your/project:/workspace:ro \
  docs-mcp serve
```

### Run with HTTP transport

```bash
docker run -d --rm \
  -p 8000:8000 \
  -v /path/to/your/project:/workspace:ro \
  docs-mcp serve --transport http --host 0.0.0.0 --port 8000
```

### MCP config with Docker

```json
{
  "mcpServers": {
    "docs-mcp": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "/path/to/your/project:/workspace:ro",
        "docs-mcp", "serve"
      ]
    }
  }
}
```

## Available Tools

DocsMCP provides 40 MCP tools across these categories:

### Session
- `docs_session_start` - Initialize session and detect project context
- `docs_config` - View or update DocsMCP configuration

### Analysis
- `docs_project_scan` - Comprehensive documentation state audit
- `docs_module_map` - Hierarchical Python module tree
- `docs_api_surface` - Public API surface of a Python file
- `docs_git_summary` - Git history with conventional commit parsing

### Generation
- `docs_generate_readme` - Generate or update README.md (minimal/standard/comprehensive)
- `docs_generate_changelog` - Generate CHANGELOG.md from git history
- `docs_generate_release_notes` - Generate release notes for a version
- `docs_generate_api` - Generate API documentation (markdown/mkdocs/sphinx_rst)
- `docs_generate_adr` - Generate Architecture Decision Records (MADR/Nygard)
- `docs_generate_onboarding` - Generate getting-started guide
- `docs_generate_contributing` - Generate CONTRIBUTING.md
- `docs_generate_prd` - Generate Product Requirements Document
- `docs_generate_diagram` - Generate Mermaid/PlantUML/D2 diagrams (8 types: dependency/class/module/ER/C4/sequence, D2 themes)
- `docs_generate_architecture` - Self-contained HTML architecture report with SVG
- `docs_generate_interactive_diagrams` - Interactive HTML viewer with pan/zoom for Mermaid diagrams
- `docs_generate_epic` - Generate epic planning docs with expert enrichment
- `docs_generate_story` - Generate user story docs with expert enrichment
- `docs_generate_prompt` - Generate reusable prompt templates from project context
- `docs_generate_llms_txt` - Machine-readable llms.txt project summary
- `docs_generate_frontmatter` - YAML frontmatter injection/update for markdown files
- `docs_generate_purpose` - Purpose/intent architecture template
- `docs_generate_doc_index` - Documentation index/map with auto-categorization

### Validation
- `docs_validate_epic` - Validate epic documents for completeness and consistency
- `docs_check_drift` - Detect code changes not reflected in docs
- `docs_check_completeness` - Score documentation completeness (0-100)
- `docs_check_links` - Validate internal links in markdown files
- `docs_check_freshness` - Score documentation freshness (fresh/aging/stale/ancient)
- `docs_check_diataxis` - Diataxis quadrant coverage analysis and balance scoring
- `docs_check_cross_refs` - Cross-reference validation (orphans, broken refs, backlinks)
- `docs_check_style` - Deterministic markdown style/tone checks
- `docs_validate_release_update` - Validate a release-update document against the canonical template
- `docs_release_gate` - Aggregate pre-release verdict (drift + freshness + broken links)

### Release generation
- `docs_generate_release_update` - Generate a structured release-update document

### Linear
- `docs_lint_linear_issue` - Lint a Linear issue payload against the agent-issue template
- `docs_validate_linear_issue` - Pre-create gate for Linear issues (`agent_ready`)
- `docs_save_linear_issue` - Pre-save gate sentinel before Linear `save_issue`
- `docs_linear_triage` - Batch-triage Linear issue payloads

### Knowledge graph
- `docs_kg_query` - Query brain knowledge graph (`mode=neighbors` or `mode=explain`)

### Tool presets

Set `tool_preset` in `.docsmcp.yaml` or `DOCS_MCP_TOOL_PRESET` to limit exposed tools:

| Preset | Tools | Use case |
|--------|-------|----------|
| `core` | 6 | Bootstrap, drift, readme, completeness, links |
| `planner` | 10 | Epic/story planning + Linear issue quality |
| `release` | 10 | Changelog, release notes, release gate |
| `auditor` | 10 | Full documentation health checks |
| `full` | 40 | All tools (default) |

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TAPPS_MCP_PROJECT_ROOT` | Project root directory | Current working directory |
| `DOCS_MCP_OUTPUT_DIR` | Output directory for generated docs | `docs/` |
| `DOCS_MCP_LOG_LEVEL` | Logging level | `WARNING` |
| `DOCS_MCP_LOG_JSON` | Enable JSON log format | `false` |
