# Story 92.5 -- Improved Gherkin Scaffolding

<!-- docsmcp:start:user-story -->

> **As a** developer using Gherkin-format acceptance criteria, **I want** the Given/When/Then scaffolding to be derived from my AC text and role, **so that** I get meaningful scenario outlines instead of "[describe the precondition]" placeholders.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the Gherkin output quality rises from 3/10 to 7/10. Currently `_render_gherkin_criteria` produces bracket placeholders for Given/When/Then regardless of input. With role, want, and AC text available, much better scaffolding is possible.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Upgrade `_render_gherkin_criteria` to use available story context:

**Current output:**
```gherkin
Scenario: Login validates credentials
  Given [describe the precondition]
  When [describe the action that triggers: login validates credentials]
  Then [describe the expected observable outcome]
```

**Improved output:**
```gherkin
Scenario: Login validates credentials
  Given a developer has navigated to the login form
  When the developer submits login credentials
  Then login validates credentials successfully
```

Logic:
- **Given**: "a {role} has {precondition from AC context}" -- extract setup/state keywords from AC text
- **When**: "the {role} {action}" -- use `want` field or extract verb phrase from AC
- **Then**: "{AC text} successfully" or "the expected outcome is observed"

Fall back to current bracket placeholders when role/want/AC are too ambiguous to parse.

See [Epic 92](../EPIC-92-story-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/stories.py`
- `packages/docs-mcp/tests/unit/test_stories.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Implement `_derive_given(role, ac_text) -> str` using role and context keywords
- [ ] Implement `_derive_when(role, want, ac_text) -> str` using want field or AC verb
- [ ] Implement `_derive_then(ac_text, so_that) -> str` from AC text or so_that
- [ ] Update `_render_gherkin_criteria` to call derivation methods
- [ ] Fall back to bracket placeholders when derivation produces empty strings
- [ ] Add unit tests: role+want+AC produces meaningful Gherkin
- [ ] Add unit test: missing role falls back to bracket placeholders
- [ ] Add unit test: AC with verb phrase extracts When correctly

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Gherkin Given clause uses role when provided
- [ ] Gherkin When clause uses want field or AC verb phrase
- [ ] Gherkin Then clause reflects AC text
- [ ] Missing context falls back to bracket placeholders (no empty lines)

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
