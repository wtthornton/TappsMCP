# Epic 65.5: Auto-Capture Hook (2026 Best Practices)

**Status:** Proposed
**Priority:** P1 | **LOE:** 1.5-2 weeks | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 36, 55, 65.3 (memory, hooks, save_bulk, capture prompt)

## Problem Statement

The agent decides what to save, leading to missed writes and compaction loss. Mem0's extraction phase and OpenClaw's memoryFlush automatically extract and store durable facts on session stop. This epic adds an auto-capture hook that runs on Stop/session end, extracts durable facts from context, and calls `tapps_memory(action="save_bulk")`.

**Reference:** Mem0 extraction phase, OpenClaw memoryFlush

## Stories

### Story 65.5.1: Extraction helper (rule-based)

**Files:** `packages/tapps-core/src/tapps_core/memory/extraction.py` (new)

1. Create `extract_durable_facts(context: str, capture_prompt: str) -> list[dict]`:
   - Rule-based extraction: look for decision patterns ("we decided", "key decision", "architecture choice")
   - Optional: keyword/entity extraction for architectural, pattern, context tiers
   - Deterministic; no LLM calls
   - Uses `capture_prompt` from config (Epic 65.3) as criteria
2. Return list of `{key, value, tier}` candidates
3. Limit: max 10 candidates per run; max 4096 chars per value

**Acceptance criteria:**
- `extract_durable_facts` returns list of candidates
- Deterministic
- Configurable capture_prompt

### Story 65.5.2: Auto-capture hook template

**Files:** `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py`

1. Add `memory_auto_capture` hook template:
   - Runs on Stop/session end
   - Receives context (or last N messages) from platform
   - Calls `extract_durable_facts`
   - Calls `tapps_memory(action="save_bulk", entries=[...])` via MCP or direct MemoryStore
   - Configurable: `max_facts` (default 5), `min_context_length` (skip if short)
2. Platform-specific: Claude Code Stop, Cursor afterFileEdit or equivalent
3. Handle: no MemoryStore, MCP unavailable, extraction returns empty (no-op)

**Acceptance criteria:**
- Hook template exists
- Invokes extraction + save_bulk
- Graceful fallback

### Story 65.5.3: Hook script generation and tapps_init integration

**Files:** `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hooks.py`, `init.py`

1. Generate auto-capture hook script for Claude Code (Stop), Cursor
2. tapps_init includes auto-capture hook when `memory_auto_capture.enabled`
3. Document: coverage vs noise; importance of capture_prompt quality (Epic 65.3)

**Acceptance criteria:**
- Generated scripts work on Stop/session end
- tapps_init wires when enabled
- AGENTS.md documents flush prompt tuning

## Testing

- Unit: extract_durable_facts returns expected candidates
- Unit: hook template produces valid save_bulk payload
- Integration: hook executes; entries saved (mock store)
