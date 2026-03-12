# Recommended Tool Subsets and Docker Tool Filtering (Epic 79.4)

**Purpose:** Document how to keep active MCP tool count in the optimal range (&lt;30 tools) for TappsMCP and DocsMCP, including by task, by role, and when using Docker MCP.

---

## Why tool count matters

Research (2026) shows that LLM tool-selection accuracy and context efficiency degrade when too many tools are in context; ~30 tools is a practical upper bound. TappsMCP has 29 tools and DocsMCP 22; combined that is 51 tools. This doc describes how to expose only a subset.

---

## 1. Tier-based subsets (TappsMCP)

See [TOOL-TIER-RANKING.md](TOOL-TIER-RANKING.md) for the full ranking.

| Preset | Tools | Use case |
|--------|-------|----------|
| **core** | 7 tools: session_start, quick_check, validate_changed, quality_gate, checklist, lookup_docs, security_scan | Minimal pipeline + docs lookup + security |
| **pipeline** | Core + Tier 2 (score_file, consult_expert, research, memory, project_profile, impact_analysis, validate_config) | Full quality loop + experts + memory |
| **full** | All 29 tools | No restriction (default) |

**Config (direct stdio):** In `.tapps-mcp.yaml` set `tool_preset: core` or `tool_preset: pipeline`, or use env `TAPPS_MCP_TOOL_PRESET=core`. See [AGENTS.md](../AGENTS.md) § "Reducing tool count".

---

## 2. Role-based presets (Epic 79.5)

Phase 1 role presets map workflow to a curated tool set:

| Role | Description | TappsMCP tools (approx.) |
|------|-------------|---------------------------|
| **reviewer** | Code review & security | session_start, quick_check, validate_changed, quality_gate, checklist, security_scan, score_file, dead_code, dependency_scan, project_profile |
| **planner** | Epics, stories, planning | session_start, checklist, validate_changed, quality_gate, score_file, memory, consult_expert, project_profile |
| **frontend** | Frontend / UX work | session_start, quick_check, score_file, lookup_docs, consult_expert, quality_gate, project_profile |
| **developer** | Daily feature/bugfix dev | session_start, quick_check, validate_changed, quality_gate, checklist, score_file, security_scan, lookup_docs, memory, consult_expert, project_profile, impact_analysis |

**Config:** `tool_preset: reviewer | planner | frontend | developer` in `.tapps-mcp.yaml` or `TAPPS_MCP_TOOL_PRESET=reviewer`. Full list: [ROLE-PRESETS-IMPLEMENT-FIRST.md](research/ROLE-PRESETS-IMPLEMENT-FIRST.md).

---

## 3. Docker MCP: gateway tool filtering

When using Docker MCP Gateway:

1. **Import catalog and profile:**  
   `docker mcp catalog import docker-mcp/catalog.yaml`  
   `docker mcp profile import docker-mcp/profiles/tapps-core-tools.yaml` (or a role profile: `tapps-reviewer`, `tapps-planning`, `tapps-frontend`, `tapps-developer`).

2. **Restrict tools via `tools.yaml`:**  
   Copy an example from `docker-mcp/examples/` to `~/.docker/mcp/tools.yaml` (or your gateway config path):
   - `tools-core-tier1.yaml` — Tier 1 only (~11 tools combined)
   - `tools-core-tier1-tier2.yaml` — Tier 1 + Tier 2 (~23 tools)

3. **Role-named profiles (Epic 79.6):**  
   Profiles `tapps-reviewer`, `tapps-planning`, `tapps-frontend`, `tapps-developer` include the same servers; use the profile’s suggested tools.yaml or the Docker MCP UI **Tools** tab to enable only the tools for that role.

See [docker-mcp/README.md](../docker-mcp/README.md) and [docs/DOCKER_MCP_TOOLKIT.md](../docs/DOCKER_MCP_TOOLKIT.md) for step-by-step usage.

---

## 4. DocsMCP subsets

DocsMCP supports `enabled_tools`, `disabled_tools`, and `tool_preset: full | core` in `.docsmcp.yaml` or env `DOCS_MCP_ENABLED_TOOLS`, `DOCS_MCP_TOOL_PRESET`. Core preset exposes 6 tools (e.g. session_start, project_scan, check_drift, generate_readme, check_completeness, check_links). See DocsMCP AGENTS.md.

---

## 5. Summary

| Context | How to limit tools |
|---------|--------------------|
| **TappsMCP direct stdio** | `tool_preset: core | pipeline | reviewer | planner | frontend | developer` or `enabled_tools` in `.tapps-mcp.yaml` |
| **DocsMCP direct stdio** | `tool_preset: core` or `enabled_tools` in `.docsmcp.yaml` |
| **Docker MCP Gateway** | Use a profile + `tools.yaml` from `docker-mcp/examples/` or the profile’s recommended tool set |
| **Server-side (TappsMCP)** | Use **tapps-mcp-core** from catalog (same image with `TAPPS_MCP_TOOL_PRESET=core`) to expose 7 tools without gateway filtering |

All options are backward compatible: default remains "all tools" when no preset or allow list is set.
