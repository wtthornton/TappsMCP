# Epic 5: Adaptive Learning & Intelligence

**Status:** Not Started
**Priority:** P2 — Important (improves quality over time, completes expert system)
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 1 (Core Quality), Epic 3 (Expert System)
**Blocks:** Epic 7 (Metrics & Dashboard depends on outcome tracker and adaptive data)

---

## Goal

Make the MCP server learn from usage to improve quality predictions over time. This epic has two parts: (1) adaptive scoring and expert weight adjustment based on feedback, and (2) completing the expert system with optional components deferred from Epic 3 (vector RAG, adaptive domain detection, knowledge management).

## 2026 Best Practices Applied

- **Feedback-driven quality**: Track which quality gate failures lead to actual rework vs. false positives. Adjust scoring weights based on real-world outcomes.
- **Optional heavy dependencies**: FAISS and sentence-transformers are extras (`tapps-mcp[vector]`). The system works perfectly without them via simple RAG. Never force users to install ML libraries for a code quality tool.
- **Auto-fallback pattern**: `vector_rag.py` checks for `faiss-cpu` at import time. If missing, auto-fallback to `simple_rag.py`. Zero configuration, zero error messages — it just works with reduced precision.
- **Telemetry opt-in**: Usage statistics and feedback data are local-only by default. No data leaves the machine unless explicitly configured.

## Acceptance Criteria

- [ ] Adaptive scorer adjusts category weights based on historical gate pass/fail patterns
- [ ] Expert voting weights adapt based on consultation accuracy tracking
- [ ] Adaptive engine consumes outcome data from Epic 7's OutcomeTracker
- [ ] **Note:** `tapps_feedback` and `tapps_stats` MCP tools moved to [Epic 7](EPIC-7-METRICS-DASHBOARD.md) (Metrics & Dashboard)
- [ ] Vector RAG works when `faiss-cpu` is installed, auto-falls back to simple RAG when not
- [ ] Adaptive domain detector improves expert routing based on usage patterns
- [ ] Knowledge freshness tracking identifies stale knowledge files
- [ ] Knowledge ingestion supports adding new knowledge files at runtime
- [ ] All adaptive data persists across server restarts
- [ ] Unit tests: ~35 tests (adaptive ~15, vector RAG ~10, knowledge mgmt ~10)

---

## Stories

### 5.1 — Extract Adaptive Scoring

**Points:** 5

Extract the adaptive scoring system that learns from usage patterns.

**Tasks:**
- Extract `agents/reviewer/adaptive_scorer.py` → `tapps_mcp/scoring/adaptive.py`
  - Remove agent base dependency
  - Retain: weight adaptation, historical pattern tracking
- Extract `core/adaptive_scoring.py` → `tapps_mcp/scoring/adaptive_weights.py`
  - Standalone adaptive weight system
  - Persists learned weights to `{TAPPS_MCP_PROJECT_ROOT}/.tapps-mcp/adaptive/scoring_weights.json`
- Implement feedback loop:
  - Track gate pass/fail events over time
  - Identify categories with high false-positive rates
  - Adjust weights to reduce false positives while maintaining quality floor
- Port ~8 unit tests

**Definition of Done:** Scoring weights adjust based on historical gate results. Learned weights persist across restarts.

---

### 5.2 — Extract Expert Adaptation

**Points:** 3

Extract the expert system adaptation modules deferred from Epic 3.

**Tasks:**
- Extract standalone modules:
  - `experts/adaptive_voting.py` → `tapps_mcp/experts/adaptive_voting.py`
  - `experts/weight_distributor.py` → `tapps_mcp/experts/weight_distributor.py`
  - `experts/performance_tracker.py` → `tapps_mcp/experts/performance_tracker.py`
- Expert voting weights adapt based on:
  - Consultation frequency per domain
  - User feedback on advice quality
  - Confidence calibration (did high-confidence answers prove correct?)
- Persist adaptation data to `{TAPPS_MCP_PROJECT_ROOT}/.tapps-mcp/adaptive/expert_weights.json`
- Port ~7 unit tests

**Definition of Done:** Expert weights adapt over time. High-accuracy domains get higher weight. Data persists.

---

### 5.3 — Integrate with Metrics Infrastructure

**Points:** 2

Wire adaptive learning into the metrics and feedback infrastructure from [Epic 7](EPIC-7-METRICS-DASHBOARD.md).

> **Note:** The `tapps_feedback` and `tapps_stats` MCP tools have been moved to Epic 7 (Metrics & Dashboard), which owns all metrics collection, aggregation, and dashboard tooling. This story focuses on consuming metric data for adaptive weight learning.

**Tasks:**
- Wire adaptive scoring engine to consume `OutcomeTracker` data from Epic 7
- Wire expert adaptation to consume `ExpertPerformanceTracker` data from Epic 7
- Wire feedback data (from `tapps_feedback` tool in Epic 7) into adaptive weight adjustment
- Ensure adaptive weights persist to `.tapps-mcp/adaptive/` directory

**Definition of Done:** Adaptive learning consumes outcomes and feedback from Epic 7's metrics infrastructure.

---

### 5.4 — Extract Vector RAG (Optional FAISS)

**Points:** 5

Extract the optional FAISS-based vector RAG system for improved knowledge retrieval.

**Tasks:**
- Extract from `experts/`:
  - `vector_rag.py` → `tapps_mcp/experts/vector_rag.py` — FAISS semantic search
  - `rag_chunker.py` → `rag_chunker.py` — knowledge file chunking
  - `rag_embedder.py` → `rag_embedder.py` — embedding generation
  - `rag_index.py` → `rag_index.py` — vector index management
- Implement auto-fallback pattern:
  ```python
  try:
      import faiss
      HAS_FAISS = True
  except ImportError:
      HAS_FAISS = False
  ```
  - If FAISS available: use vector_rag for semantic search
  - If FAISS missing: use simple_rag (already working from Epic 3)
  - No configuration needed, no error messages
- Port ~10 unit tests (mock FAISS for tests without it installed)

**Definition of Done:** Vector RAG works with FAISS, auto-falls back to simple RAG without it. Zero-config switching.

---

### 5.5 — Extract Knowledge Management

**Points:** 3

Extract knowledge management modules deferred from Epic 3.

**Tasks:**
- Extract standalone modules:
  - `experts/adaptive_domain_detector.py` → improved domain detection
  - `experts/knowledge_freshness.py` → track knowledge file staleness
  - `experts/knowledge_validator.py` → validate knowledge file format
  - `experts/knowledge_ingestion.py` → add new knowledge files at runtime
- Knowledge freshness:
  - Track when knowledge files were last updated
  - Flag stale knowledge in expert responses (e.g., "source last updated 6 months ago")
- Knowledge ingestion:
  - Support adding new knowledge files without server restart
  - Validate format before accepting
  - Re-index vector RAG if available

**Definition of Done:** Knowledge files have freshness tracking. New knowledge can be added at runtime.

---

### 5.6 — Tests

**Points:** 2

Unit and integration tests for all adaptive and optional components.

**Tasks:**
- Adaptive scoring tests (~8 tests): weight adjustment over multiple sessions
- Expert adaptation tests (~7 tests): vote weight adjustment, accuracy tracking
- Vector RAG tests (~10 tests): FAISS available/missing, fallback behavior
- Knowledge management tests (~10 tests): freshness, validation, ingestion
- Integration: feedback loop → weight adjustment → improved scoring
- Test with FAISS: mark as `@pytest.mark.skipif(not HAS_FAISS)`

**Definition of Done:** ~35+ tests pass. Optional FAISS tests skip gracefully when not installed.

---

## Performance Targets

| Tool | Target (p95) | Notes |
|---|---|---|
| `tapps_feedback` | < 100ms | Write to local file |
| `tapps_stats` | < 100ms | In-memory aggregation |
| `tapps_consult_expert` (vector RAG) | < 2s | Same target as simple RAG |

## Key Dependencies
- None beyond Epic 1 + Epic 3 dependencies

## Optional Dependencies (extras)
- `faiss-cpu` — vector similarity search
- `sentence-transformers` — embedding generation for vector RAG
- Published as `tapps-mcp[vector]` extras
