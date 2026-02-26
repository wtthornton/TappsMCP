# GitHub Copilot Agent Setup

## Copilot Coding Agent (GA 2025)

Assign a GitHub issue to Copilot and it autonomously:
1. Creates a branch
2. Writes code
3. Commits changes
4. Opens a pull request

The agent runs in a GitHub Actions environment configured by
`.github/workflows/copilot-setup-steps.yml`.

## Environment Setup

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

## Copilot Instructions

`.github/copilot-instructions.md` provides project-specific guidance:

```markdown
# Copilot Instructions
- Use pytest for testing
- Follow PEP 8 style
- Add type annotations to all functions
```

## Custom Agent Profiles (October 2025)

`.github/agents/*.md` with YAML frontmatter:

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

## Path-Scoped Instructions (September 2025)

`.github/instructions/*.instructions.md`:

```markdown
---
applyTo: "**/*.py"
---

All Python files must have type annotations.
```

## Copilot Code Review

Automatic reviews via rulesets:
1. Add Copilot as a required reviewer in rulesets
2. Configure review standards in copilot-instructions.md
3. Copilot reviews PRs with full project context

## MCP Server Registration

Register MCP servers in repository Copilot settings:
- Settings > Copilot > MCP Servers
- Or via REST API (when available)

The coding agent accesses MCP tools during autonomous sessions.
Secrets for MCP servers come from the "copilot" environment.

## GitHub Copilot CLI (GA — February 2026)

GitHub Copilot CLI reached general availability in February 2026:

- Ships with GitHub's MCP server built in, supports custom MCP servers
- **Agent Skills**: Markdown-based skill files that load automatically when relevant
- **Custom agents**: `.agent.md` files specifying tools, MCP servers, and instructions
- **Models available**: Claude Opus 4.6, Claude Sonnet 4.6, GPT-5.3-Codex, Gemini 3 Pro
- **Background delegation**: Prefix prompt with `&` to delegate to cloud coding agent

## MCP in Copilot Agent Mode (2026)

GitHub Copilot agent mode in VS Code is now GA with full MCP support:

- MCP servers extend agent mode with external tools, APIs, and data sources
- **GitHub MCP Server**: Open source local server for GitHub issues, PRs, search
- Agent mode plans, executes, self-corrects, and runs terminal commands autonomously

## AGENTS.md Best Practices

From GitHub's analysis of 2,500+ repositories:
- Keep instructions concise and actionable
- Use concrete examples over abstract rules
- Specify which tools to use and when
- Include project-specific patterns and conventions
