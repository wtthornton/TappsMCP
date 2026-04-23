# Getting Started with TappsMCP

This guide walks you through setting up TappsMCP for development or as a consumer in your own project.

## For Consumers (Using TappsMCP in Your Project)

### Quick Start

The fastest way to add TappsMCP quality tools to your project:

```bash
# Install from PyPI
pip install tapps-mcp

# Or with uv
uv add tapps-mcp
```

### Configure Your MCP Client

**Claude Code** (`~/.claude.json` or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uvx",
      "args": ["tapps-mcp", "serve"]
    }
  }
}
```

**Cursor** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uvx",
      "args": ["tapps-mcp", "serve"]
    }
  }
}
```

### Bootstrap Your Project

Once the MCP server is running, call from your AI assistant:

```
tapps_init()
```

This creates:
- `AGENTS.md` -- AI assistant workflow instructions
- `TECH_STACK.md` -- detected technology stack
- Platform-specific hooks, skills, and agents
- Quality gate configuration

### Daily Workflow

1. **Start session**: `tapps_session_start()` -- initializes project context
2. **Before using libraries**: `tapps_lookup_docs("fastapi")` -- get current docs
3. **After editing Python**: `tapps_quick_check("path/to/file.py")` -- lint + score
4. **Before finishing**: `tapps_validate_changed()` -- full quality gate on all changes
5. **Final step**: `tapps_checklist(task_type="feature")` -- verify completeness

---

## For Developers (Contributing to TappsMCP)

### Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** -- the package manager for this project
- **Git**

### Setup

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd tapps-mcp

# Install all three packages in the workspace
uv sync --all-packages
```

### Project Structure

```
packages/
  tapps-core/     # Shared library (config, security, logging, knowledge, memory, experts)
  tapps-mcp/      # Code quality MCP server (26 tools)
  docs-mcp/       # Documentation MCP server (32 tools)
```

**Dependency graph:**
```
tapps-core (library)  <--  tapps-mcp (26 tools)
                      <--  docs-mcp  (32 tools)
```

### Key Directories in tapps-mcp

| Directory | Purpose |
|---|---|
| `server*.py` | MCP tool handlers (8 files) |
| `scoring/` | 7-category code scoring engine |
| `gates/` | Quality gate evaluation |
| `tools/` | External checker wrappers (ruff, mypy, bandit, radon, vulture) |
| `experts/` | 17 domain experts with 174 knowledge files |
| `memory/` | Persistent cross-session knowledge — HTTP client to the [tapps-brain](https://github.com/wtthornton/tapps-brain) service (Postgres) |
| `knowledge/` | Documentation cache and Context7 integration |
| `pipeline/` | Platform artifact generation (hooks, agents, skills) |
| `security/` | Path validation, secret scanning, content safety |

### Running the Servers

```bash
# TappsMCP (code quality)
uv run tapps-mcp serve

# DocsMCP (documentation)
uv run docsmcp serve

# Combined platform server
python examples/combined_server.py
```

### Running Tests

```bash
# Per-package (recommended)
uv run pytest packages/tapps-core/tests/ -v
uv run pytest packages/tapps-mcp/tests/ -v
uv run pytest packages/docs-mcp/tests/ -v

# Single test
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -k "test_name" -v
```

### Useful CLI Commands

```bash
uv run tapps-mcp doctor           # Diagnose config issues
uv run tapps-mcp upgrade --dry-run  # Preview generated file updates
uv run docsmcp doctor             # DocsMCP diagnostics
```

## Next Steps

- Read the [Contributing Guide](../CONTRIBUTING.md) for coding standards and PR workflow
- Check the [README](../README.md) for the full tools reference
- See the [Architecture Reference](ARCHITECTURE.md) for internal design details
- Review [CLAUDE.md](../CLAUDE.md) for AI assistant instructions
