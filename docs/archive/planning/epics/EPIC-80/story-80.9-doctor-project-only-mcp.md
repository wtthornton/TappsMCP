# Story 80.9 -- Doctor: user-scope Claude MCP vs project-only

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** Claude Code user, **I want** doctor to downgrade or clarify when project .mcp.json is sufficient, **so that** I am not pushed to duplicate config unnecessarily

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 2 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that valid project-only MCP setups are not reported as hard failures when user-level ~/.claude.json omits tapps-mcp.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

If project-level MCP config exists and enables tapps-mcp, treat missing user global entry as WARNING or INFO with explanation. Update messaging in doctor.

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Adjust doctor severity logic for Claude user vs project MCP (`packages/tapps-mcp/src/tapps_mcp/`)
- [x] Document project-only support in troubleshooting (`docs/TROUBLESHOOTING.md`)
- [x] Unit test doctor output for project-only valid case (`packages/tapps-mcp/tests/unit/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] Project-valid + user-missing does not FAIL by default
- [x] Message explains optional user scope
- [x] Test locks behavior

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_projectvalid_usermissing_does_not_fail_by_default` -- Project-valid + user-missing does not FAIL by default
2. `test_ac2_message_explains_optional_user_scope` -- Message explains optional user scope
3. `test_ac3_test_locks_behavior` -- Test locks behavior

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document implementation hints, API contracts, data formats...

### Expert Recommendations

- **Security Expert** (72%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (63%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

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
