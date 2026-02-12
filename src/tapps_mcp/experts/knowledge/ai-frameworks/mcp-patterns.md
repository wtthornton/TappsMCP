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

## Best Practices

### Tool Design

1. **Clear descriptions**: Tool and parameter descriptions are the LLM's documentation
2. **Type annotations**: Use Python type hints - FastMCP auto-generates JSON schemas
3. **Return strings**: Tools should return human-readable string output
4. **Idempotent reads**: Read operations should be safe to repeat
5. **Explicit errors**: Return error messages as strings, don't raise exceptions

### Security

1. **Path validation**: Always validate and sanitize file paths
2. **Input bounds**: Limit string lengths and collection sizes
3. **No secrets in output**: Never return API keys or credentials
4. **Least privilege**: Only expose necessary filesystem access
5. **Rate limiting**: Protect expensive operations from excessive calls

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

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [FastMCP Documentation](https://gofastmcp.com/)
