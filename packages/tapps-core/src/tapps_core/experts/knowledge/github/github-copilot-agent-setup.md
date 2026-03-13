# GitHub Copilot Agent Setup

## Overview

GitHub Copilot has evolved from an autocomplete tool into a full agent platform.
As of early 2026, Copilot offers local agent mode (VS Code), an async coding
agent (GitHub-hosted), code review, CLI agent mode, and MCP integration.

## Agent Mode (GA in VS Code)

Agent mode is generally available in VS Code and allows Copilot to:
- Plan multi-step tasks autonomously
- Read and write files across the project
- Execute terminal commands
- Self-correct when errors occur
- Use MCP servers for extended tool access

Agent mode splits into two distinct experiences:

### Local Agent Mode

Runs in your VS Code instance with full workspace access:

- Edits files, runs terminal commands, iterates on errors
- Accesses MCP servers configured in VS Code settings
- Uses the model picker to select from available AI models
- Works offline (with local models) or with cloud models

### Async Coding Agent (Cloud)

Triggered via GitHub Issues, Copilot Chat, or third-party integrations
(Slack, Teams, Linear). Runs in a GitHub Actions environment:

1. Creates a branch
2. Writes code autonomously
3. Performs self-review (runs linters, tests, security scans)
4. Opens a pull request with a summary of changes

## Coding Agent Setup

### Environment Configuration

```yaml
# .github/workflows/copilot-setup-steps.yml
name: Copilot Setup Steps
on: workflow_dispatch
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: "3.12"
  - run: pip install -e ".[dev]"
  - run: pip install ruff mypy bandit radon
```

### Triggering the Coding Agent

The coding agent can be triggered from:

1. **GitHub Issues** - assign an issue to Copilot
2. **Copilot Chat** - ask Copilot to implement a feature
3. **Slack/Teams** - delegate coding tasks via integrations
4. **Linear** - link Linear issues to trigger Copilot

### Self-Review

The coding agent automatically reviews its own changes before opening a PR:

- Runs configured linters and formatters
- Executes the test suite
- Performs code scanning (CodeQL) and secret scanning
- Checks dependency vulnerabilities via Dependabot
- Only opens the PR if self-review passes

If self-review fails, the agent iterates on the code until checks pass
or reports that it could not resolve the issue.

## Built-in Security Scanning

The coding agent integrates GitHub's security features:

| Feature | Description |
|---|---|
| Code scanning | CodeQL analysis of generated code |
| Secret scanning | Detects accidentally committed secrets |
| Dependency checks | Flags vulnerable dependencies |
| Push protection | Blocks pushes containing secrets |

These checks run automatically as part of the agent's self-review loop.

## Copilot Instructions

`.github/copilot-instructions.md` provides project-specific guidance:

```markdown
# Copilot Instructions
- Use pytest for testing
- Follow PEP 8 style
- Add type annotations to all functions
- Run ruff check before committing
```

## Custom Agent Profiles

`.github/agents/*.md` with YAML frontmatter define specialized agents:

```markdown
---
name: quality-reviewer
description: Reviews code quality
tools:
  - tapps_score_file
  - tapps_quality_gate
---

Review code quality using TappsMCP tools.
```

Custom agents can be:
- Task-specific (security review, documentation, testing)
- Domain-specific (frontend, backend, infrastructure)
- Workflow-specific (release management, issue triage)

## Path-Scoped Instructions

`.github/instructions/*.instructions.md`:

```markdown
---
applyTo: "**/*.py"
---

All Python files must have type annotations.
Use structlog for logging, never print().
```

## Copilot Code Review

Automatic reviews via rulesets:
1. Add Copilot as a required reviewer in rulesets
2. Configure review standards in copilot-instructions.md
3. Copilot reviews PRs with full project context
4. Provides inline suggestions with Copilot Autofix

## Model Picker

Copilot supports multiple AI models, selectable per session:

- Claude Opus 4.6, Claude Sonnet 4.6 (Anthropic)
- GPT-5.3-Codex (OpenAI)
- Gemini 3 Pro (Google)
- o3-mini (OpenAI, reasoning)

Select models based on task complexity:
- Quick edits: faster models (Sonnet, GPT-4o)
- Complex reasoning: Claude Opus, o3-mini
- Large codebases: models with larger context windows

## MCP Support in Agent Mode

### VS Code MCP Configuration

```json
{
  "mcp": {
    "servers": {
      "tapps-mcp": {
        "command": "uv",
        "args": ["run", "tapps-mcp", "serve"],
        "env": {
          "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}"
        }
      },
      "github": {
        "command": "gh",
        "args": ["mcp", "serve"]
      }
    }
  }
}
```

### Coding Agent MCP Registration

Register MCP servers in repository Copilot settings:
- Settings > Copilot > MCP Servers
- Or via REST API
- Secrets for MCP servers come from the "copilot" environment

The coding agent accesses MCP tools during autonomous sessions.

## GitHub Copilot CLI (GA - February 2026)

GitHub Copilot CLI reached general availability in February 2026:

- Ships with GitHub's MCP server built in, supports custom MCP servers
- **Agent Skills**: Markdown-based skill files that load automatically when relevant
- **Custom agents**: `.agent.md` files specifying tools, MCP servers, and instructions
- **Models available**: Claude Opus 4.6, Claude Sonnet 4.6, GPT-5.3-Codex, Gemini 3 Pro
- **Background delegation**: Prefix prompt with `&` to delegate to cloud coding agent

### CLI Handoff

The CLI supports handoff between local and cloud execution:

```bash
# Start locally, hand off to cloud agent
gh copilot agent "Implement the feature described in issue #42" &

# Check agent status
gh copilot agent status

# Review agent's work
gh copilot agent review
```

## Multi-Agent Collaboration

Copilot supports multi-agent workflows where different agents handle
different aspects of a task:

- **Copilot + Claude Code**: Copilot handles GitHub operations while
  Claude Code handles complex reasoning and code generation
- **Copilot + Custom MCP agents**: Specialized MCP servers provide
  domain-specific capabilities (quality scoring, security scanning)
- **Agent handoff**: One agent can delegate subtasks to another

## AgentHQ Platform (Announced 2025)

GitHub announced AgentHQ as a platform for customizable, task-specific
AI assistants:

- Build and deploy custom agents for specific workflows
- Agents run in secure, sandboxed environments
- Integration with GitHub Actions for CI/CD triggers
- Marketplace for sharing and discovering agents

## AGENTS.md Best Practices

From GitHub's analysis of 2,500+ repositories:
- Keep instructions concise and actionable
- Use concrete examples over abstract rules
- Specify which tools to use and when
- Include project-specific patterns and conventions
- Reference copilot-instructions.md for Copilot-specific guidance

## Quick Reference

| Feature | Status | Configuration |
|---|---|---|
| Agent Mode (VS Code) | GA | Built-in, model picker |
| Coding Agent (async) | GA | `.github/workflows/copilot-setup-steps.yml` |
| Code Review | GA | Rulesets + copilot-instructions.md |
| CLI Agent Mode | GA | `gh copilot agent` |
| MCP Support | GA | VS Code settings or repo settings |
| Custom Agents | GA | `.github/agents/*.md` |
| Self-Review | GA | Automatic in coding agent |
| AgentHQ | Preview | github.com/features/agenthq |
