# TappMCP: Setup and Use Summary

TappMCP is an **MCP (Model Context Protocol) server** that exposes **code quality tools** to LLMs (Claude, Cursor, etc.): file scoring, security scanning, quality gates, and checklists. This doc is a short guide to set it up and use it.

---

## 1. What You Need

- **Python 3.12+**
- **uv** (recommended) or pip: `pip install uv`
- **Optional** (improve scoring; server works without them): **ruff**, **mypy**, **bandit**, **radon**

---

## 2. Setup

### Install and run locally

```bash
# Clone (or open) the repo
cd c:\cursor\TappMCP   # or your path

# Install dependencies with uv
uv sync

# Verify: run server (stdio mode for Cursor/Claude)
uv run tapps-mcp serve
```

- **stdio** (default): for local clients (Cursor, Claude Desktop). Server runs and talks over stdin/stdout.
- **HTTP**: for remote/container use:
  ```bash
  uv run tapps-mcp serve --transport http --port 8000
  ```

### Run via Docker (local MCP server)

With Docker and Docker Compose installed:

```bash
docker compose up --build -d
```

The MCP server listens on **http://localhost:8000** (Streamable HTTP at `/mcp`). See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for full details.

### Optional project config

In the **project root** you want the agent to analyze, add **`.tapps-mcp.yaml`** (optional):

```yaml
quality_preset: standard   # standard | strict | framework
log_level: INFO
tool_timeout: 30
```

---

## 3. Use with Cursor

1. **Cursor MCP config**  
   Add the server in Cursor’s MCP settings (e.g. **Settings → MCP** or `.cursor/mcp.json` in the project):

   Use a **command** that is on your PATH (e.g. `uv`); do not use a local file path as the command. Recommended config:

   ```json
   {
     "mcpServers": {
       "tapps-mcp": {
         "command": "uv",
         "args": ["--directory", "C:\\cursor\\TappMCP", "run", "--no-sync", "tapps-mcp", "serve"],
         "env": {
           "TAPPS_MCP_CONTEXT7_API_KEY": "your-context7-api-key"
         }
       }
     }
   }
   ```

   - Replace `C:\cursor\TappMCP` with your actual TappMCP repo path.
   - **`--no-sync`** makes `uv run` skip syncing the venv, which avoids “file is being used by another process” when Cursor starts the server.
   - The subcommand must be **`serve`** (not `serv`).
   - Set `TAPPS_MCP_CONTEXT7_API_KEY` so `tapps_lookup_docs` can fetch live docs; omit `env` to use cache-only.

2. **Restart or reload Cursor** so it picks up the new MCP server.

3. In chat/composer, the AI can call TappMCP tools (e.g. `tapps_score_file`, `tapps_quality_gate`) once the server is connected.

### If Cursor shows "Error" for tapps-mcp

- **Wrong subcommand:** The args must end with **`serve`** (not `serv`). In **Settings → Tools & MCP**, set the args to include `tapps-mcp` and **`serve`**.
- **"File is being used by another process" (uv):** Add **`--no-sync`** to the args so uv doesn’t sync the venv on start, e.g. `["--directory", "C:\\cursor\\TappMCP", "run", "--no-sync", "tapps-mcp", "serve"]`. The command must be a PATH command (e.g. `uv`), not a local file path.
- **Show Output:** In **Settings → Tools & MCP**, click **"Error - Show Output"** next to tapps-mcp to see the exact error.

---

## 4. Use with Claude Desktop

In **Claude Desktop** config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["--directory", "C:\\cursor\\TappMCP", "run", "--no-sync", "tapps-mcp", "serve"]
    }
  }
}
```

Restart Claude Desktop after changing the config.

---

## 5. Main Tools and How to Use Them

| Tool | Purpose |
|------|--------|
| **tapps_server_info** | Server version, available tools, which checkers (ruff, mypy, etc.) are installed. Call once at session start. |
| **tapps_score_file** | Score a Python file 0–100 (complexity, security, maintainability, etc.). Use `quick: true` for fast checks, full for final pass. |
| **tapps_security_scan** | Security scan (e.g. bandit + secret detection). |
| **tapps_quality_gate** | Pass/fail vs thresholds (e.g. overall ≥ 70 for `standard`). Use before “done”. |
| **tapps_checklist** | See which TappMCP tools were used this session and what’s missing. Use before “done”. |

**Suggested workflow for the AI:**

1. Call **tapps_server_info** at session start.
2. Use **tapps_score_file** (quick) during edit–lint–fix loops.
3. Use **tapps_score_file** (full) and **tapps_quality_gate** before marking work complete.
4. Call **tapps_checklist** to ensure no required steps were skipped.

---

## 6. Environment Variables (optional)

- **TAPPS_MCP_PROJECT_ROOT** – Restrict file operations to this directory (recommended for security). If unset, current working directory is used.
- **TAPPS_MCP_CONTEXT7_API_KEY** – Only needed for planned “knowledge/docs” features (e.g. doc lookup); not required for current scoring/gates/checklist.

---

## 7. Quick Reference

| Task | Command / location |
|------|---------------------|
| Install deps | `uv sync` |
| Run server (stdio) | `uv run tapps-mcp serve` |
| Run server (HTTP) | `uv run tapps-mcp serve --transport http --port 8000` |
| Run tests | `uv run pytest tests/` |
| Lint | `uv run ruff check src/` |
| **Docker** | `docker compose up --build -d` → http://localhost:8000 |
| **Use Docker from another project** | Mount that project at `/workspace`, connect Cursor to http://localhost:8000/mcp (HTTP/SSE). See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md#using-tappmcp-docker-from-another-project). |
| Project config | `.tapps-mcp.yaml` in project root |
| Cursor MCP config | Cursor Settings → MCP or `.cursor/mcp.json` |
| Docker deployment | [docs/DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) |
| Full plan / roadmap | [docs/planning/TAPPS_MCP_PLAN.md](planning/TAPPS_MCP_PLAN.md) |
| Claude full access (no prompts) | [docs/CLAUDE_FULL_ACCESS_SETUP.md](CLAUDE_FULL_ACCESS_SETUP.md) |

---

## Summary

1. **Setup:** `uv sync` in TappMCP repo, then run `uv run tapps-mcp serve`.
2. **Use in Cursor/Claude:** Add the server to MCP config with `uv` + path to TappMCP + `run tapps-mcp serve`.
3. **Use the tools:** Have the AI call `tapps_server_info` first, then `tapps_score_file` / `tapps_quality_gate` / `tapps_checklist` as in the workflow above.
4. **Optional:** Install ruff/mypy/bandit/radon for best scoring; set `TAPPS_MCP_PROJECT_ROOT` and `.tapps-mcp.yaml` as needed.
