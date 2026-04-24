# Linear Issue Standards (TappsMCP)

All Linear writes in this project — epic creation, story creation, issue updates — MUST route through the `linear-issue` skill, which in turn routes through the docs-mcp generator and validator tools. Raw calls to `mcp__plugin_linear_linear__save_issue` are a rule violation.

## Required flow

### For a new epic
1. `mcp__docs-mcp__docs_generate_epic(title, purpose_and_intent, goal, motivation, acceptance_criteria, stories, ...)` — produces `docs/epics/EPIC-<N>.md` in the template shape.
2. `mcp__docs-mcp__docs_validate_linear_issue(title, description, is_epic=true)` — must return `agent_ready: true` with score 100.
3. Confirm with user.
4. `mcp__plugin_linear_linear__save_issue(...)` to push.
5. Create each child story via the story flow with `parent_id=<epic TAP-id>`.
6. `mcp__tapps-mcp__tapps_linear_snapshot_invalidate(team, project)`.

### For a new story
1. `mcp__docs-mcp__docs_generate_story(title, files, acceptance_criteria, ...)` — emits the 5-section template (`## What` / `## Where` / `## Why` / `## Acceptance` / `## Refs`).
2. `mcp__docs-mcp__docs_validate_linear_issue(title, description)` — must return `agent_ready: true`.
3. Confirm with user.
4. `mcp__plugin_linear_linear__save_issue(..., parent_id=<epic>)`.
5. `mcp__tapps-mcp__tapps_linear_snapshot_invalidate(team, project)`.

### Before updating an existing issue
1. `mcp__plugin_linear_linear__get_issue(id)` — fetch current state.
2. `mcp__docs-mcp__docs_lint_linear_issue(title, description, labels, priority, estimate)` — surface findings.
3. Regenerate via `docs_generate_story` or manual edit only if the existing body is broken.
4. Validate before push.
5. `save_issue(id=..., description=...)`; invalidate cache.

## Formatting rules (enforced by docs-mcp validator)

- Title ≤ 80 characters; no em-dash preambles.
- `## Acceptance` must contain at least one `- [ ]` checkbox.
- `## Where` must contain at least one `file.ext:LINE-RANGE` anchor.
- Bare `TAP-###` references, never `<issue id="UUID">TAP-###</issue>` wrappers.

## Linear markdown workarounds (observed 2026-04-24)

Linear's server-side markdown processor silently drops some content. These patterns preserve data:

- **Numbered lists, not bulleted, in `## Where` and `## Acceptance`** when items reference file paths. Bulleted `* path/...` entries get deduped on auto-linked filenames (especially `.md` files), keeping only the first. Numbered lists (`1.`, `2.`) survive intact.
- **Inline-code file paths**: `` `path/to/file.py:1-100` `` rather than bare `path/to/file.py:1-100`. Prevents the auto-linker from mangling.
- **Don't write bare `.md` filenames in prose** when a markdown auto-link would interfere. Use "the agents-md template", "the claude-md file", or wrap in backticks.
- **Avoid tables with many columns** — Linear's table rendering is fragile; prefer numbered lists with `—` separators for row fields.

## How to apply

When the user says "create a Linear issue", "file an epic", "open a ticket for X", or "track this in Linear" — invoke the `linear-issue` skill. Do not call `save_issue` directly. If the skill is unavailable in the session, flag it to the user rather than falling back to raw writes.

When updating an existing issue, the same routing applies: fetch, lint/validate, regenerate or edit, re-validate, save, invalidate.

## Enforcement

Currently soft-enforced (rule is auto-loaded into the system prompt). A follow-up ticket covers adding a `PreToolUse` hook that blocks `mcp__plugin_linear_linear__save_issue` when no prior `docs_validate_linear_issue` call has been recorded in the same turn cluster.
