# Epic 71: Expert Critical Rules & Default Stance (Agency-Personas Leverage)

<!-- docsmcp:start:metadata -->
**Status:** Complete
**Priority:** P2
**Estimated LOE:** 0 (optional: add critical_rules to 2–3 more experts, ~0.5 day)
**Dependencies:** Epic 69 (Expert Personas), optionally Epic 70 (Persona Completion)
**Source:** [TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md](../../reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md)
**2026 Research:** [2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md](../research/2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md)
<!-- docsmcp:end:metadata -->

## Should we do it? **Yes — done.** ExpertConfig has `critical_rules`; engine prepends it after persona; Security, Testing, and Accessibility have pilot rules. Improves domain-appropriate stance for `tapps_consult_expert` / `tapps_research` (MCP_DOCKER unchanged; no Context7 changes).

---

<!-- docsmcp:start:goal -->
## Goal

Add an optional **critical rules** or **default stance** to domain experts so that consultation answers follow domain-appropriate constraints (e.g. Security: "assume breach"; Testing: "prefer explicit tests over implicit behavior"; Reality-check style: "default to NEEDS WORK"). The engine will prepend these rules with the persona so the model "must follow" them when answering.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Agency-agents define "Critical Rules You Must Follow" per persona (e.g. Reality Checker: "Default to NEEDS WORK," "require overwhelming evidence"). TappMCP experts today have no equivalent; answers are built from RAG chunks + optional persona only. Adding an optional rules/stance field gives domain-appropriate caution and consistency without changing RAG or tool contract.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] ExpertConfig (and business expert config) support an optional `critical_rules` field (string) — **Done** (models.py)
- [x] Engine prepends critical rules to the answer-assembly prompt when set (after persona) — **Done** (engine.py: `**Critical rules:** {expert.critical_rules}`)
- [x] At least 3 pilot experts (Security, Testing, Accessibility) have non-empty critical_rules in registry — **Done**
- [x] Documentation updated (ExpertConfig, knowledge README or EXPERT_CONFIG_GUIDE)
- [x] All existing tests pass; new tests cover rules in answer assembly and optional field behavior
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

### Story 71.1: Add critical_rules / default_stance field to ExpertConfig and business config

> **As a** TappMCP maintainer, **I want** ExpertConfig to support an optional critical rules or default stance field, **so that** experts can enforce domain-appropriate constraints in consultation answers.

**Points:** 2 | **Size:** S

**Files:**
- `packages/tapps-core/src/tapps_core/experts/models.py` (ExpertConfig)
- `packages/tapps-core/src/tapps_core/experts/business_config.py` (BusinessExpertEntry if it mirrors ExpertConfig)
- `packages/tapps-mcp/src/tapps_mcp/experts/models.py` (re-exports if any)

**Tasks:**
- [ ] Add optional field: e.g. `critical_rules: str = ""` or `default_stance: str = ""` (single string preferred to avoid schema drift; multi-line allowed)
- [ ] Document field: "Optional rules or default stance prepended with persona; e.g. 'Assume breach' (Security), 'Default to recommending tests' (Testing)."
- [ ] Ensure business expert loader and registry can set the field (no breaking change to existing configs)
- [ ] Add unit tests for config with and without the field

**Acceptance Criteria:**
- [x] ExpertConfig and business expert entry support the new optional field
- [x] Default is empty string; existing experts unchanged
- [x] Tests pass

**Definition of Done:**
- [ ] Schema updated, backward compatible, tests pass

---

### Story 71.2: Wire critical rules into consultation answer assembly

> **As a** user of tapps_consult_expert, **I want** the expert's critical rules or default stance to be included in the answer prompt when set, **so that** responses follow domain-appropriate constraints.

**Points:** 2 | **Size:** M

**Files:**
- `packages/tapps-core/src/tapps_core/experts/engine.py` (_build_answer or equivalent)

**Tasks:**
- [ ] After persona preamble, if expert has non-empty critical_rules/default_stance, append a "Critical rules" or "Default stance" block to the prompt text used for answer assembly (e.g. "You must follow: {rules}" or "Default stance: {stance}")
- [ ] Keep total preamble (persona + rules) concise to avoid token bloat; recommend max 2–4 sentences for rules in docs
- [ ] Add unit tests: expert with persona only, expert with persona + rules, expert with rules only, expert with neither
- [ ] Ensure ConsultationResult or answer metadata does not require changes (rules are prompt-only)

**Acceptance Criteria:**
- [x] When critical_rules is set, it appears in the assembly prompt after persona
- [x] When empty, behavior unchanged from current (persona-only) behavior
- [x] Tests cover all combinations above

**Definition of Done:**
- [ ] Engine updated, tests pass, no regression in consultation output schema

---

### Story 71.3: Add pilot critical rules for Security, Testing, and Accessibility experts

> **As a** consumer of tapps_consult_expert, **I want** Security, Testing, and Accessibility experts to apply explicit default stances, **so that** answers are consistently cautious and actionable.

**Points:** 1 | **Size:** S

**Files:**
- `packages/tapps-core/src/tapps_core/experts/registry.py`

**Tasks:**
- [ ] Security: e.g. "Assume an attacker; require explicit justification for any exception to secure-by-default."
- [ ] Testing: e.g. "Prefer explicit tests over implicit behavior; never approve untested critical paths; default to recommending coverage."
- [ ] Accessibility: e.g. "WCAG 2.1 AA as baseline; assume diverse abilities and assistive technology; recommend testing with real assistive tech."
- [ ] Keep each rule to 1–2 sentences; avoid markdown in the field

**Acceptance Criteria:**
- [x] At least these three experts have non-empty critical_rules in BUILTIN_EXPERTS (Security, Testing, Accessibility)
- [x] Rules are concise and domain-appropriate
- [x] Documentation (knowledge README or EXPERT_CONFIG_GUIDE) updated with examples and guidance on writing rules

**Definition of Done:**
- [ ] Registry updated, docs updated, tests pass
<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- **ExpertConfig:** `tapps_core/experts/models.py` — `critical_rules: str = ""` (optional).
- **Engine:** `tapps_core/experts/engine.py` — `_build_answer` prepends `**Critical rules:** {expert.critical_rules}\n\n` when set (after persona).
- **Context7 / MCP_DOCKER:** No contract changes. Critical rules improve expert answer framing for `tapps_consult_expert` and `tapps_research` via any transport.
<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope

- Changing RAG retrieval or chunk selection
- Adding more than one new optional field (communication_style is separate — Epic 73)
- Enforcing rules in code (rules are prompt hints for the answer generator)
<!-- docsmcp:end:non-goals -->
