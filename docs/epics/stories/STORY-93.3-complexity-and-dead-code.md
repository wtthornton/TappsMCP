# Story 93.3 -- Complexity and Dead Code Removal

<!-- docsmcp:start:user-story -->

> **As a** contributor reading TappsMCP code for the first time, **I want** complex functions decomposed and unused code removed, **so that** I can understand any single file without pager-scrolling through 200-line handlers or tracing symbols that turn out to be unreachable.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

Functions with cyclomatic complexity above 15 are hard to review and hard to test. Dead code adds load on every reader and raises false positives in future reviews. This story fixes both.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Run `radon cc packages/*/src/ -n C` to list every function with cyclomatic complexity > 15. Refactor each into smaller helpers, preserving behavior. Then run `tapps_dead_code` on each package. Before deleting any flagged symbol, verify via `tapps_impact_analysis` that it has zero importers anywhere in the monorepo. Delete confirmed dead code and its associated tests.

See [Epic 93](../EPIC-93-full-code-review-and-fixes.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/*/src/**/*.py` (refactors and deletions)
- `packages/*/tests/**/*.py` (remove tests for deleted code)

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Run `radon cc packages/*/src/ -n C` and capture list of CC > 15 functions
- [ ] Refactor each CC > 15 function into smaller helpers
- [ ] Verify tests still pass after each refactor
- [ ] Run `tapps_dead_code` on each package
- [ ] For each dead-code candidate, confirm zero importers via `tapps_impact_analysis`
- [ ] Delete confirmed dead code and its tests
- [ ] Re-run radon and verify no function exceeds CC 15

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Zero functions with cyclomatic complexity > 15
- [ ] Every deletion verified to have zero dependents
- [ ] All tests still pass after refactors and deletions
- [ ] No behavioral changes introduced

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
