# Paste-ready prompt — wire the audit→fix loop into the Ralph harness

Open Claude Code **inside the `ralph-claude-code` repo** and paste the prompt below. It
implements the consumer side of the audit→fix loop whose producer side shipped in
tapps-mcp under epic **TAP-2716** (stories TAP-2717…TAP-2722).

## Context

The producer side is done and on tapps-mcp `master`:

- `tapps_finding_to_story` emits fix stories with `labels: ["audit-fix"]`, severity-derived
  `estimate` / `priority`, and Linear-snapshot dedup (`should_file` / `duplicate_of`).
- `tapps_audit_campaign(mode="fix_plan")` emits a companion fix epic + child fix stories.
- `close_coverage()` (in `tapps_mcp.tools.audit_manifest`) updates
  `audit:coverage:<rel_path>` with the new commit SHA and links finding→fix→coverage so a
  re-audit re-examines the fixed file.

Ralph (the consumer) does not yet honor the labels or call coverage-close. These two changes
close the loop. Full spec: `docs/handoff/RALPH-audit-fix-loop.md` in the tapps-mcp repo.

## The prompt (copy from here)

```text
Implement the consumer side of the tapps-mcp audit→fix loop in this (ralph-claude-code) repo.
The producer side already ships these signals; treat this request as standing authorization to
make the two changes below, run the test suite, and commit. Do NOT pause between steps.

CHANGE 1 — Label-aware linear-mode issue selection.
- Where: the linear-mode next-issue selection step driven from the consuming project's
  `.ralph/PROMPT.md` and the `ralph-workflow` skill's audit-task protocol. Update BOTH so the
  label filter is explicit.
- Behavior:
  - Issues labeled `audit-fix` in Backlog/Todo are selectable like any normal story.
  - Issues labeled `not-implementable` or `audit-digest` are NEVER auto-selected (a digest
    packs many findings and is not a single coherent task).
  - Continue excluding `audit-readonly` audit-session tickets from the fix loop (already
    handled — those are read-only audit work, R1-exempt).
- Acceptance:
  - A `not-implementable` / `audit-digest` issue is never auto-selected by the loop.
  - An `audit-fix` issue in Backlog/Todo is selectable like any other story.
  - Add a test that asserts the selection filter on a fixture issue list.

CHANGE 2 — Call coverage-close at fix-story completion.
- When Ralph completes a fix story carrying the `audit-fix` label, AFTER the commit lands, call
  the tapps-mcp coverage-close mechanism (TAP-2722) for each changed file, passing the fixed
  file path(s), the new commit SHA, and the fix-ticket id. This updates
  `audit:coverage:<rel_path>` so a subsequent campaign treats those files as changed
  (not stale-clean).
- Acceptance:
  - On completing an `audit-fix` story, Ralph invokes coverage-close for each changed file.
  - A subsequent campaign treats those files as changed.
  - Add a test covering the post-commit coverage-close call.

Then: run the repo's test suite, fix anything red, and commit per this repo's workflow.
Report the files changed, the test result, and any follow-ups.
```

## Interface contract (producer ↔ consumer)

| Concern | tapps-mcp produces | Ralph consumes |
|---|---|---|
| Pickable fix story | issue with `audit-fix` label, Backlog status, `agent_ready=true` body | select & implement |
| Non-pickable bundle | issue with `not-implementable` / `audit-digest` label | skip |
| Loop closure | coverage-close (updates SHA, links tickets) | call at fix completion |

## After implementing

File the two changes as issues in the **Ralph project's own tracker** (not tapps-mcp's — per
tapps-mcp `.claude/rules/agent-scope.md`, the producer repo cannot file cross-project issues).
The proposal lives in `docs/handoff/RALPH-audit-fix-loop.md`.
