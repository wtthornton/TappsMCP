# TappsMCP

Standalone MCP Server for LLM Code Quality -- extracting the highest-value components from TappsCodingAgents into a Model Context Protocol (MCP) server.

## Quick Start

```bash
# Install with uv
uv sync

# Run via stdio (for Claude Desktop, Cursor, etc.)
uv run tapps-mcp serve

# Run via HTTP (for remote clients)
uv run tapps-mcp serve --transport http --port 8000

# Or run via Docker (Streamable HTTP on port 8000)
docker compose up --build -d
```

### Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/TappMCP", "run", "tapps-mcp", "serve"]
    }
  }
}
```

## Available Tools

### `tapps_score_file`
Score a Python file across 7 quality categories (0-100 overall).

| Category | Weight | Description |
|---|---|---|
| complexity | 0.20 | Cyclomatic complexity (radon cc / AST fallback) |
| security | 0.20 | Bandit static analysis / pattern heuristics |
| maintainability | 0.15 | Maintainability index (radon mi / AST fallback) |
| test_coverage | 0.10 | Heuristic based on matching test file existence |
| performance | 0.15 | AST-based: nested loops, large functions, deep nesting |
| structure | 0.10 | Project layout (pyproject.toml, tests/, README, .git) |
| devex | 0.10 | Developer experience (docs, AGENTS.md, tooling config) |

**Modes:**
- **Full** (default): Runs ruff, mypy, bandit, and radon in parallel (~1-3s)
- **Quick**: Ruff-only scoring (< 500ms)
- **Quick + Fix**: Apply ruff auto-fixes then score

### `tapps_security_scan`
Run a security scan combining bandit static analysis with secret detection.

- Bandit with OWASP Top 10 2021 mapping (~50 rules)
- Regex-based secret detection (API keys, tokens, passwords, AWS keys, private keys)
- Redacted context in findings

### `tapps_quality_gate`
Evaluate a file against quality gate thresholds. Runs full scoring then checks pass/fail.

**Presets:**
| Preset | Overall Min | Description |
|---|---|---|
| standard | 70 | Default -- good for most projects |
| strict | 80 | For production-critical code |
| framework | 75 | For framework/library code |

### `tapps_checklist`
Check which TappsMCP tools have been called this session and what's still missing.

**Task types:** `feature`, `bugfix`, `refactor`, `security`, `review`

### `tapps_server_info`
Return server version, available tools, installed checkers, and configuration.

## Configuration

Create `.tapps-mcp.yaml` in your project root:

```yaml
quality_preset: standard    # standard | strict | framework
log_level: INFO             # DEBUG | INFO | WARNING | ERROR
log_json: false             # JSON-structured logs
tool_timeout: 30            # Subprocess timeout in seconds
```

### Scoring Weights

Custom weights in `.tapps-mcp.yaml`:

```yaml
scoring_weights:
  complexity: 0.20
  security: 0.20
  maintainability: 0.15
  test_coverage: 0.10
  performance: 0.15
  structure: 0.10
  devex: 0.10
```

## External Tool Dependencies

TappsMCP works best with these tools installed but degrades gracefully without them:

| Tool | Purpose | Install |
|---|---|---|
| ruff | Linting + formatting | `pip install ruff` |
| mypy | Type checking | `pip install mypy` |
| bandit | Security scanning | `pip install bandit` |
| radon | Complexity + maintainability | `pip install radon` |

When a tool is unavailable, TappsMCP falls back to AST-based heuristics and reports `degraded: true` in the response.

## Development

```bash
# Install dev dependencies
uv sync

# Run tests (368 tests)
uv run pytest tests/

# Type checking
uv run mypy --strict src/tapps_mcp/

# Linting
uv run ruff check src/
uv run ruff format --check src/
```

## Architecture

```
src/tapps_mcp/
  __init__.py, cli.py, server.py, py.typed
  common/    exceptions.py, logging.py, models.py
  config/    settings.py, default.yaml
  security/  path_validator.py, io_guardrails.py, governance.py,
             api_keys.py, secret_scanner.py, security_scanner.py
  scoring/   models.py, constants.py, scorer.py
  gates/     models.py, evaluator.py
  tools/     subprocess_utils.py, subprocess_runner.py, tool_detection.py,
             ruff.py, mypy.py, bandit.py, radon.py, parallel.py, checklist.py
```

## Docker

Run TappMCP as a local MCP server in a container (Streamable HTTP on port 8000):

```bash
docker compose up --build -d
```

See [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) for details, verification, and connecting clients.

## Roadmap

See [docs/planning/TAPPS_MCP_PLAN.md](docs/planning/TAPPS_MCP_PLAN.md) for the full implementation plan.

| Epic | Focus | Status |
|---|---|---|
| 0 | Foundation + Security | Complete |
| 1 | Core Quality MVP | Complete |
| 2 | Knowledge & Docs | Planned |
| 3 | Expert System | Planned |
| 4 | Project Context | Planned |
| 5 | Adaptive Learning | Planned |
| 6 | Distribution | Planned |
| 7 | Metrics & Dashboard | Planned |
