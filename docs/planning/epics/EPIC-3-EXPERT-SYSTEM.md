# Epic 3: Expert System & Domain Knowledge

**Status:** Not Started
**Priority:** P1 — High Value (addresses wrong domain patterns with 16-domain expert consultation)
**Estimated LOE:** ~3-4 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation & Security)
**Blocks:** Epic 5 (Adaptive Learning depends on expert system)

---

## Goal

Add `tapps_consult_expert` and `tapps_list_experts` — RAG-backed expert consultation across 16 technical domains (security, performance, testing, database, API design, etc.). This is the largest extraction in the project: 40+ files, 119 knowledge files, and a multi-module coupling chain that requires careful decoupling.

## LLM Error Sources Addressed

| Error Source | Tool |
|---|---|
| Wrong domain patterns | `tapps_consult_expert` |
| Prompt injection via RAG | `tapps_consult_expert` (rag_safety defense) |

## 2026 Best Practices Applied

- **RAG with safety guardrails**: All retrieved knowledge content passes through prompt injection detection before returning to the LLM. RAG-retrieved content is **untrusted** — treat it like user input.
- **PII/secret governance**: All expert responses pass through `GovernanceLayer` to filter secrets, tokens, credentials, and PII. Expert knowledge files may contain example credentials that must not leak.
- **Confidence scoring**: Expert responses include confidence scores with breakdowns. LLMs can use confidence to decide whether to trust the advice or seek additional information.
- **Pluggable expert registry**: New domains can be added without code changes — drop knowledge files + register domain config.
- **Optional vector RAG**: FAISS-based semantic search is optional. System auto-falls back to file-based simple RAG when `faiss-cpu` is not installed. Zero degradation in functionality, only in retrieval precision.

## Acceptance Criteria

- [ ] `tapps_consult_expert` accepts domain, question, and optional context
- [ ] Expert consultation returns domain-specific guidance with confidence score
- [ ] 16 domains available: security, performance, testing, data-privacy, accessibility, ux, code-quality, architecture, devops, documentation, ai-frameworks, observability, api-design, cloud-infrastructure, database, agent-learning
- [ ] All RAG-retrieved content passes `rag_safety.py` prompt injection detection
- [ ] All expert responses pass `governance.py` PII/secret filter
- [ ] `tapps_list_experts` returns all available domains with descriptions
- [ ] Domain detection suggests relevant experts based on question context
- [ ] Expert responses include confidence scores with breakdowns
- [ ] 119 knowledge files copied and validated
- [ ] Simple RAG works without any optional dependencies (no FAISS required)
- [ ] Expert response latency < 2s (p95)
- [ ] Unit tests: ~45 tests ported (engine, RAG, confidence, domain detection)
- [ ] Security tests: RAG safety catches prompt injection in knowledge files

---

## Stories

### 3.1 — Extract Expert Engine Core

**Points:** 8

Extract the expert consultation engine — the hardest decoupling task in the project.

**Tasks:**
- Extract `expert_engine.py` → `tapps_mcp/experts/engine.py`
  - **This is the hardest decoupling.** The engine is coupled to agent base classes.
  - Remove all agent-specific imports and lifecycle management
  - Retain: consultation logic, domain routing, response assembly
  - Replace framework logging with structlog
- Copy standalone modules:
  - `expert_registry.py` → `registry.py`
  - `builtin_registry.py` → `builtins.py`
  - `base_expert.py` → `base_expert.py`
  - `domain_detector.py` → `domain_detector.py`
  - `expert_suggester.py` → `expert_suggester.py`
  - `domain_config.py` → `domain_config.py`
  - `domain_utils.py` → `domain_utils.py`
  - `expert_config.py` → `expert_config.py`
  - `cache.py` → `cache.py`
  - `history_logger.py` → `history_logger.py`
  - `observability.py` → `observability.py`
  - `report_generator.py` → `report_generator.py`
- Verify the coupling chain works end-to-end:
  `engine.py` → `registry.py` → `builtins.py` → `base_expert.py` → domain configs

**Definition of Done:** Expert engine routes questions to correct domain, retrieves knowledge, returns structured responses. Fully decoupled from agent base.

---

### 3.2 — Extract RAG System

**Points:** 5

Extract the RAG (Retrieval-Augmented Generation) system for knowledge retrieval.

**Tasks:**
- Extract `simple_rag.py` → `tapps_mcp/experts/rag.py`
  - File-based RAG — no vector DB, no external dependencies
  - This is the **primary** RAG backend; vector RAG is optional (deferred to Epic 5)
- Copy supporting modules:
  - `rag_evaluation.py` → `rag_evaluation.py` — RAG quality evaluation
  - `rag_metrics.py` → `rag_metrics.py` — RAG performance metrics
- Ensure RAG safety integration:
  - All retrieved content passes through `rag_safety.py` (extracted in Epic 0)
  - All responses pass through `governance.py` PII filter (extracted in Epic 0)
- Port RAG-specific tests

**Definition of Done:** Simple RAG retrieves relevant knowledge from files, filters for safety, returns with confidence scores.

---

### 3.3 — Extract Confidence Scoring

**Points:** 3

Extract the confidence scoring system for expert responses.

**Tasks:**
- Copy standalone modules:
  - `confidence_calculator.py` → `tapps_mcp/experts/confidence.py`
  - `confidence_breakdown.py` → `confidence_breakdown.py`
  - `confidence_metrics.py` → `confidence_metrics.py`
- Confidence scores indicate how reliable the expert response is
- Breakdown shows which factors contribute to confidence (source quality, relevance, recency)

**Definition of Done:** Expert responses include confidence scores with detailed breakdowns.

---

### 3.4 — Copy Knowledge Files

**Points:** 2

Copy all 119 knowledge files across 16 domains and validate them.

**Tasks:**
- Copy entire `experts/knowledge/` directory (16 subdirectories, 119 files)
- Validate all files are readable and properly formatted
- Run `rag_safety.py` scan on all knowledge files (ensure none contain injection patterns)
- Verify domain mapping: each subdirectory maps to a registered domain
- Document knowledge file format and contribution guidelines

**Knowledge Domains:**
| Domain | Knowledge Files |
|---|---|
| security | ~10 files |
| performance | ~8 files |
| testing | ~8 files |
| data-privacy-compliance | ~7 files |
| accessibility | ~6 files |
| user-experience | ~6 files |
| observability-monitoring | ~7 files |
| api-design-integration | ~8 files |
| cloud-infrastructure | ~7 files |
| database-data-management | ~8 files |
| agent-learning | ~6 files |
| ai-frameworks | ~7 files |
| software-architecture | ~8 files |
| code-quality-analysis | ~7 files |
| development-workflow | ~8 files |
| documentation-knowledge-management | ~8 files |

**Definition of Done:** All 119 knowledge files copied, validated, and scannable by RAG system.

---

### 3.5 — Wire MCP Tools

**Points:** 3

Wire `tapps_consult_expert` and `tapps_list_experts` into the MCP server.

**Tasks:**
- Implement `tapps_consult_expert` MCP tool handler:
  - `domain` parameter: one of 16 expert domains
  - `question` parameter: specific question for the expert
  - `context` parameter: optional code/architectural context
  - Flow: domain routing → RAG retrieval → rag_safety check → confidence scoring → governance filter → response
  - Include `confidence`, `domain`, `sources`, `elapsed_ms` in response
- Implement `tapps_list_experts` MCP tool handler:
  - Returns all 16 domains with descriptions and example questions
  - In-memory, < 100ms

**Definition of Done:** Expert consultation works end-to-end via MCP protocol. Safety and governance filters applied.

---

### 3.6 — Unit Tests

**Points:** 3

Comprehensive unit tests for expert system.

**Tasks:**
- Port engine tests (~20 tests): domain routing, consultation flow
- Port RAG tests (~15 tests): knowledge retrieval, relevance scoring
- Port confidence tests (~10 tests): confidence calculation, breakdowns
- Add security tests:
  - RAG safety catches prompt injection in knowledge files
  - Governance filter catches PII/secrets in expert responses
  - Domain detector handles adversarial inputs
- Mock at RAG boundary — don't require knowledge files for unit tests

**Definition of Done:** ~45+ tests pass. Security tests verify safety guardrails.

---

### 3.7 — RAG Safety Integration Tests

**Points:** 2

Verify that the full pipeline (RAG → safety → governance → response) catches injection attempts.

**Tasks:**
- Create test knowledge files with known injection patterns
- Test: injection patterns in knowledge files are detected and filtered
- Test: PII in expert responses is redacted by governance layer
- Test: SecretStr API keys never appear in responses
- Test: domain detection doesn't route to wrong domain on adversarial input

**Definition of Done:** Security integration tests verify end-to-end safety of the expert pipeline.

---

## Cross-References

- **Metrics recording:** Expert tool handlers will be automatically instrumented by [Epic 7](EPIC-7-METRICS-DASHBOARD.md) (Story 7.7) with a metrics decorator. Design `tapps_consult_expert` to return `confidence`, `domain`, `elapsed_ms` to feed metrics.
- **Expert metrics:** [Epic 7](EPIC-7-METRICS-DASHBOARD.md) (Story 7.3) extracts `performance_tracker.py`, `confidence_metrics.py`, `rag_metrics.py`, `history_logger.py`, and `observability.py` into a dedicated metrics layer. These modules track expert effectiveness over time and identify weak domains.
- **Business metrics:** [Epic 7](EPIC-7-METRICS-DASHBOARD.md) (Story 7.4) extracts `business_metrics.py` which aggregates adoption, effectiveness, and ROI from expert consultation data.

## Deferred to Epic 5 (Adaptive Learning)

The following modules are intentionally deferred from this epic. The simple RAG + basic domain detection is sufficient for launch:

- `vector_rag.py`, `rag_chunker.py`, `rag_embedder.py`, `rag_index.py` — optional FAISS vector RAG chain
- `adaptive_domain_detector.py` — improved adaptive domain detection
- `knowledge_freshness.py`, `knowledge_validator.py`, `knowledge_ingestion.py` — knowledge management tools
- `adaptive_voting.py`, `weight_distributor.py`, `performance_tracker.py` — expert adaptation

## Performance Targets

| Tool | Target (p95) | Notes |
|---|---|---|
| `tapps_consult_expert` | < 2s | RAG retrieval + confidence scoring |
| `tapps_list_experts` | < 100ms | In-memory registry |

## Key Dependencies
- `pyyaml` — knowledge file parsing (if YAML-formatted)

## Optional Dependencies (deferred to Epic 5)
- `faiss-cpu` — vector RAG (auto-fallback to simple_rag)
- `sentence-transformers` — embeddings for vector RAG
