# TappsPlatform Composition Guide

TappsMCP (29 code quality tools) and DocsMCP (19 documentation tools) can be served as a single combined MCP server — **TappsPlatform** — or as separate standalone servers.

## When to use each mode

| | Standalone TappsMCP | Standalone DocsMCP | Combined TappsPlatform |
|---|---|---|---|
| **Tools** | 29 (`tapps_*`) | 19 (`docs_*`) | 48 (all) |
| **Use case** | Code quality only | Documentation only | Full platform |
| **Claude Code** | Yes | Yes | Yes (recommended) |
| **Cursor** | Yes | Yes | No (exceeds 40-tool limit) |
| **VS Code Copilot** | Yes | Yes | Yes |
| **GitHub Copilot** | Yes | Yes | Yes |
| **Memory overhead** | Baseline | Baseline | ~Same (shared singletons) |
| **Startup** | ~2s | ~1s | ~3s |

**Rule of thumb**: Use the combined server unless you only need one tool set or your MCP client has a tool limit (Cursor).

## Server modes

| Mode | Tools | Command |
|---|---|---|
| **Combined** | 48 (all) | `python examples/combined_server.py` |
| **Quality only** | 29 | `uv run tapps-mcp serve` |
| **Docs only** | 19 | `uv run docsmcp serve` |

The platform CLI wraps all three modes:

```bash
python examples/platform_cli.py serve          # combined (default)
python examples/platform_cli.py serve-tapps    # TappsMCP only
python examples/platform_cli.py serve-docs     # DocsMCP only
```

## How composition works

The MCP Python SDK (v1.x) does not provide a `mount()` API for combining servers. Instead, `examples/combined_server.py` creates a new `FastMCP("TappsPlatform")` instance and copies registered Tool, Resource, and Prompt objects from both servers' internal managers. This preserves all tool metadata (descriptions, schemas, annotations) without re-registration.

No namespace prefixes are needed because TappsMCP tools use `tapps_*` and DocsMCP tools use `docs_*` — there are zero name collisions.

## Client configuration

### Claude Code — combined server

Add to `.claude/settings.json` or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tapps-platform": {
      "command": "uv",
      "args": ["run", "python", "examples/combined_server.py"]
    }
  }
}
```

### Claude Code — separate servers

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["run", "tapps-mcp", "serve"]
    },
    "docs-mcp": {
      "command": "uv",
      "args": ["run", "docsmcp", "serve"]
    }
  }
}
```

### Cursor — separate servers (required)

Cursor has a **40-tool limit** per MCP server. The combined server has 48 tools, which exceeds this limit. Use separate servers:

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["run", "tapps-mcp", "serve"]
    },
    "docs-mcp": {
      "command": "uv",
      "args": ["run", "docsmcp", "serve"]
    }
  }
}
```

Save as `.cursor/mcp.json` in your project root.

### VS Code Copilot

Add to `.vscode/settings.json`:

```json
{
  "github.copilot.chat.mcpServers": {
    "tapps-platform": {
      "command": "uv",
      "args": ["run", "python", "examples/combined_server.py"]
    }
  }
}
```

Or separate servers:

```json
{
  "github.copilot.chat.mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["run", "tapps-mcp", "serve"]
    },
    "docs-mcp": {
      "command": "uv",
      "args": ["run", "docsmcp", "serve"]
    }
  }
}
```

### Streamable HTTP transport

All modes support HTTP transport for remote or multi-client setups:

```bash
# Combined
python examples/combined_server.py --transport http --port 8000

# Standalone
uv run tapps-mcp serve --transport http --host 0.0.0.0 --port 8000
uv run docsmcp serve --transport http --host 0.0.0.0 --port 8000
```

Client config for HTTP (any MCP client):

```json
{
  "mcpServers": {
    "tapps-platform": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

## Docker usage

### Standalone images

```bash
# TappsMCP only (from repo root)
docker build -t tapps-mcp .
docker run -v $(pwd):/workspace tapps-mcp

# DocsMCP only (from repo root)
docker build -f packages/docs-mcp/Dockerfile -t docs-mcp .
docker run -v $(pwd):/workspace docs-mcp

# HTTP transport
docker run -p 8000:8000 -v $(pwd):/workspace tapps-mcp \
  tapps-mcp serve --transport http --host 0.0.0.0 --port 8000
```

### Combined TappsPlatform image

```bash
# Build from repo root
docker build -f Dockerfile.platform -t tapps-platform .

# Run (stdio — for MCP client integration)
docker run -v $(pwd):/workspace tapps-platform

# Run (HTTP — for remote/multi-client)
docker run -p 8000:8000 -v $(pwd):/workspace tapps-platform \
  python -m examples.combined_server --transport http --host 0.0.0.0 --port 8000

# Run TappsMCP only from the combined image
docker run -v $(pwd):/workspace tapps-platform tapps-mcp serve

# Run DocsMCP only from the combined image
docker run -v $(pwd):/workspace tapps-platform docsmcp serve
```

MCP client config for Docker (stdio):

```json
{
  "mcpServers": {
    "tapps-platform": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "${workspaceFolder}:/workspace", "tapps-platform"]
    }
  }
}
```

## Shared singletons

When composed, both servers share the same tapps-core singletons:

- **Settings** — `load_settings()` returns one cached instance
- **MemoryStore** — single SQLite-backed memory database
- **CodeScorer** — single scorer instance
- **KBCache** — shared documentation cache with LRU eviction
- **PathValidator** — same security sandbox boundary

Configuration set via environment variables or `.tapps-mcp.yaml` applies uniformly to both tool sets.

## Performance characteristics

- **Tool dispatch overhead**: Zero additional overhead per tool call in combined mode — tools are direct function references, not proxied. The composition copies Tool objects once at startup.
- **Startup**: The combined server imports both packages, adding ~1s over the larger standalone server.
- **Memory**: Shared singletons (Settings, MemoryStore, CodeScorer, KBCache) mean the combined server uses less memory than running two separate servers side by side.
- **Recommendation**: For local development, the combined server is simpler to manage. For production or Cursor, use separate servers.

## Troubleshooting

### Cursor shows fewer tools than expected

Cursor enforces a 40-tool limit per MCP server. The combined TappsPlatform server has 48 tools and will be silently truncated. Use separate servers in Cursor (see configuration above).

### Tools not appearing after configuration change

Restart the MCP server process. Claude Code: re-open the project. Cursor: toggle the MCP server off/on in settings.

### `TAPPS_MCP_PROJECT_ROOT` not set

Both servers default to the current working directory. When running in Docker, mount your project to `/workspace` and the environment variable is set automatically. For local use, set it explicitly if tools report path validation errors:

```bash
export TAPPS_MCP_PROJECT_ROOT=/path/to/your/project
```

### HTTP transport connection refused

Ensure you bind to `0.0.0.0` (not `127.0.0.1`) when running inside Docker:

```bash
docker run -p 8000:8000 -v $(pwd):/workspace tapps-platform \
  python -m examples.combined_server --transport http --host 0.0.0.0 --port 8000
```

### Combined server import errors

The combined server requires both `tapps-mcp` and `docs-mcp` packages. Install all workspace packages:

```bash
uv sync --all-packages
```
