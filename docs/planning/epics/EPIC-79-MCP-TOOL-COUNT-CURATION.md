# Epic 79: MCP Tool Count & Curation (2026 Best Practices)

<!-- docsmcp:start:metadata -->
- **Status:** Complete (2026-03-11) — all 6 stories delivered
- **Priority:** P1–P2 (mix by story)
- **Estimated LOE:** ~2–3 weeks (1 developer)
- **Dependencies:** Epic 1, Epic 8, Epic 46 (Docker MCP Distribution); research in docs/planning/research/
- **Blocks:** None
- **Source:** docs/planning/research/2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md, TOOL-TIER-RANKING.md, Docker MCP Toolkit (profiles + tools.yaml)
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Align TappsMCP and DocsMCP with 2026 MCP best practices on tool count: implement server-side “default tools off” (expose a small core set by default), document and ship Docker MCP “core tools” profiles and example tools.yaml, and document recommended tool subsets by task and by role so that users and gateways can keep active tool count in the optimal range (&lt;30 tools) without changing server code where the gateway already filters.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Research (2026) shows that LLM tool-selection accuracy and context efficiency degrade when too many tools are in context: ~30 tools is a critical threshold for large models; 80–100+ tools leads to confusion and failure. TappsMCP has 29 tools, DocsMCP 22; combined that is 51 tools—above the safe range. Recommendations:

1. **Server-side:** Allow defaulting to a “core” tool set (e.g. Tier 1 from TOOL-TIER-RANKING) so that direct stdio users get a small default without gateway filtering.
2. **Docker MCP Toolkit:** The gateway supports per-tool filtering via `tools.yaml` and `docker mcp profile tools`. We should ship a “core tools” profile or example tools.yaml so Docker users can run tapps-mcp + docs-mcp but expose only 10–15 tools.
3. **Documentation:** Document recommended tool subsets by task and by **role** (reviewer, planner, frontend, developer, etc.); reference TOOL-TIER-RANKING and [ROLE-PRESETS-IMPLEMENT-FIRST.md](../research/ROLE-PRESETS-IMPLEMENT-FIRST.md) so that users and automation can curate intentionally.

This epic does not change tool behavior—only which tools are registered by default (optional config) and how we document and package curation for Docker and non-Docker users.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this because **tool count directly affects LLM accuracy and context efficiency**. Research shows that beyond ~30 tools, selection accuracy degrades and confusion increases; at 80–100+ tools the model can fail to use the right tool. TappsMCP has 29 tools and DocsMCP 22; combined that is 51—above the safe range. We want adopters to get maximum value without paying a "too many tools" tax. By supporting server-side "default tools off" (core or role-based subsets), shipping Docker MCP profiles and example tools.yaml for curated sets, and documenting recommended subsets by task and role, we give users and gateways the knobs to keep active tool count in the optimal range. The intent is to align with 2026 MCP best practices, improve reliability for both direct stdio and Docker users, and make curation a first-class, documented choice—not an afterthought.
<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria (Epic-level)

- [ ] TappsMCP supports config (e.g. `enabled_tools` allow list and/or `disabled_tools` deny list) so that only a subset of tools is registered; default can be “core” (e.g. Tier 1) or “all” (current behavior).
- [ ] DocsMCP supports the same config pattern (or documents gateway-only curation) so that tool count can be limited when running standalone.
- [ ] Docker MCP artifacts include a “core tools” profile or example tools.yaml that enables only Tier 1 (and optionally Tier 2) tools for tapps-mcp and docs-mcp.
- [ ] AGENTS.md (and/or tool reference) documents recommended tool subsets by task and by role; references TOOL-TIER-RANKING and role presets; Docker MCP docs explain how to use gateway tool filtering and role profiles to stay under ~30 tools.
- [ ] All changes backward-compatible; existing config sees “all tools” unless new settings are set.
- [ ] New/updated tests for conditional registration; existing tests pass.
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

| Story | Title | Priority | LOE |
|-------|--------|----------|-----|
| [79.1](EPIC-79/story-79.1-tappsmcp-enabled-tools-config.md) | TappsMCP server-side enabled_tools / disabled_tools | P1 | 3–5 days |
| [79.2](EPIC-79/story-79.2-docsmcp-enabled-tools-config.md) | DocsMCP server-side enabled_tools config (optional) | P2 | 2–3 days |
| [79.3](EPIC-79/story-79.3-docker-mcp-core-tools-profile.md) | Docker MCP: core-tools profile and example tools.yaml | P1 | 2–3 days |
| [79.4](EPIC-79/story-79.4-document-recommended-tool-subsets.md) | Document recommended tool subsets and Docker tool filtering | P2 | 1–2 days |
| [79.5](EPIC-79/story-79.5-role-presets-server-config.md) | Role presets (tool_preset by role slug) in server config | P1 | 2–3 days |
| [79.6](EPIC-79/story-79.6-docker-mcp-role-named-profiles.md) | Docker MCP role-named profiles (Phase 1: reviewer, planner, frontend, developer) | P1 | 2–3 days |

<!-- docsmcp:end:stories -->

## References

- **Role presets (full list):** [ROLE-PRESETS-IMPLEMENT-FIRST.md](../research/ROLE-PRESETS-IMPLEMENT-FIRST.md) — nine presets, tool sets, Phase 1/2
- **Research:** [2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md](../research/2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md) (tool count thresholds, Docker MCP §6, server-side default off §5)
- **Tier ranking:** [TOOL-TIER-RANKING.md](../TOOL-TIER-RANKING.md) (Tier 1 = core, Tier 2 = high value)
- **Docker MCP:** Epic 46 (Docker MCP Distribution); [Docker MCP Profiles](https://docs.docker.com/ai/mcp-catalog-and-toolkit/profiles/) (enable/disable tools), [docker mcp profile tools](https://docs.docker.com/reference/cli/docker/mcp/profile/tools/)
