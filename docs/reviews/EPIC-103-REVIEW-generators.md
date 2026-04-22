# Review: `docs_generate_epic` / `docs_generate_story` vs. locked agent template

**Status**: Review complete (STORY-103.6)
**Reviewed**: 2026-04-22
**Against**: [docs/linear/AGENT_ISSUES.md](../linear/AGENT_ISSUES.md) (5-section agent template, 2-level hierarchy) and the four Linear tools shipped under EPIC-103.

## Summary

**Good news**: [EPIC-91](../epics/EPIC-91-epic-generator-quality-gaps.md) (epic
generator quality gaps) and [EPIC-92](../epics/EPIC-92-story-generator-quality-gaps.md)
(story generator quality gaps) are **fully implemented**. All 10 stories across
both landed. Those epics fixed prose quality, speed, and suggestion engines —
they did NOT address agent-template conformance, so this review is
complementary, not redundant.

**The real issue**: the generators target a different audience (humans reviewing
plans) than the agent template (agents picking up work). The two shapes should
coexist, not merge. Two concrete drift bugs to fix, one new mode to add, one
small additive section.

## 1. EPIC-91 / EPIC-92 status — confirmed DONE

| Story | Scope | Implementation evidence |
|---|---|---|
| 91.1 Context-aware placeholder prose | epic generator | [epics.py:446-704](../../packages/docs-mcp/src/docs_mcp/generators/epics.py) |
| 91.2 Quick-start mode | epic generator | `quick_start` param at [server_gen_tools.py:1100](../../packages/docs-mcp/src/docs_mcp/server_gen_tools.py); `_infer_quick_start_defaults()` [epics.py:244-283](../../packages/docs-mcp/src/docs_mcp/generators/epics.py) |
| 91.3 Adaptive detail level | epic generator | `_auto_detect_style()` [epics.py:395-413](../../packages/docs-mcp/src/docs_mcp/generators/epics.py) |
| 91.4 Story + risk suggestion engine | epic generator | `_suggest_stories()` [epics.py:192-220](../../packages/docs-mcp/src/docs_mcp/generators/epics.py), `_suggest_risks()` [epics.py:223-241](../../packages/docs-mcp/src/docs_mcp/generators/epics.py) |
| 91.5 Performance targets | epic generator | `_render_performance_targets()` [epics.py:944-1013](../../packages/docs-mcp/src/docs_mcp/generators/epics.py) |
| 92.1 Performance parity | story generator | module depth cap [stories.py:889](../../packages/docs-mcp/src/docs_mcp/generators/stories.py); 15s budget [stories.py:840-862](../../packages/docs-mcp/src/docs_mcp/generators/stories.py) |
| 92.2 Context-aware placeholders | story generator | [stories.py:403-450](../../packages/docs-mcp/src/docs_mcp/generators/stories.py) |
| 92.3 Quick-start mode | story generator | [server_gen_tools.py:1323](../../packages/docs-mcp/src/docs_mcp/server_gen_tools.py), [stories.py:208-261](../../packages/docs-mcp/src/docs_mcp/generators/stories.py) |
| 92.4 Task suggestions | story generator | `_suggest_tasks()` [stories.py:156-206](../../packages/docs-mcp/src/docs_mcp/generators/stories.py) |
| 92.5 Improved Gherkin | story generator | `_derive_given/when/then()` [stories.py:544-601](../../packages/docs-mcp/src/docs_mcp/generators/stories.py) |

**Recommendation**: mark both epics as closed (if not already). No further work
from this review touches their scope.

## 2. Vocabulary mismatch — intentional, not a bug

The generators emit documents for humans reviewing PLANS. The agent template
targets agents EXECUTING work. The vocabularies diverge on purpose:

| Agent template | Epic generator | Story generator | Meaning |
|---|---|---|---|
| `## What` | `## Purpose & Intent` + `## Goal` | `## User Story Statement` ("As a / I want / So that") | Why the work exists |
| `## Where` | `## Files Affected` (comprehensive only) | `## Files` (conditional) | Which files are touched |
| `## Why` | `## Motivation` (always) | `## Purpose & Intent` | Business rationale |
| `## Acceptance` | `## Acceptance Criteria` | `## Acceptance Criteria` (checkbox or Gherkin) | Exit criteria |
| `## Refs` | metadata block (Dependencies / Blocks) + `## References` | `## Dependencies` (comprehensive only) | Cross-refs |

**Don't try to unify these.** A product-review doc under `docs/epics/` should
keep "As a / I want / So that" because humans find it clearer. A Linear issue
an agent picks up should keep the 5-section template because it's terser and
verifiable.

What IS missing: the generators have no way to emit in the agent shape. That's
story 103.6.a below.

## 3. Drift bugs to fix

Two concrete bugs surfaced by the review where validator expectations don't
match generator output. Both are small and should ship as a minor fix epic.

### Bug 3.1: minimal-style epics fail validation

- **Where**: [epics.py:353-360](../../packages/docs-mcp/src/docs_mcp/generators/epics.py) (minimal style skips `## Motivation`); [epic_validator.py:551-556](../../packages/docs-mcp/src/docs_mcp/validators/epic_validator.py) (requires it).
- **Symptom**: `docs_generate_epic(style="minimal")` produces a doc that
  `docs_validate_epic` flags as missing a required section.
- **Fix options**:
  1. Have minimal style emit a single-line `## Motivation` stub ("See parent epic" when present, else "N/A").
  2. Relax the validator — Motivation becomes a warning, not an error, for minimal-style epics (detect via presence of some minimal marker).
- **Recommendation**: option 1. Cheaper, preserves validator semantics, stub is fine.

### Bug 3.2: in-epic story stubs lack `## Acceptance Criteria` heading

- **Where**: [epics.py:558-596](../../packages/docs-mcp/src/docs_mcp/generators/epics.py) emits stories as `### EPIC.N -- TITLE` followed by inline `(N acceptance criteria)` text; [epic_validator.py:396-398, 638-645](../../packages/docs-mcp/src/docs_mcp/validators/epic_validator.py) looks for an H2 or H4 `Acceptance Criteria` heading and marks the story as errored if absent.
- **Symptom**: any epic with in-line stories (not linked to separate `docs/stories/*.md`) raises a per-story error on validation.
- **Fix**: emit `#### Acceptance Criteria` inside each story stub when
  `ac_count > 0`, even if the actual items are elided, OR teach the validator
  to accept the `(N acceptance criteria)` inline marker as proof of presence.
- **Recommendation**: emit the heading. More explicit, doesn't mutate the
  validator's standard-of-proof, and makes the stubs grep-friendly for agents.

## 4. Additive: agent-template mode for the generators

The generators currently can't emit Linear-ready issue markdown. To dogfood
our own linter/validator when *creating* issues, add an `agent_template=True`
parameter to `docs_generate_story` (and optionally `docs_generate_epic`) that
emits the locked 5-section shape instead of the product-review shape.

**Design**:

```python
# server_gen_tools.py
async def docs_generate_story(
    ...,
    agent_template: bool = False,
) -> dict[str, Any]:
    """When agent_template=True, emits the 5-section Linear-issue template
    from docs/linear/AGENT_ISSUES.md instead of the full human-review shape.
    Output passes docs_validate_linear_issue by construction."""
```

**Behavior when `agent_template=True`**:
- Emit `## What` / `## Where` / `## Why` / `## Acceptance` / `## Refs` only.
- Translate the existing `role / want / so_that` into a one-sentence `## What`.
- Derive `## Where` from `files` parameter, requiring `file:LINE` ranges;
  return an error if no line ranges supplied (matches our HIGH-severity
  lint rule for missing anchors).
- Copy `acceptance_criteria` straight through, enforce ≥1 checkbox.
- Derive `## Refs` from `dependencies` and any TAP-### found in
  `description`.

**Round-trip check**: the generator output should pass
`docs_validate_linear_issue` with `agent_ready=true`. This is a one-line test.

**Effort**: 3-4 h. One story. Call it **STORY-104.1** in a new light-weight
epic (**EPIC-104: agent-mode for doc generators**). Keeping it separate from
EPIC-103 because 103 is "tools for Linear"; 104 is "add Linear-issue output
to existing generators."

## 5. Additive: bare-`TAP-###` `## Refs` emitter

Both generators currently bury issue refs inside metadata blocks (Dependencies,
Blocks) or free-form References lists. Add a `## Refs` section emitter when
any TAP-### is found in the inputs:

- Input: list of issue IDs OR text scanned for `\bTAP-\d+\b`.
- Output:
  ```markdown
  ## Refs
  TAP-496, TAP-834 (prior work)
  TAP-910 (related)
  ```

**Effort**: 1 h. Roll into STORY-104.1 — it's conceptually the same work.

## 6. What NOT to change

- Don't rename `## Goal` to `## What` in the generators. The human-review
  vocabulary is load-bearing for `docs_generate_epic`'s current consumers.
- Don't drop `## User Story Statement` ("As a / I want / So that"). Keep it
  as the default format; the agent-template mode opts out.
- Don't merge `docs_generate_epic` output into Linear. Epics in `docs/epics/`
  are local design docs; Linear epics can be a separate summary issue. If
  Linear-epic support is wanted later, it's a new story — out of scope for
  103.6.
- Don't rewrite validators. `docs_validate_epic` is fine; the drift is on
  the generator side.

## 7. Proposed follow-on work

**New epic**: `EPIC-104 — agent-mode for doc generators` (optional; only if
the team wants dogfooded Linear-issue creation from the generators).

| Story | Scope | Effort |
|---|---|---|
| 104.1 | `agent_template=True` flag on `docs_generate_story` + `## Refs` emitter | 3-4 h |
| 104.2 | Fix bug 3.1: minimal-style epics emit `## Motivation` stub | 1 h |
| 104.3 | Fix bug 3.2: in-epic story stubs emit `#### Acceptance Criteria` heading | 1 h |
| 104.4 (optional) | `agent_template=True` on `docs_generate_epic` if Linear-epic support is wanted | 2-3 h |

Stories 104.2 and 104.3 are independent bugs and can land any time — they
don't need to wait for 104.1.

## 8. Decisions required from the user

1. **Create EPIC-104?** Or park the additions and ship only the bug fixes
   (3.1 / 3.2) as a small PR?
2. **Ship 104.1 at all?** The `linear-issue` skill already expands the
   5-section template from free-form input; a generator flag is
   nice-to-have, not critical. Skipping it saves 3-4 h.
3. **Close EPIC-91 / EPIC-92**? If not already, they're genuinely done per
   this audit.

## References

- Locked template / labels / hierarchy: [docs/linear/AGENT_ISSUES.md](../linear/AGENT_ISSUES.md)
- Parent epic: [EPIC-103](../epics/EPIC-103-linear-issue-quality-tooling.md)
- Completed generator-quality epics: [EPIC-91](../epics/EPIC-91-epic-generator-quality-gaps.md), [EPIC-92](../epics/EPIC-92-story-generator-quality-gaps.md)
- Generators: [epics.py](../../packages/docs-mcp/src/docs_mcp/generators/epics.py), [stories.py](../../packages/docs-mcp/src/docs_mcp/generators/stories.py)
- Validators: [epic_validator.py](../../packages/docs-mcp/src/docs_mcp/validators/epic_validator.py)
