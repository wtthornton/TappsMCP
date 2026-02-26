# TappsMCP: Setup and Use Summary

TappsMCP is an **MCP (Model Context Protocol) server** that exposes **code quality tools** to LLMs (Claude, Cursor, etc.): file scoring, security scanning, quality gates, and checklists. This doc is a short guide to set it up and use it.

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
cd c:\cursor\TappsMCP   # or your path

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

### Recommended install and upgrade

- **Recommended:** Install with **pip** or **uv** so the full package (including session checklist) is available:
  - **PyPI:** `pip install tapps-mcp` or `uv tool install tapps-mcp`
  - **From repo:** `uv sync` then `uv run tapps-mcp serve`, or `pip install -e .` then `tapps-mcp serve`
- **Upgrade:** `pip install -U tapps-mcp` or `uv tool install -U tapps-mcp`. See [CHANGELOG.md](../CHANGELOG.md) for breaking changes.
- **Refresh templates after upgrade:** If you use TappsMCP in a consuming project (not this repo), call `tapps_init` with `overwrite_agents_md=True` and `overwrite_platform_rules=True` (and `platform="cursor"` or `"claude"`) to get the latest AGENTS.md and pipeline rules. Run `tapps-mcp init --force` to refresh MCP host config. See [INIT_AND_UPGRADE_FEATURE_LIST.md](INIT_AND_UPGRADE_FEATURE_LIST.md#upgrading-when-tappsmcp-ships-new-features-consuming-projects).
- **Standalone binary (.exe):** If you use a pre-built executable, it must include the full `tapps_mcp` package (including `tapps_mcp.tools.checklist`). If tools fail with a checklist import error, switch to a pip/uv install (see [Troubleshooting](#8-troubleshooting) below). **If you build your own binary** (e.g. PyInstaller, shiv, uv tool), ensure the build includes the entire `tapps_mcp` package and subpackages (e.g. `tapps_mcp.tools`, `tapps_mcp.tools.checklist`); otherwise all tools will fail when they try to record session state.
- **Windows:** Same setup as above. Use `uv` or `pip` from your project or a dedicated venv; ensure the MCP config `command` is on PATH (e.g. `uv`, `python`, or full path to `tapps-mcp` if installed as a script).

### Optional project config

In the **project root** you want the agent to analyze, add **`.tapps-mcp.yaml`** (optional):

```yaml
quality_preset: standard   # standard | strict | framework
log_level: INFO
tool_timeout: 30
```

---

## 2b. Auto-setup with `tapps-mcp init`

The fastest way to configure your AI client:

```bash
tapps-mcp init                        # auto-detect installed clients
tapps-mcp init --host claude-code     # configure Claude Code
tapps-mcp init --host cursor          # configure Cursor
tapps-mcp init --host vscode          # configure VS Code
tapps-mcp init --check                # verify existing setup
tapps-mcp doctor                      # diagnose connectivity issues
```

This generates the correct MCP configuration file and platform-specific artifacts:
- **Platform rules** (CLAUDE.md or .cursor/rules/)
- **Hook scripts** (.claude/hooks/ or .cursor/hooks/) for automatic quality enforcement
- **Subagent definitions** (.claude/agents/ or .cursor/agents/) for parallel quality workflows
- **Skill templates** (.claude/skills/ or .cursor/skills/) for quick access to scoring/gating/validation
- **Cursor rule types** (.cursor/rules/*.mdc) with always-on, auto-attach, and agent-requested rules

Use `--force` to overwrite existing config without prompting.

---

## 2c. Use with Claude Code

Run `tapps-mcp init --host claude-code` or manually add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "tapps-mcp",
      "args": ["serve"]
    }
  }
}
```

For project-level config, use `tapps-mcp init --host claude-code --scope project` to create `.mcp.json` in the project root. For full access without permission prompts, see [CLAUDE_FULL_ACCESS_SETUP.md](CLAUDE_FULL_ACCESS_SETUP.md).

---

## 3. Use with Cursor

1. **Cursor MCP config**  
   Add the server in Cursor’s MCP settings (e.g. **Settings → Tools & MCP** or `.cursor/mcp.json` in the project). Choose **one** of the following depending on how you run the server.

   **Option A — Docker (when the container is running)**  
   Point Cursor at the HTTP endpoint. This repo’s `.cursor/mcp.json` is set up for this:

   ```json
   {
     "mcpServers": {
       "tapps-mcp": {
         "url": "http://localhost:8000/mcp"
       }
     }
   }
   ```

   Ensure the container is running (`docker compose up -d` from this repo) and port 8000 is free. No `command`/`args` are used; Cursor connects via HTTP/SSE.

   **Option B — Local stdio (no Docker)**  
   Cursor starts the server as a subprocess. Use a **command** that is on your PATH (e.g. `uv`); do not use a local file path as the command:

   ```json
   {
     "mcpServers": {
       "tapps-mcp": {
         "command": "uv",
         "args": ["--directory", "C:\\cursor\\TappsMCP", "run", "--no-sync", "tapps-mcp", "serve"],
         "env": {
           "TAPPS_MCP_CONTEXT7_API_KEY": "your-context7-api-key"
         }
       }
     }
   }
   ```

   - Replace `C:\cursor\TappsMCP` with your actual TappsMCP repo path.
   - **`--no-sync`** makes `uv run` skip syncing the venv, which avoids “file is being used by another process” when Cursor starts the server.
   - The subcommand must be **`serve`** (not `serv`).
   - Set `TAPPS_MCP_CONTEXT7_API_KEY` so `tapps_lookup_docs` can fetch live docs; omit `env` to use cache-only.

2. **Restart or reload Cursor** so it picks up the new MCP server.

3. In chat/composer, the AI can call TappsMCP tools (e.g. `tapps_score_file`, `tapps_quality_gate`) once the server is connected.

### If you see two "tapps-mcp" entries (one Error, one Disabled)

Use **only one** transport. If you run TappsMCP in Docker, use the **url** config (Option A) and remove or disable any **stdio** (command/args) entry for tapps-mcp from **Settings → Tools & MCP**. Duplicate entries often come from having both a project `.cursor/mcp.json` and a user-level MCP config; keep a single tapps-mcp entry that matches how you run the server (Docker → url, local → command/args).

### If Cursor shows "Error" for tapps-mcp

- **Wrong subcommand:** The args must end with **`serve`** (not `serv`). In **Settings → Tools & MCP**, set the args to include `tapps-mcp` and **`serve`**.
- **"File is being used by another process" (uv):** Add **`--no-sync`** to the args so uv doesn’t sync the venv on start, e.g. `["--directory", "C:\\cursor\\TappsMCP", "run", "--no-sync", "tapps-mcp", "serve"]`. The command must be a PATH command (e.g. `uv`), not a local file path.
- **Show Output:** In **Settings → Tools & MCP**, click **"Error - Show Output"** next to tapps-mcp to see the exact error.

---

## 4. Use with Claude Desktop

In **Claude Desktop** config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["--directory", "C:\\cursor\\TappsMCP", "run", "--no-sync", "tapps-mcp", "serve"]
    }
  }
}
```

Restart Claude Desktop after changing the config.

---

## 5. Main Tools and How to Use Them

| Tool | Purpose |
|------|--------|
| **tapps_session_start** | **FIRST call** — combines server info + project profile. Initialize context for all subsequent tools. |
| **tapps_server_info** | Server version, available tools, which checkers (ruff, mypy, etc.) are installed. |
| **tapps_score_file** | Score a Python file 0-100 (complexity, security, maintainability, etc.). Use `quick: true` for fast checks, full for final pass. |
| **tapps_quick_check** | Fast score + gate + basic security in one call. Use after each file edit. |
| **tapps_security_scan** | Security scan (e.g. bandit + secret detection). |
| **tapps_quality_gate** | Pass/fail vs thresholds (e.g. overall >= 70 for `standard`). Use before "done". |
| **tapps_validate_changed** | Score + gate + security scan all changed files (auto-detects via git diff). |
| **tapps_lookup_docs** | Fetch current library docs via Context7. Use before writing code that calls library APIs. |
| **tapps_validate_config** | Validate Dockerfile, docker-compose, WebSocket/MQTT/InfluxDB configs against best practices. |
| **tapps_consult_expert** | Ask a domain expert (17 domains) and get RAG-backed guidance with confidence scores. |
| **tapps_research** | Combined expert + docs lookup in one call (auto-supplements with Context7). |
| **tapps_list_experts** | List available expert domains and their knowledge base status. |
| **tapps_project_profile** | Detect project type, tech stack, and structure. Call at session start for context-aware analysis. |
| **tapps_session_notes** | Save/retrieve key decisions and constraints across a session. |
| **tapps_impact_analysis** | Analyze what depends on a file and what could break from changes. |
| **tapps_report** | Generate a quality report (JSON, Markdown, or HTML) for scored files. |
| **tapps_checklist** | See which TappsMCP tools were used this session and what's missing. Use before "done". |
| **tapps_dashboard** | View metrics dashboard: execution stats, expert performance, alerts, trends. |
| **tapps_stats** | Retrieve usage statistics: call counts, success rates, durations, gate pass rates. |
| **tapps_feedback** | Submit feedback on tool results to improve adaptive scoring and expert weights. |
| **tapps_init** | Bootstrap TappsMCP in a project: create AGENTS.md, TECH_STACK.md, platform rules, warm caches. |
| **tapps_workflow** | Generate recommended tool call order for a specific task type. |

**Suggested workflow for the AI:**

1. Call **tapps_session_start** at session start (combines server info + project profile).
2. Use **tapps_lookup_docs** before writing code that uses an external library.
3. Use **tapps_session_notes** to record key decisions during the session.
4. Use **tapps_quick_check** (or `tapps_score_file` with `quick: true`) during edit-lint-fix loops.
5. Use **tapps_validate_changed** before marking work complete (validates all changed files).
6. Call **tapps_checklist** to ensure no required steps were skipped.

---

## 6. Environment Variables (optional)

- **TAPPS_MCP_PROJECT_ROOT** – Restrict file operations to this directory (recommended for security). If unset, current working directory is used.
- **TAPPS_MCP_HOST_PROJECT_ROOT** – Optional. When the server runs with a different root (e.g. Docker `/workspace`), set this to the **host path** the client/IDE uses (e.g. `C:\projects\myapp`). Then the server will accept absolute host paths from Cursor and map them to the project root, avoiding "path denied" errors.
- **TAPPS_MCP_CONTEXT7_API_KEY** – Used by `tapps_lookup_docs` for live Context7 API fetches. Cache still works without it.

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
| **Use Docker from another project** | Mount that project at `/workspace`, connect Cursor to http://localhost:8000/mcp (HTTP/SSE). See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md#using-tappsmcp-docker-from-another-project). |
| Project config | `.tapps-mcp.yaml` in project root |
| Cursor MCP config | Cursor Settings → MCP or `.cursor/mcp.json` |
| Docker deployment | [docs/DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) |
| Init and upgrade (tapps_init, tapps-mcp init) | [docs/INIT_AND_UPGRADE_FEATURE_LIST.md](INIT_AND_UPGRADE_FEATURE_LIST.md) |
| MCP client timeouts / long-running tools | [docs/MCP_CLIENT_TIMEOUTS.md](MCP_CLIENT_TIMEOUTS.md) |
| Upgrade guide for consuming projects | [docs/UPGRADE_FOR_CONSUMERS.md](UPGRADE_FOR_CONSUMERS.md) |
| Epic 10+11 (complete): Expert + Context7 | [docs/planning/TAPPS_MCP_IMPROVEMENT_IMPLEMENTATION_PLAN.md](planning/TAPPS_MCP_IMPROVEMENT_IMPLEMENTATION_PLAN.md) |
| Full plan / roadmap | [docs/planning/TAPPS_MCP_PLAN.md](planning/TAPPS_MCP_PLAN.md) |
| Claude full access (no prompts) | [docs/CLAUDE_FULL_ACCESS_SETUP.md](CLAUDE_FULL_ACCESS_SETUP.md) |
| **Cache & RAG architecture** | [docs/ARCHITECTURE_CACHE_AND_RAG.md](ARCHITECTURE_CACHE_AND_RAG.md) — SWR, TTL, index rebuild |
| **Migration from tapps-agents** | [docs/MIGRATION_FROM_TAPPS_AGENTS.md](MIGRATION_FROM_TAPPS_AGENTS.md) — what to remove, keep, configure |

---

## 8. Troubleshooting

| Symptom | What to do |
|--------|------------|
| **All tools fail with `No module named 'tapps_mcp.tools.checklist'`** | The runtime is missing the checklist module (common with a standalone binary). **Fix:** Install via pip or uv so the full package is present: `pip install tapps-mcp` or `uv tool install tapps-mcp`, then point MCP config at that environment (e.g. `command`: `uv`, `args`: `["run", "tapps-mcp", "serve"]` with appropriate `--directory` if using a project). If you must use a binary, rebuild it so it includes the full `tapps_mcp` package. |
| **Cursor shows "Error" for tapps-mcp** | See [If Cursor shows "Error" for tapps-mcp](#if-cursor-shows-error-for-tappsmcp) above (wrong subcommand, `--no-sync`, Show Output). |
| **Path denied / file not found** | Set `TAPPS_MCP_PROJECT_ROOT` (and optionally `TAPPS_MCP_HOST_PROJECT_ROOT` when using Docker or a different host path). |
| **"This operation was aborted" when calling tapps_init** | MCP client timeout. Full init can take 10–35+ seconds. **Fix:** Use `dry_run: true` to preview (~2–5s), or `verify_only: true` (~1–3s), or set `warm_cache_from_tech_stack: false` and `warm_expert_rag_from_tech_stack: false` for faster init. See [MCP_CLIENT_TIMEOUTS.md](MCP_CLIENT_TIMEOUTS.md). |

---

## Summary

1. **Install:** `pip install tapps-mcp` or `uv sync` in the TappsMCP repo.
2. **Configure your client:** `tapps-mcp init` (auto-detect) or manually add to MCP config.
3. **Verify:** `tapps-mcp doctor` to diagnose any issues.
4. **Run:** `tapps-mcp serve` to start the server (stdio for local clients, `--transport http` for remote).
5. **Use the tools:** Have the AI call `tapps_session_start` first, then `tapps_quick_check` during edits, `tapps_validate_changed` + `tapps_checklist` before declaring work complete.
6. **Optional:** Install ruff/mypy/bandit/radon for best scoring; set `TAPPS_MCP_PROJECT_ROOT` and `.tapps-mcp.yaml` as needed.
