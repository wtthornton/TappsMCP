# Epic 65.16: Context Budget for Memory Injection (2026 Best Practices)

**Status:** Complete
**Priority:** P2 | **LOE:** 2-3 days | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 25 (memory injection)

## Problem Statement

RAG 2025: "Context budgeting; retrieve only highly relevant; avoid context bloat." Memory injection can consume too many tokens. This epic adds `memory.injection_max_tokens` and truncation logic.

**Reference:** RAG context budgeting, context window management

## Stories

### Story 65.16.1: injection_max_tokens config

**Files:** `packages/tapps-core/src/tapps_core/config/settings.py`, `default.yaml`, `memory/injection.py`

1. Add `memory.injection_max_tokens: int` (default: 2000)
2. In `inject_memory_context()`: truncate injected content to stay within budget
3. Truncation: prioritize by composite score (relevance, confidence, recency); cut lowest until under budget
4. Approximate: 1 token ≈ 4 chars (or use tiktoken if available)

**Acceptance criteria:**
- Config loads injection_max_tokens
- Injected content truncated when over budget
- Priority order respected

### Story 65.16.2: Token estimation

**Files:** `packages/tapps-core/src/tapps_core/memory/injection.py`

1. Add `estimate_tokens(text: str) -> int`:
   - Simple: `len(text) // 4`
   - Optional: tiktoken when installed
2. Use in truncation logic
3. Return `truncated: bool` and `injected_tokens: int` in injection result for observability

**Acceptance criteria:**
- Token estimation implemented
- Truncation metadata in result

### Story 65.16.3: Documentation

**Files:** AGENTS.md

1. Document injection_max_tokens
2. Tuning guidance: increase for complex projects, decrease for cost/latency

**Acceptance criteria:**
- AGENTS.md updated
