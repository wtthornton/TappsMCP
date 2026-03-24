# Story 80.5 -- MCP config: PATH detection and uv-run fallback

**Status:** Complete  
**Completed:** 2026-03-24


<!-- docsmcp:start:user-story -->

> **As a** Windows developer, **I want** init to emit a working command block when tapps-mcp is not on PATH, **so that** Cursor/VS Code/Claude can launch the server without manual JSON surgery

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that generated MCP server entries start on hosts where tapps-mcp is only available via uv from a checkout, not globally on PATH.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Detect shutil.which('tapps-mcp') or equivalent; if missing, generate uv + --directory <placeholder> run ... template and prompt or document placeholder. When merging existing mcp.json, preserve unrelated env vars (e.g. TAPPS_MCP_CONTEXT7_API_KEY).

See [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:tasks -->
## Tasks

- [x] Add PATH detection in MCP writer (`packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`)
- [x] Implement uv-run template with configurable TappMCP root (`packages/tapps-mcp/src/tapps_mcp/pipeline/`)
- [x] Merge preserves existing env object keys (`packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`)
- [x] Tests for merge preservation and template selection (`packages/tapps-mcp/tests/unit/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] When binary absent generated config uses uv-run pattern
- [x] Env vars not dropped on merge
- [x] Tests cover both PATH and non-PATH branches

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

Definition of Done per [Epic 80](../EPIC-80-CONSUMER-INIT-BOOTSTRAP-HARDENING.md).

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. `test_ac1_binary_absent_generated_config_uses_uvrun_pattern` -- When binary absent generated config uses uv-run pattern
2. `test_ac2_env_vars_not_dropped_on_merge` -- Env vars not dropped on merge
3. `test_ac3_tests_cover_both_path_nonpath_branches` -- Tests cover both PATH and non-PATH branches

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document implementation hints, API contracts, data formats...

### Expert Recommendations

- **Security Expert** (77%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (59%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

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
