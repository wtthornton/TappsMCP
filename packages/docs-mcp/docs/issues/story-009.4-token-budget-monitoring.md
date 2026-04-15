# Story 9.4 -- Claude CLI Token Budget Monitoring

<!-- docsmcp:start:user-story -->

> **As a** server administrator, **I want** MCP tools that track Claude CLI usage costs and warn when approaching budget limits, **so that** I get early warning before running out of tokens and can switch to a fallback or pause work

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the server agent can proactively monitor Claude CLI token/cost usage and alert before budget exhaustion, enabling preemptive action.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Add tools to the claude_cli module that parse --output-format json cost data, track cumulative spend per session/day, and emit warnings at configurable thresholds. Depends on claude_run_prompt's JSON output which includes total_cost_usd.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `src/server_agent/tools/claude_cli.py`
- `tests/unit/test_claude_cli.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Add usage tracking to claude_cli.py (parse total_cost_usd from JSON output) (`src/server_agent/tools/claude_cli.py`)
- [ ] Create persistent usage store (SQLite or JSON file) (`src/server_agent/tools/claude_cli.py`)
- [ ] Add claude_usage_summary() tool (`src/server_agent/tools/claude_cli.py`)
- [ ] Add configurable budget threshold and warning logic (`src/server_agent/config/`)
- [ ] Write unit tests for usage tracking (`tests/unit/test_claude_cli.py`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] claude_usage_summary() returns cumulative cost and token counts
- [ ] Configurable budget threshold with warning output
- [ ] Usage data persisted across sessions (SQLite or JSON)
- [ ] Integration with existing claude_run_prompt JSON output
- [ ] Unit tests with mocked cost data

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Claude CLI Token Budget Monitoring code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] Documentation updated
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
