# Story 91.5 -- Performance Targets Section Enhancement

<!-- docsmcp:start:user-story -->

> **As a** developer generating comprehensive epics, **I want** the performance targets section to auto-derive meaningful metrics from the epic context, **so that** I get useful targets even without expert enrichment.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 2 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the Performance Targets section in comprehensive epics is never empty. Currently it only renders when expert enrichment provides guidance, leaving a blank section most of the time.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Enhance `_render_performance_targets` to derive targets from `EpicConfig` signals when expert enrichment is absent:

- **AC count > 5**: suggest "Acceptance criteria pass rate | 0% | 100% | CI pipeline"
- **Files > 3**: suggest "Quality gate score | N/A | >= 70/100 | tapps_quality_gate"
- **Stories > 3**: suggest "Story completion rate | 0% | 100% | Sprint tracking"
- Always suggest: "Test coverage | baseline | >= 80% | pytest --cov"

Expert-derived targets (when available) take precedence.

See [Epic 91](../EPIC-91-epic-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/epics.py`
- `packages/docs-mcp/tests/unit/test_epics.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Add config-signal derivation logic to `_render_performance_targets`
- [ ] Derive test coverage target (always present)
- [ ] Derive AC pass rate target when AC count > 5
- [ ] Derive quality gate target when files > 3
- [ ] Expert targets override config-derived targets for same metric
- [ ] Add unit tests for each derivation path

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Comprehensive epic with no expert enrichment still renders Performance Targets with at least 1 row
- [ ] Expert-derived targets appear when enrichment is available
- [ ] Config-derived targets reflect actual AC/story/file counts

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
