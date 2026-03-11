# Story 79.4: Document recommended tool subsets and Docker tool filtering

**Epic:** [EPIC-79-MCP-TOOL-COUNT-CURATION](../EPIC-79-MCP-TOOL-COUNT-CURATION.md)  
**Priority:** P2 | **LOE:** 1–2 days

## Problem

Users and automation need clear guidance on which tools to use for which task and how to keep tool count in the optimal range. We have TOOL-TIER-RANKING and 2026 research, but AGENTS.md and Docker MCP docs do not yet tell users to “enable only Tier 1 for minimal context” or “use Docker MCP profile tools to trim to &lt;30 tools.”

## Purpose & Intent

This story exists so that **users know why and how to curate tools**—by task, by role, and via Docker MCP. Without clear guidance in AGENTS.md and Docker docs, the server-side and profile options from 79.1–79.3 and 79.6 would be underused. Documentation ties the implementation to user goals (e.g. "use reviewer preset for code review") and to the research that justifies the &lt;30-tool recommendation.

## Tasks

- [ ] In AGENTS.md (TappsMCP and optionally DocsMCP): add a short section “Tool count and curation” that (1) references the &lt;30-tool recommendation and TOOL-TIER-RANKING, (2) describes recommended subsets by task and by **role** (reviewer, planner, frontend, developer—link to [ROLE-PRESETS-IMPLEMENT-FIRST.md](../../research/ROLE-PRESETS-IMPLEMENT-FIRST.md)), (3) for Docker MCP users: point to gateway tool filtering (Tools tab or `docker mcp profile tools`), the core-tools profile (79.3), and role-named profiles (79.6).
- [ ] Optionally add a “Recommended tool subsets” table or link to TOOL-TIER-RANKING from the “When to use each tool” section.
- [ ] In Docker MCP docs (docker-mcp/README.md or DOCKER_MCP_TOOLKIT.md): add a subsection on “Keeping tool count optimal” that explains tools.yaml / profile tools and points to the example from story 79.3; mention disabling Dynamic MCP if users want a stable small set.
- [ ] Ensure TOOL-TIER-RANKING.md is linked from planning docs and that the research doc (2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md) is referenced where appropriate.

## Acceptance criteria

- [ ] AGENTS.md (or equivalent) contains guidance on tool subsets by task and on using gateway tool filtering when using Docker MCP.
- [ ] Docker MCP README or toolkit doc explains how to curate tools to stay under ~30 and references the core-tools profile (79.3) and role-named profiles (79.6).
- [ ] No code changes required unless we add a small “tool presets” reference section in config docs.

## Files

- `AGENTS.md` (repo root and/or packages/tapps-mcp, packages/docs-mcp)
- `docker-mcp/README.md`
- `docs/DOCKER_MCP_TOOLKIT.md` or expert knowledge `docker-mcp-toolkit.md`

## Dependencies

- Stories 79.3 and 79.6 (so we can reference the core-tools profile and role-named profiles by name).
- [ROLE-PRESETS-IMPLEMENT-FIRST.md](../../research/ROLE-PRESETS-IMPLEMENT-FIRST.md) for the role → tool set table.
