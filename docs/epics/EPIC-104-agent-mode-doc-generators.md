# EPIC-104: Agent-mode for doc generators

**Status**: In progress (104.2 + 104.3 shipped 2026-04-22; 104.1 + 104.4 deferred)
**Owner**: Bill Thornton
**Created**: 2026-04-22
**Parent review**: [docs/reviews/EPIC-103-REVIEW-generators.md](../reviews/EPIC-103-REVIEW-generators.md)

## Outcome

Close the two generator/validator drift bugs found during the
[EPIC-103 review](../reviews/EPIC-103-REVIEW-generators.md), and (optionally)
teach `docs_generate_story` to emit the locked 5-section agent-issue template
so Linear issues can be produced directly from the generator — dogfooding
`docs_validate_linear_issue` on generator output.

## Scope

| ID | Title | Type | Home | Est | Gate |
|---|---|---|---|---|---|
| STORY-104.1 | `agent_template=True` flag on `docs_generate_story` + `## Refs` emitter | tool | docs-mcp | 3-4 h | Optional — pending user Q2 |
| STORY-104.2 | Bug fix: minimal-style epics emit `## Motivation` stub | bugfix | docs-mcp | 1 h | **Done 2026-04-22** |
| STORY-104.3 | Bug fix: in-epic story stubs emit `#### Acceptance Criteria` heading | bugfix | docs-mcp | 1 h | **Done 2026-04-22** |
| STORY-104.4 | (optional) `agent_template=True` on `docs_generate_epic` if Linear-epic support desired | tool | docs-mcp | 2-3 h | Gate on 104.1 landing |

Stories 104.2 and 104.3 are independent bug fixes — they can land any time and
don't block 104.1.

## Bug details (104.2 / 104.3)

### 104.2 — minimal-style epics fail validation

- **Symptom**: `docs_generate_epic(style="minimal")` produces a doc that
  `docs_validate_epic` flags as missing a required section.
- **Root cause**: [epics.py:353-360](../../packages/docs-mcp/src/docs_mcp/generators/epics.py) (minimal style skips `## Motivation`); [epic_validator.py:551-556](../../packages/docs-mcp/src/docs_mcp/validators/epic_validator.py) requires it.
- **Fix**: Emit a single-line `## Motivation` stub in minimal style ("N/A" or "See parent epic" when parent present).

### 104.3 — in-epic story stubs lack `## Acceptance Criteria` heading

- **Symptom**: Every in-epic story stub raises a validator error for missing AC.
- **Root cause**: [epics.py:558-596](../../packages/docs-mcp/src/docs_mcp/generators/epics.py) emits `(N acceptance criteria)` as inline text, not a heading; [epic_validator.py:396-398, 638-645](../../packages/docs-mcp/src/docs_mcp/validators/epic_validator.py) requires an H4 heading.
- **Fix**: Emit `#### Acceptance Criteria` inside each in-epic story stub when `ac_count > 0`, even if items are elided.

## Acceptance

- [ ] 104.2: `docs_generate_epic(style="minimal")` output passes `docs_validate_epic` on a fresh project
- [ ] 104.3: An epic with ≥1 in-line story stub (not linked) passes `docs_validate_epic` without per-story AC errors
- [ ] 104.1 (if shipped): `docs_generate_story(agent_template=True)` output passes `docs_validate_linear_issue` with `agent_ready=true` by construction (add a round-trip test)
- [ ] 104.4 (if shipped): same round-trip guarantee for epic agent-template mode

## Non-goals

- Not renaming `## Goal` → `## What` in the default generator output. Vocabulary
  divergence between product-review docs and agent-issue payloads is intentional.
- Not merging epic generator output into Linear. Epics live in `docs/epics/`;
  Linear epics (if desired) stay a separate summary issue and are out of
  scope here.
- Not rewriting validators. Drift is on the generator side; validators are fine.

## References

- Source-code review: [docs/reviews/EPIC-103-REVIEW-generators.md](../reviews/EPIC-103-REVIEW-generators.md)
- Locked agent template: [docs/linear/AGENT_ISSUES.md](../linear/AGENT_ISSUES.md)
- Parent EPIC: [EPIC-103](EPIC-103-linear-issue-quality-tooling.md) (closed)
- Prior generator-quality work: [EPIC-91](EPIC-91-epic-generator-quality-gaps.md), [EPIC-92](EPIC-92-story-generator-quality-gaps.md)
