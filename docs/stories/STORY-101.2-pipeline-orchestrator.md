# Story 101.2 -- tapps_pipeline one-call orchestrator

<!-- docsmcp:start:user-story -->

> **As a** agent or human using TappsMCP, **I want** one tapps_pipeline call that runs the full quality pipeline with smart defaults, **so that** I never skip a step and always get a clear pass/fail with exact next actions

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that a single MCP call runs the entire quality loop end-to-end, removing the cognitive load of chaining session_start → quick_check → validate_changed → checklist by hand.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

New MCP tool tapps_pipeline(files, task_type) runs session_start (if stale), quick_check per file, validate_changed batched, and checklist — short-circuiting on security floor failure. Returns a structured verdict with one top-priority next action.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/tapps-mcp/src/tapps_mcp/pipeline/orchestrator.py`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/models.py`
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Define PipelineVerdict schema (`packages/tapps-mcp/src/tapps_mcp/pipeline/models.py`)
- [ ] Implement orchestrator with short-circuit (`packages/tapps-mcp/src/tapps_mcp/pipeline/orchestrator.py`)
- [ ] Register tapps_pipeline MCP tool (`packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`)
- [ ] Add AGENTS.md guidance and deprecate manual chaining (`AGENTS.md`)
- [ ] Add unit + integration tests (`packages/tapps-mcp/tests/unit/test_pipeline_orchestrator.py`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

### AC: Given staged Python files When tapps_pipeline runs Then returns pass/fail verdict with one next action

```gherkin
Feature: given-staged-python-files-when-tapps-pipeline-runs-then-returns-passfail-verdict-with-one-next-action
  Scenario: Given staged Python files When tapps_pipeline runs Then returns pass/fail verdict with one next action
    Given a agent or human using TappsMCP is ready to perform the action
    When the agent or human using TappsMCP one tapps_pipeline call that runs the full quality pipeline with smart defaults
    Then Given staged Python files When tapps_pipeline runs Then returns pass/fail verdict with one next action successfully
```

### AC: Given a security floor failure When orchestrator runs Then short-circuits and surfaces the security issue first

```gherkin
Feature: given-a-security-floor-failure-when-orchestrator-runs-then-short-circuits-and-surfaces-the-security-issue-first
  Scenario: Given a security floor failure When orchestrator runs Then short-circuits and surfaces the security issue first
    Given a agent or human using TappsMCP is ready to perform the action
    When the agent or human using TappsMCP one tapps_pipeline call that runs the full quality pipeline with smart defaults
    Then Given a security floor failure When orchestrator runs Then short-circuits and surfaces the security issue first successfully
```

### AC: Given no session_start in last 24h When orchestrator runs Then auto-initializes session

```gherkin
Feature: given-no-session-start-in-last-24h-when-orchestrator-runs-then-auto-initializes-session
  Scenario: Given no session_start in last 24h When orchestrator runs Then auto-initializes session
    Given a agent or human using TappsMCP is ready to perform the action
    When the agent or human using TappsMCP one tapps_pipeline call that runs the full quality pipeline with smart defaults
    Then Given no session_start in last 24h When orchestrator runs Then auto-initializes session successfully
```

### AC: Given 10 changed files When orchestrator runs in quick mode Then completes in under 30s

```gherkin
Feature: given-10-changed-files-when-orchestrator-runs-in-quick-mode-then-completes-in-under-30s
  Scenario: Given 10 changed files When orchestrator runs in quick mode Then completes in under 30s
    Given a agent or human using TappsMCP is ready to perform the action
    When the agent or human using TappsMCP one tapps_pipeline call that runs the full quality pipeline with smart defaults
    Then Given 10 changed files When orchestrator runs in quick mode Then completes in under 30s successfully
```

### AC: Given orchestrator success When called again Then cache hits make it under 2s

```gherkin
Feature: given-orchestrator-success-when-called-again-then-cache-hits-make-it-under-2s
  Scenario: Given orchestrator success When called again Then cache hits make it under 2s
    Given a agent or human using TappsMCP is ready to perform the action
    When the agent or human using TappsMCP one tapps_pipeline call that runs the full quality pipeline with smart defaults
    Then Given orchestrator success When called again Then cache hits make it under 2s successfully
```

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] tapps_pipeline one-call orchestrator code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] Documentation updated
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. Clean repo passes in quick mode
2. Security vulnerability short-circuits pipeline
3. Cache hit path is under 2s
4. Missing session_start triggers auto-init
5. Verdict always includes next_steps length 1

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Reuse existing tool handlers
- Do not duplicate logic — compose
- Verdict must be JSON-serializable for plugin consumers
- Honor .tapps-mcp.yaml presets

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:dependencies -->
## Dependencies

- List stories or external dependencies that must complete first...

<!-- docsmcp:end:dependencies -->

<!-- docsmcp:start:invest -->
## INVEST Checklist

- [x] **I**ndependent -- Can be developed and delivered independently
- [ ] **N**egotiable -- Details can be refined during implementation
- [x] **V**aluable -- Delivers value to a user or the system
- [x] **E**stimable -- Team can estimate the effort
- [x] **S**mall -- Completable within one sprint/iteration
- [x] **T**estable -- Has clear criteria to verify completion

<!-- docsmcp:end:invest -->
