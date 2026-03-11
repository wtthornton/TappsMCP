# Story 79.5: Role presets (tool_preset by role slug) in server config

**Epic:** [EPIC-79-MCP-TOOL-COUNT-CURATION](../EPIC-79-MCP-TOOL-COUNT-CURATION.md)  
**Priority:** P1 | **LOE:** 2–3 days  
**Depends on:** Story 79.1 (enabled_tools / tool_preset mechanism)

## Problem

Users want to select a tool set by **role** (e.g. “this session is for review” or “this project is for planning”) without maintaining a long allow list. Story 79.1 adds `enabled_tools` / `disabled_tools` and optionally `tool_preset: core | full`. We need `tool_preset` to accept **role slugs** (reviewer, planner, frontend, developer, full, security, refactor, docs, release) so that one config value selects the predefined tool set for that role from [ROLE-PRESETS-IMPLEMENT-FIRST.md](../../research/ROLE-PRESETS-IMPLEMENT-FIRST.md).

## Purpose & Intent

This story exists so that **users can select a tool set by role with one config value** (e.g. tool_preset: reviewer) instead of maintaining a long allow list. Role-based presets match how people work ("this session is for review" or "this project is for planning") and keep tool count optimal per use case without manual curation.

## Tasks

- [ ] Extend `tool_preset` (or equivalent) in TappsMCP config to accept the nine role slugs: `reviewer`, `planner`, `frontend`, `developer`, `full`, `security`, `refactor`, `docs`, `release`. Map each slug to the exact TappsMCP tool list defined in ROLE-PRESETS-IMPLEMENT-FIRST.md §2. `full` = all tools (same as current default).
- [ ] Optionally support `default_role: <slug>` in `.tapps-mcp.yaml` as an alias for or in addition to `tool_preset`, so project-level config can set “this project defaults to planner tools.”
- [ ] Ensure conditional registration (from 79.1) uses the role’s tool list when `tool_preset` is set to a role slug. No new registration logic—only the source of the “enabled” list (preset name → list from ROLE-PRESETS-IMPLEMENT-FIRST).
- [ ] Add unit tests: each Phase 1 role (reviewer, planner, frontend, developer, full) yields the correct tool count and expected tool names; invalid slug is rejected or falls back to full.
- [ ] Document in config reference and AGENTS.md that `tool_preset` can be a role slug and link to ROLE-PRESETS-IMPLEMENT-FIRST for the full table.

## Acceptance criteria

- [ ] `tool_preset: reviewer` (and planner, frontend, developer, full, etc.) results in only that role’s TappsMCP tools being registered. Tool lists match ROLE-PRESETS-IMPLEMENT-FIRST.md.
- [ ] Phase 1 roles (reviewer, planner, frontend, developer, full) are implemented and tested; Phase 2 (security, refactor, docs, release) can be added in same or follow-on change.
- [ ] Config docs list all supported role slugs and reference the role presets doc.

## Files

- `packages/tapps-core/src/tapps_core/config/settings.py` (tool_preset validation / allowed values)
- `packages/tapps-mcp/src/tapps_mcp/` (mapping from role slug → tool list; can live in checklist or a new small module)
- `packages/tapps-mcp/tests/unit/` (tests per role preset)
- Config and AGENTS.md

## References

- [ROLE-PRESETS-IMPLEMENT-FIRST.md](../../research/ROLE-PRESETS-IMPLEMENT-FIRST.md) — tool sets per preset
- Story 79.1 (enabled_tools / tool_preset mechanism)
