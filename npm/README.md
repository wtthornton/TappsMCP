# tapps-mcp (npm wrapper)

npm wrapper for the [TappsMCP](https://github.com/wtthornton/TappsMCP) Python MCP server — a quality toolset for AI coding assistants.

TappsMCP gives Claude Code, Cursor, VS Code Copilot, and other MCP-capable clients deterministic code quality tools: scoring, security scanning, quality gates, documentation lookup, and config validation.

## Installation

This wrapper assumes the `tapps-mcp` Python package is already installed locally. TappsMCP is **not published to PyPI**; install it from a local checkout first:

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd TappsMCP
uv tool install -e packages/tapps-mcp
```

Then add this npm wrapper to any project that needs to launch the server through a Node-only toolchain:

```bash
npm install -g tapps-mcp
tapps-mcp serve
```

If `tapps-mcp` is not on `$PATH`, the wrapper will fail with a clear error pointing back at the checkout install.

## Available commands

```bash
tapps-mcp serve                    # Start the MCP server (stdio)
tapps-mcp serve --transport http   # Start with HTTP transport
tapps-mcp init                     # Generate MCP config for your AI client
tapps-mcp doctor                   # Diagnose configuration issues
```

## Requirements

- Node.js 18+
- Python 3.12+
- The `tapps-mcp` Python entry point on `$PATH` (installed via `uv tool install -e` from the TappsMCP checkout)

## What this does

This is a thin wrapper that forwards all arguments to the `tapps-mcp` CLI. It exists so projects with Node-centric tooling can launch TappsMCP from `package.json` scripts without juggling Python paths directly.

## Optional dependencies

For best scoring results, install these Python tools alongside tapps-mcp:

```bash
pip install ruff mypy bandit radon vulture pip-audit
```

## Documentation

For full documentation, see the [TappsMCP repo](https://github.com/wtthornton/TappsMCP).
