# Epic 65.6: Hook Integration in tapps_init (2026 Best Practices)

**Status:** Proposed
**Priority:** P1 | **LOE:** 2-3 days | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 65.4, 65.5 (auto-recall, auto-capture hooks)

## Problem Statement

Epic 65.4 and 65.5 add auto-recall and auto-capture hook templates. This epic wires them into `tapps_init` output and engagement-level templates, and documents trade-offs.

## Stories

### Story 65.6.1: tapps_init hook wiring

**Files:** `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`, `platform_hook_templates.py`, `platform_rules.py`

1. When `tapps_init` runs, add memory auto-recall and auto-capture to generated hooks
2. Config in `.tapps-mcp.yaml`:
   ```yaml
   memory_hooks:
     auto_recall:
       enabled: false  # conservative default
       max_results: 5
       min_score: 0.3
     auto_capture:
       enabled: false
       max_facts: 5
   ```
3. Engagement-level: high → both enabled; medium → auto_recall only; low → both disabled

**Acceptance criteria:**
- tapps_init generates both hooks when configured
- Engagement level affects default enablement

### Story 65.6.2: Engagement-level template variants

**Files:** `packages/tapps-mcp/src/tapps_mcp/prompts/platform_*_*.md`

1. Add memory hook section to platform rules per engagement level
2. High: "Memory auto-recall injects relevant memories before each turn. Auto-capture saves durable facts on session end."
3. Medium: "Memory auto-recall injects relevant memories. Auto-capture optional."
4. Low: "Memory is manual: call tapps_memory at session start/end."

**Acceptance criteria:**
- Platform rules reflect engagement-level memory behavior
- AGENTS.md updated

### Story 65.6.3: Documentation and trade-offs

**Files:** AGENTS.md, docs/

1. Document trade-offs:
   - Auto-recall: coverage vs noise; tune min_score
   - Auto-capture: flush prompt quality critical; avoid junk
2. Link to Epic 65.3 (capture prompt) for tuning
3. Add troubleshooting: "too much/too little memory injected"

**Acceptance criteria:**
- AGENTS.md memory section includes auto-recall/capture guidance
- Trade-offs and tuning documented

## Testing

- Unit: tapps_init output includes memory hooks when enabled
- Integration: full init → verify hooks present in generated files
