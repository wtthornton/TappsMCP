# Agent-facing Linear issues — conventions

Durable policy for how Linear issues are written, labeled, and nested in the
`TappsCodingAgents / TappsMCP Platform` project. Agents read issues via the
Linear MCP plugin and act on them — every convention here exists to reduce
token spend or eliminate an agent failure mode observed in the 50-issue audit
(2026-04-22).

Tools that enforce this policy:
- `docs_lint_linear_issue` — read-only lint of an existing issue.
- `docs_validate_linear_issue` — `{agent_ready, missing, score}`.
- `docs_generate_linear_issue` (skill, possibly promoted to tool) — emits the template.
- `tapps_linear_triage` — batch label/parent proposals across a project.

## Template (locked)

```markdown
## What
<one sentence: file + symptom, or file + change>

## Where
`path/to/file.py:LINE-RANGE` (plus any sibling files)

## Why (optional, ≤2 lines)
<only if non-obvious; skip for self-evident bugs>

## Acceptance
- [ ] <verifiable fact 1 — e.g., `mypy --strict` clean>
- [ ] <verifiable fact 2 — e.g., `test_X` passes>
- [ ] <verifiable fact 3 — e.g., `tapps_quick_check` reports no new findings>

## Refs
TAP-### (prior work), commit <sha>
```

### Rules

- **Title ≤ 80 chars.** Pattern: `file.py: symptom` for bugs, `file.py: change` for features. Drop em-dash preambles.
- **No fenced code blocks** unless the bug IS the exact text (regex, specific error string). A `file.py:LINE` anchor beats a reprinted snippet.
- **Inline-code filenames**: `` `AGENTS.md` `` — never `[AGENTS.md](AGENTS.md)`. Linear's autolinker mangles bare filenames into `<http://AGENTS.md>` garbage.
- **Bare issue refs**: `TAP-###`. Never wrap in `<issue id="UUID">…</issue>` — the UUID is pure noise.
- **Acceptance is mandatory.** Every issue needs ≥1 verifiable checkbox. If you can't write one, the issue isn't agent-ready — label `needs-clarification`.
- **Estimates required** on all stories. Agents use estimate as a "fits-one-session" budget signal.

## Labels (locked)

Exactly one agent-readiness label per issue:

| Label | Meaning | Criteria |
|---|---|---|
| `agent-ready` | An agent can start without human input | Template-compliant + file anchor + ≥1 verifiable AC + title ≤80 + no autolink/UUID noise |
| `needs-clarification` | Valid ask, template elements missing | Missing AC, vague scope, or refs external context an agent can't fetch |
| `agent-blocked` | Human/policy decision required | Waiting on design call, approval, or another issue |

Hierarchy-type labels (mutually exclusive with the above — can coexist):

| Label | Meaning |
|---|---|
| `epic` | Parent issue with no `parent_id` |
| `story` | Child of an epic; one deliverable, one PR |
| `task` | Child of a story; only when AC >5 items or parallel work |

Existing functional labels (`Bug`, `backend`, `brain-api`, etc.) stay and are orthogonal.

## Hierarchy

Default to **2 levels**: epic → story. Add a 3rd level (sub-story / task) only when:
- Story AC list has >5 checkboxes that split cleanly, OR
- Two agents could work in parallel on separable parts.

Three-level nesting requires justification in the epic's description. Most issues are correctly flat — the audit showed over-nesting is as harmful as under-nesting.

## Anti-patterns (from the audit)

Concrete things the linter flags:

1. `[AGENTS.md](<http://AGENTS.md>)` — broken autolinker output. Replace with `` `AGENTS.md` ``.
2. `<issue id="<UUID>">TAP-###</issue>` — replace with bare `TAP-###`.
3. Titles >80 chars — restate the symptom as the title, not a preamble.
4. Fenced code block with no `file.py:LINE` anchor — add the anchor; drop the snippet unless it's load-bearing.
5. No `## Acceptance` section — either write one or apply `needs-clarification`.
6. Mixed templates (`Goal/Context` + `Summary/Problem/Evidence` + `File-first`) — migrate to the template above.

## References

- Audit of 50 existing issues: see `docs/epics/EPIC-103-linear-issue-quality-tooling.md` (commit history)
- Agent-scope write rules: `.claude/rules/agent-scope.md`
