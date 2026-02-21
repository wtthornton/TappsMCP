# tapps-mcp

npm wrapper for the [TappsMCP](https://github.com/tapps-mcp/tapps-mcp) Python MCP server — a quality toolset for AI coding assistants.

TappsMCP gives Claude Code, Cursor, VS Code Copilot, and other MCP-capable clients deterministic code quality tools: scoring, security scanning, quality gates, documentation lookup, config validation, and domain expert consultation.

## Usage

```bash
npx tapps-mcp serve
```

Or install globally:

```bash
npm install -g tapps-mcp
tapps-mcp serve
```

### Available commands

```bash
tapps-mcp serve                    # Start the MCP server (stdio)
tapps-mcp serve --transport http   # Start with HTTP transport
tapps-mcp init                     # Generate MCP config for your AI client
tapps-mcp doctor                   # Diagnose configuration issues
```

## Requirements

- Node.js 18+
- Python 3.12+ (auto-detected)
- pip or uv (for auto-installing the Python package)

## What this does

This is a thin wrapper that:
1. Checks for Python 3.12+
2. Installs the `tapps-mcp` Python package if needed
3. Forwards all arguments to the `tapps-mcp` CLI

## Optional dependencies

For best results, install these Python tools: `pip install ruff mypy bandit radon`

For semantic expert search: `pip install tapps-mcp[rag]`

## Documentation

For full documentation, see [tapps-mcp on GitHub](https://github.com/tapps-mcp/tapps-mcp).
