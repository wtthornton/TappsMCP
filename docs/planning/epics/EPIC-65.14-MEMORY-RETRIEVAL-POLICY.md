# Epic 65.14: Memory Retrieval Policy (2026 Best Practices)

**Status:** Proposed
**Priority:** P2 | **LOE:** 3-5 days | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 25 (memory, retrieval)

## Problem Statement

Neuronex: "Memory retrieval policy: block sensitive categories unless explicitly needed; prefer high-confidence memories; show what was used; retrieve only when task requires it." This epic formalizes retrieval policy in config and docs, with optional enforcement.

**Reference:** Neuronex memory retrieval policy

## Stories

### Story 65.14.1: Retrieval policy config

**Files:** `packages/tapps-core/src/tapps_core/config/settings.py`, `default.yaml`

1. Add `memory.retrieval_policy`:
   ```yaml
   memory:
     retrieval_policy:
       block_sensitive_tags: ["pii", "secret", "credentials"]
       min_confidence: 0.4
       include_debug_trace: false  # show what memory was used
       retrieve_only_when_needed: true  # semantic; documented only
   ```
2. Document each field
3. `block_sensitive_tags`: entries with these tags excluded from search when not explicitly requested
4. `min_confidence`: filter out entries below threshold
5. `include_debug_trace`: add `_used_memory_keys` to response for debugging

**Acceptance criteria:**
- Config loads retrieval_policy
- Documented

### Story 65.14.2: Policy enforcement in retrieval

**Files:** `packages/tapps-core/src/tapps_core/memory/retrieval.py`

1. When `block_sensitive_tags` set: filter out entries with matching tags (unless `include_sensitive: true` in search params)
2. When `min_confidence` set: filter out entries below decayed confidence
3. When `include_debug_trace`: add `used_memory_keys` to search result
4. `retrieve_only_when_needed`: documentation only; no enforcement (semantic)

**Acceptance criteria:**
- Tag filter applied
- Confidence filter applied
- Debug trace optional

### Story 65.14.3: AGENTS.md and platform rules

**Files:** AGENTS.md, platform rules

1. Document retrieval policy best practices
2. Verification before acting: prefer live tool reads over stale memory when memory affects actions
3. Add to tapps_memory tool doc

**Acceptance criteria:**
- AGENTS.md includes retrieval policy section
- Verification-before-acting documented
