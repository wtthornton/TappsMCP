# Cursor IDE Features — Complete Reference

**Source:** Deep research conducted 2026-02-21
**Version:** Cursor 2.5 (February 2026)

## Cursor Hooks (`.cursor/hooks.json`)

### File Locations

- **Project:** `.cursor/hooks.json` (version controlled)
- **User:** `~/.cursor/hooks.json` (personal, all projects)
- Both locations are merged; all hooks execute.

### Schema

```json
{
  "$schema": "https://unpkg.com/cursor-hooks@latest/schema/hooks.schema.json",
  "version": 1,
  "hooks": {
    "beforeSubmitPrompt": [{ "command": "path/to/script" }],
    "beforeShellExecution": [{ "command": "path/to/script" }],
    "beforeMCPExecution": [{ "command": "path/to/script" }],
    "beforeReadFile": [{ "command": "path/to/script" }],
    "afterFileEdit": [{ "command": "path/to/script" }],
    "stop": [{ "command": "path/to/script" }]
  }
}
```

### Hook Events (6 Total)

#### beforeSubmitPrompt
- **Stdin:** `conversation_id`, `generation_id`, `prompt`, `attachments`, `workspace_roots`
- **Response:** `{ "continue": true|false }`
- **Cannot inject context** — only block or allow

#### beforeShellExecution
- **Stdin:** `conversation_id`, `generation_id`, `command`, `cwd`, `workspace_roots`
- **Response:** `{ "continue": bool, "permission": "allow"|"deny"|"ask", "userMessage": "...", "agentMessage": "..." }`

#### beforeMCPExecution
- **Stdin:** `conversation_id`, `generation_id`, `tool_name`, `tool_input` (escaped JSON), `command` (server launch cmd), `workspace_roots`
- **Response:** `{ "continue": bool, "permission": "allow"|"deny"|"ask", "agentMessage": "..." }`
- **CAN block/modify MCP calls** via permission field and agentMessage injection

#### beforeReadFile
- **Stdin:** `conversation_id`, `generation_id`, `content`, `file_path`, `workspace_roots`
- **Response:** `{ "permission": "allow"|"deny", "agentMessage": "...", "userMessage": "..." }`
- Primary use: secret redaction

#### afterFileEdit
- **Stdin:** `conversation_id`, `generation_id`, `file_path`, `old_string`, `new_string`, `workspace_roots`
- **Fire-and-forget** — cannot block, no response honored
- Use: auto-format, auto-stage, run linters

#### stop
- **Stdin:** `conversation_id`, `status` ("completed"|"aborted"|"error"), `loop_count`, `workspace_roots`
- **Response:** `{ "followup_message": "..." }`
- `followup_message` **restarts the agent loop** (weaker than Claude's exit-2 blocking)

### Comparison with Claude Code Hooks

| Capability | Claude Code (17 events) | Cursor (6 events) |
|-----------|:-----------------------:|:------------------:|
| Block agent from stopping | Yes (exit 2) | No (only followup_message) |
| Block task completion | Yes (exit 2) | No |
| Inject context into prompts | Yes | No |
| Post-process MCP output | Yes | No |
| Modify MCP tool inputs | Yes | No |
| Subagent lifecycle hooks | Yes | No |
| Agent Teams hooks | Yes | No |
| Context compaction hook | Yes | No |
| Guard MCP calls | Yes | Yes |
| Auto-format after edit | Yes | Yes (fire-and-forget) |

---

## Cursor Rules (`.cursor/rules/`)

### Rule Types

| Type | Trigger | Frontmatter |
|------|---------|-------------|
| **Always** | Every chat | `alwaysApply: true` |
| **Auto Attached** | When matching files referenced | `globs: "*.py"`, `alwaysApply: false` |
| **Agent Requested** | Agent reads description, decides | `description: "..."` only |
| **Manual** | Explicit @-mention | No description, no globs |

### .mdc File Format

```yaml
---
description: "Quality standards for Python files"
globs: "*.py"
alwaysApply: false
---

Markdown instructions here...
```

### Rule Precedence
Team Rules > Project Rules > User Rules. All applicable rules are merged.

### TappsMCP Opportunities
- **Current:** Only generates `alwaysApply` rules
- **Gap:** Should generate `autoAttach` rules with `globs: "*.py"` for scoring
- **Gap:** Should generate `agentRequested` rules for expert consultation

---

## Cursor Skills (`.cursor/skills/`)

### Directory Locations
- **Project:** `.cursor/skills/skill-name/SKILL.md`
- **User:** `~/.cursor/skills/skill-name/SKILL.md`

### SKILL.md Format

```yaml
---
name: tapps-quality-gate
description: Use this skill when the user wants to run a quality gate check using TappsMCP.
---

# TappsMCP Quality Gate

## When to Use
- User asks to check code quality
- Before creating a PR

## Step-by-Step Instructions
1. Call `tapps_session_start` MCP tool
2. Call `tapps_quick_check` on changed files
3. Call `tapps_quality_gate` with preset
4. Report results

## Important Notes
- Requires tapps-mcp MCP server
```

| Field | Required | Description |
|-------|----------|-------------|
| `description` | Yes | Agent decides when to activate based on this |
| `name` | No | Defaults to folder name |

### Supporting Files
```
.cursor/skills/tapps-quality-gate/
  SKILL.md
  references/
    scoring-categories.md
  scripts/
    validate.sh
```

### Key Behavior
- Agent-decided — loaded only when relevant
- Skills **can reference MCP tools by name** and agent will invoke them
- Skills are "meta-prompts" that orchestrate MCP tool usage
- Cannot be configured as always-apply or manual

---

## Cursor Subagents (`.cursor/agents/`)

### Format (Different from Claude Code)

```markdown
---
name: security-reviewer
description: Use when reviewing code for security vulnerabilities.
model: inherit
readonly: true
is_background: false
tools:
  - code_search
  - git_history
---

You are a security review expert...
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Identifier |
| `description` | string | When to spawn |
| `model` | string | `inherit` or specific model |
| `readonly` | boolean | Cannot modify files if true |
| `is_background` | boolean | Runs in background |
| `tools` | string[] | YAML array (not comma-separated like Claude) |

### Key Differences from Claude Code
- Max **4 concurrent** (vs Claude's 7)
- **Can spawn sub-subagents** (Claude cannot)
- Built-in types: `generalPurpose`, `explore`, `shell`, `browser-use`
- Tools listed as YAML array, not comma-separated string

---

## Cursor Plugin Format (`.cursor-plugin/`)

### Directory Structure

```
my-plugin/
  .cursor-plugin/
    plugin.json
  skills/
    my-skill/SKILL.md
  rules/
    coding-standards.mdc
  agents/
    reviewer.md
  hooks/
    hooks.json
    after-edit.ts
  mcp.json
  logo.png
  README.md
  LICENSE
```

### plugin.json

```json
{
  "name": "tapps-mcp-plugin",
  "displayName": "TappsMCP Quality Tools",
  "author": "TappsMCP Team",
  "description": "Code quality scoring, security scanning, and quality gates",
  "keywords": ["code-quality", "security", "scoring"],
  "license": "MIT",
  "version": "1.0.0"
}
```

All fields required. Name must be lowercase kebab-case.

### Installation
- Browse: `cursor.com/marketplace`
- In-editor: `/add-plugin`
- Deep link: `cursor://install-plugin/plugin-name`
- Private: Enterprise team marketplaces

---

## Cursor BugBot

### Configuration: `.cursor/BUGBOT.md`
- Uses **directory hierarchy inheritance** — walks up directory tree
- Cannot trigger MCP tools (uses Cursor-internal tools only)
- Reviews 2M+ PRs/month, 70% resolution rate

### TappsMCP Opportunity
Generate `.cursor/BUGBOT.md` with quality standards for PR review.

---

## Cursor Sandbox (v2.5)

### Impact on MCP Servers
- MCP servers via stdio are **child processes** — inherit sandbox restrictions
- External API access requires domains in `allowedDomains`
- MCP servers **cannot opt out** of sandbox
- Remote MCP servers (SSE/HTTP) are not affected

### Required Domains for TappsMCP
- `mcp.context7.com` (Context7 documentation lookup)
- Any other external APIs TappsMCP calls

---

## Cursor Background Agents

### MCP Access: NOT AVAILABLE
- Run in isolated Ubuntu VMs
- Cannot see project-level `.cursor/mcp.json`
- No stable API for MCP integration
- Biggest Cursor gap — cannot solve from MCP server side

### environment.json
```json
{
  "baseImage": "ghcr.io/cursor-images/node-20:latest",
  "install": "pip install tapps-mcp",
  "env": { "TAPPS_MCP_PROJECT_ROOT": "/workspace" }
}
```

---

## MCP Elicitation (Cursor Only)

### Request Format
```json
{
  "method": "elicitation/create",
  "params": {
    "message": "Which quality gate preset?",
    "requestedSchema": {
      "type": "object",
      "properties": {
        "preset": {
          "type": "string",
          "enum": ["development", "staging", "production"],
          "enumNames": ["Development (lenient)", "Staging (moderate)", "Production (strict)"]
        }
      },
      "required": ["preset"]
    }
  }
}
```

### Supported Types
string (formats: email, uri, date, date-time), number, integer, boolean, enum

### Response
```json
{
  "action": "accept",
  "content": { "preset": "production" }
}
```
Actions: `"accept"` | `"decline"` | `"cancel"`
