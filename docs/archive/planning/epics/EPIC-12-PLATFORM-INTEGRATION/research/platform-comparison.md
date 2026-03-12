# Platform Comparison — Claude Code vs Cursor vs VS Code

**Source:** Deep research conducted 2026-02-21

## Feature Support Matrix

| Feature | Claude Code | Cursor | VS Code (Copilot) |
|---------|:-----------:|:------:|:------------------:|
| MCP Tools | Yes (21) | Yes (40 limit) | Yes |
| MCP Resources | Yes (4) | Yes (subscriptions) | Limited |
| MCP Prompts | Yes (3) | Yes | No |
| MCP Elicitation | No | Yes | No |
| MCP Dynamic Tools | Via Tool Search | Yes | No |
| Tool Annotations | Yes | Yes | Yes |
| stdio transport | Yes | Yes | Yes |
| Streamable HTTP | Yes | Yes | No |
| SSE transport | Yes | Yes (legacy) | No |
| Hooks | **17 events** | **6 events** | No |
| Subagents | `.claude/agents/` | `.cursor/agents/` | No |
| Skills | `.claude/skills/` | `.cursor/skills/` | No |
| Plugins | `.claude-plugin/` | `.cursor-plugin/` | Extensions |
| Agent Teams | Yes (experimental) | Parallel agents (8) | No |
| Background Agents | No | Yes (no MCP access) | No |
| Project Rules | CLAUDE.md | `.cursor/rules/*.mdc` | `.github/copilot-instructions.md` |
| Cross-tool Rules | AGENTS.md | AGENTS.md | AGENTS.md |
| Tech Stack | TECH_STACK.md | TECH_STACK.md | — |
| BugBot/PR Review | No | Yes (.cursor/BUGBOT.md) | No |
| Sandbox | No | Yes (2.5) | No |
| Memories | No native | Session-scoped | No |
| Permission Config | `.claude/settings.json` | Yolo mode | No |
| Server Instructions | Yes (MCP config) | No | No |

## TappsMCP Current Coverage

| Platform | What tapps_init Generates | Gaps |
|----------|--------------------------|------|
| **Claude Code** | CLAUDE.md | Hooks, subagents, skills, plugin, settings, env, instructions |
| **Cursor** | `.cursor/rules/tapps-pipeline.md` (alwaysApply) | Hooks, subagents, skills, plugin, rule types, BugBot rules |
| **VS Code** | Nothing | copilot-instructions.md |
| **Cross-platform** | AGENTS.md, TECH_STACK.md | Tool annotations, env in MCP config |

## Hook Power Comparison

| Capability | Claude Code | Cursor |
|-----------|:-----------:|:------:|
| Total events | 17 | 6 |
| Block agent stopping | Yes (exit 2) | No (followup_message) |
| Block task completion | Yes (exit 2) | No |
| Inject prompt context | Yes | No |
| Post-process MCP output | Yes | No |
| Modify MCP inputs | Yes | No |
| Subagent hooks | Yes (2 events) | No |
| Agent Teams hooks | Yes (2 events) | No |
| Compaction hook | Yes | No |
| Setup/onboarding | Yes | No |
| Guard MCP calls | Yes | Yes |
| After-edit action | Yes (blocking) | Yes (fire-and-forget) |

## Subagent Comparison

| Aspect | Claude Code | Cursor |
|--------|:-----------:|:------:|
| Format | YAML frontmatter (comma-sep tools) | YAML frontmatter (YAML array tools) |
| Max concurrent | 7 | 4 |
| Can nest | No | Yes (sub-subagents) |
| MCP access | Yes (foreground only) | Depends on config |
| Permission mode | Configurable per-agent | Not configurable |
| Memory | MEMORY.md persistence | No |
| Hooks in frontmatter | Yes | No |
| Skills in frontmatter | Yes | No |

## Plugin Comparison

| Aspect | Claude Code | Cursor |
|--------|:-----------:|:------:|
| Manifest | `.claude-plugin/plugin.json` | `.cursor-plugin/plugin.json` |
| Bundles MCP | Yes (`.mcp.json`) | Yes (`mcp.json`) |
| Bundles agents | Yes (`agents/`) | Yes (`agents/`) |
| Bundles skills | Yes (`skills/`) | Yes (`skills/`) |
| Bundles hooks | Yes (`hooks/`) | Yes (`hooks/`) |
| Bundles rules | No (uses CLAUDE.md) | Yes (`rules/*.mdc`) |
| Marketplace | No | Yes (`cursor.com/marketplace`) |
| Install method | Plugin system | `/add-plugin` or marketplace |
