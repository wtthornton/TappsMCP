# Story 92.4 -- Task Suggestion Engine

<!-- docsmcp:start:user-story -->

> **As a** developer creating a story with no pre-defined tasks, **I want** the tool to suggest relevant implementation tasks from my title and description, **so that** I get actionable work items instead of "Define implementation tasks..." placeholders.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** L

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the "Creative Ideation" gap for stories is addressed. Task brainstorming was scored 9/10 for LLM vs 2/10 for DocsMCP. A keyword-based suggestion engine can close this to ~6/10 deterministically.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Create `_suggest_tasks(config) -> list[StoryTask]` that maps title/description keywords to common implementation tasks:

| Keywords | Suggested tasks |
|----------|----------------|
| model, schema, database | "Define data model fields and relationships", "Write migration script", "Add model validation" |
| endpoint, api, route | "Define request/response schema", "Implement endpoint handler", "Add input validation", "Add error responses" |
| test, coverage | "Write unit tests for happy path", "Write edge case tests", "Add integration test" |
| ui, component, form | "Create component scaffold", "Add form validation", "Add styling/CSS", "Add accessibility attributes" |
| validate, validation | "Define validation rules", "Implement validation logic", "Add validation error messages" |
| auth, login, token | "Implement auth flow", "Add token generation/validation", "Add session management" |

When `config.files` is provided, associate file_path with relevant tasks.

Fallback: "Implement {title.lower()}", "Write unit tests", "Update documentation".

See [Epic 92](../EPIC-92-story-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/stories.py`
- `packages/docs-mcp/tests/unit/test_stories.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Define `_TASK_PATTERNS: ClassVar` keyword-to-tasks mapping
- [ ] Implement `_suggest_tasks(config) -> list[StoryTask]`
- [ ] Associate `file_path` from `config.files` when available
- [ ] Integrate into `_render_tasks` when `config.tasks` is empty
- [ ] Ensure user-provided tasks always override suggestions
- [ ] Add unit tests for each keyword pattern
- [ ] Add unit test for fallback when no keywords match
- [ ] Add unit test for file_path association

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Title "Add user login endpoint" with empty tasks produces API-related task suggestions
- [ ] Title "Database migration" with empty tasks produces schema-related suggestions
- [ ] No keyword match falls back to generic 3-task pattern
- [ ] User-provided tasks always override suggestions

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
