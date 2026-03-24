# Story 80.8 -- TECH_STACK low-confidence wrapper layouts

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** consumer maintainer, **I want** TECH_STACK.md to surface low confidence and optional subfolder scan, **so that** profiles improve manually or via configurable detection

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 2 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that wrapper repos with docs at root and code in a subdirectory are not mislabeled as documentation-only without a visible disclaimer.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

When classifier confidence is below threshold, emit HTML comment or markdown callout in TECH_STACK.md. Optional: scan first pyproject.toml or package.json under subdirs.

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Add low-confidence banner to TECH_STACK template (`packages/tapps-mcp/src/tapps_mcp/pipeline/`)
- [x] Optional subfolder probe for primary manifest (`packages/tapps-core/src/tapps_core/`)
- [x] Unit tests for wrapper layout fixture (`packages/tapps-mcp/tests/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] Low confidence produces visible note in TECH_STACK.md
- [x] Configurable or heuristic subfolder scan documented
- [x] Test uses wrapper-style fixture

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_low_confidence_produces_visible_note_techstackmd` -- Low confidence produces visible note in TECH_STACK.md
2. `test_ac2_configurable_or_heuristic_subfolder_scan_documented` -- Configurable or heuristic subfolder scan documented
3. `test_ac3_test_uses_wrapperstyle_fixture` -- Test uses wrapper-style fixture

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document implementation hints, API contracts, data formats...

### Expert Recommendations

- **Security Expert** (73%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (67%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

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
