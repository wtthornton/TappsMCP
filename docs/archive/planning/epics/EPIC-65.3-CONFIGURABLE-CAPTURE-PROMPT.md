# Epic 65.3: Configurable Capture Prompt & Write Rules (2026 Best Practices)

**Status:** Complete
**Priority:** P1 | **LOE:** 4-6 days | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, config/settings

## Problem Statement

OpenClaw's default memoryFlush uses a generic "Store durable memories" prompt, leading to noise. Neuronex: "Only store: validated, non-sensitive, improves outcomes, will matter later." Zylos: "Store understanding, not action sequences." This epic adds configurable capture prompt and optional write rules to `.tapps-mcp.yaml` for auto-capture (Epic 65.5) and manual save guidance.

## Stories

### Story 65.3.1: memory.capture_prompt in config

**Files:** `packages/tapps-core/src/tapps_core/config/settings.py`, `packages/tapps-mcp/src/tapps_mcp/config/default.yaml`

1. Add to `default.yaml`:
   ```yaml
   memory:
     capture_prompt: |
       Store durable memories: architectural (project structure, key decisions), pattern (coding conventions, recurring solutions), context (session-specific facts that matter next week).
       Skip: raw action logs, transient state, sensitive data.
       If it won't change future decisions, don't store it.
   ```
2. Add `MemoryConfig` (or extend settings) with `capture_prompt: str`
3. Load from `.tapps-mcp.yaml`; fallback to default
4. Document in AGENTS.md and platform rules

**Acceptance criteria:**
- Config loads `memory.capture_prompt`
- Default prompt matches Neuronex/Zylos criteria
- Documented in config schema and AGENTS.md

### Story 65.3.2: memory.write_rules in config

**Files:** `packages/tapps-core/src/tapps_core/config/settings.py`, `packages/tapps-mcp/src/tapps_mcp/config/default.yaml`

1. Add optional `write_rules`:
   ```yaml
   memory:
     write_rules:
       block_sensitive_keywords: ["password", "secret", "api_key", "token"]
       min_value_length: 10
       max_value_length: 4096  # existing limit
   ```
2. Write rules used by optional validation gate (Epic 65.17)
3. For now, config only; validation enforcement in 65.17

**Acceptance criteria:**
- Config supports `memory.write_rules` with block_sensitive_keywords, min/max length
- Documented

### Story 65.3.3: Platform rules documentation

**Files:** `packages/tapps-mcp/src/tapps_mcp/prompts/*.md`, AGENTS.md

1. Add memory capture prompt guidance to platform rules
2. Add "write rules" best practice to AGENTS.md tapps_memory section
3. Ensure `tapps_init` can optionally write custom capture_prompt to generated config

**Acceptance criteria:**
- AGENTS.md documents capture_prompt and write_rules
- Platform rules mention memory capture best practices

## Testing

- Unit: settings load capture_prompt and write_rules
- Unit: default values applied when absent
- Integration: tapps_init generates config with memory section when applicable
