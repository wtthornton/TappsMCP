# Epic 73: Expert Communication Style (Agency-Personas Leverage — Optional)

<!-- docsmcp:start:metadata -->
**Status:** Complete
**Priority:** P3
**Estimated LOE:** 0 (optional: add communication_style to more experts)
**Dependencies:** Epic 69 (Expert Personas); optionally Epic 70, 71
**Source:** [TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md](../../reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md)
**2026 Research:** [2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md](../research/2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md)
<!-- docsmcp:end:metadata -->

## Should we do it? **Yes — done.** ExpertConfig has `communication_style`; engine appends it after persona and critical_rules. Security and Testing have pilot values. Optional: add to more experts or document "persona + critical_rules often sufficient." No Context7 or MCP_DOCKER changes.

---

<!-- docsmcp:start:goal -->
## Goal

Add an optional **communication style** or **example phrases** hint to domain experts so that consultation answers use tonality and phrasing aligned with the domain (e.g. Testing: "Recommend a test for…"; Security: "Assume an attacker…"). This epic is **optional** and lower priority; it can be deferred or dropped if persona + critical rules (Epic 70–71) and knowledge enrichment (Epic 72) are sufficient.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Agency-agents define "Communication Style" and example phrases per persona. TappMCP could append a short "Respond in this style: …" when assembling the answer prompt. Benefit: more consistent tone (e.g. Testing: recommend tests; Security: assume threat). Risk: prompt bloat and marginal gain if persona + rules already steer tone.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] ExpertConfig (and business expert config) support an optional `communication_style` field (string) — **Done** (models.py)
- [x] Engine appends this to the answer-assembly prompt when set (after persona and critical_rules) — **Done** (engine.py: `*Style: {expert.communication_style}*`)
- [x] At least 2 pilot experts have non-empty communication_style (Testing, Security) — **Done**
- [x] Documentation updated; total preamble (persona + rules + style) kept concise
- [x] All existing tests pass; new tests cover optional field
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

### Story 73.1: Add communication_style field and wire into answer assembly

> **As a** TappMCP maintainer, **I want** experts to optionally define a communication style or example phrases, **so that** consultation answers use domain-appropriate tone and phrasing.

**Points:** 2 | **Size:** S

**Files:**
- `packages/tapps-core/src/tapps_core/experts/models.py` (ExpertConfig)
- `packages/tapps-core/src/tapps_core/experts/business_config.py` (if applicable)
- `packages/tapps-core/src/tapps_core/experts/engine.py` (_build_answer)
- `packages/tapps-core/src/tapps_core/experts/registry.py` (pilot values for 2 experts)

**Tasks:**
- [ ] Add optional `communication_style: str = ""` to ExpertConfig (and business entry). Description: "Optional hint for tone/phrasing; e.g. 'Recommend a test for…' (Testing), 'Assume an attacker…' (Security)."
- [ ] In engine, after persona and critical_rules (if present), if communication_style is set, append e.g. "Respond in this style: {communication_style}" to the preamble. Keep to one short sentence or 2–3 example phrases.
- [ ] Add pilot values for Testing and Security experts in registry
- [ ] Add unit tests: expert with/without communication_style; ensure no regression when empty
- [ ] Update knowledge README or EXPERT_CONFIG_GUIDE with guidance (concise; avoid prompt bloat)

**Acceptance Criteria:**
- [x] Optional field added and wired; default empty; backward compatible
- [x] At least 2 experts have non-empty communication_style (Security, Testing)
- [x] Tests pass; documentation updated

**Definition of Done:**
- [ ] Schema, engine, registry, docs, and tests updated
<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- **Order of preamble:** persona → critical_rules (Epic 71) → communication_style (this epic) → "Based on domain knowledge…"
- **Token budget:** Keep communication_style to one sentence or 2–3 short phrases; document max length if needed.
- **Context7 / MCP_DOCKER:** No contract changes. Style improves expert answer tone for `tapps_consult_expert` and `tapps_research` via any transport.
<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope

- Changing RAG or retrieval
- Adding more than one new optional field in this epic
- Making communication style mandatory
<!-- docsmcp:end:non-goals -->
