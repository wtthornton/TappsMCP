# Migration from tapps-agents to TappsMCP

If you were using **tapps-agents** (e.g. `.tapps-agents/`, experts config, knowledge files) and are moving to **TappsMCP**, this guide explains what to remove, what to keep, and how to configure your MCP host.

---

## What to remove or stop using

- **tapps-agents runtime and config**
  Stop relying on the old agent-specific runtime. Remove or archive:
  - `.tapps-agents/` (if present in your project)
  - Any agents-specific config that pointed at tapps-agents (e.g. Cursor/Claude config that invoked the old stack)
- **Duplicate MCP entries**
  In your MCP host settings (Claude Code, Cursor, VS Code), remove the old tapps-agents server entry so only **tapps-mcp** is configured.

---

## What to keep

- **Project layout and quality expectations**
  Your repo structure, test layout, and quality bar stay the same. TappsMCP tools (scoring, gates, security scan, checklist) replace the previous quality flow.
- **File-based knowledge you care about**
  Any markdown docs, rules, or guidelines that lived under tapps-agents and that you still want can be kept as normal files. TappsMCP has its own expert knowledge base (in the repo under `src/tapps_mcp/experts/knowledge/`) and does not read legacy `.tapps-agents` knowledge by default; you can reuse content by copying into your project or into TappsMCP's knowledge layout if you customize it.

---

## What to configure

1. **Auto-setup (recommended)**
   Run `tapps-mcp init` to auto-detect your MCP host and generate configuration:
   ```bash
   tapps-mcp init                        # auto-detect
   tapps-mcp init --host claude-code     # Claude Code
   tapps-mcp init --host cursor          # Cursor
   tapps-mcp init --host vscode          # VS Code
   ```

2. **Manual setup**
   Point your IDE/client at the TappsMCP server instead of tapps-agents:
   - **Claude Code:** `tapps-mcp init --host claude-code` or add to `~/.claude.json`
   - **Cursor:** In **Settings > MCP** or project `.cursor/mcp.json`, add the `tapps-mcp` server. Use either:
     - **HTTP:** `"url": "http://localhost:8000/mcp"` when running TappsMCP in Docker, or
     - **stdio:** `"command": "tapps-mcp"` with `"args": ["serve"]` (or use `uv` with `--directory`)
   - **VS Code:** `tapps-mcp init --host vscode` or edit `.vscode/mcp.json`

   See [TAPPS_MCP_SETUP_AND_USE.md](TAPPS_MCP_SETUP_AND_USE.md) for full examples.

3. **Project root (recommended)**
   Set `TAPPS_MCP_PROJECT_ROOT` to the project you want the AI to analyze, or rely on the default (current working directory). For Docker or when the host path differs, set `TAPPS_MCP_HOST_PROJECT_ROOT` as in the setup doc.

4. **Optional project config**
   Add `.tapps-mcp.yaml` in the project root to set `quality_preset`, `log_level`, `tool_timeout`, etc.

5. **Bootstrap pipeline (optional)**
   Call `tapps_init` via your AI assistant to create AGENTS.md, TECH_STACK.md, and platform rules in your project.

---

## Quick checklist

- [ ] TappsMCP installed (`pip install tapps-mcp` or `uv sync` or Docker).
- [ ] Old tapps-agents MCP/server entry removed from your client.
- [ ] New tapps-mcp entry added via `tapps-mcp init` or manually.
- [ ] Verified with `tapps-mcp doctor`.
- [ ] `TAPPS_MCP_PROJECT_ROOT` set if needed.
- [ ] Optional: `.tapps-mcp.yaml` in project root.
- [ ] Session workflow: start with `tapps_session_start`; use `tapps_checklist` before declaring work complete.

For install and troubleshooting (including the "checklist module not found" error when using a binary), see [TAPPS_MCP_SETUP_AND_USE.md](TAPPS_MCP_SETUP_AND_USE.md).
