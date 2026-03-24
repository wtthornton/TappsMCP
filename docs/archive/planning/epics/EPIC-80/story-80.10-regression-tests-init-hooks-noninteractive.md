# Story 80.10 -- Regression tests: init root hooks non-interactive

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** QA engineer, **I want** automated tests mirroring the consumer appendix, **so that** releases catch regressions before users do

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the three failure modes from the consumer report cannot regress: wrong project root, missing hook files, and interactive hang.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Implement tests: dry-run init with --project-root tmp asserts no writes under TappMCP; Windows path asserts hook ps1 exist iff referenced; non-interactive init with existing mcp.json exits without blocking.

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Test init dry-run project root isolation (`packages/tapps-mcp/tests/`)
- [x] Test hook file presence vs settings references (`packages/tapps-mcp/tests/`)
- [x] Test non-TTY MCP merge completes (`packages/tapps-mcp/tests/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] All three scenarios from feedback appendix covered in CI
- [x] Tests run on Windows job or simulated paths
- [x] Failures have clear assertion messages

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_all_three_scenarios_from_feedback_appendix_covered_ci` -- All three scenarios from feedback appendix covered in CI
2. `test_ac2_tests_run_on_windows_job_or_simulated_paths` -- Tests run on Windows job or simulated paths
3. `test_ac3_failures_clear_assertion_messages` -- Failures have clear assertion messages

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document implementation hints, API contracts, data formats...

### Expert Recommendations

- **Security Expert** (69%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (65%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:dependencies -->
## Dependencies

- Stories 80.1 80.3 80.4 for full coverage

<!-- docsmcp:end:dependencies -->

<!-- docsmcp:start:invest -->
## INVEST Checklist

- [ ] **I**ndependent -- Can be developed and delivered independently
- [ ] **N**egotiable -- Details can be refined during implementation
- [x] **V**aluable -- Delivers value to a user or the system
- [x] **E**stimable -- Team can estimate the effort
- [x] **S**mall -- Completable within one sprint/iteration
- [x] **T**estable -- Has clear criteria to verify completion

<!-- docsmcp:end:invest -->
