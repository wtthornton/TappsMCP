# MCP Server Architecture Patterns

## Overview

The Model Context Protocol (MCP) defines a client-server architecture where a host
application (IDE, agent, or CLI) connects to one or more MCP servers that expose
tools, resources, and prompts. This guide covers MCP 2025-11-25 specification
patterns, FastMCP design, module splitting strategies, caching, security,
transport options, and deployment considerations.

## MCP Protocol Fundamentals (2025-11-25)

### Protocol Layers

```
Host Application (Cursor, Claude Code, VS Code Copilot)
    |
    v
MCP Client (SDK-provided, manages connection lifecycle)
    |
    v
Transport Layer (stdio, Streamable HTTP)
    |
    v
MCP Server (FastMCP instance, registers tools/resources/prompts)
    |
    v
Tool Handlers (async functions that implement tool logic)
```

### Capability Negotiation

When a client connects, the server declares its capabilities:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("TappsMCP")

# Capabilities are inferred from registered tools, resources, prompts.
# The server advertises:
# - tools: list of tool definitions with JSON schemas
# - resources: URI-based data providers
# - prompts: reusable prompt templates
```

### Message Flow

1. Client sends `initialize` request with client capabilities
2. Server responds with server capabilities and protocol version
3. Client sends `initialized` notification
4. Client can now call tools, read resources, get prompts
5. Either side can send notifications (progress, logging)

### Tool Definition Schema

Every MCP tool has a name, description, and JSON Schema for its input:

```python
@mcp.tool()
async def tapps_score_file(
    file_path: str,
    quick: bool = False,
    fix: bool = False,
    mode: str = "auto",
) -> str:
    """Score a Python file across 7 quality categories.

    Args:
        file_path: Path to the Python file to score.
        quick: If True, run ruff-only scoring (under 500ms).
        fix: If True, apply ruff auto-fixes first (requires quick=True).
        mode: Execution mode - subprocess, direct, or auto.
    """
    # FastMCP auto-generates the JSON Schema from type annotations
    # and docstring. No manual schema definition needed.
```

## FastMCP Design Patterns

### Creating the Server Instance

FastMCP is the high-level API for building MCP servers in Python:

```python
from mcp.server.fastmcp import FastMCP

# Create a single shared instance
mcp = FastMCP("TappsMCP")

# Do NOT pass version= (FastMCP does not accept it)
# Do NOT create multiple instances - use one shared object
```

### Tool Registration with @mcp.tool()

The `@mcp.tool()` decorator registers an async function as an MCP tool:

```python
@mcp.tool()
async def tapps_quick_check(
    file_path: str,
    preset: str = "standard",
    fix: bool = False,
) -> str:
    """Quick quality check with scoring and gate evaluation."""
    _record_call("tapps_quick_check")
    # Tool implementation...
    return json.dumps(result)
```

Key conventions:

- All tool handlers must be `async def`
- Type annotations drive the JSON Schema (no manual schema needed)
- The docstring becomes the tool description
- Return type is typically `str` (JSON-serialized)
- Call `_record_call("tool_name")` at the top for checklist tracking

### Resource Registration

Resources provide read-only data access via URI patterns:

```python
@mcp.resource("tapps://config")
async def get_config() -> str:
    """Return current TappsMCP configuration."""
    settings = _get_settings()
    return json.dumps(settings.model_dump(), indent=2)
```

### Prompt Registration

Prompts are reusable templates for guiding LLM behavior:

```python
@mcp.prompt()
async def develop_workflow() -> str:
    """Return the development workflow prompt."""
    return load_prompt("develop.md")
```

## Server Module Split Strategy

### Why Split?

A single `server.py` with 20+ tools becomes unmaintainable. Split by domain
to keep each module under complexity limits (radon CC < 10 per function):

```
server.py                    # FastMCP instance, resources, prompts, 14 core tools
server_scoring_tools.py      # tapps_score_file, tapps_quality_gate, tapps_quick_check
server_pipeline_tools.py     # tapps_validate_changed, tapps_init, tapps_upgrade, etc.
server_metrics_tools.py      # tapps_dashboard, tapps_stats, tapps_feedback, tapps_research
server_memory_tools.py       # tapps_memory (save, get, list, delete, search)
server_helpers.py            # Shared utilities, singleton caches, response builders
```

### Shared MCP Instance Pattern

All modules register tools on the same `mcp` object created in `server.py`:

```python
# server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("TappsMCP")

# Register core tools here with @mcp.tool()...

# Import sub-modules AFTER creating mcp - they import and decorate on the shared instance
import tapps_mcp.server_scoring_tools  # noqa: F401 - registers tools
import tapps_mcp.server_pipeline_tools  # noqa: F401
import tapps_mcp.server_metrics_tools  # noqa: F401
import tapps_mcp.server_memory_tools  # noqa: F401
```

```python
# server_scoring_tools.py
from tapps_mcp.server import mcp
from tapps_mcp.server_helpers import _record_call, _get_scorer

@mcp.tool()
async def tapps_score_file(file_path: str, quick: bool = False) -> str:
    _record_call("tapps_score_file")
    scorer = _get_scorer()
    # ...
```

### Adding a New Tool

1. Add the handler in the appropriate `server_*.py` file using `@mcp.tool()`
2. Call `_record_call("tool_name")` at the top
3. Register in the checklist task map (`tools/checklist.py`)
4. Add to AGENTS.md and README.md
5. Add tests in `tests/unit/` and optionally `tests/integration/`

## Singleton Caching Patterns

### Why Singletons?

Expensive objects (scorer, settings, memory store) should be created once and
reused across tool calls within a session:

```python
# server_helpers.py
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.scoring.scorer import CodeScorer
    from tapps_mcp.config.settings import TappsMCPSettings
    from tapps_mcp.memory.store import MemoryStore

_scorer_instance: CodeScorer | None = None
_settings_instance: TappsMCPSettings | None = None
_memory_store_instance: MemoryStore | None = None


def _get_scorer() -> CodeScorer:
    """Get or create the singleton CodeScorer."""
    global _scorer_instance
    if _scorer_instance is None:
        from tapps_mcp.scoring.scorer import CodeScorer
        _scorer_instance = CodeScorer()
    return _scorer_instance


def _reset_scorer_cache() -> None:
    """Reset the scorer singleton (for test isolation)."""
    global _scorer_instance
    _scorer_instance = None
```

### Cache Reset for Test Isolation

Tests must reset all singletons to prevent cross-test contamination:

```python
# tests/conftest.py
import pytest

@pytest.fixture(autouse=True)
def _reset_caches():
    """Reset all singleton caches after each test."""
    yield
    from tapps_mcp.server_helpers import (
        _reset_scorer_cache,
        _reset_memory_store_cache,
    )
    from tapps_mcp.config.settings import _reset_settings_cache
    from tapps_mcp.tools.tool_detection import _reset_tools_cache

    _reset_scorer_cache()
    _reset_memory_store_cache()
    _reset_settings_cache()
    _reset_tools_cache()
```

### Four Caches to Track

| Cache | Module | Reset Function |
|---|---|---|
| Settings | `config/settings.py` | `_reset_settings_cache()` |
| CodeScorer | `server_helpers.py` | `_reset_scorer_cache()` |
| MemoryStore | `server_helpers.py` | `_reset_memory_store_cache()` |
| Tool detection | `tools/tool_detection.py` | `_reset_tools_cache()` |

## Security: Path Sandboxing

### The Path Validator

All file I/O goes through the path validator to prevent directory traversal:

```python
from tapps_mcp.security.path_validator import validate_path

def read_file_safely(file_path: str, project_root: str) -> str:
    """Read a file only if it is within the project sandbox."""
    validated = validate_path(file_path, project_root)
    return validated.read_text(encoding="utf-8")
```

### Security Principles

1. **Sandbox to project root** - no reading/writing outside `TAPPS_MCP_PROJECT_ROOT`
2. **Validate all user-provided paths** - tool arguments are untrusted input
3. **RAG safety on knowledge content** - filter prompt injection in stored data
4. **Secret scanning** - detect hardcoded credentials before they reach the LLM
5. **IO guardrails** - rate limiting and size limits on file operations

### Environment Variable Configuration

```bash
# Set the project root (all file ops sandboxed here)
export TAPPS_MCP_PROJECT_ROOT=/path/to/project

# Override config file location
export TAPPS_MCP_CONFIG=/path/to/.tapps-mcp.yaml
```

## Error Handling Patterns

### Structured Error Responses

Return errors as structured JSON, not exceptions:

```python
@mcp.tool()
async def tapps_score_file(file_path: str) -> str:
    _record_call("tapps_score_file")
    try:
        result = await _do_scoring(file_path)
        return json.dumps(result)
    except FileNotFoundError:
        return json.dumps({
            "error": "file_not_found",
            "message": f"File not found: {file_path}",
        })
    except PermissionError:
        return json.dumps({
            "error": "path_outside_sandbox",
            "message": "File is outside the project root.",
        })
```

### Graceful Degradation

When optional tools are missing, fall back to AST-based analysis:

```python
async def score_with_fallback(file_path: str) -> dict:
    """Score a file, falling back to AST analysis if tools are missing."""
    tools = detect_installed_tools()

    if tools.ruff_available:
        ruff_result = await run_ruff(file_path)
    else:
        ruff_result = ast_based_lint(file_path)

    return {
        "score": ruff_result.score,
        "degraded": not tools.ruff_available,
        "fallback_used": "ast" if not tools.ruff_available else None,
    }
```

### Progress Notifications

For long-running tools, send progress updates via MCP context:

```python
@mcp.tool()
async def tapps_validate_changed(file_paths: str = "") -> str:
    """Validate all changed files."""
    _record_call("tapps_validate_changed")
    files = detect_changed_files(file_paths)

    for i, fp in enumerate(files):
        # MCP progress notification (if context available)
        await notify_progress(i + 1, len(files), f"Scoring {fp}")
        result = await score_file(fp)
```

## Transport Options

### stdio Transport (Default)

The simplest transport - server reads from stdin, writes to stdout:

```python
# Entry point
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Client configuration:

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["run", "tapps-mcp", "serve"],
      "env": {
        "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

### Streamable HTTP Transport

For remote or multi-client scenarios. SSE transport is deprecated as of
MCP 2025-11-25 - use Streamable HTTP instead:

```python
# Remote server mode
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
```

### Docker MCP Gateway Transport

The Docker MCP Gateway introduces a third transport topology. The client connects
to the gateway via stdio, and the gateway manages container lifecycle internally:

```
Client --stdio--> Docker MCP Gateway --container stdio--> MCP Server Container
```

From the client's perspective, this is a single stdio connection. The gateway
multiplexes tool calls to the correct container based on tool name routing.
This means a profile with 3 servers still appears as one MCP connection to the
client, keeping configuration minimal.

### Docker MCP Catalog Publishing Workflow

To publish an MCP server to the Docker MCP Catalog:

1. **Prepare** `server.yaml` (metadata, image, config, secrets) and `tools.json`
   (static tool definitions for build-time validation)
2. **Fork** `docker/mcp-registry` and create `servers/<name>/`
3. **Build and test** locally: `task build -- --tools <name>`
4. **Import** to Docker Desktop: `docker mcp catalog import $PWD/catalogs/<name>/catalog.yaml`
5. **Submit PR** -- approved entries available within 24 hours
6. Docker builds, signs, and publishes the image to `mcp/<name>` on Docker Hub
   with cryptographic signatures, SBOM, and provenance tracking

Self-built images (hosted on GHCR/ACR) skip Docker's build pipeline but still
get a catalog entry. See `cloud-infrastructure/docker-mcp-toolkit.md` for full
`server.yaml` and `tools.json` format reference.

### Transport Selection Guidelines

| Transport | Use Case | Latency | Complexity |
|---|---|---|---|
| stdio | Local IDE integration | Lowest | Simplest |
| Streamable HTTP | Remote servers, multi-client | Medium | Moderate |
| Docker MCP Gateway | Managed multi-server profiles | Low (container overhead) | Simplest for users |

## Dual CLI / MCP Tool Pattern

### Shared Logic Layer

Features accessible from both CLI and MCP tools share implementation:

```python
# pipeline/init.py (shared logic)
async def init_project(
    project_root: Path,
    create_handoff: bool = True,
    dry_run: bool = False,
) -> dict:
    """Initialize TappsMCP in a project. Used by both CLI and MCP tool."""
    results = {}
    if create_handoff and not dry_run:
        create_handoff_file(project_root)
        results["handoff"] = "created"
    return results
```

```python
# cli.py (Click CLI)
@click.command()
@click.option("--dry-run", is_flag=True)
def init(dry_run: bool) -> None:
    """Initialize TappsMCP in the current project."""
    result = asyncio.run(init_project(Path.cwd(), dry_run=dry_run))
    click.echo(json.dumps(result, indent=2))
```

```python
# server_pipeline_tools.py (MCP tool)
@mcp.tool()
async def tapps_init(dry_run: bool = False) -> str:
    _record_call("tapps_init")
    result = await init_project(get_project_root(), dry_run=dry_run)
    return json.dumps(result)
```

## Deployment Patterns

### PyPI Distribution

```toml
# pyproject.toml
[project]
name = "tapps-mcp"
requires-python = ">=3.12"

[project.scripts]
tapps-mcp = "tapps_mcp.cli:main"
```

### Docker MCP Toolkit (Recommended)

The Docker MCP Toolkit provides managed distribution via Docker Desktop. Servers
are packaged as container images and published to the Docker MCP Catalog:

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml .
RUN pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.12-slim
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
USER nonroot
# stdio default for Docker MCP Gateway compatibility
ENTRYPOINT ["tapps-mcp", "serve"]
```

Client configuration uses a single gateway entry:

```json
{
  "mcpServers": {
    "tapps-platform": {
      "command": "docker",
      "args": ["mcp", "gateway", "run", "--profile", "tapps-platform"]
    }
  }
}
```

The gateway manages container lifecycle, routing, secrets, and tool discovery.
Publish via PR to `docker/mcp-registry` (24-hour review). Custom catalogs
support private/enterprise registries.

See `cloud-infrastructure/docker-mcp-toolkit.md` for full details.

### Container Image Best Practices for MCP Servers

- **stdio entrypoint** -- the gateway expects stdio; support HTTP via flag override
- **Multi-stage builds** -- keep images under 200 MB for fast pulls
- **Non-root user** -- required for catalog security compliance
- **Volume mount support** -- expose `TAPPS_MCP_PROJECT_ROOT=/workspace` for project access
- **Health checks** -- Docker Desktop monitors container health
- **`.dockerignore`** -- exclude tests, docs, `.git` from build context
- **Semver tags** -- provide `latest`, `0.8.1`, and `0.8` for version pinning

### Docker Deployment (Direct)

For environments without Docker Desktop MCP Toolkit:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
ENTRYPOINT ["tapps-mcp", "serve"]
```

### npm Wrapper

For Node.js ecosystem distribution, an npm package can wrap the Python server:

```json
{
  "name": "tapps-mcp",
  "bin": {
    "tapps-mcp": "./bin/tapps-mcp.js"
  }
}
```

## Testing MCP Servers

### Unit Testing Tool Handlers

Test tool logic independently from the MCP transport:

```python
@pytest.mark.asyncio
async def test_score_file_returns_scores(tmp_path):
    """Test scoring a simple Python file."""
    target = tmp_path / "example.py"
    target.write_text("x = 1\n")

    result = await tapps_score_file(str(target), quick=True)
    data = json.loads(result)
    assert "overall_score" in data
    assert 0 <= data["overall_score"] <= 100
```

### Integration Testing

Test the full MCP message flow:

```python
@pytest.mark.asyncio
async def test_tool_call_via_client(mcp_server):
    """Test calling a tool through the MCP client."""
    result = await mcp_server.call_tool(
        "tapps_score_file",
        {"file_path": "/test/example.py", "quick": True},
    )
    assert result is not None
```

## Anti-Patterns

### Monolithic Server File

Putting all tools in one file leads to high complexity and merge conflicts.
Split by domain (scoring, pipeline, metrics, memory).

### Mutable Global State

Avoid module-level mutable state beyond singletons. Use the singleton
pattern with explicit reset functions for testability.

### Blocking I/O in Tool Handlers

All tool handlers are async. Never use synchronous file reads or subprocess
calls directly - use `asyncio.to_thread()` or async subprocess utilities.

### Missing Call Recording

Forgetting `_record_call("tool_name")` means the checklist cannot track
which tools were used during a session.

## Quick Reference

| Aspect | Recommendation |
|---|---|
| Protocol version | MCP 2025-11-25 |
| Server framework | FastMCP (`@mcp.tool()`) |
| Transport (local) | stdio |
| Transport (remote) | Streamable HTTP (not SSE) |
| Module split | By domain, shared `mcp` instance |
| Caching | Singleton with reset functions |
| Security | Path sandboxing via `path_validator.py` |
| Error handling | Structured JSON, graceful degradation |
| Testing | pytest-asyncio, fixture-based mocking |
