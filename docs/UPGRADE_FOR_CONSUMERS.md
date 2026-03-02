# Upgrading TappsMCP — Guide for Consuming Projects

When you **install or upgrade** TappsMCP in a project that uses it for quality checks, doc lookup, and experts, you may want to refresh pipeline templates and rules so the AI gets the latest workflow guidance.

---

## 1. Upgrade the package

```bash
pip install -U tapps-mcp
# or: uv tool install -U tapps-mcp
```

---

## 2. Run the upgrade command (recommended)

The easiest way to refresh all generated files:

```bash
tapps-mcp upgrade                           # auto-detect host, update everything
tapps-mcp upgrade --host claude-code        # target a specific host
tapps-mcp upgrade --dry-run                 # preview what would change
```

This updates AGENTS.md, platform rules, hooks, agents, skills, and `.claude/settings.json` permissions in one step.

---

## 3. Or use the MCP tools from within a session

**Quick upgrade (new in v0.3.0):** Use the **`tapps_upgrade`** MCP tool to refresh all generated files without leaving your AI session:

```
tapps_upgrade(dry_run=true)   # preview changes
tapps_upgrade()               # apply updates
tapps_upgrade(force=true)     # overwrite even if up-to-date
```

**Fine-grained control:** Use the **`tapps_init`** MCP tool (via your AI assistant) with:

| Option | Purpose |
|--------|---------|
| `overwrite_agents_md=True` | Replace AGENTS.md with the latest template (new workflow, tool hints) |
| `overwrite_platform_rules=True` | Refresh platform rule files (CLAUDE.md, .cursor/rules) |
| `llm_engagement_level="high"` / `"medium"` / `"low"` | Use a specific engagement level for template language and checklist |
| `platform="cursor"` or `"claude"` | Which platform rules to generate |

To change engagement level only: use **`tapps_set_engagement_level(level)`** then `tapps_init(overwrite_agents_md=True)` to regenerate AGENTS.md and rules with the new level.

---

## 4. Refresh MCP host config (optional)

If the MCP server entry or startup command changed, run:

```bash
tapps-mcp init --force --host cursor        # for Cursor
tapps-mcp init --force --host claude-code   # for Claude Code
tapps-mcp init --force --host vscode        # for VS Code
```

---

## 5. Verify the upgrade

```bash
tapps-mcp doctor                  # diagnose configuration and connectivity
tapps-mcp init --check            # verify MCP config is correct
```

---

## 6. Re-run init for caches and TECH_STACK

A normal `tapps_init` run (without overwrite flags) will:

- Refresh TECH_STACK.md with current project profile
- Warm Context7 cache for detected libraries
- Warm expert RAG indices for relevant domains

---

## Summary

| What | How |
|------|-----|
| Upgrade the package | `pip install -U tapps-mcp` |
| Refresh everything (recommended) | `tapps-mcp upgrade` (CLI) or `tapps_upgrade()` (MCP tool) |
| Get latest AGENTS.md and workflow | `tapps_init(overwrite_agents_md=True)` |
| Get latest platform rules | `tapps_init(overwrite_platform_rules=True, platform="cursor")` or `platform="claude"` |
| Refresh MCP config | `tapps-mcp init --force` |
| Refresh caches and TECH_STACK | `tapps_init()` (default) |
| Verify upgrade | `tapps-mcp doctor` |
| Rollback if upgrade causes issues | `tapps-mcp rollback` (restores from automatic pre-upgrade backup) |
| List available backups | `tapps-mcp rollback --list` |

Backups are stored in `.tapps-mcp/backups/` with the 5 most recent kept automatically. Each backup includes a `manifest.json` listing all files that were overwritten.

See [INIT_AND_UPGRADE_FEATURE_LIST.md](INIT_AND_UPGRADE_FEATURE_LIST.md) for the full init and upgrade behavior.
