# Epic 73: Expert Communication Style (Agency-Personas Leverage — Optional)

<!-- docsmcp:start:metadata -->
**Status:** Draft
**Priority:** P3
**Estimated LOE:** ~2–3 days (1 developer)
**Dependencies:** Epic 69 (Expert Personas); optionally Epic 70, 71
**Source:** [TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md](../../reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md)
<!-- docsmcp:end:metadata -->

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

- [ ] ExpertConfig (and business expert config) support an optional `communication_style` or `example_phrases` field (string)
- [ ] Engine appends this to the answer-assembly prompt when set (e.g. after rules, before "Based on domain knowledge…" or at end of preamble)
- [ ] At least 2 pilot experts have non-empty communication style (e.g. Testing, Security)
- [ ] Documentation updated; total preamble (persona + rules + style) kept concise
- [ ] All existing tests pass; new tests cover optional field
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
- [ ] Optional field added and wired; default empty; backward compatible
- [ ] At least 2 experts have non-empty communication_style
- [ ] Tests pass; documentation updated

**Definition of Done:**
- [ ] Schema, engine, registry, docs, and tests updated
<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- **Order of preamble:** persona → critical_rules (Epic 71) → communication_style (this epic) → "Based on domain knowledge…"
- **Token budget:** Keep communication_style to one sentence or 2–3 short phrases; document max length if needed
<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope

- Changing RAG or retrieval
- Adding more than one new optional field in this epic
- Making communication style mandatory
<!-- docsmcp:end:non-goals -->
