# 2026 Research: Epics 70–73 (Expert Personas) — Deep Dive & Recommendation

**Date:** 2026-03-11  
**Scope:** Epics 70 (Persona Completion), 71 (Critical Rules), 72 (Knowledge Enrichment), 73 (Communication Style)  
**Sources:** Codebase audit (registry, engine, models, knowledge), [TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md](../../reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md), [2026-AGENCY-AGENTS-LEVERAGE-FOR-TAPPSMCP-DOCSMCP.md](2026-AGENCY-AGENTS-LEVERAGE-FOR-TAPPSMCP-DOCSMCP.md), Context7/MCP tooling (tapps_consult_expert, tapps_research, MCP_DOCKER).

---

## 1. Executive summary

| Question | Answer |
|---------|--------|
| **Should we do Epics 70–73?** | **Yes.** Most of 70, 71, and 73 is already implemented; remaining work is documentation, optional pilot expansion, and **Epic 72 (knowledge content)**. Doing it improves consistency of expert voice, domain-appropriate stance, and actionable answers without changing the tool contract. |
| **Context7 / MCP_DOCKER relevance** | `tapps_consult_expert` (and `tapps_research`) are exposed via MCP_DOCKER; expert persona/rules/style improve the quality of those tool responses. Context7 enriches `tapps_research` and docs fallback when RAG is empty; expert preamble (persona + rules + style) steers how that combined answer is framed. Completing 70–73 makes the expert path more consistent with 2026 best practices (clear identity, rules, actionable content). |
| **Remaining LOE** | ~2–5 days: Epic 70 doc only; Epic 71 optional expansion; **Epic 72** 1–1.5 wk (content across 5+ domains); Epic 73 optional expansion or close as done. |

---

## 2. Implementation audit (codebase vs epics)

### 2.1 Epic 70: Expert Persona Completion

| Story | Epic ask | Current state |
|-------|----------|---------------|
| 70.1 Define personas for remaining 15 experts | All 17 built-in experts have non-empty `persona` (1–3 sentences, role + stance) | **Done.** All 17 experts in `ExpertRegistry.BUILTIN_EXPERTS` have `persona` set (registry.py). |
| 70.2 Document persona guidelines | Knowledge README or EXPERT_CONFIG_GUIDE with persona writing guidelines + examples | **Partial.** Knowledge README has "Knowledge Enrichment Patterns" but no dedicated "Persona guidelines" section. TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY exists as reference. |

**Verdict:** 70.1 complete. 70.2: add a short "Persona guidelines" subsection (or link to TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY) in `knowledge/README.md` or docs; ~0.5 day.

---

### 2.2 Epic 71: Expert Critical Rules & Default Stance

| Story | Epic ask | Current state |
|-------|----------|---------------|
| 71.1 Add critical_rules field to ExpertConfig | Optional field, backward compatible | **Done.** `ExpertConfig.critical_rules: str = ""` in models.py; business config supports it. |
| 71.2 Wire critical rules into answer assembly | Engine prepends rules after persona | **Done.** `engine._build_answer` prepends `**Critical rules:** {expert.critical_rules}` when set (engine.py). |
| 71.3 Pilot critical rules for Security, Testing, Accessibility | At least 3 experts with non-empty critical_rules | **Done.** Security, Testing, Accessibility have `critical_rules` in registry.py. |

**Verdict:** Epic 71 complete. Optional: add `critical_rules` to 2–3 more experts (e.g. Performance, Data Privacy, Code Quality) for consistency; ~0.5 day.

---

### 2.3 Epic 72: Expert Knowledge Enrichment

| Story | Epic ask | Current state |
|-------|----------|---------------|
| 72.1 Success metrics / Definition of done | ≥5 domains with success metrics in key knowledge files | **Partial.** Some files (e.g. testing/best-practices, code-quality/quality-gates, accessibility) have related content; not all 5 domains have a consistent `## Success metrics` section. |
| 72.2 Workflow hints (Typical steps / Recommended process) | ≥5 domains with workflow sections | **Partial.** Some files (threat-modeling, test-strategies, restful-api-design, migration-strategies, ci-cd-patterns) have steps; need audit for consistent headers. |
| 72.3 Deliverable templates | ≥3 domains with template/checklist | **Partial.** security/secure-coding-practices, testing/best-practices, accessibility/testing-accessibility have checklist/template content; README already documents the pattern. |
| 72.4 Document enrichment patterns in README | Knowledge README describes success metrics, workflow, templates, when-to-use | **Done.** `knowledge/README.md` has "Knowledge Enrichment Patterns" with all four (success metrics, typical steps, deliverable templates, when-to-use). |

**Verdict:** 72.4 complete. 72.1–72.3 need content work: add or standardize sections across 5 (metrics), 5 (workflow), 3 (templates) domains. LOE ~1–1.5 wk content-heavy.

---

### 2.4 Epic 73: Expert Communication Style

| Story | Epic ask | Current state |
|-------|----------|---------------|
| 73.1 Add communication_style field and wire into answer assembly | Optional field; engine appends after persona + rules | **Done.** `ExpertConfig.communication_style: str = ""` in models.py; `_build_answer` appends `*Style: {expert.communication_style}*` when set. Security and Testing have non-empty `communication_style` in registry. |

**Verdict:** Epic 73 complete. Optional: add `communication_style` to 1–2 more experts (e.g. Accessibility) or document "optional; persona + critical_rules often sufficient" and close.

---

## 3. Context7 and MCP_DOCKER relevance

- **tapps_consult_expert** is the primary expert tool. Persona, critical_rules, and communication_style are assembled in `_build_answer` and sent as preamble to the answer generator; they directly improve response consistency and domain stance when users call this tool (including via MCP_DOCKER).
- **tapps_research** combines expert consultation with docs lookup. When expert RAG has no matches, Context7 (or bundled docs) can fill fallback content; the same expert preamble (persona + rules + style) frames how the combined answer is presented. So completing 70–73 improves both “expert-only” and “expert + docs” flows.
- **MCP_DOCKER** exposes TappsMCP (and optionally DocsMCP, Context7) through a single gateway. Tool descriptors (e.g. `tapps_consult_expert.json`) do not change; only the server-side assembly of the expert prompt changes. No MCP contract or Docker profile changes required for 70–73.
- **Context7 API** (used inside `tapps_lookup_docs` / `tapps_research`): Expert enrichment (70–73) is orthogonal to Context7—Context7 supplies up-to-date library docs; experts supply domain voice and rules. Both improve answer quality; 70–73 do not depend on Context7.

**Conclusion:** Epics 70–73 improve the quality of `tapps_consult_expert` and `tapps_research` responses. Context7 and MCP_DOCKER are complementary; no changes to Context7 or MCP_DOCKER are required to “do” 70–73.

---

## 4. 2026 best practices alignment

- **Agency-agents leverage (2026-AGENCY-AGENTS-LEVERAGE):** Document recommends enriching experts with identity, critical rules, success metrics, workflow. Epics 70–73 implement that; current codebase already implements most of it.
- **Tool effectiveness (2026-MCP-TOOLS-BEST-PRACTICES):** Keeping tool count and descriptions stable while improving answer quality (persona + rules + better knowledge) aligns with “curate by task” and “deterministic, tool-driven” model.
- **TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY:** “Persona + critical rules + knowledge (success metrics, workflow, templates)” is the recommended scope; 70–73 match. Communication style is optional; we have it implemented for two pilots.

---

## 5. Recommendation

1. **Do it.** Treat 70, 71, 73 as **substantially complete**; update epic/story status and add the small remaining doc/optional items. Treat **72** as the main remaining epic: content-only, 1–1.5 wk.
2. **Epic 70:** Mark 70.1 Complete. Complete 70.2: add "Persona guidelines" (or pointer to TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY) in knowledge README or EXPERT_CONFIG_GUIDE; then mark epic Complete.
3. **Epic 71:** Mark Complete. Optionally add critical_rules to 2–3 more experts in a follow-up.
4. **Epic 72:** Keep as Draft/Open. Prioritize 72.1–72.3: audit knowledge dirs, add `## Success metrics`, `## Typical steps` / `## Recommended process`, and `## Checklist` / `## Template` to meet acceptance criteria (5, 5, 3 domains). 72.4 already done.
5. **Epic 73:** Mark Complete. Optionally add communication_style to more experts or document as optional and close.
6. **Context7 / MCP_DOCKER:** No changes required. Document in epics that 70–73 improve `tapps_consult_expert` and `tapps_research` quality when used via any transport (stdio, MCP_DOCKER).

---

## 6. References

- `packages/tapps-core/src/tapps_core/experts/registry.py` — BUILTIN_EXPERTS (all 17 with persona; Security, Testing, Accessibility with critical_rules; Security, Testing with communication_style)
- `packages/tapps-core/src/tapps_core/experts/models.py` — ExpertConfig (persona, critical_rules, communication_style)
- `packages/tapps-core/src/tapps_core/experts/engine.py` — _build_answer (persona_line, rules_line, style_line)
- `packages/tapps-core/src/tapps_core/experts/knowledge/README.md` — Knowledge Enrichment Patterns (72.4)
- `docs/reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md`
- `docs/planning/research/2026-AGENCY-AGENTS-LEVERAGE-FOR-TAPPSMCP-DOCSMCP.md`
- `docs/planning/research/2026-BEST-PRACTICES-NEXT-STEPS-PLAN.md` (Phase 4)
- MCP_DOCKER: `mcps/user-MCP_DOCKER/tools/tapps_consult_expert.json`, `tapps_research.json`
