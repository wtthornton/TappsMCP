# docs-mcp (npm wrapper)

npm wrapper for the [DocsMCP](https://github.com/wtthornton/TappsMCP/tree/master/packages/docs-mcp) Python MCP server — a documentation toolset for AI coding assistants.

DocsMCP gives Claude Code, Cursor, VS Code Copilot, and other MCP-capable clients deterministic documentation tools: README generation, changelog creation, API reference docs, drift detection, completeness scoring, and link validation.

## Installation

This wrapper assumes the `docs-mcp` Python entry point is already installed locally. DocsMCP is **not published to PyPI**; install it from a local checkout first:

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd TappsMCP
uv tool install -e packages/docs-mcp
```

Then add this npm wrapper to any project that needs to launch the server through a Node-only toolchain:

```bash
npm install -g docs-mcp
docs-mcp serve
```

If `docsmcp` is not on `$PATH`, the wrapper will fail with a clear error pointing back at the checkout install.

## Available commands

```bash
docs-mcp serve                    # Start the MCP server (stdio)
docs-mcp serve --transport http   # Start with HTTP transport
docs-mcp doctor                   # Diagnose configuration issues
docs-mcp scan                     # Inventory documentation files
```

## Requirements

- Node.js 18+
- Python 3.12+
- The `docsmcp` Python entry point on `$PATH` (installed via `uv tool install -e` from the TappsMCP checkout)

## What this does

This is a thin wrapper that forwards all arguments to the `docsmcp` CLI. It exists so projects with Node-centric tooling can launch DocsMCP from `package.json` scripts without juggling Python paths directly.

## Documentation

For full documentation, see the [TappsMCP repo](https://github.com/wtthornton/TappsMCP/tree/master/packages/docs-mcp).
