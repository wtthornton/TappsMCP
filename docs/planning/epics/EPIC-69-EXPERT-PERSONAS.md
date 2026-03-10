# Epic 69: Expert Personas

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P2
**Estimated LOE:** ~1 week (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Add an optional persona (or voice) field to domain experts so that consultation responses have a consistent identity and scope. Experts today are name + domain + knowledge only; a short persona would clarify who is speaking and improve disambiguation when multiple domains could apply.

**Tech Stack:** TappMCP

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Research showed experts are defined as ExpertConfig + Markdown knowledge; the answer is built from expert name, domain, and RAG context with no explicit persona. Adding an optional persona improves clarity and consistency of expert responses.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] ExpertConfig (and BusinessExpertEntry) support optional persona field
- [ ] _build_answer in engine prepends persona when set
- [ ] Built-in registry includes persona for at least 2 pilot experts
- [ ] Knowledge README documents how to write personas
- [ ] All existing tests pass; new tests cover persona in answer assembly

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 69.1 -- Add persona field to ExpertConfig and business config

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement add persona field to expertconfig and business config
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Add persona field to ExpertConfig and business config is implemented, tests pass, and documentation is updated.

---

### 69.2 -- Wire persona into consultation answer assembly

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement wire persona into consultation answer assembly
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Wire persona into consultation answer assembly is implemented, tests pass, and documentation is updated.

---

### 69.3 -- Add pilot personas and docs

**Points:** 1

Describe what this story delivers...

**Tasks:**
- [ ] Implement add pilot personas and docs
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Add pilot personas and docs is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- ExpertConfig in tapps_core/experts/models.py
- Engine._build_answer in tapps_core/experts/engine.py
- ExpertRegistry.BUILTIN_EXPERTS in registry.py

**Project Structure:** 47 packages, 799 modules, 3160 public APIs

### Expert Recommendations

- **Security Expert** (70%): Based on domain knowledge (3 source(s), confidence 70%):
- **Software Architecture Expert** (61%): Based on domain knowledge (3 source(s), confidence 61%):

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Changing RAG or retrieval; persona is answer-assembly only

<!-- docsmcp:end:non-goals -->
