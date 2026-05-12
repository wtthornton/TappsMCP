# TappsMCP + Agent SDK Examples

These examples show how to use TappsMCP as an MCP server within Claude Agent SDK
sessions for both Python and TypeScript.

## Prerequisites

### Python

- Python 3.12+
- `claude-code-sdk` package (`pip install claude-code-sdk`)
- `ANTHROPIC_API_KEY` environment variable set
- TappsMCP installed from local checkout (`uv tool install -e packages/tapps-mcp` from the TappsMCP repo) — the package is not on PyPI

### TypeScript

- Node.js 18+
- `@anthropic-ai/claude-code` npm package
- `ANTHROPIC_API_KEY` environment variable set
- TappsMCP installed from local checkout (`uv tool install -e packages/tapps-mcp`)

## Python Examples

### basic_quality_check.py

Runs a quick quality check on a single file using the Agent SDK with TappsMCP
configured as an MCP server.

```bash
export ANTHROPIC_API_KEY=sk-...
export TAPPS_MCP_PROJECT_ROOT=/path/to/your/project
python examples/agent-sdk/python/basic_quality_check.py src/main.py
```

### quality_gate_pipeline.py

A CI-ready quality gate pipeline that validates all changed files and exits
non-zero if any file fails.

```bash
python examples/agent-sdk/python/quality_gate_pipeline.py staging
```

### subagent_example.py

Demonstrates registering TappsMCP subagents programmatically via the Agent
SDK's `agents` parameter.

```bash
python examples/agent-sdk/python/subagent_example.py
```

## TypeScript Examples

### basic_quality_check.ts

Minimal TypeScript example of running a quality check via the Agent SDK.

```bash
cd examples/agent-sdk/typescript
npm install
npx tsx basic_quality_check.ts src/main.py
```

### subagent_pipeline.ts

TypeScript example showing programmatic subagent registration.

```bash
npx tsx subagent_pipeline.ts
```

## How It Works

The Agent SDK's `query()` function accepts an `mcpServers` (TypeScript) or
`mcp_servers` (Python) parameter that defines MCP servers to attach to the
session. TappsMCP is configured as:

```json
{
  "tapps-mcp": {
    "command": "tapps-mcp",
    "args": ["serve"],
    "env": {
      "TAPPS_MCP_PROJECT_ROOT": "/path/to/project"
    }
  }
}
```

The `allowedTools` parameter restricts which tools Claude can call, ensuring
the session only uses TappsMCP tools for quality analysis.
