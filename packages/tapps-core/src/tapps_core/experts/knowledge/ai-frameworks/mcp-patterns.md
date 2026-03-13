# Model Context Protocol (MCP) Patterns

## Overview

The Model Context Protocol (MCP) is an open standard for connecting AI assistants to external tools, data sources, and services. It provides a structured way for LLMs to interact with the outside world through tools, resources, and prompts.

## Core Concepts

### Architecture

- **Host**: The AI application (e.g., Claude Code, Cursor, VS Code)
- **Client**: Protocol client inside the host that manages server connections
- **Server**: Lightweight service exposing tools, resources, and prompts
- **Transport**: Communication layer (stdio for local, Streamable HTTP for remote)

### Server Components

1. **Tools**: Functions the LLM can invoke (e.g., file operations, API calls)
2. **Resources**: Data the LLM can read (e.g., files, database records)
3. **Prompts**: Reusable prompt templates for common workflows

## Server Implementation

### Pattern 1: Basic MCP Server with FastMCP

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MyTools")

@mcp.tool()
async def search_code(query: str, file_type: str = "") -> str:
    """Search the codebase for a pattern.

    Args:
        query: The search pattern to look for.
        file_type: Optional file extension filter (e.g., 'py', 'ts').
    """
    results = await run_search(query, file_type)
    return format_results(results)

@mcp.resource("config://settings")
async def get_settings() -> str:
    """Return current application settings."""
    return json.dumps(load_settings(), indent=2)

@mcp.prompt()
def review_prompt(file_path: str) -> str:
    """Generate a code review prompt for a file."""
    return f"Please review the code in {file_path} for quality and security issues."
```

### Pattern 2: Tool with Structured Input/Output

```python
from pydantic import BaseModel, Field

class AnalysisResult(BaseModel):
    score: int = Field(ge=0, le=100, description="Quality score")
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

@mcp.tool()
async def analyze_file(
    file_path: str,
    checks: list[str] | None = None,
) -> str:
    """Analyze a file for quality issues.

    Args:
        file_path: Path to the file to analyze.
        checks: Optional list of specific checks to run.
    """
    result = await run_analysis(file_path, checks)
    return result.model_dump_json(indent=2)
```

### Pattern 3: Error Handling in Tools

```python
@mcp.tool()
async def safe_file_read(file_path: str) -> str:
    """Read a file with proper error handling.

    Args:
        file_path: Path to the file to read.
    """
    from pathlib import Path

    path = Path(file_path).resolve()

    # Security: prevent path traversal
    if ".." in path.parts:
        return "Error: Path traversal not allowed"

    if not path.exists():
        return f"Error: File not found: {file_path}"

    if not path.is_file():
        return f"Error: Not a file: {file_path}"

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: Cannot read binary file: {file_path}"
```

## Transport Configuration

### stdio Transport (Local)

```json
{
    "mcpServers": {
        "my-tools": {
            "command": "python",
            "args": ["-m", "my_mcp_server", "serve"]
        }
    }
}
```

### Streamable HTTP Transport (Remote/Container)

```python
mcp = FastMCP("MyTools")

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

```json
{
    "mcpServers": {
        "my-tools": {
            "url": "http://localhost:8000/mcp"
        }
    }
}
```

## MCP Specification History

| Version | Date | Key Changes |
|---------|------|-------------|
| 2024-11-05 | Nov 2024 | Initial release by Anthropic - core primitives (tools, resources, prompts), stdio transport |
| 2025-06-18 | Jun 2025 | Auth spec update (OAuth 2.1 based), structured tool outputs, elicitation, `MCP-Protocol-Version` header |
| 2025-11-25 | Nov 2025 | Major spec release (current latest). Tasks primitive for async/long-running ops, enhanced OAuth 2.1 authorization, Protected Resource Metadata discovery, Streamable HTTP (replacing SSE), OpenID Connect, icons metadata, extension framework |

### 2026 Roadmap

- **Streamable HTTP improvements**: Performance tuning, reconnection semantics
- **Tasks lifecycle**: Retry policies, expiry/TTL, cancellation improvements
- **Enterprise readiness**: Audit trails, SSO integration, API gateways
- **SEP process improvements**: Streamlined spec evolution proposals under AAIF governance

In December 2025, MCP governance was donated to the **Agentic AI Foundation (AAIF)** under the Linux Foundation.

## MCP Clients (2026)

Major clients supporting MCP: Claude Code, Claude Desktop, Cursor, Windsurf (Codeium), VS Code (GitHub Copilot agent mode), Cline, Zed, Replit, Continue.dev, Gemini CLI, and 500+ others.

## Tool Annotations (2025-06-18+)

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MyTools")

@mcp.tool(annotations={
    "title": "Score File",
    "readOnlyHint": True,
    "openWorldHint": False,
})
async def score_file(file_path: str) -> str:
    """Score a Python file for quality."""
    ...
```

Annotations help clients understand tool behaviour (read-only vs side-effect, open-world vs sandboxed).

## Best Practices

### Tool Design

1. **Clear descriptions**: Tool and parameter descriptions are the LLM's documentation
2. **Type annotations**: Use Python type hints - FastMCP auto-generates JSON schemas
3. **Return strings**: Tools should return human-readable string output
4. **Idempotent reads**: Read operations should be safe to repeat
5. **Explicit errors**: Return error messages as strings, don't raise exceptions
6. **Annotations**: Use `readOnlyHint`, `idempotentHint`, `openWorldHint` to guide client behaviour

### Security

1. **Path validation**: Always validate and sanitize file paths
2. **Input bounds**: Limit string lengths and collection sizes
3. **No secrets in output**: Never return API keys or credentials
4. **Least privilege**: Only expose necessary filesystem access
5. **Rate limiting**: Protect expensive operations from excessive calls
6. **OAuth for remote**: Use MCP's built-in OAuth for HTTP-transported servers

### Performance

1. **Async by default**: Use async functions for I/O-bound tools
2. **Caching**: Cache expensive computations (e.g., file analysis results)
3. **Timeouts**: Set reasonable timeouts for external API calls
4. **Lazy loading**: Import heavy dependencies inside tool functions

### Distribution

- **PyPI**: `pip install my-mcp-server` with `[project.scripts]` entry point
- **npx**: Wrap with `@anthropic/mcp-wrapper` for `npx my-mcp-server`
- **Docker**: Containerize for Streamable HTTP deployment

## Anti-Patterns

1. **Giant tools**: Don't create tools that do too many things - split into focused tools
2. **Missing descriptions**: Without good descriptions, the LLM can't use tools effectively
3. **Synchronous I/O**: Blocking the event loop degrades server responsiveness
4. **Unbounded output**: Returning megabytes of data overwhelms the LLM's context
5. **Side effects in resources**: Resources should be read-only; use tools for mutations

## MCP Context Progress Notifications

### Overview

Long-running MCP tools can report progress to the client via `ctx.info()`
and `ctx.report_progress()`. This provides real-time feedback during
operations that may take several seconds (validation, scanning, reporting).

### ctx.info() for Status Messages

Use `ctx.info()` to send human-readable status updates:

```python
@mcp.tool()
async def validate_changed(
    file_paths: str = "",
    ctx: Context | None = None,
) -> str:
    """Validate changed files against quality gate."""
    if ctx:
        await ctx.info("Detecting changed files...")

    files = detect_changed_files(file_paths)

    for i, f in enumerate(files):
        if ctx:
            await ctx.info(f"Scoring {f.name} ({i+1}/{len(files)})...")
        await score_file(f)

    if ctx:
        await ctx.info("Validation complete.")
    return format_results(files)
```

### ctx.report_progress() for Numeric Progress

Use `ctx.report_progress()` for operations with known step counts:

```python
if ctx:
    await ctx.report_progress(current=i + 1, total=len(files))
```

### Defensive ctx Access Pattern

The `ctx` parameter may be `None` (when called programmatically) or may
lack `info`/`report_progress` methods (older SDK versions). Use a
defensive pattern:

```python
async def emit_ctx_info(ctx: object | None, message: str) -> None:
    """Safely emit a ctx.info() notification.

    Handles: ctx is None, ctx has no info attribute,
    ctx.info() raises an exception.
    """
    if ctx is None:
        return
    info_fn = getattr(ctx, "info", None)
    if info_fn is None:
        return
    try:
        await info_fn(message)
    except Exception:
        pass  # suppress - progress is non-critical
```

This shared helper (`emit_ctx_info` in `server_helpers.py`) is used across
all tools that support progress notifications, ensuring consistent and
safe handling.

### Sidecar Progress Files

For redundant progress delivery, tools write JSON sidecar files that
Claude Code hooks can read:

```python
import json
from pathlib import Path

def write_sidecar_progress(
    project_root: Path,
    filename: str,
    data: dict,
) -> None:
    """Write a progress sidecar file for hook consumption."""
    sidecar_dir = project_root / ".tapps-mcp"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = sidecar_dir / filename
    sidecar_path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )
```

Two sidecar files are used:

| File | Written By | Contents |
|---|---|---|
| `.tapps-mcp/.validation-progress.json` | `tapps_validate_changed` | Per-file scoring status, overall progress |
| `.tapps-mcp/.report-progress.json` | `tapps_report` | Report generation progress, file count |

### Hook-Based Redundant Delivery

Claude Code hooks read sidecar files to display progress even when
`ctx.info()` messages are not surfaced in the UI:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "tapps_validate_changed",
        "command": "bash .claude/hooks/post-validate.sh"
      },
      {
        "matcher": "tapps_report",
        "command": "bash .claude/hooks/post-report.sh"
      }
    ],
    "Stop": [
      {
        "command": "bash .claude/hooks/stop-progress-summary.sh"
      }
    ],
    "TaskCompleted": [
      {
        "command": "bash .claude/hooks/task-completed-summary.sh"
      }
    ]
  }
}
```

The hook script reads the sidecar and outputs a summary:

```bash
#!/usr/bin/env bash
PROGRESS=".tapps-mcp/.validation-progress.json"
if [ -f "$PROGRESS" ]; then
    cat "$PROGRESS"
    rm -f "$PROGRESS"  # clean up after reading
fi
```

### Tools with ctx Support

The following tools emit progress notifications via `ctx.info()`:

| Tool | Progress Type | Notes |
|---|---|---|
| `tapps_validate_changed` | Per-file scoring progress | Also writes sidecar |
| `tapps_report` | Report generation steps | Also writes sidecar |
| `tapps_init` | Pipeline initialization steps | Multi-phase setup |
| `tapps_upgrade` | File upgrade progress | Async operation |
| `tapps_dependency_scan` | Dependency audit progress | External tool call |
| `tapps_dead_code` | File scanning progress | Per-file or project-wide |
| `tapps_dependency_graph` | Graph analysis steps | Cycle detection, coupling |

### Best Practices

1. **Always use the defensive helper** (`emit_ctx_info`) rather than calling `ctx.info()` directly
2. **Include counts** in messages: "Scoring file 3/10..." is better than "Scoring file..."
3. **Keep messages short** - they appear in status bars or log panels
4. **Write sidecars atomically** - write to a temp file then rename
5. **Clean up sidecars** after reading to avoid stale data on next run
6. **Never block on ctx failures** - progress is informational, not critical

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [FastMCP Documentation](https://gofastmcp.com/)
- [MCP Spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
