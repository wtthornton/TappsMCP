# Story 91.2 -- Quick-Start Mode

<!-- docsmcp:start:user-story -->

> **As a** developer who wants a fast first draft, **I want** to generate a complete epic document from just a title, **so that** I can bootstrap planning without filling in 15+ parameters upfront.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the "Speed for One-offs" score rises from 5/10 to 8/10. A single `docs_generate_epic(title="User Auth System", quick_start=True)` call should produce a complete, well-structured epic with inferred defaults.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Add a `quick_start: bool = False` parameter to `docs_generate_epic`. When True:

1. **Goal** -- inferred from title: "Implement {title} with full test coverage and documentation."
2. **Motivation** -- generic but title-aware: "This epic addresses the need for {title} in the project."
3. **Stories** -- generate 3 default stubs:
   - `{N}.1 -- Foundation & Setup` (points: 2)
   - `{N}.2 -- Core Implementation` (points: 5)
   - `{N}.3 -- Testing & Documentation` (points: 3)
4. **Acceptance criteria** -- 3 defaults: "Core functionality implemented", "Unit tests passing with >= 80% coverage", "Documentation updated"
5. **Priority** -- default "P2 - Medium"
6. **Status** -- "Proposed"
7. **Style** -- auto-detect (delegates to 91.3 if available, otherwise "standard")

Explicit parameters always override quick-start defaults.

See [Epic 91](../EPIC-91-epic-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/epics.py`
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py`
- `packages/docs-mcp/tests/unit/test_epics.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Add `quick_start` bool parameter to `docs_generate_epic` in `server_gen_tools.py`
- [ ] Implement `_infer_defaults(config)` on `EpicGenerator` that fills empty fields
- [ ] Generate 3 default story stubs with title-derived names
- [ ] Set default AC from title
- [ ] Ensure explicit params override quick-start defaults (test: pass goal + quick_start=True)
- [ ] Add unit tests: quick_start with just title, quick_start with partial overrides

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `docs_generate_epic(title="Auth System", quick_start=True)` produces a complete epic with goal, motivation, 3 stories, and AC
- [ ] Explicit parameters override quick-start defaults
- [ ] `quick_start=False` (default) behavior is unchanged
- [ ] Generated stories have title-derived names, not "Story Title"

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] All 145+ existing epic tests still pass
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
