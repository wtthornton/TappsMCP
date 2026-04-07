# Epic 94: Expert System Extraction — Delegate to AgentForge

<!-- docsmcp:start:metadata -->
**Status:** Completed (superseded by v2.0.0)
**Priority:** P1 - High
**Estimated LOE:** ~1-2 weeks (1 developer)
**Dependencies:** AgentForge EPIC-13 (Expert Migration — must land first so agents exist to delegate to)
**Blocks:** EPIC-96 (Profiling/Session Dedup — cleaner after expert removal)

> **Closed (2026-04-07):** This epic is obsolete. The expert system (23 modules,
> 184 knowledge files, 19 shims) was fully deleted in v2.0.0 (EPIC-93 Phase 2,
> commit d651a14). No delegation to AgentForge was needed — the code was removed
> outright rather than migrated.

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that tapps-mcp's expert system (tapps_consult_expert, tapps_manage_experts, tapps_research, tapps_list_experts) is removed in favor of AgentForge's native agent catalog. The expert system duplicates agent orchestration capabilities that AgentForge already provides — domain routing, knowledge injection, lifecycle management, and dynamic creation. Extracting it reduces tapps-mcp's surface area by ~4 tools and eliminates an entire subsystem (expert routing, RAG retrieval, business expert CRUD, knowledge directory management).

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Remove the built-in expert system from tapps-mcp and replace it with a thin delegation layer that routes expert queries to AgentForge's agent catalog. Deprecate tapps_consult_expert, tapps_manage_experts, tapps_research, and tapps_list_experts with a migration path to AgentForge agents.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

tapps-mcp's expert system maintains 17+ built-in domain experts with auto-detection routing, RAG knowledge bases, confidence scoring, and a full CRUD lifecycle for custom business experts. This is a parallel agent infrastructure that duplicates AgentForge's config matching (TF-IDF/keyword scoring), workspace context (system prompt composition with knowledge injection), config CRUD, and proposal engine. Maintaining both systems means bugs get fixed in one but not the other, knowledge bases diverge, and users must learn two different expert/agent paradigms. By extracting, tapps-mcp becomes focused on what it does uniquely well: deterministic quality analysis tooling.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] tapps_consult_expert marked deprecated with migration guidance pointing to AgentForge
- [ ] tapps_manage_experts marked deprecated — CRUD redirects to AgentForge config endpoints
- [ ] tapps_research marked deprecated — researcher agent in AgentForge replaces it
- [ ] tapps_list_experts returns AgentForge catalog filtered by agent_type=expert
- [ ] Expert routing code (domain detection and RAG retrieval) removed from tapps-mcp codebase
- [ ] Knowledge directory scaffolding (.tapps-mcp/experts/) documented as migrated to AgentForge workspace
- [ ] All existing expert tests updated or removed
- [ ] tapps-mcp tool count reduced by 4 (consult_expert and manage_experts and research and list_experts)

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 94.1 -- Deprecation Notices on Expert Tools

**Points:** 2

Add deprecation warnings to tapps_consult_expert, tapps_manage_experts, tapps_research, and tapps_list_experts. Warnings include migration instructions pointing to AgentForge's POST /tasks/invoke and config CRUD endpoints. Tools still function during transition period.

**Tasks:**
- [ ] Implement deprecation notices on expert tools
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Deprecation Notices on Expert Tools is implemented, tests pass, and documentation is updated.

---

### 94.2 -- AgentForge Delegation Shim for tapps_consult_expert

**Points:** 3

Replace tapps_consult_expert's internal expert routing with an HTTP call to AgentForge's POST /tasks/invoke. The shim maps domain to an agent config hint, forwards the question as the prompt, and returns the response in the existing tapps format. This provides backward compatibility during migration.

**Tasks:**
- [ ] Implement agentforge delegation shim for tapps_consult_expert
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** AgentForge Delegation Shim for tapps_consult_expert is implemented, tests pass, and documentation is updated.

---

### 94.3 -- Remove Built-in Expert Definitions

**Points:** 3

Remove the 17 built-in expert definitions (domain configs, routing weights, default knowledge) from tapps-mcp's codebase. These are now AGENT.md configs in AgentForge's catalog. Update any internal references.

**Tasks:**
- [ ] Implement remove built-in expert definitions
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Remove Built-in Expert Definitions is implemented, tests pass, and documentation is updated.

---

### 94.4 -- Remove Business Expert CRUD Subsystem

**Points:** 3

Remove tapps_manage_experts and its supporting code: experts.yaml parsing, knowledge directory scaffolding, auto_generate analysis, and validation logic. Document migration path for existing business experts to AgentForge configs.

**Tasks:**
- [ ] Implement remove business expert crud subsystem
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Remove Business Expert CRUD Subsystem is implemented, tests pass, and documentation is updated.

---

### 94.5 -- Remove RAG Knowledge Retrieval Engine

**Points:** 5

Remove the expert RAG retrieval subsystem: knowledge directory scanning, document chunking, embedding/similarity search, and context injection. This is the largest code removal. tapps_lookup_docs (Context7) is NOT affected — it stays as a standalone tool.

**Tasks:**
- [ ] Implement remove rag knowledge retrieval engine
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Remove RAG Knowledge Retrieval Engine is implemented, tests pass, and documentation is updated.

---

### 94.6 -- Update Tests and Documentation

**Points:** 2

Remove expert-related test suites. Update AGENTS.md, CONFIG_REFERENCE.md, and any docs referencing expert tools. Update CLAUDE.md pipeline instructions to route expert queries through AgentForge.

**Tasks:**
- [ ] Implement update tests and documentation
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Update Tests and Documentation is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- The delegation shim (story 2) is temporary — it exists only during the migration window so existing CLAUDE.md instructions don't break immediately
- tapps_lookup_docs is NOT part of this extraction — it's a pure data retrieval tool that stays in tapps-mcp
- The RAG engine removal (story 5) is the largest change — audit all imports before deleting
- Expert feedback weights (tapps_feedback for domain routing) should be migrated to AgentForge's feedback system
- Consider a feature flag to toggle between native experts and AgentForge delegation during testing

### Cross-repo Coordination with AgentForge EPIC-13

AgentForge EPIC-13 research findings that affect this epic:

- **AgentConfig new fields:** AgentForge adds `agent_type: str`, `domain: str`, `knowledge_version: str` to distinguish expert agents from task agents. The delegation shim (94.2) should pass `agent_hint` using the `domain` field.
- **RAG knowledge budget:** AgentForge expert agents use 1500+ token bodies (revised up from 800). Validate that the delegation shim's responses are comparable quality to tapps-mcp's internal RAG retrieval.
- **Validation approach:** AgentForge EPIC-13.7 uses G-Eval with 5 criteria (factual_accuracy, completeness, actionability, domain_specificity, no_hallucination) for side-by-side comparison. Run the same G-Eval on the delegation shim (94.2) to confirm no regression before removing built-in experts (94.3).
- **tapps_manage_experts action mapping:** AgentForge maps `add→POST /agents`, `remove→DELETE /agents/{name}`, `scaffold→POST /agents/propose`, `validate→dry-run parse`, `auto_generate→proposal engine`. The CRUD deprecation (94.4) should reference this mapping.
- **Business expert migration script:** AgentForge EPIC-13.5 includes a script to read `.tapps-mcp/experts/` and emit AGENT.md configs. Story 94.4 should coordinate with this — don't delete the experts directory until AgentForge has migrated them.

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Modifying tapps_lookup_docs or Context7 integration
- Changing tapps-mcp's quality scoring tools
- Building new features — this is purely extraction and delegation

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 8 acceptance criteria met | 0/8 | 8/8 | Checklist review |
| All 6 stories completed | 0/6 | 6/6 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 94.1: Deprecation Notices on Expert Tools
2. Story 94.2: AgentForge Delegation Shim for tapps_consult_expert
3. Story 94.3: Remove Built-in Expert Definitions
4. Story 94.4: Remove Business Expert CRUD Subsystem
5. Story 94.5: Remove RAG Knowledge Retrieval Engine
6. Story 94.6: Update Tests and Documentation

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Breaking change for users who call tapps_consult_expert directly in their CLAUDE.md workflows | Medium | Medium | Deprecation notices (94.1) with migration guidance run for 1+ release before removal. Delegation shim (94.2) provides backward compat during transition. |
| RAG knowledge quality may differ between tapps-mcp's retrieval and AgentForge's system prompt injection | Medium | High | Run G-Eval validation (5 criteria, 5 queries per domain) on delegation shim before removing built-in experts. AgentForge raised RAG budget to 1500+ tokens. |
| AgentForge EPIC-13 must land first — this epic is blocked until expert agents exist in the catalog | High | High | Hard dependency — story 94.2 requires all 17 expert AGENT.md configs to exist in AgentForge. Verify via GET /agents?agent_type=expert before starting. |
| Business expert data loss — .tapps-mcp/experts/ deleted before migration | Medium | High | Coordinate with AgentForge EPIC-13.5 migration script. Don't delete experts directory until confirmed migrated. |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| Files will be determined during story refinement | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Acceptance criteria pass rate | 0% | 100% | CI pipeline |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
