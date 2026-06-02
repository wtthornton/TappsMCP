# Handoff: Ralph-harness changes for the audit → fix loop

**For review by:** the Ralph harness project (`ralph-claude-code`)
**Source epic (tapps-mcp side):** TAP-2716 — *Audit campaign: bridge findings to Ralph-implementable fix stories*
**Status:** proposal — not yet filed in the Ralph project's own tracker

## Why this doc exists

The work to bridge `tapps_audit_campaign` findings into Ralph-implementable fix
stories is split across two projects. The **producer side** lives in tapps-mcp
and is tracked under epic **TAP-2716** (stories TAP-2717 … TAP-2722): tapps-mcp
emits the labels, generates the fix stories, and provides the coverage-close
tool.

The **consumer side** below is Ralph-harness behavior. Per
`.claude/rules/agent-scope.md`, a tapps-mcp agent must not file issues into a
different project, so these are documented here for the Ralph project to pick up
in its own tracker rather than created as cross-project Linear issues.

The producer side is independently valuable and testable without these changes;
these close the loop end to end.

## Consumer-side changes Ralph needs

### 1. Honor selection labels in linear-mode issue selection

tapps-mcp will emit (TAP-2719):

- `audit-fix` on single-implementable fix stories → **pickable**.
- `not-implementable` (and the existing `audit-digest`) on P2/P3 bundle issues
  → **must be skipped**, because a digest packs many findings and is not a
  single coherent task.

Ralph's linear-mode next-issue selection must:

- Prefer / allow issues labeled `audit-fix` in Backlog/Todo.
- Exclude issues labeled `not-implementable` or `audit-digest` from automatic
  pickup.
- Continue to exclude `audit-readonly` audit-session tickets from the fix loop
  (already handled — those are read-only audit work, R1-exempt).

Where this lives in the Ralph harness: the linear-mode issue-selection step
driven from the consuming project's `.ralph/PROMPT.md` and the
`ralph-workflow` skill's audit-task protocol. Update both so the label filter is
explicit.

**Acceptance (Ralph side):**

- A `not-implementable` / `audit-digest` issue is never auto-selected by the
  loop.
- An `audit-fix` issue in Backlog/Todo is selectable like any other story.

### 2. Invoke coverage-close at fix-story completion

tapps-mcp will provide a coverage-close mechanism (TAP-2722) that records the
new commit SHA on `audit:coverage:{rel_path}` (as `fix_sha`) and links
finding-ticket → fix-ticket → coverage. It deliberately does NOT update
`audited_sha` — a fix is not an audit (TAP-2799) — so `is_fresh()` returns
`False` at the post-fix SHA and a re-audit re-examines the fixed file
(re-audit-as-changed).

Ralph must call this when it completes a fix story carrying the `audit-fix`
label, after the commit lands, passing the fixed file path(s), the new SHA, and
the fix-ticket id.

**Acceptance (Ralph side):**

- On completing an `audit-fix` story, Ralph invokes coverage-close for each
  changed file.
- A subsequent campaign treats those files as changed (not stale-clean).

## Interface contract (producer ↔ consumer)

| Concern | tapps-mcp produces | Ralph consumes |
|---|---|---|
| Pickable fix story | issue with `audit-fix` label, Backlog status, `agent_ready=true` body | select & implement |
| Non-pickable bundle | issue with `not-implementable` / `audit-digest` label | skip |
| Loop closure | coverage-close tool (updates SHA, links tickets) | call at fix completion |

## References

- tapps-mcp epic: TAP-2716 (TAP-2717 … TAP-2722)
- Audit campaign feature: TAP-2036
- Scope rule: `.claude/rules/agent-scope.md` (no cross-project writes)
