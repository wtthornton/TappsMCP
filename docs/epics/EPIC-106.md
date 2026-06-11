# Epic 106: Narrative code scoring for document repos

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** Medium
**Estimated LOE:** S

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that layout-only narrative modules (e.g. reports/**/story.py) are not falsely failed by test_coverage weight when no per-module unit tests exist.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Add a report_authoring quality preset or path-based scoring overrides that reduce or zero test_coverage weight for narrative/layout directories.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Large reports/*/story.py files fail or depress gate on test-coverage heuristic (0 score when no test_{stem}.py), pulling overall below 70 and training agents to ignore the gate.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] - [ ] quality_preset report_authoring (or equivalent path override) is configurable in .tapps-mcp.yaml
- [ ] reports/** or consumer-configured globs reduce or zero test_coverage category weight
- [ ] reports/foo/story.py with no dedicated unit test can pass standard overall gate when other categories pass
- [ ] Existing standard/strict/framework presets unchanged for non-narrative paths

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 106.1 -- settings.py: report_authoring preset and path overrides

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement settings.py: report_authoring preset and path overrides
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** settings.py: report_authoring preset and path overrides is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **Narrative code scoring for document repos**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- - Do not remove test_coverage category globally
- Do not exempt all Python under reports/ from security or complexity scoring

<!-- docsmcp:end:non-goals -->
