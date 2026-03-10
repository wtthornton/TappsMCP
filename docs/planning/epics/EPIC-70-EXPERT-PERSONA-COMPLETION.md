# Epic 70: Expert Persona Completion (Agency-Personas Leverage)

<!-- docsmcp:start:metadata -->
**Status:** Draft
**Priority:** P2
**Estimated LOE:** ~3–5 days (1 developer)
**Dependencies:** Epic 69 (Expert Personas — Complete)
**Source:** [TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md](../../reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md)
<!-- docsmcp:end:metadata -->

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

- [ ] All 17 built-in experts in `ExpertRegistry.BUILTIN_EXPERTS` have a non-empty `persona` string (1–3 sentences)
- [ ] Personas are stance-aware (e.g. Testing: recommend tests; Security: assume breach; Accessibility: assume diverse abilities)
- [ ] Knowledge README or EXPERT_CONFIG_GUIDE documents persona writing guidelines and examples
- [ ] Existing tests pass; no regression in consultation answer assembly
- [ ] Optional: AGENTS.md "Domain hints" table unchanged; personas are answer-assembly only
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
- [ ] Add or extend `persona` for: Performance, Testing, Code Quality, DevOps, Data Privacy, Accessibility, UX, Documentation, AI Frameworks, Agent Learning, Observability, API Design, Cloud, Database, GitHub (15 experts; Security and Software Architecture already have personas)
- [ ] Keep each persona to 1–3 sentences: role + default stance (e.g. "Senior test architect; default to recommending tests and coverage; never approve untested critical paths.")
- [ ] Ensure persona text is appropriate for prepending in italics before "Based on domain knowledge…" (no markdown, no code)

**Acceptance Criteria:**
- [ ] All 17 entries in `BUILTIN_EXPERTS` have `persona` non-empty
- [ ] Personas are concise and domain-appropriate
- [ ] Unit tests that assert persona presence (e.g. in test_expert_registry or equivalent) updated or added

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
- [ ] Add a "Persona guidelines" section: 1–3 sentences, role + stance, no markdown/code in persona text, examples from 2–3 built-in experts
- [ ] Mention that persona is prepended to consultation answers when set
- [ ] If business experts are documented elsewhere, add a pointer to persona field and guidelines

**Acceptance Criteria:**
- [ ] Documentation explains what a good persona looks like and how it is used
- [ ] At least two example personas (e.g. Security, Testing) quoted

**Definition of Done:**
- [ ] Docs updated and reviewed for clarity
<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- **ExpertRegistry:** `packages/tapps-core/src/tapps_core/experts/registry.py` — `BUILTIN_EXPERTS` list of `ExpertConfig`
- **ExpertConfig.persona:** Already in `tapps_core/experts/models.py`; optional string, prepended in engine when set
- **Engine:** `_build_answer` in `tapps_core/experts/engine.py` — `persona_line = f"*{expert.persona}*\n\n"` when `expert.persona` is non-empty
- **Epic 69:** Delivered persona field, engine prepend, and pilot personas for Security and Software Architecture only
<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope

- Changing RAG retrieval or chunk content
- Adding new ExpertConfig fields (handled in Epic 71 if critical rules are added)
- Marketing/product/support personas (agency-agents non-technical domains out of scope)
<!-- docsmcp:end:non-goals -->
