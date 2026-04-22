# EPIC-103: Linear issue quality tooling

**Status**: In progress
**Owner**: Bill Thornton
**Started**: 2026-04-22

## Outcome

Agents can read, write, validate, and triage Linear issues in the
`TappsCodingAgents / TappsMCP Platform` project at **40–60% lower token cost per
issue** while producing **template-compliant, self-triageable** issues by
default. The existing 50-issue backlog gets audited and labeled for
agent-readiness without hand-editing each one.

Evidence base: 2026-04-22 audit of 50 existing issues (see conversation history
and `docs/linear/AGENT_ISSUES.md`).

## Scope

Four tools + one skill + one policy doc, all reusing existing patterns in
tapps-mcp and docs-mcp. No new package. Read/write to Linear goes through the
installed Linear MCP plugin.

Policy lives in [docs/linear/AGENT_ISSUES.md](../linear/AGENT_ISSUES.md)
(template, labels, hierarchy). **Locked 2026-04-22.**

## Stories

| ID | Title | Type | Home | Est |
|---|---|---|---|---|
| STORY-103.1 | Lock agent-issue template + labels + hierarchy | policy | `docs/linear/` | Done |
| STORY-103.2 | Generator skill — expand template from structured inputs | skill | `.claude/skills/` | XS |
| STORY-103.3 | `docs_lint_linear_issue` — read-only lint of one issue | tool | docs-mcp | M |
| STORY-103.4 | `docs_validate_linear_issue` — `{agent_ready, missing, score}` | tool | docs-mcp | S |
| STORY-103.5 | `tapps_linear_triage` — batch label + parent proposals | tool | tapps-mcp | L |
| STORY-103.6 | Deep review — `docs_generate_epic` / `docs_generate_story` | review | docs-mcp | M |

Stories 103.5 and 103.6 may warrant sub-stories (`STORY-103.5.1`, etc.) when
scoped in detail; decision deferred to story-start time per the 2-level
hierarchy default.

## Execution order (locked)

Critical path to MVP: 103.1 → 103.2 → 103.3.
Full path: add 103.4 → 103.5 → 103.6 in that order.

| # | Story | Why this position | Rough effort |
|---|---|---|---|
| 1 | 103.1 | Unblocks all code work. **Done.** | Done |
| 2 | 103.2 | Zero-risk freebie after template locked — stops new bad issues today | 30 min |
| 3 | 103.3 | Highest immediate value: audits existing 50 issues, read-only | 3–4 h |
| 4 | 103.4 | Completes the lint → validate → generate triad; small; mostly reuses `docs_validate_epic` | 2–3 h |
| 5 | 103.5 | Batch operation — wants stability from 103.3/103.4 first | 4–6 h |
| 6 | 103.6 | Last so we critique generators against real-world feedback from 103.3–5; folds in `EPIC-91` / `EPIC-92` findings | 2–3 h |

Total to MVP (#1–#3): one working day.
Total to full epic close: ~3–4 working days.

## Drafting strategy

Per 2026-04-22 decision: **draft all new issues LOCAL** (markdown under
`docs/stories/STORY-103.N-*.md`) until 103.3 + 103.4 exist. Once those ship,
migrate drafts to Linear using the validator as the pre-create gate.
Linear MCP is used read-only for the existing 50 issues during 103.3 audit.

## Acceptance

- [ ] 103.1 artifact `docs/linear/AGENT_ISSUES.md` committed (done)
- [ ] 103.2 skill at `.claude/skills/linear-issue/` — produces template-compliant markdown on invocation
- [ ] 103.3 `docs_lint_linear_issue` reports all 6 anti-patterns from the policy doc on a known-bad fixture
- [ ] 103.4 `docs_validate_linear_issue` returns `agent_ready=true` for a compliant issue, `false` with specific `missing[]` otherwise
- [ ] 103.5 `tapps_linear_triage` proposes labels + parent groupings for the current 50-issue backlog; writes gated on explicit confirmation
- [ ] 103.6 review doc committed with specific diffs for `docs_generate_epic` / `docs_generate_story` (merging with EPIC-91 / EPIC-92 scope)
- [ ] All 50 existing issues either labeled `agent-ready`, `needs-clarification`, or `agent-blocked` (bulk via 103.5)

## Risks / open questions

- **Linear MCP rate limits / pagination** on 103.5 batch scan — untested. Mitigation: chunk by 25, cache locally.
- **Label creation**: `agent-ready` / `needs-clarification` / `agent-blocked` may need to be created in Linear before 103.5 can apply them. One-time bootstrap as part of 103.5 kickoff.
- **Overlap with EPIC-91/EPIC-92** (generator quality gaps): 103.6 scope will be adjusted to avoid duplication — decide at story-start.

## References

- Policy: [docs/linear/AGENT_ISSUES.md](../linear/AGENT_ISSUES.md)
- Related epics: [EPIC-91](EPIC-91-epic-generator-quality-gaps.md), [EPIC-92](EPIC-92-story-generator-quality-gaps.md)
- Agent-scope write rules: [.claude/rules/agent-scope.md](../../.claude/rules/agent-scope.md)
