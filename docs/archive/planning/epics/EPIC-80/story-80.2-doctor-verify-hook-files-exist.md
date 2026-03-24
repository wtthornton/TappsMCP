# Story 80.2 -- Doctor: verify hook files exist for settings references

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** consumer developer, **I want** doctor to validate that each hook script path referenced under .claude/settings exists, **so that** I get an actionable FAIL or WARNING instead of silent hook errors

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that tapps-mcp doctor catches broken hook configurations before users discover failures at runtime, including stale paths after partial upgrades.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Parse .claude/settings.json (and _PS variant) for hook commands pointing at .claude/hooks/tapps-*.ps1 or .sh; verify file exists. Integrate with existing doctor output style.

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Implement hook path existence checks in doctor command (`packages/tapps-mcp/src/tapps_mcp/`)
- [x] Add unit tests with temp settings missing a referenced hook (`packages/tapps-mcp/tests/unit/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] Doctor reports missing hook files referenced by settings
- [x] Check covers PostToolUse matchers for tapps- hook scripts
- [x] Tests cover positive and negative cases

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_doctor_reports_missing_hook_files_referenced_by_settings` -- Doctor reports missing hook files referenced by settings
2. `test_ac2_check_covers_posttooluse_matchers_tapps_hook_scripts` -- Check covers PostToolUse matchers for tapps- hook scripts
3. `test_ac3_tests_cover_positive_negative_cases` -- Tests cover positive and negative cases

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document implementation hints, API contracts, data formats...

### Expert Recommendations

- **Security Expert** (77%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (65%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:dependencies -->
## Dependencies

- Story 80.1 preferred so fewer false positives

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
