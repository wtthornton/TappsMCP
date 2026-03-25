# Story 92.1 -- Port Performance Fixes to Story Generator

<!-- docsmcp:start:user-story -->

> **As a** developer using docs_generate_story with auto_populate, **I want** the story generator to complete within 15 seconds on large projects, **so that** the tool doesn't hang or time out.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the story generator matches the epic generator's performance characteristics after commit 31237f1. The story generator currently has the same three bottlenecks: unbounded module map depth, sequential expert consultations, and no wall-clock budget.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Apply the identical three performance fixes from the epic generator:

1. **Cap module map depth**: `analyzer.analyze(project_root, depth=3)` in `_enrich_module_map`
2. **Parallel expert consultations**: Wrap the 4-domain loop in `ThreadPoolExecutor(max_workers=4)` with `as_completed`
3. **Wall-clock budget**: Add `_AUTO_POPULATE_TIMEOUT_S = 15.0` ClassVar, check remaining budget before each enrichment step, skip and log when exceeded

The story generator has 4 expert domains (vs epic's 8), so parallelization gives ~4x speedup on that step.

See [Epic 92](../EPIC-92-story-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/stories.py`
- `packages/docs-mcp/tests/unit/test_stories.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Change `analyzer.analyze(project_root)` to `analyzer.analyze(project_root, depth=3)` in `_enrich_module_map`
- [ ] Refactor `_enrich_experts` sequential loop into `ThreadPoolExecutor(max_workers=4)` with `as_completed`
- [ ] Add `_AUTO_POPULATE_TIMEOUT_S: ClassVar[float] = 15.0` to `StoryGenerator`
- [ ] Refactor `_auto_populate` to check `_remaining()` budget before each step
- [ ] Log `story_auto_populate_budget_exceeded` with `skipped=` key when budget hit
- [ ] Add unit test: `_auto_populate` returns partial enrichment on timeout
- [ ] Add unit test: experts run in parallel (mock to verify concurrent execution)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `_enrich_module_map` uses `depth=3`
- [ ] `_enrich_experts` runs all 4 domains concurrently via thread pool
- [ ] `_auto_populate` completes within 15s even if individual steps are slow
- [ ] Partial enrichment returned when budget exceeded (not empty dict)

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] All existing story tests still pass
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
