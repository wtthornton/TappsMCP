# Story 79.1: TappsMCP server-side enabled_tools / disabled_tools

**Epic:** [EPIC-79-MCP-TOOL-COUNT-CURATION](../EPIC-79-MCP-TOOL-COUNT-CURATION.md)  
**Priority:** P1 | **LOE:** 3–5 days

## Problem

TappsMCP registers all 29 tools at startup. For users who connect via direct stdio (no Docker MCP Gateway), there is no way to expose only a subset of tools. Research shows that keeping active tool count under ~30 (and ideally a “core” set of ~7–10) improves LLM accuracy and context efficiency. We need server-side config so that only selected tools are registered and returned from `tools/list`.

## Purpose & Intent

This story exists so that **direct stdio users can keep tool count in the optimal range** without relying on a gateway. Server-side enabled_tools/disabled_tools (and optional presets) give projects a single place to curate which tools are exposed, improving LLM accuracy and context efficiency for the most common deployment path.

## Tasks

- [ ] Add settings to `TappsMCPSettings` (tapps-core config): e.g. `enabled_tools: list[str] | None = None` (allow list) and/or `disabled_tools: list[str] = []` (deny list). Precedence: if `enabled_tools` is non-empty, only those tools are exposed; otherwise `disabled_tools` is applied to the full set. Empty/missing `enabled_tools` = current behavior (all tools).
- [ ] Define a default “core” set (e.g. Tier 1 from TOOL-TIER-RANKING: session_start, quick_check, validate_changed, quality_gate, checklist, lookup_docs, security_scan). Document that default in the setting description; do not change default to “core” in this story unless product agrees—default can remain “all” with an optional preset e.g. `tool_preset: full | core | pipeline`.
- [ ] In TappsMCP server registration flow, only register tools that pass the filter: when building the tool list for FastMCP, skip registration (or register conditionally) for tools not in the allowed set / in the disabled set. Ensure all tool handlers remain unchanged; only registration is conditional.
- [ ] Support YAML and env: e.g. `enabled_tools` in `.tapps-mcp.yaml` or `TAPPS_MCP_ENABLED_TOOLS` (comma-separated). If `tool_preset` is used (e.g. `core`, `full`, or a role slug—see story 79.5), map it to the predefined list.
- [ ] Add unit tests: server returns only enabled tools when `enabled_tools` is set; disabled_tools excludes correctly; empty/missing = all tools; invalid tool names in config are ignored or logged.
- [ ] Update AGENTS.md and config docs to describe the new setting and presets (if any).

## Acceptance criteria

- [ ] Config supports at least one of: `enabled_tools` (allow list), `disabled_tools` (deny list), or `tool_preset` (full | core | pipeline; role slugs are added in story 79.5). Empty/not set = all tools (backward compatible).
- [ ] `tools/list` returns only the filtered set when config is set; existing tests that assume all tools can be updated or run with full preset.
- [ ] Tests cover: enabled_tools subset, disabled_tools subset, preset “core”, default “all”.
- [ ] Documentation describes how to reduce tool count for direct stdio users.

## Files

- `packages/tapps-core/src/tapps_core/config/settings.py` (new fields)
- `packages/tapps-core/src/tapps_core/config/default.yaml` (optional defaults)
- `packages/tapps-mcp/src/tapps_mcp/server.py` and registration helpers (conditional registration)
- `packages/tapps-mcp/tests/unit/` (tests for filtered tool list)
- `AGENTS.md` and/or config reference

## References

- [2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md](../../research/2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md) §5 (server-side default off)
- [TOOL-TIER-RANKING.md](../../TOOL-TIER-RANKING.md) (Tier 1 = core set)
- Story 79.5 (role presets: tool_preset by role slug builds on this)
