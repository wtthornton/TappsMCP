# Story 79.6: Docker MCP role-named profiles (Phase 1: reviewer, planner, frontend, developer)

**Epic:** [EPIC-79-MCP-TOOL-COUNT-CURATION](../EPIC-79-MCP-TOOL-COUNT-CURATION.md)  
**Priority:** P1 | **LOE:** 2–3 days  
**Depends on:** Story 79.3 (core-tools profile / tools.yaml pattern)

## Problem

Users who connect via Docker MCP Gateway want to choose a **role** (reviewer, planner, frontend, developer) and get the right tools automatically—e.g. “this window is for code review” → use profile `tapps-reviewer` with tools.yaml that enables only the reviewer tool set. We ship a “core tools” profile in 79.3; we should also ship **role-named profiles** so that one profile = one role = one curated tool set per [ROLE-PRESETS-IMPLEMENT-FIRST.md](../../research/ROLE-PRESETS-IMPLEMENT-FIRST.md).

## Purpose & Intent

This story exists so that **Docker MCP users can choose a role and get the right tools automatically**—e.g. profile tapps-reviewer for code review, tapps-planning for epics/stories. Role-named profiles make the gateway workflow align with the server-side role presets (79.5) and give Docker users a one-profile-per-role experience without manual tools.yaml editing.

## Tasks

- [ ] Add Phase 1 role-named profiles to `docker-mcp/profiles/`: `tapps-reviewer`, `tapps-planning`, `tapps-frontend`, `tapps-developer`. Each profile specifies which servers (tapps-mcp; planner also includes docs-mcp) and includes or references a **tools.yaml** (or equivalent) that enables only the tools for that role as defined in ROLE-PRESETS-IMPLEMENT-FIRST.md §2.
- [ ] For **planner**, profile includes docs-mcp with the planner DocsMCP tool list (docs_session_start, docs_project_scan, docs_check_drift, docs_generate_readme, docs_generate_epic, docs_generate_story, docs_generate_prd, docs_check_completeness, docs_module_map, docs_git_summary). Other Phase 1 profiles (reviewer, frontend, developer) are TappsMCP-only unless we add optional docs-mcp with minimal tools.
- [ ] Document in `docker-mcp/README.md`: how to import and use role-named profiles; “use profile tapps-reviewer for code review,” “use tapps-planning for epics/stories,” etc.; link to ROLE-PRESETS-IMPLEMENT-FIRST.
- [ ] Ensure profiles can be imported via `docker mcp profile import` (or equivalent) and that the gateway applies the tool filter when the profile is used. If Docker MCP stores tools per profile in a different way (e.g. tools.yaml path per profile), follow that pattern.

## Acceptance criteria

- [ ] Four Phase 1 role profiles exist: tapps-reviewer, tapps-planning, tapps-frontend, tapps-developer. Each exposes only the tool set for that role (tool counts: reviewer ~10, planner ~18 with docs-mcp, frontend ~7, developer ~12).
- [ ] README (or Docker MCP docs) explains how to use role profiles and when to pick which one.
- [ ] Phase 2 profiles (security, refactor, docs, release) are out of scope for this story; can be added in a follow-on.

## Files

- `docker-mcp/profiles/tapps-reviewer.yaml` (or profile + tools config)
- `docker-mcp/profiles/tapps-planning.yaml`
- `docker-mcp/profiles/tapps-frontend.yaml`
- `docker-mcp/profiles/tapps-developer.yaml`
- `docker-mcp/README.md`

## References

- [ROLE-PRESETS-IMPLEMENT-FIRST.md](../../research/ROLE-PRESETS-IMPLEMENT-FIRST.md) — tool sets per role
- Story 79.3 (core-tools profile and tools.yaml pattern)
- Epic 46 (Docker MCP Distribution)
