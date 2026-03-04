# docs-mcp

npm wrapper for the [DocsMCP](https://github.com/tapps-mcp/tapps-mcp/tree/master/packages/docs-mcp) Python MCP server -- a documentation toolset for AI coding assistants.

DocsMCP gives Claude Code, Cursor, VS Code Copilot, and other MCP-capable clients deterministic documentation tools: README generation, changelog creation, API reference docs, drift detection, completeness scoring, and link validation.

## Usage

```bash
npx docs-mcp serve
```

Or install globally:

```bash
npm install -g docs-mcp
docs-mcp serve
```

### Available commands

```bash
docs-mcp serve                    # Start the MCP server (stdio)
docs-mcp serve --transport http   # Start with HTTP transport
docs-mcp doctor                   # Diagnose configuration issues
docs-mcp scan                     # Inventory documentation files
```

## Requirements

- Node.js 18+
- Python 3.12+ (auto-detected)
- pip or uv (for auto-installing the Python package)

## What this does

This is a thin wrapper that:
1. Checks for Python 3.12+
2. Installs the `docs-mcp` Python package if needed
3. Forwards all arguments to the `docsmcp` CLI

## Documentation

For full documentation, see [docs-mcp on GitHub](https://github.com/tapps-mcp/tapps-mcp/tree/master/packages/docs-mcp).
