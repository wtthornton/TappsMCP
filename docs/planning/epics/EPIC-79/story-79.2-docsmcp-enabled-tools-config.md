# Story 79.2: DocsMCP server-side enabled_tools config (optional)

**Epic:** [EPIC-79-MCP-TOOL-COUNT-CURATION](../EPIC-79-MCP-TOOL-COUNT-CURATION.md)  
**Priority:** P2 | **LOE:** 2–3 days

## Problem

DocsMCP has 22 tools. When used with TappsMCP (e.g. via Docker MCP Gateway) the combined count can exceed the recommended ~30 tools. For direct stdio users who run DocsMCP alone or together with TappsMCP, server-side control over which tools are exposed would align with Epic 79 goals. This story is optional if we rely solely on Docker MCP Gateway tool filtering for DocsMCP; it becomes useful for parity and for non-Docker users.

## Purpose & Intent

This story exists so that **DocsMCP has the same curation knobs as TappsMCP** when run standalone or alongside TappsMCP. Parity allows consistent tool-count control across both servers and supports non-Docker users who want to stay under the recommended tool count without gateway filtering.

## Tasks

- [ ] Add to DocsMCP settings (e.g. `DocsMCPSettings`): `enabled_tools: list[str] | None = None` and/or `disabled_tools: list[str] = []`, with same semantics as TappsMCP (allow list takes precedence; empty = all tools).
- [ ] Define a “core” set for DocsMCP (e.g. session_start, project_scan, check_drift, generate_readme, check_completeness, check_links) and optional preset e.g. `tool_preset: full | core`.
- [ ] In DocsMCP server registration, only register tools that pass the filter (same pattern as story 79.1).
- [ ] Support `.docsmcp.yaml` and env (e.g. `DOCS_MCP_ENABLED_TOOLS`).
- [ ] Add tests for filtered tool list; document in DocsMCP AGENTS.md/config.

## Acceptance criteria

- [ ] When `enabled_tools` or preset is set, `tools/list` returns only the allowed set; default = all tools (backward compatible).
- [ ] Tests cover at least one preset and allow-list scenario.
- [ ] DocsMCP config docs describe the option and reference tool-count best practices.

## Files

- `packages/docs-mcp/src/docs_mcp/config/settings.py`
- `packages/docs-mcp/src/docs_mcp/server.py` and server_*.py registration
- `packages/docs-mcp/tests/unit/`
- `packages/docs-mcp/AGENTS.md` or config docs

## Dependencies

- Story 79.1 (TappsMCP) can be done first to establish the pattern; this story mirrors it for DocsMCP.
