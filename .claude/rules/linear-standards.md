---
alwaysApply: false
---
# Linear Issue Standards (TappsMCP)

**Core rule:** All Linear writes — epic, story, issue updates — MUST route through the `linear-issue` skill (which runs docs-mcp generator + validator). Raw `save_issue` calls are a rule violation. For reads: use `linear-read` for lists (cache-first); `get_issue` for single lookups.

**Do not use the generic `linear` skill** — it bypasses docs-mcp validation and the cache gate. Use `linear-issue`, `linear-read`, or `linear-release-update` skills.

## Essential rules

- **Write flow:** Generate → validate (`agent_ready: true`) → save → invalidate cache. See [LINEAR_TECHNICAL_DETAILS.md](../references/LINEAR_TECHNICAL_DETAILS.md#required-flow--detailed-steps).
- **Assignee:** Always agent, never the OAuth human. Resolve `agent_user` from `.tapps-mcp.yaml` once per session.
- **Title:** ≤80 characters, no em-dash preambles.
- **Acceptance:** Include at least one `- [ ]` checkbox.
- **Anchors:** `## Where` must cite at least one `file.ext:LINE-RANGE`.
- **References:** Bare `TAP-###`, never `<issue>` wrappers.
- **Markdown quirks:** Use numbered lists (not bulleted) for file paths; inline-code file refs (`` `path:1-100` ``). See [workarounds](../references/LINEAR_TECHNICAL_DETAILS.md#linear-markdown-workarounds-observed-2026-04-24).

## How to apply

- Create issue: invoke `linear-issue` skill.
- List issues: invoke `linear-read` skill (cache-first dance).
- Single lookup: `get_issue(id)` directly.
- Update: fetch → lint → edit → validate → save → invalidate.
- Release: `linear-release-update` skill.

## Detailed reference

Full technical flows, enforcement mechanisms, and markdown workarounds: [LINEAR_TECHNICAL_DETAILS.md](../references/LINEAR_TECHNICAL_DETAILS.md).
