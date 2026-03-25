# Story 91.1 -- Context-Aware Placeholder Prose

<!-- docsmcp:start:user-story -->

> **As a** developer using docs_generate_epic, **I want** placeholder text that reflects my epic's title and goal, **so that** the generated document reads as a meaningful draft rather than a template with generic fill-in-the-blank prompts.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that every placeholder section in a generated epic uses the title, goal, and detected tech stack to produce specific, actionable hint text. This is the single highest-impact change for closing the prose quality gap (3/10 to 7/10).

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Currently, `_render_goal` emits "Describe the measurable outcome this epic achieves. What will be different when this work is complete?" regardless of what the user provided as a title. This should become: "Describe how **{title}** will change the system. What measurable outcome proves this epic is complete?"

Similarly for:
- `_render_motivation` -- "Explain why **{title}** matters. What pain point or opportunity does it address?"
- `_render_technical_notes` -- "Document architecture decisions for **{title}**. Key tech: **{tech_stack}**." (when auto_populate enrichment available)
- `_render_non_goals` -- "What is explicitly out of scope for **{title}**? Consider: {keyword-derived boundaries}"
- `_render_acceptance_criteria` -- "Define verifiable criteria for **{title}**..."

The interpolation must be safe (no format string injection) and gracefully degrade when fields are empty.

See [Epic 91](../EPIC-91-epic-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/epics.py`
- `packages/docs-mcp/tests/unit/test_epics.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Refactor `_render_goal` to interpolate `config.title` into placeholder text
- [ ] Refactor `_render_motivation` to reference title in prompt
- [ ] Refactor `_render_technical_notes` to include enrichment tech_stack in placeholder
- [ ] Update `_render_non_goals` to suggest boundaries from title keywords (e.g., "auth" title suggests "Multi-factor authentication" as a non-goal candidate)
- [ ] Update `_render_acceptance_criteria` placeholder to reference title
- [ ] Add guard for empty/whitespace title (fall back to current generic text)
- [ ] Add unit tests: one per section, verifying title appears in placeholder output
- [ ] Add unit test: empty title falls back to generic placeholder

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `_render_goal` placeholder includes the epic title when title is non-empty
- [ ] `_render_motivation` placeholder includes the epic title
- [ ] `_render_technical_notes` placeholder includes tech_stack when enrichment provides it
- [ ] `_render_non_goals` suggests at least one boundary derived from title keywords
- [ ] Empty title gracefully falls back to existing generic placeholder text

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] All 145+ existing epic tests still pass
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
