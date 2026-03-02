# MCP Composition and Rule Hierarchy

TappMCP works as one MCP server in a larger AI-assistant setup. This doc explains how to compose it with other MCPs and how rule/CLAUDE.md hierarchy applies.

---

## Rule hierarchy

Claude Code and Cursor support hierarchical rule files. **More specific always wins** when rules conflict:

| Scope | Location | When applied |
|-------|----------|--------------|
| Enterprise | Organization-wide config | All users in the org |
| Personal | `~/.claude/` or user settings | All projects for that user |
| Project | `CLAUDE.md`, `.cursor/rules/` | Current project only |
| Local | Path-scoped rules (e.g. `**/*.py`) | Files matching the path |

For TappMCP-generated rules:

- **CLAUDE.md** (Claude Code) and **`.cursor/rules/tapps-pipeline.md`** (Cursor) are project-level.
- TappMCP adds a path-scoped Python quality rule when supported by the host.
- If your org or personal config has conflicting instructions, the more specific scope overrides the broader one.

**Best practice:** Put only non-negotiable, always-needed standards in project rules. Put task-specific guidance (e.g. tool reference, checklist per task type) in skills that load on demand.

---

## MCP composition

TappMCP is one MCP server. It composes with hooks, skills, sub-agents, and **other MCP servers** in the same project.

### Composing with other MCPs

Add TappMCP alongside the MCPs your workflow needs:

| MCP | Use case |
|-----|----------|
| **GitHub** | PRs, issues, Actions, repo metadata |
| **Context7** | Up-to-date library docs (TappMCP can use it internally) |
| **Sentry** | Error tracking, release health |
| **YouTube** | Video tutorials, demos |
| **Database / Postgres** | Schema inspection, query help |
| **Your custom MCP** | Domain-specific tools |

### How they work together

- **Hooks** run on events (SessionStart, PostToolUse, Stop) and can remind the agent to use any MCP tools.
- **Skills** load on demand; the agent invokes them when the task matches.
- **Sub-agents** run in isolated context and can use any configured MCPs.
- **MCP tools** from different servers appear in the same tool list; the agent chooses based on the task.

### Adding other MCPs

1. Add the server entry to your MCP config (e.g. `.cursor/mcp.json` or Claude Code MCP settings).
2. Ensure the host can reach the server (stdio, HTTP, or Docker).
3. Optionally update your AGENTS.md or rules to mention when to use the new tools.

TappMCP’s init wizard does not configure other MCPs by default. If you want a prompt to add complementary MCPs during init, use the optional wizard question when available.

---

## Related docs

- [TAPPSMCP_VIDEO_BEST_PRACTICES_UPDATE.md](planning/TAPPSMCP_VIDEO_BEST_PRACTICES_UPDATE.md) — Decision matrix from Claude Code "5 Features" video
- [INIT_AND_UPGRADE_FEATURE_LIST.md](INIT_AND_UPGRADE_FEATURE_LIST.md) — Init options including minimal mode
- [MCP_YOUTUBE_SETUP.md](MCP_YOUTUBE_SETUP.md) — Example of adding the YouTube MCP
