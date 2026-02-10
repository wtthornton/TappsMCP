# tapps-mcp

npm wrapper for the [TappsMCP](https://github.com/tapps-mcp/tapps-mcp) Python MCP server.

## Usage

```bash
npx tapps-mcp serve
```

Or install globally:

```bash
npm install -g tapps-mcp
tapps-mcp serve
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

For full documentation, see [tapps-mcp on GitHub](https://github.com/tapps-mcp/tapps-mcp).
