# MCP Server Architecture Patterns

## Overview

MCP (Model Context Protocol) servers follow a client-server architecture where a host (IDE or agent) connects to a server that exposes tools, resources, and prompts. This document describes architectural patterns for designing and structuring MCP servers.

## Core Architecture

### Component Layout

```
Host (Cursor/Claude) <-> Transport (stdio/HTTP) <-> MCP Server
                                                          |
                                              +------------+------------+
                                              |            |            |
                                           Tools      Resources    Prompts
```

### Server Structure

1. **Entry point** — Script or CLI that starts the server and binds to the transport.
2. **Tool registry** — Central list of tool names to handler functions.
3. **Handler modules** — Group tools by domain (scoring, pipeline, metrics).
4. **Shared state** — Project root, settings, call tracker — injected into handlers.

### Delegation Pattern

Avoid monolithic server files. Delegate tool handlers to domain-specific modules:

```python
# server.py
from tapps_mcp.server_scoring_tools import tapps_score_file, tapps_quality_gate
from tapps_mcp.server_pipeline_tools import tapps_init

TOOLS = {
    "tapps_score_file": tapps_score_file,
    "tapps_init": tapps_init,
}
```

## Design Principles

- **Stateless handlers** — Each tool call should not rely on prior calls except via persisted state (e.g. checklist JSONL).
- **Configurable paths** — Support `TAPPS_MCP_PROJECT_ROOT` and host path mapping for Docker.
- **Graceful degradation** — When optional checkers (ruff, mypy) are missing, return clear errors instead of crashing.
