# GitHub Agentic Workflows (Technical Preview 2026)

## Overview

Agentic Workflows allow AI agents to run as part of CI/CD pipelines on GitHub
Actions. Written in Markdown instead of YAML, they are compiled to `.lock.yml`
files for execution. This guide covers authoring, compilation, security model,
agent capabilities, and production patterns.

## Supported Agents

| Agent | Provider | Capabilities |
|---|---|---|
| GitHub Copilot | GitHub | Code review, issue triage, docs |
| Claude Code | Anthropic | Complex reasoning, multi-step tasks |
| OpenAI Codex | OpenAI | Code generation, analysis |

## Workflow Authoring

### Markdown Format

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

### Frontmatter Options

```yaml
---
trigger: pull_request           # GitHub event trigger
agent: copilot                  # Agent to use
model: gpt-4                   # Model override (optional)
timeout: 300                   # Max execution time in seconds
permissions:
  contents: read
  pull-requests: write
tools:                          # Scoped tool access
  - code_search
  - file_read
  - pr_comment
---
```

### Multi-Step Workflows

```markdown
---
trigger: issues.opened
agent: copilot
---

# Issue Triage

## Step 1: Classify Issue

Read the issue title and body. Classify as one of:
- Bug report
- Feature request
- Question
- Documentation

## Step 2: Apply Labels

Based on classification, apply the appropriate label:
- bug -> "type: bug"
- feature -> "type: feature"
- question -> "type: question"
- docs -> "type: docs"

## Step 3: Assign Team

Route to the appropriate team based on content:
- Security issues -> @security-team
- UI issues -> @frontend-team
- API issues -> @backend-team
```

## Compilation

### gh-aw Extension

```bash
# Install the gh aw extension
gh extension install github/gh-aw

# Compile Markdown to .lock.yml
gh aw compile .github/workflows/review.md

# Compile all agentic workflows
gh aw compile .github/workflows/*.md

# Preview without writing
gh aw compile .github/workflows/review.md --dry-run
```

### Compiled Output

The compiled `.lock.yml` is a standard GitHub Actions workflow with
SHA-pinned dependencies and security constraints:

```yaml
# .github/workflows/review.lock.yml (auto-generated)
name: PR Quality Review
on:
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
      - uses: github/copilot-action@abc123
        with:
          prompt-file: .github/workflows/review.md
          tools: code_search,file_read,pr_comment
```

### Version Locking

Lock files pin all action versions to SHA hashes:

```bash
# Update lock files with latest SHA pins
gh aw lock .github/workflows/review.lock.yml

# Verify lock file integrity
gh aw verify .github/workflows/review.lock.yml
```

## Security Model

### Principle of Least Privilege

Agentic workflows run with minimal permissions by default:

1. **Read-only access** - agents cannot push code directly
2. **Firewall-restricted** - network access is limited to GitHub APIs
3. **Content sanitization** - inputs are sanitized before agent processing
4. **Safe outputs** - writes go through controlled channels (PR comments, labels)
5. **Sandboxed execution** - isolated runner environment

### Permission Scoping

```yaml
# Explicit permission declaration
permissions:
  contents: read          # read repository files
  pull-requests: write    # post PR comments and reviews
  issues: write           # apply labels and assignments
```

### Tool Access Control

Limit which tools the agent can use:

```yaml
tools:
  - code_search     # search repository code
  - file_read       # read file contents
  - pr_comment      # post PR comments
  # NOT included: pr_merge, code_push, etc.
```

### Secret Handling

Agents cannot access repository secrets by default. Use explicit secret
injection with scoped permissions:

```yaml
secrets:
  - name: QUALITY_API_KEY
    description: "API key for external quality service"
    required: false
```

## Agent Tool Capabilities

### Available Tools

| Tool | Description | Permission |
|---|---|---|
| `code_search` | Search repository code | contents: read |
| `file_read` | Read file contents | contents: read |
| `file_list` | List directory contents | contents: read |
| `pr_comment` | Post PR comment | pull-requests: write |
| `pr_review` | Submit PR review | pull-requests: write |
| `issue_comment` | Post issue comment | issues: write |
| `issue_label` | Apply/remove labels | issues: write |
| `issue_assign` | Assign users | issues: write |

### MCP Integration

Agentic workflows can use MCP servers for extended capabilities:

```yaml
---
trigger: pull_request
agent: copilot
mcp_servers:
  - name: tapps-mcp
    command: uvx tapps-mcp serve
    tools:
      - tapps_score_file
      - tapps_quick_check
---

# Quality Gate

Score changed files using TappsMCP. If any file scores below 70,
post a comment with improvement suggestions.
```

## Use Cases

### PR Quality Review

```markdown
---
trigger: pull_request
agent: copilot
---

# PR Quality Review

Review the changed files in this pull request:

1. Check for common security issues (SQL injection, XSS, hardcoded secrets)
2. Identify code that lacks test coverage
3. Flag functions with cyclomatic complexity above 10
4. Verify all public functions have docstrings
5. Post a summary comment with findings and suggestions
```

### Issue Triage

```markdown
---
trigger: issues.opened
agent: copilot
---

# Issue Triage

Analyze this new issue and:

1. Classify the issue type (bug, feature, question, docs)
2. Estimate severity (critical, high, medium, low)
3. Apply appropriate labels
4. If critical/high severity, assign to on-call team
5. Add to the appropriate project board
```

### CI Failure Investigation

```markdown
---
trigger: workflow_run.completed
agent: copilot
---

# CI Failure Investigation

When a CI workflow fails:

1. Read the failing job's logs
2. Identify the root cause of the failure
3. Check if the failure is flaky (has it passed recently?)
4. Post a comment on the triggering PR with:
   - Root cause analysis
   - Suggested fix
   - Whether this is a known flaky test
```

### Documentation Sync

```markdown
---
trigger: pull_request
agent: copilot
---

# Documentation Check

For each changed source file:

1. Check if the corresponding documentation exists
2. If API signatures changed, verify docs are updated
3. If new public functions were added, check for docstrings
4. Post a review requesting documentation updates if needed
```

### Quality Hygiene

```markdown
---
trigger: schedule
cron: "0 9 * * 1"
agent: copilot
---

# Weekly Quality Hygiene

Run a weekly codebase health check:

1. Identify the 10 most complex functions
2. Find unused imports across the codebase
3. Check for TODO/FIXME comments older than 30 days
4. Create an issue with a summary of findings
```

## Integration with TappsMCP

### Quality Gate Workflow

```markdown
---
trigger: pull_request
agent: copilot
mcp_servers:
  - name: tapps-mcp
    command: uvx tapps-mcp serve
---

# TappsMCP Quality Gate

1. Call tapps_session_start
2. For each changed Python file, call tapps_quick_check
3. Call tapps_validate_changed for comprehensive analysis
4. If any file fails the quality gate:
   - Post a review requesting changes
   - List specific files and their scores
5. If all files pass:
   - Approve the PR
   - Post a summary of quality scores
```

## Best Practices

1. **Keep prompts focused** - one clear objective per workflow
2. **Define success criteria** - tell the agent what "done" looks like
3. **Scope tool access** - only grant tools the agent needs
4. **Set timeouts** - prevent runaway agent execution
5. **Use tool references** - explicitly list available tools
6. **Test with dry-run** - verify compilation before committing
7. **Monitor agent actions** - review workflow logs regularly
8. **Gate behind feature flags** - use conditional triggers until stable
9. **Version lock files** - commit `.lock.yml` files for reproducibility
10. **Review agent outputs** - do not blindly trust agent-generated content

## Anti-Patterns

### Over-Broad Permissions

Granting `write-all` to an agentic workflow creates excessive risk.
Always use minimal permissions.

### Unscoped Agent Tools

Not restricting tool access means the agent can perform unintended actions.
Always declare a `tools` list.

### Missing Timeouts

Without timeouts, agents can run indefinitely and consume Actions minutes.
Always set `timeout` in frontmatter.

### Trusting Agent Output

Agent output should be treated as suggestions, not authoritative actions.
Use require-approval gates for destructive actions.

## Quick Reference

| Command | Description |
|---|---|
| `gh extension install github/gh-aw` | Install aw extension |
| `gh aw compile {file}.md` | Compile to .lock.yml |
| `gh aw compile --dry-run` | Preview without writing |
| `gh aw lock {file}.lock.yml` | Update SHA pins |
| `gh aw verify {file}.lock.yml` | Verify lock integrity |
