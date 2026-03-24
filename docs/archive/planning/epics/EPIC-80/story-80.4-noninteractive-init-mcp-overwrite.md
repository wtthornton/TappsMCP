# Story 80.4 -- Non-interactive init: MCP overwrite and env/TTY behavior

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** automation engineer, **I want** deterministic non-TTY behavior for existing .mcp.json merge, **so that** pipelines complete with clear logs and documented flags

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that CI, scripts, and AI agents never block indefinitely on overwrite prompts when MCP entries already exist.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

When stdin is not a TTY, skip interactive overwrite or default to no-overwrite with explicit log line; optionally support TAPPS_MCP_INIT_ASSUME_YES=1. Document --force for intentional overwrites.

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Detect TTY in init MCP merge path (`packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`)
- [x] Implement env-driven assume-yes or safe skip (`packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`)
- [x] Add non-interactive test (no hang) (`packages/tapps-mcp/tests/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] No indefinite wait without TTY
- [x] Log line tells user to pass --force when needed
- [x] Behavior documented in README or init help

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_no_indefinite_wait_without_tty` -- No indefinite wait without TTY
2. `test_ac2_log_line_tells_user_pass_force_needed` -- Log line tells user to pass --force when needed
3. `test_ac3_behavior_documented_readme_or_init_help` -- Behavior documented in README or init help

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document implementation hints, API contracts, data formats...

### Expert Recommendations

- **Security Expert** (74%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (68%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

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
