# Story 92.2 -- Context-Aware Story Placeholders

<!-- docsmcp:start:user-story -->

> **As a** developer generating user stories, **I want** placeholder text that reflects my story's title and role, **so that** the generated document reads as a meaningful draft instead of generic "Describe what this story delivers..." text.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that story prose quality rises from 3/10 to 7/10 by making every placeholder section context-specific.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Replace generic placeholders in `StoryGenerator` render methods with context-interpolated text:

- `_render_description`: "Describe how **{title}** will enable **{role}** to **{want}**..." (when role/want provided)
- `_render_tasks`: "- [ ] Implement {title.lower()}" instead of "- [ ] Define implementation tasks..."
- `_render_checkbox_criteria`: "- [ ] {title} works as specified" instead of "- [ ] Feature works as specified"
- `_render_definition_of_done`: "- [ ] {title} code reviewed and approved"

Fall back to current generic text when title is empty/whitespace.

See [Epic 92](../EPIC-92-story-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/stories.py`
- `packages/docs-mcp/tests/unit/test_stories.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Refactor `_render_description` to interpolate title/role/want into placeholder
- [ ] Refactor `_render_tasks` default tasks to use title
- [ ] Refactor `_render_checkbox_criteria` default items to use title
- [ ] Refactor `_render_definition_of_done` items to use title
- [ ] Add empty-title fallback guard for all modified methods
- [ ] Add unit tests for context-aware and fallback paths

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Description placeholder includes story title when non-empty
- [ ] Task placeholder uses title instead of generic "Define implementation tasks"
- [ ] AC placeholder uses title instead of generic "Feature works as specified"
- [ ] Empty title falls back to existing generic text (backward compat)

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
