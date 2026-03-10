# Epic 65.17: Optional Write Rules Validation (2026 Best Practices)

**Status:** Proposed
**Priority:** P2 | **LOE:** 2-3 days | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 65.3 (memory, write rules config)

## Problem Statement

Neuronex: "Only store: validated, non-sensitive, improves outcomes, will matter later." Epic 65.3 adds write_rules config. This epic adds an optional validation gate before save: block sensitive keywords, enforce min/max length.

**Reference:** Neuronex write rules

## Stories

### Story 65.17.1: Write rules validation in store.save

**Files:** `packages/tapps-core/src/tapps_core/memory/store.py`

1. Add `_validate_write_rules(value: str, write_rules: WriteRules) -> bool | str`:
   - Check block_sensitive_keywords: if value contains any, return error
   - Check min_value_length, max_value_length
   - Return True if pass, error string if fail
2. When `memory.write_rules.enforced: true` (config): call before save; reject if fail
3. When enforced false: no-op (backward compat)

**Acceptance criteria:**
- Validation runs when enforced
- Sensitive keywords blocked
- Length enforced
- Error message returned on rejection

### Story 65.17.2: Config integration

**Files:** `packages/tapps-core/src/tapps_core/config/settings.py`, `default.yaml`

1. Add `memory.write_rules.enforced: bool` (default: false)
2. Load block_sensitive_keywords, min_value_length, max_value_length from Epic 65.3 config
3. Document: enforced = strict mode; use for high-sensitivity projects

**Acceptance criteria:**
- Config supports enforced
- Default: false (opt-in)

### Story 65.17.3: tapps_memory error response

**Files:** `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py`

1. When store.save rejects (write rules): return `{error: "write_rules_violation", message: "..."}` 
2. Include which rule failed (sensitive, length)

**Acceptance criteria:**
- tapps_memory returns clear error on violation
