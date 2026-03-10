# Epic 65.4: Auto-Recall Hook (2026 Best Practices)

**Status:** Proposed
**Priority:** P1 | **LOE:** 1-1.5 weeks | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 25, 34, 36 (memory, retrieval, hooks)

## Problem Statement

Agents must manually call `tapps_memory(action="search")` to inject relevant memories. OpenClaw Memory Auto-Recall and Kumiho use a `before_prompt_build` hook that automatically searches and injects memories. This epic adds an auto-recall hook template so memories are injected before the agent responds.

**Reference:** OpenClaw Memory Auto-Recall, Kumiho zero-latency prefetch

## Stories

### Story 65.4.1: Auto-recall hook template

**Files:** `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py`

1. Add `memory_auto_recall` hook template:
   - Runs before agent prompt build (or PreCompact, SessionStart)
   - Calls `MemoryRetriever.search()` with query from current prompt (or last user message)
   - Formats results as XML/structured block: `<memory_context>...</memory_context>`
   - Prepends to prompt
2. Hook receives: `prompt` or `context`, returns: `enhanced_prompt`
3. Configurable: `max_results` (1-10, default 5), `min_score` (0-1, default 0.3), `min_prompt_length` (skip if prompt < N chars, default 50)
4. Platform-specific variants: Claude Code (PreCompact, SessionStart), Cursor (beforeMCPExecution or equivalent)

**Acceptance criteria:**
- Hook template exists in `platform_hook_templates.py`
- Configurable max_results, min_score, min_prompt_length
- Output format documented (XML block)

### Story 65.4.2: Hook script generation

**Files:** `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hooks.py`, `platform_generators.py`

1. Generate hook script that:
   - Invokes MemoryRetriever (or tapps_memory MCP tool if available)
   - Injects results into context per platform spec
2. Claude Code: PreCompact, SessionStart hooks
3. Cursor: beforeMCPExecution or equivalent
4. Script must handle: no MemoryStore, no MCP connection, empty results (graceful fallback)

**Acceptance criteria:**
- Generated hook scripts work for Claude Code and Cursor
- Graceful fallback when memory unavailable

### Story 65.4.3: Integration with tapps_init

**Files:** `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`

1. `tapps_init` can optionally include auto-recall hook in generated platform files
2. Config: `memory_auto_recall.enabled` (default: false for backward compat)
3. Engagement-level: high/medium may enable; low may disable
4. Document trade-offs: coverage vs noise, min_score tuning

**Acceptance criteria:**
- tapps_init generates auto-recall hook when enabled
- Config controls enablement
- AGENTS.md documents trade-offs

## Testing

- Unit: hook template produces valid output
- Integration: hook script executes; memory injected (mock MemoryStore)
