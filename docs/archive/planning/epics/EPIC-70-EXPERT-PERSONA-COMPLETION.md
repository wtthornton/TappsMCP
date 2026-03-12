# Epic 70: Expert Persona Completion (Agency-Personas Leverage)

<!-- docsmcp:start:metadata -->
**Status:** Complete
**Priority:** P2
**Estimated LOE:** ~0.5 day remaining (persona guidelines doc)
**Dependencies:** Epic 69 (Expert Personas — Complete)
**Source:** [TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md](../../reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md)
**2026 Research:** [2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md](../research/2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md)
<!-- docsmcp:end:metadata -->

## Should we do it? **Yes — done.** All 17 experts have persona; persona guidelines added to knowledge README (70.2). Improves consistency of `tapps_consult_expert` / `tapps_research`; no Context7 or MCP contract changes required.

---

<!-- docsmcp:start:goal -->
## Goal

Give **all 17 built-in domain experts** a short, stance-aware **persona** (1–3 sentences: role + default stance). Epic 69 added the persona field and wired it into answer assembly for two pilot experts (Security, Software Architecture). This epic completes personas for the remaining 15 experts so consultation responses have a consistent, expert-like voice across all domains.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Agency-agents personas use "Identity & Memory" and "Communication Style" to create distinct, memorable voices. TappMCP experts today are name + description + RAG; only Security and Software Architecture have a persona. Adding a concise persona for every expert improves clarity, disambiguation when multiple domains could apply, and consistency of tone (e.g. Testing: "default to recommending tests"; Accessibility: "WCAG 2.1 AA as baseline").
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] All 17 built-in experts in `ExpertRegistry.BUILTIN_EXPERTS` have a non-empty `persona` string (1–3 sentences) — **Done** (registry.py)
- [x] Personas are stance-aware (e.g. Testing: recommend tests; Security: assume breach; Accessibility: assume diverse abilities)
- [x] Knowledge README or EXPERT_CONFIG_GUIDE documents persona writing guidelines and examples — **Done** (knowledge/README.md "Persona Guidelines")
- [x] Existing tests pass; no regression in consultation answer assembly
- [x] Optional: AGENTS.md "Domain hints" table unchanged; personas are answer-assembly only
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

### Story 70.1: Define personas for remaining 15 built-in experts

> **As a** TappMCP maintainer, **I want** every built-in expert to have a short, stance-aware persona, **so that** consultation answers have a consistent identity and default stance per domain.

**Points:** 2 | **Size:** S

**Files:**
- `packages/tapps-core/src/tapps_core/experts/registry.py`

**Tasks:**
- [x] Add or extend `persona` for all 17 experts (Security, Software Architecture, Performance, Testing, Code Quality, DevOps, Data Privacy, Accessibility, UX, Documentation, AI Frameworks, Agent Learning, Observability, API Design, Cloud, Database, GitHub) — **Done** in registry.py
- [x] Keep each persona to 1–3 sentences: role + default stance
- [x] Ensure persona text is appropriate for prepending in italics before "Based on domain knowledge…" (no markdown, no code)

**Acceptance Criteria:**
- [x] All 17 entries in `BUILTIN_EXPERTS` have `persona` non-empty
- [x] Personas are concise and domain-appropriate
- [x] Unit tests that assert persona presence (e.g. in test_expert_registry or equivalent) updated or added

**Definition of Done:**
- [ ] Registry updated and tests pass
- [ ] No change to ExpertConfig schema (persona already exists)

---

### Story 70.2: Document persona guidelines for maintainers and business experts

> **As a** maintainer or consumer adding business experts, **I want** clear guidance on how to write expert personas, **so that** new experts get a consistent voice and stance.

**Points:** 1 | **Size:** S

**Files:**
- `packages/tapps-core/src/tapps_core/experts/knowledge/README.md` or `docs/EXPERT_CONFIG_GUIDE.md` (if present)
- Optional: `docs/reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md` (add "Persona guidelines" pointer)

**Tasks:**
- [x] Add a "Persona guidelines" section: 1–3 sentences, role + stance, no markdown/code in persona text, examples from 2–3 built-in experts
- [x] Mention that persona is prepended to consultation answers when set
- [x] Reference to TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY for agency-style personas

**Acceptance Criteria:**
- [x] Documentation explains what a good persona looks like and how it is used
- [x] At least two example personas (Security, Testing, Accessibility) quoted

**Definition of Done:**
- [ ] Docs updated and reviewed for clarity
<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- **ExpertRegistry:** `packages/tapps-core/src/tapps_core/experts/registry.py` — `BUILTIN_EXPERTS` list of `ExpertConfig`; all 17 have non-empty `persona`.
- **ExpertConfig.persona:** In `tapps_core/experts/models.py`; prepended in engine when set.
- **Engine:** `_build_answer` in `tapps_core/experts/engine.py` — `persona_line = f"*{expert.persona}*\n\n"` when `expert.persona` is non-empty.
- **Context7 / MCP_DOCKER:** No changes to Context7 or MCP tool contract. Persona improves `tapps_consult_expert` and `tapps_research` response quality when used via any transport (stdio or MCP_DOCKER gateway).
<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope

- Changing RAG retrieval or chunk content
- Adding new ExpertConfig fields (handled in Epic 71 if critical rules are added)
- Marketing/product/support personas (agency-agents non-technical domains out of scope)
<!-- docsmcp:end:non-goals -->
