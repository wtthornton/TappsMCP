# Epic 44: Business Expert Consultation and Integration

- **Status:** Complete
- **Priority:** P1 - High Value (makes business experts actually usable)
- **Estimated LOE:** ~2-2.5 weeks (1 developer)
- **Dependencies:** Epic 43 (Business Expert Foundation)
- **Blocks:** Epic 45 (Business Expert Lifecycle Management)

---

## Goal

Wire business experts into the consultation pipeline so that questions are routed to the correct expert (built-in or business), knowledge is retrieved from custom knowledge directories, and the MCP tools (`tapps_consult_expert`, `tapps_list_experts`, `tapps_research`) work seamlessly with both expert types. This epic makes business experts consultable.

## Motivation

Epic 43 creates the configuration and registry infrastructure. Without Epic 44, business experts exist in config but cannot answer questions. This epic completes the core value proposition: users define a "Home Assistant Expert" and can immediately ask it domain-specific questions via `tapps_consult_expert(question="How do I configure MQTT discovery?", domain="home-automation")`.

### User Stories Driving This Epic

1. **Consulting a Business Expert:** User prompts: "Ask the lease manager expert: what's the best data model for tracking lease renewals with variable rent escalation clauses?" The engine routes to the custom expert, loads knowledge from `.tapps-mcp/knowledge/lease-management/`, and returns domain-specific guidance.
2. **Auto-Detection:** User asks: "How should I handle zigbee device pairing?" without specifying a domain. The system detects "zigbee" as a business expert keyword and routes to the Home Assistant expert.

## Design Decisions

1. **Domain detection merging.** The `DomainDetector.detect_from_question()` currently scores against `DOMAIN_KEYWORDS` (17 technical domains). Business experts bring their own `keywords` lists. The detection must merge both keyword sets. We add a `detect_from_question_merged()` class method that includes business expert keywords in the scoring.

2. **Knowledge retrieval path.** `_retrieve_knowledge()` in `engine.py` currently always looks up knowledge from `ExpertRegistry.get_knowledge_base_path()` (the bundled package directory). For business experts, it must look up knowledge from `get_business_knowledge_path()` (the `.tapps-mcp/knowledge/` directory). The change is localized: check `expert.is_builtin` to determine the base path.

3. **Confidence scoring.** Business domains currently get 0.7 domain relevance (the `else` branch in `confidence.py`). We raise this to 0.9 for registered business domains (they are "known" even though not "technical") and keep 0.7 for truly unknown domains.

4. **MCP tool contract.** `tapps_consult_expert` and `tapps_list_experts` docstrings currently hardcode "17 built-in experts" and the domain list. These must become dynamic based on what is registered.

## Acceptance Criteria

- [ ] `tapps_consult_expert(question, domain="home-automation")` routes to a registered business expert and returns knowledge-backed answers
- [ ] Auto-detection (no explicit `domain`) routes business-keyword questions to business experts
- [ ] `tapps_list_experts` returns both built-in and business experts, with `is_builtin` flag
- [ ] `tapps_research` works with business expert domains
- [ ] Business expert knowledge is retrieved from `.tapps-mcp/knowledge/<domain>/`
- [ ] Business expert knowledge passes through `content_safety.py` prompt injection filter (same as built-in)
- [ ] Confidence scoring assigns 0.9 domain relevance to registered business domains
- [ ] RAG warming (`rag_warming.py`) can optionally warm business expert domains
- [ ] If a business expert has no knowledge files, the response clearly states this and suggests adding knowledge
- [ ] Built-in expert behavior is completely unchanged when no business experts are configured
- [ ] Unit tests: ~50 tests covering routing, knowledge retrieval, confidence, edge cases
- [ ] Integration test: full consultation cycle with mock business expert YAML and knowledge files

---

## Stories

### 44.1 -- Domain Detection for Business Keywords

**Points:** 5

Extend the `DomainDetector` to include business expert keywords in question routing, so that questions containing business-specific terms route to the correct business expert.

**Tasks:**
- Modify `packages/tapps-core/src/tapps_core/experts/domain_detector.py`:
  - Add `detect_from_question_merged(cls, question: str) -> list[DomainMapping]`:
    - Call existing `detect_from_question()` for built-in domains
    - Load business experts from `ExpertRegistry.get_business_experts()`
    - For each business expert, score the question against `expert.keywords` using the same word-boundary matching logic
    - Merge and re-sort all results by confidence
    - Business keyword matches get the same confidence formula as technical keywords
  - Add `_score_keywords(cls, question_clean: str, domain: str, keywords: list[str]) -> DomainMapping | None`:
    - Extract the shared scoring logic from `detect_from_question` into a reusable method
    - Both `detect_from_question` and the business keyword scoring call this
- Modify `packages/tapps-core/src/tapps_core/experts/query_expansion.py`:
  - Add `register_business_synonyms(synonyms: dict[str, str]) -> None` to allow business experts to contribute synonym mappings
  - Business synonyms are loaded from `experts.yaml` (optional `synonyms` field in each expert entry)
- Modify `packages/tapps-core/tests/unit/test_domain_detector.py` (or its tapps-core equivalent):
  - Test: question with business keyword routes to business domain
  - Test: question with technical keyword still routes to built-in domain
  - Test: question matching both gives higher-confidence domain first
  - Test: question with no matches falls back to software-architecture
  - Test: merged detection includes both types
  - Test: empty business experts produces same results as before

**Definition of Done:** Questions containing business expert keywords are detected and ranked alongside technical domains. Existing detection behavior unchanged when no business experts are registered. ~12 new tests.

---

### 44.2 -- Engine Routing for Business Experts

**Points:** 5

Modify the consultation engine (`engine.py`) to route questions to business experts when they are the best match, and retrieve knowledge from the correct directory.

**Tasks:**
- Modify `packages/tapps-core/src/tapps_core/experts/engine.py`:
  - In `_resolve_domain()`:
    - Replace `ExpertRegistry.get_expert_for_domain(resolved_domain)` with `ExpertRegistry.get_expert_for_domain_merged(resolved_domain)`
    - Replace `DomainDetector.detect_from_question(question)` with `DomainDetector.detect_from_question_merged(question)`
  - In `_retrieve_knowledge()`:
    - Check `expert.is_builtin` to determine knowledge base path:
      ```python
      if expert.is_builtin:
          knowledge_path = ExpertRegistry.get_knowledge_base_path() / knowledge_dir_name
      else:
          from tapps_core.experts.business_knowledge import get_business_knowledge_path
          from tapps_core.config.settings import load_settings
          settings = load_settings()
          knowledge_path = get_business_knowledge_path(settings.project_root, expert)
      ```
    - Handle case where business knowledge directory does not exist (return empty `_KnowledgeResult` with helpful message)
  - In `list_experts()`:
    - Replace `ExpertRegistry.get_all_experts()` with `ExpertRegistry.get_all_experts_merged()`
    - For business experts, count knowledge files from `.tapps-mcp/knowledge/<domain>/` instead of bundled path
  - In `_check_freshness()`:
    - Use the correct `knowledge_base_path` based on `expert.is_builtin`
- Create `packages/tapps-core/tests/unit/test_engine_business.py`:
  - Test: consult_expert routes to business expert when domain matches
  - Test: consult_expert auto-detects business domain from question keywords
  - Test: knowledge retrieval uses `.tapps-mcp/knowledge/` for business experts
  - Test: missing knowledge directory returns empty result with helpful message
  - Test: freshness check works for business expert knowledge files
  - Test: list_experts includes business experts with correct knowledge file count
  - Test: built-in expert behavior unchanged when business experts exist
  - Test: built-in fallback when no business expert matches

**Definition of Done:** `consult_expert(question, domain="home-automation")` returns a consultation result from the business expert's knowledge base. Auto-detection works. `list_experts()` includes business experts. ~15 new tests.

---

### 44.3 -- Confidence Scoring for Business Domains

**Points:** 3

Update the confidence scoring system to properly handle business expert domains instead of penalizing them as "unknown."

**Tasks:**
- Modify `packages/tapps-core/src/tapps_core/experts/confidence.py`:
  - In `compute_confidence()`:
    - Replace the binary check `ExpertRegistry.is_technical_domain(domain)` with a three-tier check:
      ```python
      if ExpertRegistry.is_technical_domain(domain):
          domain_relevance = 1.0
      elif ExpertRegistry.is_business_domain(domain):
          domain_relevance = 0.9  # Known business domain
      else:
          domain_relevance = 0.7  # Truly unknown domain
      ```
    - This means business experts can achieve confidence up to ~0.97 (vs the current 0.91 cap for non-technical domains)
- Update `packages/tapps-core/tests/unit/test_expert_confidence.py`:
  - Test: technical domain gets 1.0 relevance
  - Test: registered business domain gets 0.9 relevance
  - Test: unknown domain gets 0.7 relevance
  - Test: end-to-end confidence score for business domain with good RAG quality

**Definition of Done:** Business expert domains are scored fairly (0.9 relevance vs 0.7 for unknown). All existing confidence tests pass. ~4 new tests.

---

### 44.4 -- MCP Tool Updates for Mixed Expert Types

**Points:** 5

Update the MCP tool handlers (`tapps_consult_expert`, `tapps_list_experts`, `tapps_research`) to work with business experts and reflect the mixed expert set in their docstrings, responses, and structured output.

**Tasks:**
- Modify `packages/tapps-mcp/src/tapps_mcp/server.py`:
  - `tapps_consult_expert`:
    - Update docstring to mention business experts: "Routes to one of 17+ built-in experts or user-defined business experts..."
    - Update available domains list to be dynamic (include registered business domains)
    - Add `is_builtin` field to response
    - Add `expert_type: "builtin" | "business"` to structured output
  - `tapps_list_experts`:
    - Update docstring: "Returns built-in and business experts with domain, description, and knowledge-base status."
    - Add `is_builtin` and `expert_type` fields to each expert entry in response
    - Add `builtin_count` and `business_count` to response summary
- Modify `packages/tapps-mcp/src/tapps_mcp/server_metrics_tools.py`:
  - `tapps_research`:
    - Update docstring domain list to mention "plus any user-defined business domains"
    - No structural changes needed -- `tapps_research` delegates to `consult_expert` which already uses the merged registry (after 44.2)
- Modify `packages/tapps-mcp/src/tapps_mcp/common/output_schemas.py`:
  - Add `is_builtin: bool` and `expert_type: str` to `ExpertOutput` (if it exists)
- Update `packages/tapps-mcp/tests/unit/test_server_consult_expert.py` (or equivalent):
  - Test: consultation response includes `is_builtin=True` for built-in
  - Test: consultation response includes `is_builtin=False` for business
  - Test: list_experts response includes both types with counts
  - Test: structured output includes `expert_type` field

**Definition of Done:** MCP tools reflect both expert types in responses. Docstrings are updated. Structured output includes type information. ~8 new tests.

---

### 44.5 -- RAG Warming for Business Experts

**Points:** 3

Extend the RAG warming system to optionally build vector indices for business expert knowledge directories, so the first consultation is fast.

**Tasks:**
- Modify `packages/tapps-core/src/tapps_core/experts/rag_warming.py`:
  - Add `warm_business_expert_rag_indices(project_root: Path, max_domains: int = 10) -> dict[str, object]`:
    - Load business experts from registry
    - For each with `rag_enabled=True`, build/load `VectorKnowledgeBase` at `.tapps-mcp/knowledge/<domain>/` with index at `.tapps-mcp/rag_index/<domain>/`
    - Return summary dict (same shape as `warm_expert_rag_indices`)
  - Add call in `tapps_init` warm path (when `warm_expert_rag_from_tech_stack=True` and business experts are loaded)
- Modify `packages/tapps-core/tests/unit/test_rag_warming.py`:
  - Test: `warm_business_expert_rag_indices` with mock business experts
  - Test: skips experts with `rag_enabled=False`
  - Test: graceful when knowledge directory is empty
  - Test: warm result includes business domains

**Definition of Done:** Business expert RAG indices are warmed during init. Graceful when FAISS is unavailable. ~5 new tests.

---

### 44.6 -- Content Safety for Business Knowledge

**Points:** 3

Ensure all business expert knowledge files pass through the same content safety (prompt injection detection) pipeline as built-in knowledge.

**Tasks:**
- Verify that `VectorKnowledgeBase` and `SimpleKnowledgeBase` already pass retrieved content through `content_safety.py` -- if they do, this is mostly a validation/testing story
- If not, add content safety filtering in `_retrieve_knowledge()` for business expert knowledge (same pattern as built-in)
- Create `packages/tapps-core/tests/unit/test_business_knowledge_safety.py`:
  - Test: business knowledge with prompt injection is detected and filtered
  - Test: clean business knowledge passes through unmodified
  - Test: business knowledge with hidden instruction markers is caught
  - Test: mixed clean/malicious content in business knowledge directory
- Add an integration test that creates a temp business expert with malicious knowledge and verifies the safety filter catches it

**Definition of Done:** Business expert knowledge receives identical content safety treatment as built-in knowledge. Prompt injection in user-provided knowledge files is caught. ~6 new tests.

---

## Summary

| Story | Points | New Files | Modified Files | Est. Tests |
|-------|--------|-----------|----------------|------------|
| 44.1 | 5 | 0 | 2 (domain_detector.py, query_expansion.py) + test | ~12 |
| 44.2 | 5 | 1 (test) | 1 (engine.py) | ~15 |
| 44.3 | 3 | 0 | 1 (confidence.py) + test | ~4 |
| 44.4 | 5 | 0 | 3 (server.py, server_metrics_tools.py, output_schemas.py) + test | ~8 |
| 44.5 | 3 | 0 | 1 (rag_warming.py) + test | ~5 |
| 44.6 | 3 | 1 (test) | 0 | ~6 |
| **Total** | **24** | **2** | **8** | **~50** |

## Cross-References

- **Epic 43** ([EPIC-43-BUSINESS-EXPERT-FOUNDATION.md](EPIC-43-BUSINESS-EXPERT-FOUNDATION.md)): Provides the config, registry, and knowledge directory infrastructure this epic builds on
- **Epic 3** ([EPIC-3-EXPERT-SYSTEM.md](EPIC-3-EXPERT-SYSTEM.md)): Original expert system -- engine.py, domain_detector.py, confidence.py modified here
- **Epic 35** ([EPIC-35-EXPERT-ADAPTIVE-INTEGRATION.md](EPIC-35-EXPERT-ADAPTIVE-INTEGRATION.md)): Adaptive domain detection -- `AdaptiveDomainDetector` should also learn business domain patterns over time (deferred to future epic)
- **Epic 45** ([EPIC-45-BUSINESS-EXPERT-LIFECYCLE.md](EPIC-45-BUSINESS-EXPERT-LIFECYCLE.md)): Lifecycle management tool that depends on consultation working

## Architecture: Consultation Flow

```
User: "How do I configure MQTT discovery in Home Assistant?"
                    |
                    v
        tapps_consult_expert(question, domain?)
                    |
                    v
            _resolve_domain()
            +--> DomainDetector.detect_from_question_merged()
            |    Scores: "home-assistant" (0.85), "api-design" (0.3)
            |
            +--> ExpertRegistry.get_expert_for_domain_merged("home-assistant")
                 Returns: ExpertConfig(is_builtin=False, ...)
                    |
                    v
            _retrieve_knowledge()
            +--> expert.is_builtin? No
            |    knowledge_path = .tapps-mcp/knowledge/home-assistant/
            |
            +--> VectorKnowledgeBase(knowledge_path).search(question)
            |    Returns: chunks from mqtt-config.md, integrations.md
            |
            +--> content_safety.filter(chunks)
                    |
                    v
            ConsultationResult(
                domain="home-assistant",
                expert_name="Home Assistant Expert",
                is_builtin=False,
                confidence=0.92,
                knowledge_chunks=[...],
            )
```

## Deferred to Future Work

- **Adaptive learning for business domains:** `AdaptiveDomainDetector` currently only learns routing for technical domains. Teaching it business domain patterns would improve auto-detection over time. Defer to a future epic.
- **Cross-expert consultation:** Querying multiple experts (e.g., "Home Assistant" + "Security") for a single question. The original TappsCodingAgents supported this via the 51% authority model. Defer unless demand arises.
