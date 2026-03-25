# Story 91.4 -- Story and Risk Suggestion Engine

<!-- docsmcp:start:user-story -->

> **As a** developer creating an epic with no pre-defined stories, **I want** the tool to suggest relevant story stubs and risks from my title and goal, **so that** I get a useful starting point instead of generic "Story Title" placeholders.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** L

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the "Creative Ideation" score rises from 2/10 to 6/10. The suggestion engine bridges the gap between DocsMCP's structural strength and the LLM's ability to brainstorm -- deterministically.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Create a keyword-to-pattern mapping that analyzes the epic title and goal to suggest relevant stories and risks.

### Story Suggestion Patterns

| Keywords in title/goal | Suggested stories |
|------------------------|-------------------|
| auth, login, user, account | Data models, Auth endpoints, Session management, Tests |
| api, endpoint, rest, graphql | Schema/models, Endpoint handlers, Validation, Client SDK, Tests |
| ui, frontend, page, form | Component scaffold, State management, Form validation, Styling, Tests |
| database, migration, schema | Schema design, Migration scripts, Query layer, Seed data, Tests |
| deploy, ci, pipeline, infra | Config setup, Build pipeline, Deploy scripts, Monitoring, Tests |
| security, audit, scan | Threat model, Scanner integration, Remediation, Policy docs, Tests |

Fallback when no keywords match: "Foundation & Setup", "Core Implementation", "Testing & Documentation".

### Risk Suggestion Patterns

| Keywords | Suggested risks |
|----------|----------------|
| auth, security | "Authentication bypass if token validation incomplete" |
| api, endpoint | "Breaking API changes affecting existing clients" |
| database, migration | "Data loss during migration if rollback path untested" |
| deploy, infra | "Deployment downtime if blue-green not configured" |
| performance, scale | "Performance degradation under load without benchmarks" |

See [Epic 91](../EPIC-91-epic-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/epics.py`
- `packages/docs-mcp/tests/unit/test_epics.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Define `_STORY_PATTERNS: ClassVar` keyword-to-stories mapping dict
- [ ] Define `_RISK_PATTERNS: ClassVar` keyword-to-risks mapping dict
- [ ] Implement `_suggest_stories(title, goal) -> list[EpicStoryStub]`
- [ ] Implement `_suggest_risks(title, goal) -> list[str]`
- [ ] Integrate into `_render_stories`: use suggestions when `config.stories` empty
- [ ] Integrate into `_render_risk_assessment`: use suggestions when `config.risks` empty
- [ ] Mark suggested stories with "(suggested)" suffix to distinguish from user-provided
- [ ] Add unit tests for each keyword pattern
- [ ] Add unit test for fallback when no keywords match

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Title "User Authentication" with empty stories produces auth-related story stubs
- [ ] Title "API Gateway" with empty stories produces API-related story stubs
- [ ] Title with no matching keywords falls back to generic 3-story pattern
- [ ] Comprehensive style with empty risks produces keyword-derived risk suggestions
- [ ] User-provided stories always override suggestions (no mixing)

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] All 145+ existing epic tests still pass
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
