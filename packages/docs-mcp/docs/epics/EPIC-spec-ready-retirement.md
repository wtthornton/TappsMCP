# Retire spec-ready label: complete the move to status-only readiness gating

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P3 - Low
**Estimated LOE:** ~1 day (single agent)
**Dependencies:** commit ecb850b (Path A: needs-spec/in-review retirement)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that issue readiness is expressed by exactly one signal — Linear status — instead of the dual-tracking that exists today (status AND a `spec-ready` label). The TappsCodingAgents workspace already migrated `needs-spec` and `in-review` from labels into Triage and In Review statuses; this epic finishes the migration by retiring the last readiness label.</purpose_and_intent>
<parameter name="goal">Retire the `spec-ready` label from the TappsCodingAgents workspace and remove all references to it from the deterministic tools (linter, validator, triage), deployed templates (linear_sdlc renderer), and policy docs. After this epic, any issue in Backlog is by definition agent-ready; agents read status only.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Describe how **Retire spec-ready label: complete the move to status-only readiness gating** will change the system. What measurable outcome proves this epic is complete?

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The recent workflow migration (Triage status replaces `needs-spec`, In Review status replaces `in-review`) demonstrated that status carries readiness more reliably than labels — labels drift, statuses do not because they gate UI columns. The remaining `spec-ready` label is now redundant: an issue in Backlog without `spec-ready` is just "labeled inconsistently", not "different from one with the label". Retiring it reduces cognitive load for both agents and humans, and lets us delete a class of "did the labeler forget?" bugs.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] All Backlog issues currently labeled spec-ready are reviewed and either left in Backlog or moved to Triage; the spec-ready label is deleted from the TappsCodingAgents workspace; LABEL_SPEC_READY constant is removed from packages/docs-mcp/src/docs_mcp/linters/linear_issue.py:32; suggested_label field returns the empty string in all cases (suggested_status becomes the sole readiness output); test_linear_issue_linter
- [ ] test_linear_issue_validator
- [ ] test_linear_issue_triage updated to assert empty suggested_label; packages/tapps-mcp/src/tapps_mcp/pipeline/linear_sdlc/renderer.py drops the spec-ready row from the labels table; docs/linear/AGENT_ISSUES.md describes status-only gating with no readiness labels; tapps_validate_changed and the docs-mcp test suite pass; tapps-brain memory entry created documenting the new convention

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 0.1 -- Audit current spec-ready usage and decide per-issue keep-or-triage

**Points:** 2

List every Backlog issue carrying spec-ready. For each, decide whether the issue is truly agent-ready (stays in Backlog) or has drift (moves to Triage). Output a CSV with id, current state, decision, reason.

**Tasks:**
- [ ] Implement audit current spec-ready usage and decide per-issue keep-or-triage
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Audit current spec-ready usage and decide per-issue keep-or-triage is implemented, tests pass, and documentation is updated.

---

### 0.2 -- Migrate spec-ready issues per audit decision and strip the label

**Points:** 2

Apply the migration decisions from story 1: move drift issues to Triage; strip the spec-ready label from every issue regardless of decision so the label can be deleted. Invalidate the Linear snapshot cache.

**Tasks:**
- [ ] Implement migrate spec-ready issues per audit decision and strip the label
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Migrate spec-ready issues per audit decision and strip the label is implemented, tests pass, and documentation is updated.

---

### 0.3 -- Delete spec-ready label in Linear UI

**Points:** 1

Manual workspace-admin action: Settings then Labels then delete spec-ready. No MCP tool exposes label deletion.

**Tasks:**
- [ ] Implement delete spec-ready label in linear ui
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Delete spec-ready label in Linear UI is implemented, tests pass, and documentation is updated.

---

### 0.4 -- Remove LABEL_SPEC_READY constant and suggested_label content from linter/validator/triage

**Points:** 3

Drop the LABEL_SPEC_READY constant, simplify _suggest_label to always return empty string, drop spec-ready from _AGENT_LABELS, update _build_label_proposals to no-op for label changes (callers use suggested_status), update tests.

**Tasks:**
- [ ] Implement remove label_spec_ready constant and suggested_label content from linter/validator/triage
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Remove LABEL_SPEC_READY constant and suggested_label content from linter/validator/triage is implemented, tests pass, and documentation is updated.

---

### 0.5 -- Update linear_sdlc renderer plus AGENT_ISSUES.md to status-only gating

**Points:** 2

Drop the spec-ready row from the labels table in linear_sdlc/renderer.py; rewrite AGENT_ISSUES.md so the status table is the only readiness signal; drop any remaining text suggesting spec-ready as the agent-ready stamp.

**Tasks:**
- [ ] Implement update linear_sdlc renderer plus agent_issues.md to status-only gating
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Update linear_sdlc renderer plus AGENT_ISSUES.md to status-only gating is implemented, tests pass, and documentation is updated.

---

### 0.6 -- Save tapps-brain memory entry documenting the convention

**Points:** 1

Create an architectural-tier memory entry titled Linear status is the only readiness signal explaining the convention so future agents inherit it without rediscovering.

**Tasks:**
- [ ] Implement save tapps-brain memory entry documenting the convention
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Save tapps-brain memory entry documenting the convention is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **Retire spec-ready label: complete the move to status-only readiness gating**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Re-architecting Linear project workflow; touching other workspaces label sets; adding new statuses beyond Triage and In Review

<!-- docsmcp:end:non-goals -->
