# Story 80.7 -- docs-mcp parity across hosts

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** platform integrator, **I want** a single documented full-stack snippet or init flag, **so that** all hosts register both servers the same way when desired

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that teams using both tapps-mcp and docs-mcp get consistent MCP registration across Cursor, VS Code, and Claude Code instead of editor-specific drift.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Add --with-docs-mcp or document a multi-host JSON snippet bundle. Align with Epic 12 platform integration themes.

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Design flag or template outputs for docs-mcp alongside tapps-mcp (`packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`)
- [x] Update platform generator docs (`docs/`)
- [x] Tests for generated mcp.json entries when flag set (`packages/tapps-mcp/tests/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] Documented path registers docs-mcp on Cursor VS Code Claude when chosen
- [x] Behavior covered by test or snapshot
- [x] Non-breaking default when flag off

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_documented_path_registers_docsmcp_on_cursor_vs_code_claude_chosen` -- Documented path registers docs-mcp on Cursor VS Code Claude when chosen
2. `test_ac2_behavior_covered_by_test_or_snapshot` -- Behavior covered by test or snapshot
3. `test_ac3_nonbreaking_default_flag_off` -- Non-breaking default when flag off

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document implementation hints, API contracts, data formats...

### Expert Recommendations

- **Security Expert** (68%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (64%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

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
