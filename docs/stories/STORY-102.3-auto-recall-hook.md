# Story 102.3 -- Auto-recall hook for tapps_validate_changed

<!-- docsmcp:start:user-story -->

> **As a** agent running tapps_validate_changed, **I want** relevant memories recalled automatically and surfaced in the validation result, **so that** I avoid repeating fixes that were already learned in prior sessions or sibling projects

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that every validation run benefits from relevant past learnings without the agent having to call tapps_memory search manually.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Add a pre-validation hook that queries tapps-brain for memories matching the changed file paths + detected archetype, and attaches top-3 recalls to the response with provenance.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/tapps-mcp/src/tapps_mcp/pipeline/recall.py`
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`
- `packages/tapps-mcp/src/tapps_mcp/config/settings.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Implement recall query builder (`packages/tapps-mcp/src/tapps_mcp/pipeline/recall.py`)
- [ ] Wire hook into validate_changed (`packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`)
- [ ] Add provenance field to response envelope (`packages/tapps-mcp/src/tapps_mcp/common/nudges.py`)
- [ ] Add config flag memory_hooks.auto_recall (`packages/tapps-mcp/src/tapps_mcp/config/settings.py`)
- [ ] Tests with mock brain (`packages/tapps-mcp/tests/unit/test_auto_recall.py`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

### AC: Given changed files When validate_changed runs Then response includes recalled memories with source

```gherkin
Feature: given-changed-files-when-validate-changed-runs-then-response-includes-recalled-memories-with-source
  Scenario: Given changed files When validate_changed runs Then response includes recalled memories with source
    Given a agent running tapps_validate_changed is ready to perform the action
    When the agent running tapps_validate_changed relevant memories recalled automatically and surfaced in the validation result
    Then Given changed files When validate_changed runs Then response includes recalled memories with source successfully
```

### AC: Given no relevant memories When validate_changed runs Then response omits recall block cleanly

```gherkin
Feature: given-no-relevant-memories-when-validate-changed-runs-then-response-omits-recall-block-cleanly
  Scenario: Given no relevant memories When validate_changed runs Then response omits recall block cleanly
    Given a agent running tapps_validate_changed is ready to perform the action
    When the agent running tapps_validate_changed relevant memories recalled automatically and surfaced in the validation result
    Then Given no relevant memories When validate_changed runs Then response omits recall block cleanly successfully
```

### AC: Given hook enabled When validate_changed runs Then adds under 200ms overhead

```gherkin
Feature: given-hook-enabled-when-validate-changed-runs-then-adds-under-200ms-overhead
  Scenario: Given hook enabled When validate_changed runs Then adds under 200ms overhead
    Given a agent running tapps_validate_changed is ready to perform the action
    When the agent running tapps_validate_changed relevant memories recalled automatically and surfaced in the validation result
    Then Given hook enabled When validate_changed runs Then adds under 200ms overhead successfully
```

### AC: Given opt-out config When validate_changed runs Then skips recall entirely

```gherkin
Feature: given-opt-out-config-when-validate-changed-runs-then-skips-recall-entirely
  Scenario: Given opt-out config When validate_changed runs Then skips recall entirely
    Given a agent running tapps_validate_changed is ready to perform the action
    When the agent running tapps_validate_changed relevant memories recalled automatically and surfaced in the validation result
    Then Given opt-out config When validate_changed runs Then skips recall entirely successfully
```

### AC: Given cross-scope memory When recall runs Then never crosses scope boundaries

```gherkin
Feature: given-cross-scope-memory-when-recall-runs-then-never-crosses-scope-boundaries
  Scenario: Given cross-scope memory When recall runs Then never crosses scope boundaries
    Given a agent running tapps_validate_changed is ready to perform the action
    When the agent running tapps_validate_changed relevant memories recalled automatically and surfaced in the validation result
    Then Given cross-scope memory When recall runs Then never crosses scope boundaries successfully
```

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Auto-recall hook for tapps_validate_changed code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] Documentation updated
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. Recall returns top-3 by relevance
2. Latency budget enforced by test
3. Scope isolation verified
4. Opt-out config honored
5. Provenance includes project and tier

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Use existing tapps_core memory bridge
- Do not block validation on brain failure
- Log provenance for audit

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
