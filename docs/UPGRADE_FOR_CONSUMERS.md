# Upgrading TappsMCP — Guide for Consuming Projects

When you **install or upgrade** TappsMCP in a project that uses it for quality checks, doc lookup, and experts, you may want to refresh pipeline templates and rules so the AI gets the latest workflow guidance.

---

## 1. Upgrade the package

```bash
pip install -U tapps-mcp
# or: uv tool install -U tapps-mcp
```

---

## 2. Refresh project pipeline templates

Use the **`tapps_init`** MCP tool (via your AI assistant or a script) with:

| Option | Purpose |
|--------|---------|
| `overwrite_agents_md=True` | Replace AGENTS.md with the latest template (new workflow, tool hints) |
| `overwrite_platform_rules=True` | Refresh platform rule files (CLAUDE.md, .cursor/rules) |
| `platform="cursor"` or `"claude"` | Which platform rules to generate |

**Example (ask your AI):**  
*"Call tapps_init with overwrite_agents_md=True, overwrite_platform_rules=True, and platform=cursor to refresh to the latest TappsMCP templates."*

---

## 3. Refresh MCP host config (optional)

If the MCP server entry or startup command changed, run:

```bash
tapps-mcp init --force --host cursor
```

`--force` overwrites the existing tapps-mcp entry without prompting.

---

## 4. Re-run init for caches and TECH_STACK

A normal `tapps_init` run (without overwrite flags) will:

- Refresh TECH_STACK.md
- Warm Context7 cache for detected libraries
- Warm expert RAG indices for relevant domains

---

## Summary

| What | How |
|------|-----|
| Get latest AGENTS.md and workflow | `tapps_init(overwrite_agents_md=True)` |
| Get latest platform rules | `tapps_init(overwrite_platform_rules=True, platform="cursor")` or `platform="claude"` |
| Refresh MCP config | `tapps-mcp init --force` |
| Refresh caches and TECH_STACK | `tapps_init()` (default) |

See [INIT_AND_UPGRADE_FEATURE_LIST.md](INIT_AND_UPGRADE_FEATURE_LIST.md) for the full init and upgrade behavior.
