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

DocsMCP provides 18 MCP tools across these categories:

### Analysis
- `docs_session_start` - Initialize session and detect project context
- `docs_project_scan` - Scan project for documentation inventory
- `docs_analyze_module` - Analyze a Python module's structure

### Generation
- `docs_generate_readme` - Generate or update README.md
- `docs_generate_changelog` - Generate CHANGELOG.md from git history
- `docs_generate_release_notes` - Generate release notes for a version
- `docs_generate_api` - Generate API documentation for a module
- `docs_generate_adr` - Generate Architecture Decision Records
- `docs_generate_onboarding` - Generate onboarding guides
- `docs_generate_contributing` - Generate contributing guides
- `docs_generate_diagram` - Generate architecture diagrams

### Validation
- `docs_validate_drift` - Check for code/documentation drift
- `docs_validate_completeness` - Assess documentation completeness
- `docs_validate_links` - Check for broken documentation links
- `docs_validate_freshness` - Check documentation freshness

### Git Integration
- `docs_git_history` - Analyze git history for documentation context
- `docs_git_changelog_preview` - Preview changelog from recent commits
- `docs_detect_version` - Detect project version information

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TAPPS_MCP_PROJECT_ROOT` | Project root directory | Current working directory |
| `DOCS_MCP_OUTPUT_DIR` | Output directory for generated docs | `docs/` |
| `DOCS_MCP_LOG_LEVEL` | Logging level | `WARNING` |
| `DOCS_MCP_LOG_JSON` | Enable JSON log format | `false` |
