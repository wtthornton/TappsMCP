# Story 80.6 -- Documentation: canonical install and Windows examples

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** technical writer, **I want** README and init output to show canonical install and init commands, **so that** new users succeed on first try without 404s or wrong cwd assumptions

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that public docs never imply npx install when the package is not on npm, and Windows users get copy-paste commands that match uv/pip/git workflows.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Audit README, AGENTS.md pointers, and init banner for npx references. Add prominent uv run from checkout, uv tool install, pip where applicable. Include Windows path example from consumer feedback.

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Replace or qualify npx tapps-mcp references (`README.md`)
- [x] Add Windows uv --directory + --project-root example (`docs/`)
- [x] Print recommended install command from init where helpful (`packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] No misleading npx-only path without npm publish decision
- [x] Canonical commands appear in README or top-level install doc
- [x] Example matches real consumer scenario from feedback

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_no_misleading_npxonly_path_without_npm_publish_decision` -- No misleading npx-only path without npm publish decision
2. `test_ac2_canonical_commands_appear_readme_or_toplevel_install_doc` -- Canonical commands appear in README or top-level install doc
3. `test_ac3_example_matches_real_consumer_scenario_from_feedback` -- Example matches real consumer scenario from feedback

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document implementation hints, API contracts, data formats...

### Expert Recommendations

- **Security Expert** (71%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
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
