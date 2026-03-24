# Story 80.1 -- Fix PostToolUse hook script generation (validate/report)

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** TappsMCP maintainer, **I want** to map tapps-post-validate and tapps-post-report templates to PostToolUse in platform_hooks script_event_map, **so that** init/upgrade writes the matching .ps1/.sh files and Windows consumers stop seeing hook failures

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that Claude Code hooks referenced in generated settings actually exist on disk after init and upgrade, eliminating broken PostToolUse matchers that call missing tapps-post-validate and tapps-post-report scripts.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Consumer feedback identified that _filter_scripts drops templates when event is empty because script_event_map omits tapps-post-validate and tapps-post-report. Add both basenames mapped to PostToolUse (same as tapps-post-edit). Verify generate path for Windows PowerShell and Unix shell.

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Add tapps-post-validate and tapps-post-report to script_event_map in platform_hooks.py (`packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hooks.py`)
- [x] Add unit test: filtered scripts include validate/report when PostToolUse enabled (`packages/tapps-mcp/tests/unit/`)
- [x] Run init/upgrade fixture test asserting hook files exist when settings reference them (`packages/tapps-mcp/tests/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] script_event_map includes tapps-post-validate and tapps-post-report → PostToolUse
- [x] Generated settings and on-disk hook files are consistent on Windows (.ps1)
- [x] Unit/regression test prevents reintroduction

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_scripteventmap_includes_tappspostvalidate_tappspostreport_posttooluse` -- script_event_map includes tapps-post-validate and tapps-post-report → PostToolUse
2. `test_ac2_generated_settings_ondisk_hook_files_consistent_on_windows_ps1` -- Generated settings and on-disk hook files are consistent on Windows (.ps1)
3. `test_ac3_unitregression_test_prevents_reintroduction` -- Unit/regression test prevents reintroduction

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Root cause per consumer doc: event becomes empty string and _filter_scripts drops templates

### Expert Recommendations

- **Security Expert** (71%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (56%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

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
