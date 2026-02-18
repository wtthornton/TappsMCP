# TappsMCP Expert + Context7 Integration — Implementation Plan

**Source:** [TAPPS_MCP_IMPROVEMENT_RECOMMENDATIONS.md](../../../HomeIQ/implementation/TAPPS_MCP_IMPROVEMENT_RECOMMENDATIONS.md)  
**Created:** 2026-02-18  
**Revised:** 2026-02-18 (reviewed via Context7 + TappsMCP)  
**Status:** Draft  
**Audience:** TappsMCP maintainers

---

## Review Findings (Context7 + TappsMCP)

- **tapps_consult_expert (testing-strategies)** on a plan-related query returned `chunks_used: 0`, `source_count: 0` — validates the exact scenario the plan addresses.
- **tapps_lookup_docs(pytest, "fixtures configuration monkeypatch env")** returned rich Context7 content (fixtures, monkeypatch, setenv/delenv, configuration) — proves fallback would work and is suitable for Story 10.4 content sourcing.
- **Existing code:** `experts/rag_warming.py` has `TECH_STACK_TO_EXPERT_DOMAINS` (library → domain); invert for domain→library inference. `domain_utils.py` maps `testing-strategies` → knowledge dir `testing`.
- **Sync/async:** `consult_expert()` is sync; `LookupEngine.lookup()` and `tapps_lookup_docs` are async — plan must address integration (sync wrapper or `asyncio.run()`).
- **Security:** Merged content must pass governance (PII/secrets) and RAG safety; response size limits recommended.

---

## Summary

The recommendations document captures real agent behavior: when `tapps_consult_expert` returns zero RAG chunks and low confidence, agents often stop there instead of calling `tapps_lookup_docs`. This plan implements enhancements so agents get better combined guidance from experts and library docs with fewer round-trips.

| # | Recommendation | Agreement | Priority | LOE |
|---|----------------|-----------|----------|-----|
| 1 | Auto-fallback to Context7 when expert RAG is empty | ✅ Yes | P1 | Medium |
| 2 | Workflow: "expert + doc lookup" for testing/library questions | ✅ Yes | P1 | Low |
| 3 | Stronger, structured "call tapps_lookup_docs" when no RAG | ✅ Yes | P1 | Low |
| 4 | Broader expert KB coverage (test config, URLs, env) | ✅ Yes | P2 | Low–Medium |
| 5 | Optional single `tapps_research` tool (expert + Context7) | ✅ Yes | P2 | Medium |

---

## Epic 10: Expert + Context7 Integration

**Epic ID:** EPIC-10  
**Priority:** P1  
**Dependencies:** Epic 2 (Knowledge & Docs), Epic 3 (Expert System)  
**Estimated LOE:** ~2–3 weeks (1 developer)

---

## Stories

### 10.1 — Auto-fallback to Context7 when expert RAG is empty (P1)

**Points:** 5  
**Goal:** When expert consultation returns `chunks_used=0` (or `source_count=0`), automatically call `tapps_lookup_docs` for inferred libraries/topics and merge that content into the response.

**Tasks:**
- [ ] Extend `consult_expert()` in `experts/engine.py`:
  - After RAG search, if `len(chunks) == 0` (or `len(sources) == 0`):
    - Infer `library` and `topic` from question + domain (see 10.1.1)
    - Call `LookupEngine.lookup()` via sync wrapper: `consult_expert` is sync, `LookupEngine.lookup()` is async — add `knowledge.lookup.sync_lookup()` that uses `asyncio.run()` or reuse existing async-in-sync pattern if present
    - Merge doc content into the answer with clear attribution (e.g. "## Library docs (via Context7)")
- [ ] Derive domain → library mapping from `rag_warming.TECH_STACK_TO_EXPERT_DOMAINS` (invert: each domain maps to its primary library) and extend for topics (see 10.1.1)
- [ ] Make auto-fallback configurable (e.g. `TAPPS_MCP_EXPERT_AUTO_LOOKUP_DOCS=true`) to allow opt-out
- [ ] Ensure merged response passes governance (PII/secret filter) and RAG safety before return
- [ ] Enforce response size limit (e.g. cap merged doc content to ~3000 chars or token budget) to avoid context overflow
- [ ] Add `fallback_used: true`, `fallback_library`, `fallback_topic` to response when fallback ran

**Definition of Done:**
- Empty RAG triggers Context7 lookup for inferable libraries
- Single response contains both expert guidance (or placeholder) and library docs
- Unit tests for inference logic and fallback behavior

---

#### 10.1.1 — Domain → library inference

Derive mapping from `rag_warming.TECH_STACK_TO_EXPERT_DOMAINS` (invert) and extend for topic hints:

| Domain | Default library | Topic hints |
|--------|-----------------|-------------|
| testing-strategies | pytest | fixtures, configuration, monkeypatch, env vars, base URL |
| api-design-integration | fastapi | endpoints, validation, middleware, testing |
| database-data-management | sqlalchemy | models, sessions, migrations |
| cloud-infrastructure | docker | dockerfile, compose |
| development-workflow | (git/ci varies) | — |
| security | — | varies; may need topic-only lookup or skip fallback |
| code-quality-analysis | ruff | linting, formatting |
| observability-monitoring | prometheus | metrics, alerting |

Use simple keyword matching on `question` to pick topic (e.g. "base URL" → "fixtures and configuration", "fixtures" → "fixtures", "monkeypatch" → "monkeypatch env vars"). Knowledge dir mapping: `domain_utils.DOMAIN_TO_DIRECTORY_MAP` (e.g. `testing-strategies` → `testing`).

---

### 10.2 — Workflow: “Expert + doc lookup” for testing/library questions (P1)

**Points:** 2  
**Goal:** Update AGENTS.md, `agents_template.md`, and `recommended_workflow` to explicitly couple expert and doc lookup for library-specific questions.

**Tasks:**
- [ ] Add new subsection to AGENTS.md and `agents_template.md`:

  **"For testing / pytest questions"**  
  Prefer or combine: `tapps_lookup_docs(library="pytest", topic="fixtures and configuration")` and optionally `tapps_consult_expert(domain="testing-strategies")`. If the expert returns low confidence or no chunks, treat that as a signal to call `tapps_lookup_docs` for the relevant library (e.g. pytest, unittest).

- [ ] Add general rule: **"Domain-specific questions that mention a library** (e.g. pytest, FastAPI) **should trigger both expert and doc lookup** in your plan, or the server can auto-fallback (see Epic 10)."
- [ ] Update `recommended_workflow` in `tapps_server_info` response (see `server.py` and `common/nudges.py`) to include this guidance when applicable; also ensure `pipeline.stage_tools.research` hints at combined expert+lookup for library questions
- [ ] Update `src/tapps_mcp/prompts/research.md` and `src/tapps_mcp/prompts/platform_*.md` if they reference expert-only flow

**Definition of Done:**
- AGENTS.md includes explicit expert + doc lookup coupling
- Server `recommended_workflow` reflects this when returned

---

### 10.3 — Stronger, structured “call tapps_lookup_docs” when no RAG (P1)

**Points:** 3  
**Goal:** When expert has no RAG data, return machine-parseable hints and a concrete recommended tool call so agentic loops can automatically trigger follow-up.

**Tasks:**
- [ ] Extend `ConsultationResult` model (`experts/models.py`):
  - `suggested_tool: str | None` — e.g. `"tapps_lookup_docs"`
  - `suggested_library: str | None` — e.g. `"pytest"`
  - `suggested_topic: str | None` — e.g. `"fixtures and configuration"`
- [ ] In `engine.py`, when `len(chunks) == 0`:
  - Populate `suggested_tool`, `suggested_library`, `suggested_topic` using same inference as 10.1.1
  - Ensure prose says: **"Recommended next step: call tapps_lookup_docs(library='pytest', topic='fixtures and configuration')"** with concrete values when inferable
- [ ] Include these fields in `tapps_consult_expert` MCP tool response so clients can parse and auto-invoke
- [ ] When auto-fallback (10.1) runs, set `suggested_tool=None` (already handled)

**Definition of Done:**
- Response includes `suggested_tool`, `suggested_library`, `suggested_topic` when RAG is empty
- Prose contains concrete library/topic in the recommendation
- Unit tests verify fields are populated correctly

---

### 10.4 — Broader expert KB coverage (test config, URLs, env) (P2)

**Points:** 3  
**Goal:** Curate or ingest knowledge on test configuration, base URLs, env vars, pytest fixtures for URLs/config, monkeypatch for env — so the testing-strategies expert can answer more “best practice” questions directly.

**Tasks:**
- [ ] Add new knowledge file: `experts/knowledge/testing/test-configuration-and-urls.md` (knowledge dir `testing` maps to domain `testing-strategies` per `domain_utils.DOMAIN_TO_DIRECTORY_MAP`):
  - Test configuration patterns (base URLs, environment variables)
  - Avoiding hardcoded localhost
  - pytest fixtures for config, base URL, test URLs
  - monkeypatch for env vars in tests (`setenv`, `delenv`)
  - Source: Context7 `tapps_lookup_docs(library="pytest", topic="fixtures configuration monkeypatch env")` returns suitable content — ingest or summarize
- [ ] Update `experts/knowledge/README.md` (if present) or index to reference the new file
- [ ] Validate RAG retrieves this content for queries like “base URLs in tests”, “hardcoded localhost”, “pytest fixtures for config”
- [ ] Rebuild vector index (if used) or verify simple RAG picks up the file

**Definition of Done:**
- New knowledge file exists and is included in testing-strategies domain
- Sample queries return relevant chunks from the new content

---

### 10.5 — Optional single `tapps_research` tool (P2)

**Points:** 5  
**Goal:** Provide a single tool `tapps_research(question, domain, libraries)` that (1) consults the domain expert, (2) auto-falls back to Context7 when RAG is empty or confidence is low, (3) returns one combined answer with clear attribution.

**Tasks:**
- [ ] Design `tapps_research` tool schema:
  - `question: str` — research question
  - `domain: str = ""` — optional domain hint (e.g. `testing-strategies`)
  - `libraries: list[str] = []` — optional explicit libraries (e.g. `["pytest"]`); if empty, infer from domain + question
- [ ] Implement handler:
  1. Call expert (reuse `consult_expert` or internal equivalent)
  2. If `chunks_used == 0` or `confidence < threshold`, call Context7 for each inferred/listed library
  3. Merge expert answer + doc content with attribution sections
  4. Return single combined response
- [ ] Add `tapps_research` to tool registry and AGENTS.md
- [ ] Document when to use `tapps_research` vs. separate `tapps_consult_expert` + `tapps_lookup_docs`
- [ ] Add unit tests for combined flow

**Definition of Done:**
- `tapps_research` available and documented
- One call returns expert + doc content when RAG is empty
- Latency remains acceptable (< 5s when fallback runs)

---

## Implementation Order

| Order | Story | Dependency |
|-------|-------|------------|
| 1 | 10.3 — Stronger structured hints | None |
| 2 | 10.2 — Workflow documentation | None |
| 3 | 10.1 — Auto-fallback | 10.3 (reuses inference logic) |
| 4 | 10.4 — KB coverage | None |
| 5 | 10.5 — tapps_research | 10.1 |

Stories 10.2 and 10.3 can be done in parallel. Story 10.1 depends on 10.3’s inference logic but can share code.

---

## Acceptance Criteria (Epic)

- [ ] When expert RAG is empty, agent receives either (a) auto-fallback Context7 content in one response, or (b) structured `suggested_tool` / `suggested_library` / `suggested_topic` for follow-up
- [ ] AGENTS.md and workflow docs explicitly couple expert + doc lookup for testing/library questions
- [ ] Testing-strategies expert has knowledge on test config, base URLs, env vars, fixtures
- [ ] Optional `tapps_research` tool combines expert + Context7 in one call
- [ ] All changes maintain security: merged content passes governance (PII/secret filter) and RAG safety; response size limits enforced to avoid context overflow
- [ ] Performance: auto-fallback latency acceptable when Context7 is used (target under 5s)

---

## References

- Source: `C:\cursor\HomeIQ\implementation\TAPPS_MCP_IMPROVEMENT_RECOMMENDATIONS.md`
- Epic 2: [EPIC-2-KNOWLEDGE-DOCS.md](epics/EPIC-2-KNOWLEDGE-DOCS.md)
- Epic 3: [EPIC-3-EXPERT-SYSTEM.md](epics/EPIC-3-EXPERT-SYSTEM.md)
- Current expert engine: `src/tapps_mcp/experts/engine.py`
- Current consultation result: `src/tapps_mcp/experts/models.py`
- Domain→library mapping: `src/tapps_mcp/experts/rag_warming.py` (TECH_STACK_TO_EXPERT_DOMAINS — invert for inference)
- Knowledge dir mapping: `src/tapps_mcp/experts/domain_utils.py` (DOMAIN_TO_DIRECTORY_MAP)
- Lookup layer: `src/tapps_mcp/knowledge/lookup.py` (LookupEngine — async)
- AGENTS.md: `AGENTS.md`, `src/tapps_mcp/pipeline/agents_md.py`, `src/tapps_mcp/prompts/agents_template.md`
