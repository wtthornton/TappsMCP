# Epic 106: Release-update automation: post project update on every version bump

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~2-3 weeks (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that every project using TappsMCP automatically produces a consistent, well-formatted Linear project update on each release — giving stakeholders a single, reliable place to track what shipped, which issues closed, and whether the release is on-track — without requiring the agent or developer to manually compose or remember to post updates.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Ship a full release-update pipeline: a docs-mcp template generator and validator, a tapps-mcp MCP tool and CLI wrapper, and a deployable skill — so any project using TappsMCP can post a structured Linear project update on every patch/minor/major release with one agent call.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Release communication today is ad-hoc and inconsistent: some releases get a Linear comment, most get nothing. A standardised pipeline removes the manual step, ensures every version bump is visible to stakeholders in Linear, and makes the cadence auditable.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Every patch/minor/major release creates a Linear project update via tapps_release_update
- [ ] Template is consistent across all projects using TappsMCP (shipped via tapps_init/tapps_upgrade)
- [ ] Template body sources from CHANGELOG.md when present with git-log fallback
- [ ] TAP-### references are auto-scraped from commit messages and listed in Issues Closed
- [ ] docs_generate_release_update + docs_validate_release_update enforce template compliance before any write
- [ ] linear-release-update skill is included in tapps_init bootstrap set
- [ ] All new code passes mypy strict + ruff + 80% test coverage
- [ ] Linear plugin write path (projectUpdate vs save_document) is confirmed by a spike story before downstream work begins

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 106.1 -- Spike: confirm Linear plugin project-update write path

**Points:** 2

Determine whether the Linear plugin supports projectUpdate mutations natively; if not, choose between save_document and save_comment. Output: a one-paragraph ADR comment on this epic.

#### Acceptance Criteria

- [ ] AC 1: see linked story file
- [ ] AC 2: see linked story file
- [ ] AC 3: see linked story file

**Tasks:**
- [ ] Implement spike: confirm linear plugin project-update write path
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Spike: confirm Linear plugin project-update write path is implemented, tests pass, and documentation is updated.

---

### 106.2 -- docs-mcp: docs_generate_release_update + docs_validate_release_update

**Points:** 5

New generator and validator in docs-mcp following the existing docs_generate_story pattern. Template sections: version header, health, highlights, issues closed, breaking changes (minor/major only), links.

#### Acceptance Criteria

- [ ] AC 1: see linked story file
- [ ] AC 2: see linked story file
- [ ] AC 3: see linked story file
- [ ] AC 4: see linked story file
- [ ] AC 5: see linked story file

**Tasks:**
- [ ] Implement docs-mcp: docs_generate_release_update + docs_validate_release_update
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs-mcp: docs_generate_release_update + docs_validate_release_update is implemented, tests pass, and documentation is updated.

---

### 106.3 -- tapps-mcp: tapps_release_update MCP tool + CLI wrapper

**Points:** 5

New MCP tool that orchestrates: parse version/prev_version/bump_type, source body from CHANGELOG or git log, call docs_generate_release_update, call docs_validate_release_update, post via Linear plugin, invalidate cache.

#### Acceptance Criteria

- [ ] AC 1: see linked story file
- [ ] AC 2: see linked story file
- [ ] AC 3: see linked story file
- [ ] AC 4: see linked story file
- [ ] AC 5: see linked story file

**Tasks:**
- [ ] Implement tapps-mcp: tapps_release_update mcp tool + cli wrapper
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** tapps-mcp: tapps_release_update MCP tool + CLI wrapper is implemented, tests pass, and documentation is updated.

---

### 106.4 -- linear-release-update skill + tapps_init/tapps_upgrade deployment

**Points:** 3

Ship the linear-release-update skill and include it in the tapps_init bootstrap set and tapps_upgrade generated files.

#### Acceptance Criteria

- [ ] AC 1: see linked story file
- [ ] AC 2: see linked story file
- [ ] AC 3: see linked story file

**Tasks:**
- [ ] Implement linear-release-update skill + tapps_init/tapps_upgrade deployment
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** linear-release-update skill + tapps_init/tapps_upgrade deployment is implemented, tests pass, and documentation is updated.

---

### 106.5 -- linear-standards.md rule update + docs

**Points:** 2

Add release-update flow section to linear-standards.md, update AGENTS.md and README.md tool list, add per-project override docs in .tapps-mcp.yaml schema (release_update_overrides).

#### Acceptance Criteria

- [ ] AC 1: see linked story file
- [ ] AC 2: see linked story file
- [ ] AC 3: see linked story file

**Tasks:**
- [ ] Implement linear-standards.md rule update + docs
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** linear-standards.md rule update + docs is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Spike (story 1) gates all downstream work — do not start stories 2-5 until write path is confirmed
- Template body priority: CHANGELOG.md section for version → conventional-commit groups from git log → TAP-### references from commit messages
- Project identity for Linear writes comes from .tapps-mcp.yaml team/project config (same as existing linear cache tools)
- Per-project customization via release_update_overrides block in .tapps-mcp.yaml (extra sections footer custom links)
- All tapps-mcp MCP tools must call _record_call at top of handler and be registered in checklist task map

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Auto-firing on every commit — trigger is explicit agent call or CI invocation only
- Replacing GitHub release notes — the update links to them
- Per-project template divergence beyond the override block

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 8 acceptance criteria met | 0/8 | 8/8 | Checklist review |
| All 5 stories completed | 0/5 | 5/5 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 106.1: Spike: confirm Linear plugin project-update write path
2. Story 106.2: docs-mcp: docs_generate_release_update + docs_validate_release_update
3. Story 106.3: tapps-mcp: tapps_release_update MCP tool + CLI wrapper
4. Story 106.4: linear-release-update skill + tapps_init/tapps_upgrade deployment
5. Story 106.5: linear-standards.md rule update + docs

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Linear plugin may not expose projectUpdate mutations — spike resolves this; fallback is save_document | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Three packages touched (docs-mcp + tapps-mcp + skill deploy) — coordinate releases carefully | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| Files will be determined during story refinement | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Acceptance criteria pass rate | 0% | 100% | CI pipeline |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
