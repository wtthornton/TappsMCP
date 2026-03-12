# Claude Code Subagents & Agent Teams — Complete Reference

**Source:** Deep research conducted 2026-02-21
**Version:** Claude Code v2.1.49+ (February 2026)

## Subagents Overview

Subagents are specialized AI assistants defined as Markdown files with YAML frontmatter.
Each runs in its own context window with custom system prompt, specific tool access,
and independent permissions. Claude auto-delegates based on the `description` field.

## File Locations (Priority Order)

| Location | Scope | Priority |
|----------|-------|----------|
| `--agents` CLI flag (JSON) | Current session | 1 (highest) |
| `.claude/agents/` | Current project | 2 |
| `~/.claude/agents/` | All projects (user) | 3 |
| Plugin `agents/` directory | Where plugin enabled | 4 (lowest) |

Project-level agents override user-level agents with the same name.

## File Format

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
model: sonnet
---

You are a code reviewer. When invoked, analyze the code and provide
specific, actionable feedback on quality, security, and best practices.
```

## Complete YAML Frontmatter Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | Yes | string | Unique identifier (lowercase + hyphens) |
| `description` | Yes | string | When Claude should delegate to this agent |
| `tools` | No | string | Comma-separated allowlist. Inherits all (including MCP) if omitted |
| `disallowedTools` | No | string | Tools to deny from inherited list |
| `model` | No | string | `sonnet`, `opus`, `haiku`, or `inherit` (default: inherit) |
| `permissionMode` | No | string | `default`, `acceptEdits`, `dontAsk`, `bypassPermissions`, `plan` |
| `maxTurns` | No | int | Max agentic turns before stopping |
| `skills` | No | string | Skills to preload at startup |
| `mcpServers` | No | object | MCP servers available (by name or inline definition) |
| `hooks` | No | object | Lifecycle hooks scoped to this subagent |
| `memory` | No | string | `user`, `project`, or `local` |
| `background` | No | bool | Always run as background task (default: false) |
| `isolation` | No | string | `worktree` for git worktree isolation |

## MCP Tool Access

- **Foreground subagents:** CAN access MCP tools
- **Background subagents:** CANNOT access MCP tools (hard limitation)
- **Global MCP config** (`~/.claude/mcp.json`): Works reliably
- **Project MCP config** (`.mcp.json`): Known bugs with subagent access
- **`mcpServers` frontmatter:** Per-subagent MCP config (most reliable)

## Built-in Subagent Types

| Type | Model | Tools | Purpose |
|------|-------|-------|---------|
| Explore | haiku | Read-only | Codebase search and analysis |
| Plan | inherit | Read-only | Research during plan mode |
| general-purpose | inherit | All | Complex multi-step tasks |
| Bash | inherit | Bash | Terminal commands in separate context |
| claude-code-guide | haiku | Read-only + web | Claude Code documentation lookup |

## Key Constraints

- **No nesting:** Subagents cannot spawn other subagents
- **Up to 7 concurrent** subagents
- Subagents receive only their system prompt + basic env details
- Native implementation since v1.0.60 (sub-second latency)
- `Task(agent_type)` in tools field creates an allowlist of spawnable agents

## TappsMCP Subagent Definitions

### tapps-reviewer

```markdown
---
name: tapps-reviewer
description: Use proactively to review code quality, run security scans, and enforce quality gates after editing Python files.
tools: Read, Glob, Grep
model: sonnet
permissionMode: dontAsk
memory: project
---

You are a TappsMCP quality reviewer. When invoked:

1. Identify which Python files were recently edited
2. Call `mcp__tapps-mcp__tapps_quick_check` on each changed file
3. If any file scores below 70, call `mcp__tapps-mcp__tapps_score_file` for detailed breakdown
4. Summarize findings: file, score, top issues, suggested fixes
5. If overall quality is poor, recommend calling `tapps_quality_gate`

Focus on actionable feedback. Be concise.
```

### tapps-researcher

```markdown
---
name: tapps-researcher
description: Use when needing documentation lookup, library research, or expert consultation for code decisions.
tools: Read, Glob, Grep, WebFetch
model: haiku
memory: project
---

You are a TappsMCP research assistant. When invoked:

1. Call `mcp__tapps-mcp__tapps_research` for documentation and library lookups
2. Call `mcp__tapps-mcp__tapps_consult_expert` for domain-specific guidance
3. Synthesize findings into clear, actionable recommendations
4. Return only the relevant excerpts, not full documents

Keep responses focused and concise to preserve context budget.
```

### tapps-validator

```markdown
---
name: tapps-validator
description: Use before declaring work complete to validate all changes pass quality gates.
tools: Read, Glob, Grep
model: sonnet
permissionMode: dontAsk
---

You are a TappsMCP validation agent. When invoked:

1. Call `mcp__tapps-mcp__tapps_validate_changed` to check all modified files
2. If validation fails, report which files and categories need improvement
3. If validation passes, confirm with a summary of scores

Do NOT suggest fixes — only report results. The main agent handles fixes.
```

---

## Agent Teams

### Overview

Agent Teams coordinate multiple **separate Claude Code instances** (not subagents).
One session is the team lead, which creates the team, spawns teammates, and coordinates.

### Enabling

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### Architecture

| Component | Role |
|-----------|------|
| Team lead | Creates team, spawns teammates, coordinates |
| Teammates | Separate Claude Code instances on assigned tasks |
| Task list | Shared work queue with dependencies |
| Mailbox | JSON file-based inter-agent messaging |

### File System

```
~/.claude/teams/{team-name}/
  config.json
  inboxes/
    team-lead.json
    worker-1.json
    worker-2.json
~/.claude/tasks/{team-name}/
    1.json
    2.json
```

### Subagents vs Agent Teams

| Aspect | Subagents | Agent Teams |
|--------|-----------|-------------|
| Context | Own window, results return to caller | Own window, fully independent |
| Communication | Report back to main only | Message each other directly |
| Coordination | Main agent manages | Shared task list, self-claim |
| Best for | Focused tasks | Complex collaborative work |
| Token cost | Lower | Higher (separate instances) |

### Quality Gate Hooks for Teams

- **TeammateIdle:** Exit 2 keeps teammate working (stderr = feedback)
- **TaskCompleted:** Exit 2 prevents task completion (stderr = feedback)

### TappsMCP Quality Watchdog Pattern

In Agent Teams, designate one teammate as a "quality watchdog" that:
1. Monitors filesystem for changes via `inotifywait` or polling
2. Runs `tapps_quick_check` on changed files
3. Messages other teammates about quality issues via `write`
4. TaskCompleted hook prevents completion if gates fail

---

## Claude Code Plugin Format

### Directory Structure

```
tapps-mcp-plugin/
  .claude-plugin/
    plugin.json
  agents/
    tapps-reviewer.md
    tapps-researcher.md
    tapps-validator.md
  skills/
    tapps-score/SKILL.md
    tapps-gate/SKILL.md
    tapps-validate/SKILL.md
  hooks/
    hooks.json
  .mcp.json
  README.md
```

### plugin.json

```json
{
  "name": "tapps-mcp",
  "version": "1.0.0",
  "description": "Code quality scoring, security scanning, and quality gates"
}
```

Plugins can ship subagent definitions in their `agents/` directory alongside
MCP server configurations, skills, commands, and hooks as a cohesive package.
