# Story 80.3 -- Init default project root and TappMCP self-bootstrap guard

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** consumer developer, **I want** clear warnings or refusal when default project root resolves inside the TappMCP monorepo layout, **so that** I do not pollute the upstream repo or miss files in my consumer project

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that running tapps-mcp init via uv from the TappMCP checkout cannot silently bootstrap the wrong repository when the consumer intended another project root.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Detect known TappMCP source layout (e.g. packages/tapps-mcp). If default '.' resolves there without --project-root or explicit escape hatch, warn and exit non-zero or require flag. Document canonical: uv --directory <TappMCP> run tapps-mcp init --project-root <consumer>.

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Add detection helper for running inside TappMCP package tree (`packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`)
- [x] Wire CLI messaging and exit codes (`packages/tapps-mcp/src/tapps_mcp/`)
- [x] Add tests for cwd vs project_root semantics under uv (`packages/tapps-mcp/tests/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] Init from packages/tapps-mcp without --project-root does not silently target consumer-unintended tree
- [x] Help text or error cites --project-root example
- [x] Unit/integration test covers uv-style cwd

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_init_from_packagestappsmcp_without_projectroot_does_not_silently_target` -- Init from packages/tapps-mcp without --project-root does not silently target consumer-unintended tree
2. `test_ac2_help_text_or_error_cites_projectroot_example` -- Help text or error cites --project-root example
3. `test_ac3_unitintegration_test_covers_uvstyle_cwd` -- Unit/integration test covers uv-style cwd

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document implementation hints, API contracts, data formats...

### Expert Recommendations

- **Security Expert** (70%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (66%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

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
