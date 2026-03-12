# MCP Configuration Gaps — Reference

**Source:** Deep research conducted 2026-02-21

## Server Instructions Field

### What It Is
A text field in the MCP server configuration that helps clients discover and
understand the server's purpose. Critical for Claude Code's Tool Search feature
which uses lazy loading to manage tool counts.

### Format (Claude Code `.mcp.json`)

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uvx",
      "args": ["tapps-mcp", "serve"],
      "env": {
        "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}"
      },
      "instructions": "Code quality scoring (0-100 across 7 categories), security scanning (Bandit + secret detection), quality gates (pass/fail against configurable presets), documentation lookup, domain expert consultation, and project profiling for Python projects."
    }
  }
}
```

### Impact
Without `instructions`, Claude Code's Tool Search may not discover TappsMCP tools
when they are lazily loaded (deferred). This is a discoverability gate.

---

## Environment Variables in MCP Config

### What It Is
The `env` field in MCP server configuration passes environment variables to the
server process. Currently TappsMCP relies on auto-detection for project root.

### Current Config (No env)
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

### Recommended Config (With env)

#### Claude Code (.mcp.json)
```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uvx",
      "args": ["tapps-mcp", "serve"],
      "env": {
        "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

#### Cursor (.cursor/mcp.json)
```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uvx",
      "args": ["tapps-mcp", "serve"],
      "env": {
        "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

#### VS Code (.vscode/mcp.json)
```json
{
  "servers": {
    "tapps-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["tapps-mcp", "serve"],
      "env": {
        "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

### Impact
Explicit `TAPPS_MCP_PROJECT_ROOT` prevents silent path resolution failures
when the server can't auto-detect the project root.

---

## Permission Pre-Configuration

### What It Is
Claude Code allows project-level settings that auto-allow specific MCP tools,
eliminating permission prompts for trusted tools.

### Format (`.claude/settings.json`)
```json
{
  "permissions": {
    "allow": [
      "mcp__tapps-mcp__tapps_score_file",
      "mcp__tapps-mcp__tapps_quality_gate",
      "mcp__tapps-mcp__tapps_quick_check",
      "mcp__tapps-mcp__tapps_validate_changed",
      "mcp__tapps-mcp__tapps_session_start",
      "mcp__tapps-mcp__tapps_consult_expert",
      "mcp__tapps-mcp__tapps_research",
      "mcp__tapps-mcp__tapps_lookup_docs",
      "mcp__tapps-mcp__tapps_dashboard",
      "mcp__tapps-mcp__tapps_stats",
      "mcp__tapps-mcp__tapps_checklist",
      "mcp__tapps-mcp__tapps_validate_config",
      "mcp__tapps-mcp__tapps_impact_analysis",
      "mcp__tapps-mcp__tapps_project_profile",
      "mcp__tapps-mcp__tapps_session_notes",
      "mcp__tapps-mcp__tapps_adaptive_weights",
      "mcp__tapps-mcp__tapps_explain_score",
      "mcp__tapps-mcp__tapps_compare_scores",
      "mcp__tapps-mcp__tapps_trend_analysis",
      "mcp__tapps-mcp__tapps_feedback",
      "mcp__tapps-mcp__tapps_init"
    ]
  }
}
```

### Wildcard Alternative
```json
{
  "permissions": {
    "allow": [
      "mcp__tapps-mcp__*"
    ]
  }
}
```

### Impact
Combined with tool annotations (`readOnlyHint=true`), this eliminates
100% of permission prompts for TappsMCP tools in Claude Code.

---

## Cursor Sandbox Domain Allowlist

### Required for Context7
If users have Cursor sandbox enabled, Context7 API calls will be blocked
unless the domain is whitelisted.

### Documentation Needed
Instruct users to add to sandbox config:
```json
{
  "sandbox": {
    "allowedDomains": [
      "mcp.context7.com"
    ]
  }
}
```

---

## VS Code Copilot Instructions

### What It Is
VS Code Copilot Chat reads `.github/copilot-instructions.md` for project-level
guidance. Currently TappsMCP generates nothing for VS Code.

### Format
Plain markdown — no frontmatter needed.

```markdown
# TappsMCP Quality Tools

This project uses TappsMCP for code quality analysis. When available
as an MCP server, use the following tools:

## Key Tools
- `tapps_session_start` — Call first to initialize a session
- `tapps_quick_check` — Quick quality check after editing files
- `tapps_quality_gate` — Pass/fail gate with configurable presets
- `tapps_validate_changed` — Validate all changed files before completing

## Workflow
1. Start a session with `tapps_session_start`
2. After editing Python files, run `tapps_quick_check`
3. Before declaring work complete, run `tapps_validate_changed`
```
