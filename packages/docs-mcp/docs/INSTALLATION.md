# DocsMCP Installation Guide

DocsMCP is an MCP server for automated documentation generation, validation, and maintenance.

## Installation

### Via uv (recommended)

```bash
uv add docs-mcp
```

### Via pip

```bash
pip install docs-mcp
```

### From source (development)

```bash
git clone https://github.com/tapps-mcp/tapps-mcp.git
cd tapps-mcp
uv sync --all-packages
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

DocsMCP provides 24 MCP tools across these categories:

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
- `docs_generate_diagram` - Generate Mermaid/PlantUML diagrams (dependency/class/module/ER)
- `docs_generate_architecture` - Self-contained HTML architecture report with SVG
- `docs_generate_epic` - Generate epic planning docs with expert enrichment
- `docs_generate_story` - Generate user story docs with expert enrichment
- `docs_generate_prompt` - Generate reusable prompt templates from project context

### Validation
- `docs_validate_epic` - Validate epic documents for completeness and consistency
- `docs_check_drift` - Detect code changes not reflected in docs
- `docs_check_completeness` - Score documentation completeness (0-100)
- `docs_check_links` - Validate internal links in markdown files
- `docs_check_freshness` - Score documentation freshness (fresh/aging/stale/ancient)

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TAPPS_MCP_PROJECT_ROOT` | Project root directory | Current working directory |
| `DOCS_MCP_OUTPUT_DIR` | Output directory for generated docs | `docs/` |
| `DOCS_MCP_LOG_LEVEL` | Logging level | `WARNING` |
| `DOCS_MCP_LOG_JSON` | Enable JSON log format | `false` |
