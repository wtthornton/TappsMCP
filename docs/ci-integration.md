# CI Integration Guide

TappsMCP can run quality checks in CI pipelines without an interactive session.
This guide covers GitHub Actions, Claude Code headless mode, and direct Python
invocation.

## GitHub Actions

When `tapps_init` runs with a platform configured, it generates
`.github/workflows/tapps-quality.yml` — a ready-to-use GitHub Actions workflow
that validates changed Python files on every pull request.

### Generated Workflow

```yaml
name: TappsMCP Quality Gate

on:
  pull_request:
    paths:
      - "**.py"

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install TappsMCP
        run: pip install tapps-mcp

      - name: Run TappsMCP quality gate
        env:
          TAPPS_MCP_PROJECT_ROOT: ${{ github.workspace }}
        run: |
          tapps-mcp validate-changed --preset staging
```

### Customizing the Workflow

- Change `--preset staging` to `development` (lenient) or `production` (strict)
- Add `--changed-files` to explicitly list files instead of auto-detection
- Set `TAPPS_MCP_CONTEXT7_API_KEY` for documentation lookup in CI

## Claude Code Headless Mode

Claude Code can run non-interactively in CI using `--headless`:

```bash
# Run quality validation headlessly
claude --headless \
  --allowedTools "mcp__tapps-mcp__tapps_validate_changed" \
  "Run tapps_validate_changed with preset=staging"
```

### Team Onboarding with --init-only

The `--init-only` flag triggers the Setup hook and exits, useful for
bootstrapping TappsMCP in new team member environments:

```bash
claude --init-only \
  --allowedTools "mcp__tapps-mcp__*" \
  --project-root /workspace
```

The Setup hook (`matcher: init`) fires specifically for `--init` and
`--init-only`, not for regular sessions.

## Direct Python Invocation

For CI systems that don't use Claude Code, invoke TappsMCP directly:

```bash
# Install
pip install tapps-mcp

# Validate changed files
TAPPS_MCP_PROJECT_ROOT=/workspace \
  tapps-mcp validate-changed --preset staging
```

## VS Code / Headless Settings

In headless or non-interactive VS Code contexts, enable project MCP servers:

```json
{
  "claude.enableAllProjectMcpServers": true
}
```

Or via CLI:

```bash
claude --enable-all-project-mcp-servers --headless "..."
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TAPPS_MCP_PROJECT_ROOT` | Project root directory (required) |
| `TAPPS_MCP_CONTEXT7_API_KEY` | API key for Context7 doc lookups (optional) |
| `TAPPS_MCP_LOG_LEVEL` | Log level: DEBUG, INFO, WARNING (default: INFO) |

## Exit Codes

- `0` — All quality gates passed
- `1` — One or more files failed the quality gate
- `2` — Configuration error or missing dependencies
