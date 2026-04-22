---
name: linear-issue
user-invocable: true
model: claude-haiku-4-5-20251001
description: >-
  Draft a template-compliant Linear issue for the TappsMCP Platform project.
  Enforces the locked 5-section template (What / Where / Why / Acceptance / Refs),
  ≤80-char titles, inline-code filenames, and bare TAP-### refs. Emits markdown
  ready to paste into Linear (or write locally under docs/stories/).
allowed-tools: Read Grep mcp__plugin_linear_linear__get_issue
argument-hint: "[free-form description of the ask]"
---

Produce ONE Linear issue as markdown that conforms to
[docs/linear/AGENT_ISSUES.md](../../../docs/linear/AGENT_ISSUES.md). The user's
argument is the raw ask — your job is to structure it.

## Procedure

1. **Parse the ask.** Extract: what's changing/broken, which file(s), any TAP-###
   refs, and what "done" looks like. If the ask names a file and line range,
   verify the file exists via `Read` or `Grep` before including it.

2. **If a TAP-### ref is cited**, fetch it with
   `mcp__plugin_linear_linear__get_issue` so your draft doesn't duplicate or
   conflict with prior scope.

3. **Emit the issue** in this exact shape. Omit `## Why` if the ask is
   self-evident. Omit `## Refs` if there's no prior issue or commit.

   ```markdown
   <title — ≤80 chars, pattern: `file.py: symptom` or `file.py: change`>

   ## What
   <one sentence: file + symptom OR file + change>

   ## Where
   `path/to/file.py:LINE-RANGE`

   ## Why
   <≤2 lines; skip entirely if self-evident>

   ## Acceptance
   - [ ] <verifiable fact, e.g., `mypy --strict packages/foo/` clean>
   - [ ] <verifiable fact, e.g., `pytest path/test_bar.py::test_baz` passes>
   - [ ] <verifiable fact, e.g., `tapps_quick_check` reports no new findings>

   ## Refs
   TAP-### (prior work), <commit-sha>
   ```

4. **Self-check before returning** (mirrors `docs_lint_linear_issue` rules):
   - Title ≤ 80 chars.
   - No `[AGENTS.md](AGENTS.md)` — use `` `AGENTS.md` ``.
   - No `<issue id="UUID">TAP-###</issue>` — use bare `TAP-###`.
   - No fenced code blocks unless the bug IS the exact text.
   - `## Acceptance` has ≥1 checkbox with a verifiable command or assertion.
   - `## Where` has at least one `file.py:LINE` anchor.

5. **Propose a label**: one of `agent-ready`, `needs-clarification`,
   `agent-blocked`. Default to `agent-ready` if self-check passed; downgrade
   to `needs-clarification` if you had to leave any section vague.

6. **Ask the user** where to put it:
   - "Paste into Linear manually" → print the markdown.
   - "Write to `docs/stories/STORY-NNN.N-<slug>.md`" → write with `Write`.
   - "Create in Linear via MCP" → do NOT do this yet; the MCP write path is
     gated until `docs_validate_linear_issue` ships (STORY-103.4). Print the
     markdown for manual paste instead.

## Examples

### Example 1 — bug, minimal

Input: `rglob traverses node_modules in upgrade.py _has_python_signals around line 92`

Output:

```markdown
upgrade.py: _has_python_signals rglob traverses vendor/node_modules

## What
`_has_python_signals` falls back to `project_root.rglob("*.py")` which does not prune `node_modules` / `.venv` / vendored directories.

## Where
`packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py:92-116`

## Acceptance
- [ ] rglob is replaced with a pruning walk that skips `node_modules`, `.venv`, `.git`, `dist`, `build`
- [ ] `pytest packages/tapps-mcp/tests/unit/test_upgrade.py` passes
- [ ] `tapps_quick_check` on the edited file reports no new findings

Label: `agent-ready`
```

### Example 2 — needs clarification

Input: `we should clean up the memory module`

Output:

```markdown
tapps-core/memory: scope "cleanup" into concrete changes

## What
"Clean up memory module" is too broad to act on. Need to decide which of (shim retirement, dead-code removal, docstring refresh, API rationalisation) is in scope.

## Where
`packages/tapps-core/src/tapps_core/memory/` (specific files TBD)

## Why
Prior shim work tracked in TAP-496 / TAP-834 / TAP-835; this ask may overlap or be a follow-up.

## Acceptance
- [ ] Concrete list of files / functions to change, committed to issue description
- [ ] At least one verifiable AC replaces this checklist before an agent picks up

## Refs
TAP-496, TAP-834, TAP-835

Label: `needs-clarification`
```

## Notes

- This skill draws the template from the locked policy at
  `docs/linear/AGENT_ISSUES.md`. If the policy changes, update this skill
  alongside it.
- Generator is local-only until STORY-103.3 (`docs_lint_linear_issue`) and
  STORY-103.4 (`docs_validate_linear_issue`) ship. Creating issues directly
  in Linear via this skill is intentionally out of scope — gate through the
  validator when it exists.
