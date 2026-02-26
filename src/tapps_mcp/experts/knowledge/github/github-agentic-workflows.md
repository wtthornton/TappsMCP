# GitHub Agentic Workflows (Technical Preview 2026)

## Overview

Agentic Workflows allow AI agents to run as part of CI/CD pipelines.
Written in Markdown instead of YAML, compiled to `.lock.yml` files.

## Supported Agents

- GitHub Copilot
- Claude Code
- OpenAI Codex

## Workflow Authoring

Agentic workflows use Markdown with YAML frontmatter:

```markdown
---
trigger: pull_request
agent: copilot
---

# PR Quality Review

Review this pull request for code quality issues.

1. Check for security vulnerabilities
2. Verify test coverage
3. Ensure code style compliance
4. Post findings as PR comments
```

## Compilation

```bash
# Install the gh aw extension
gh extension install github/gh-aw

# Compile Markdown to .lock.yml
gh aw compile .github/workflows/review.md
```

The compiled `.lock.yml` is a standard GitHub Actions workflow with
SHA-pinned dependencies and security constraints.

## Security Model

- **Read-only access** — agents cannot push code directly
- **Firewall-restricted** — network access is limited
- **Content sanitization** — inputs are sanitized
- **Safe outputs** — writes go through controlled channels
- **Sandboxed execution** — isolated runner environment

## Use Cases

1. **PR quality review** — automated quality analysis on every PR
2. **Issue triage** — classify, label, and assign new issues
3. **CI failure investigation** — analyze test failures and suggest fixes
4. **Documentation updates** — keep docs in sync with code changes
5. **Quality hygiene** — periodic codebase health checks

## Best Practices

- Keep workflow descriptions concise and specific
- Define clear success criteria for the agent
- Use tool references to scope agent capabilities
- Gate behind feature flags until stable
- Monitor agent actions via workflow logs
