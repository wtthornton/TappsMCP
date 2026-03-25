# Story 92.3 -- Quick-Start Story Mode

<!-- docsmcp:start:user-story -->

> **As a** developer rapidly expanding epic stubs into stories, **I want** to generate a complete story from just a title and epic number, **so that** I can batch-create stories without filling in every field manually.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that creating 5-8 stories for an epic is fast. A single `docs_generate_story(title="Add login validation", epic_number=91, quick_start=True)` call should produce a complete story.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Add `quick_start: bool = False` to `docs_generate_story`. When True:

1. **Role** -- infer "developer" (default)
2. **Want** -- derive from title: "to {title.lower()}"
3. **So that** -- "the feature is delivered and tested"
4. **Points** -- default 3
5. **Size** -- default "M"
6. **Tasks** -- 3 defaults: "Implement {title.lower()}", "Write unit tests", "Update documentation"
7. **AC** -- 3 defaults: "{title} works as specified", "Unit tests pass", "Docs updated"

Explicit parameters override quick-start defaults.

See [Epic 92](../EPIC-92-story-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/stories.py`
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py`
- `packages/docs-mcp/tests/unit/test_stories.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Add `quick_start` bool parameter to `docs_generate_story` in `server_gen_tools.py`
- [ ] Implement `_infer_story_defaults(config)` on `StoryGenerator`
- [ ] Auto-generate role/want/so_that from title
- [ ] Auto-set points=3, size="M" when not provided
- [ ] Generate default tasks and AC from title
- [ ] Ensure explicit params override quick-start defaults
- [ ] Add unit tests: quick_start with just title, quick_start with overrides

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `docs_generate_story(title="Login Validation", epic_number=91, quick_start=True)` produces complete story
- [ ] Generated story has title-derived want, tasks, and AC
- [ ] Explicit role/want override quick-start defaults
- [ ] `quick_start=False` (default) behavior unchanged

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
