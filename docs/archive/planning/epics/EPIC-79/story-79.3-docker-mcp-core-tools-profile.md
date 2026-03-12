# Story 79.3: Docker MCP — core-tools profile and example tools.yaml

**Epic:** [EPIC-79-MCP-TOOL-COUNT-CURATION](../EPIC-79-MCP-TOOL-COUNT-CURATION.md)  
**Priority:** P1 | **LOE:** 2–3 days

## Problem

Users who run TappsMCP and DocsMCP via the Docker MCP Gateway get all tools from all servers by default. The gateway supports per-tool filtering via `tools.yaml` and `docker mcp profile tools`, but we do not ship a ready-made “core tools” setup. Users who want to stay under ~30 tools must manually enable/disable tools. We should ship a profile (or example tools.yaml) that enables only Tier 1 (and optionally Tier 2) tools for tapps-mcp and docs-mcp so that one-command setup yields an optimal tool set.

## Purpose & Intent

This story exists so that **Docker MCP users get a ready-made curated setup** instead of manually building tools.yaml. Shipping a core-tools profile or example tools.yaml reduces friction and ensures Docker adopters can immediately benefit from tool-count best practices without reading research docs or maintaining their own allowlist.

## Tasks

- [ ] Add a profile `tapps-core-tools` (or extend `tapps-minimal` / `tapps-standard`) that includes tapps-mcp and optionally docs-mcp with a **pre-configured tool allowlist** (e.g. via tools.yaml or profile export).
- [ ] Create an example `tools.yaml` (or equivalent) that enables only Tier 1 tools for tapps-mcp (session_start, quick_check, validate_changed, quality_gate, checklist, lookup_docs, security_scan) and, if docs-mcp is in the profile, Tier 1 for docs-mcp (session_start, check_drift, generate_readme, project_scan). Optionally include a second example that adds Tier 2 for “standard” use.
- [ ] Document in `docker-mcp/README.md` and/or `docs/DOCKER_MCP_TOOLKIT.md`: how to use the core-tools profile, how to import the example tools.yaml, and that gateway tool filtering keeps tool count in the optimal range (reference 2026 research).
- [ ] Ensure profile can be imported via `docker mcp profile import` or that the example tools.yaml is applied when using the profile (per Docker MCP Gateway behavior: profile can have associated tools config).

## Acceptance criteria

- [ ] A profile or example tools config is available in `docker-mcp/` that, when used with the Docker MCP Gateway, exposes only ~7–15 tools total (Tier 1, or Tier 1 + selected Tier 2) for tapps-mcp and docs-mcp.
- [ ] README or Docker MCP docs explain how to use it and why (tool count best practice).
- [ ] Existing profiles (tapps-minimal, tapps-standard, tapps-full) are unchanged in server list; this story adds curation (tool filter) for at least one profile or provides a standalone example. Role-named profiles (tapps-reviewer, tapps-planning, etc.) are added in story 79.6.

## Files

- `docker-mcp/profiles/tapps-core-tools.yaml` (or similar) and/or `docker-mcp/profiles/tools-core-example.yaml`
- `docker-mcp/README.md`
- `docs/DOCKER_MCP_TOOLKIT.md` (if present) or `packages/tapps-core/.../docker-mcp-toolkit.md` (expert knowledge)

## References

- [2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md](../../research/2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md) §6 (Docker MCP Toolkit and tool count)
- [Docker MCP profile tools CLI](https://docs.docker.com/reference/cli/docker/mcp/profile/tools/)
- Epic 46 (Docker MCP Distribution)
- Story 79.6 (role-named profiles build on this pattern)
