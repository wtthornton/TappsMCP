# Implementation Plan: Critical, High, and Medium Issues

**Created:** 2026-02-22  
**Source:** TappsMCP project review, [SELF_REVIEW_FINDINGS.md](SELF_REVIEW_FINDINGS.md), [CRITICAL_HIGH_REVIEW_PLAN.md](CRITICAL_HIGH_REVIEW_PLAN.md)  
**Status:** Ready for execution

---

## Executive Summary

| Priority  | Count | Total Effort | Dependencies |
|-----------|-------|--------------|--------------|
| Critical  | 0     | —            | All resolved |
| High      | 1     | 2–3 days     | None         |
| Medium    | 8     | 8–12 days    | Some cross-deps |

**Already implemented (verified 2026-02-22):** Dry-run (H1), Checklist persistence (H2), Expert RAG failed_domains → errors (H3), Feedback → AdaptiveScoringEngine (H4), server.py split, validate_changed cap 50.

---

## Phase 1: Critical Issues

**Status:** None remaining. All critical items from prior reviews have been implemented.

| ID   | Item                         | Status  |
|------|------------------------------|---------|
| C1   | CLI exit codes               | Done    |
| C2   | Invalid JSON in host config  | Done    |
| C3   | Cache warming failures hidden| Done    |
| SR1  | server.py monolithic         | Done (split into server_* modules) |

---

## Phase 2: High Issues

### H1. Expert RAG Relevance Is Poor

**Effort:** 2–3 days  
**Dependencies:** None  
**Files:** `src/tapps_mcp/experts/vector_rag.py`, `src/tapps_mcp/experts/rag.py`, knowledge base content

**Problem:** Architecture and testing consultations return irrelevant or empty results. Keyword-based chunk matching produces low-relevance output for specific questions.

**Tasks:**

1. **Add BM25/TF-IDF scoring (1 day)**  
   - Integrate `rank-bm25` or implement TF-IDF scoring in `vector_rag.py`  
   - Use BM25/TF-IDF as primary or secondary signal alongside keyword matching

2. **Add relevance threshold (0.5 day)**  
   - Reject chunks with score &lt; 0.3 (configurable)  
   - Return "no relevant knowledge found" when all chunks are below threshold  
   - Expose threshold in config/settings if needed

3. **Expand MCP-specific knowledge (1 day)**  
   - Add MCP architecture, testing, and quality patterns to expert domains  
   - Target: `software-architecture`, `testing-strategies`, `code-quality-analysis`

**Acceptance criteria:**
- `tapps_consult_expert(domain="testing-strategies", question="...")` returns relevant chunks
- Chunks below threshold are filtered out
- Unit tests for BM25/TF-IDF scoring and threshold logic

---

## Phase 3: Medium Issues

### M1. Quality Gate Failures — adaptive/persistence.py

**Effort:** 0.5–1 day  
**Dependencies:** None  
**Files:** `src/tapps_mcp/adaptive/persistence.py`, `tests/unit/test_adaptive_persistence.py`

**Problem:** Score 67.98 (below 70), CC=5.4, test coverage low (3).

**Tasks:**
- Extract helper functions to reduce cyclomatic complexity (CC &lt; 10)
- Add unit tests to raise coverage
- Re-run `tapps_quality_gate` until passed

---

### M2. Quality Gate Failures — adaptive/voting_engine.py

**Effort:** 0.5–1 day  
**Dependencies:** None  
**Files:** `src/tapps_mcp/adaptive/voting_engine.py`, `tests/unit/test_adaptive_voting.py`

**Problem:** Score 66.74 (below 70), CC=3.26, performance concerns, no tests.

**Tasks:**
- Reduce complexity; break up large functions
- Add unit tests
- Optimize nested loops if present
- Re-run `tapps_quality_gate` until passed

---

### M3. Docker Compose: Explicit Networks

**Effort:** 0.25 day  
**Dependencies:** None  
**Files:** `docker-compose.yml`

**Problem:** Validator recommends explicit networks for `tapps-mcp` service.

**Tasks:**
- Define `networks:` block (e.g. `tapps-network`)
- Assign `tapps-mcp` service to the network
- Document for multi-service future use

---

### M4. tapps_lookup_docs 50% Success Rate

**Effort:** 1–1.5 days  
**Dependencies:** None  
**Files:** `src/tapps_mcp/knowledge/lookup.py`, `src/tapps_mcp/knowledge/context7_client.py`, possibly new cache bundle

**Problem:** Blocking tool fails often; without Context7 API key, degrades completely with poor error visibility.

**Tasks:**
1. Ship pre-built cache for top-50 Python libraries (optional bundle or package data)
2. Add expert knowledge base fallback when Context7 fails or key is missing
3. Improve error messages when API key is not set (clear, actionable guidance)

---

### M5. Quick Check vs Full Gate Inconsistency

**Effort:** 1 day  
**Dependencies:** None  
**Files:** `src/tapps_mcp/tools/ruff_direct.py` or quick check implementation, possibly new AST helper

**Problem:** `tapps_quick_check` (Ruff-only) can show 100% pass while full gate fails on complexity/maintainability.

**Tasks:**
- Add lightweight AST-based complexity heuristic (no radon subprocess)
- Emit warning when complexity exceeds threshold in quick check
- Document that quick check is heuristic; full gate is authoritative

---

### M6. tapps_report Performance

**Effort:** 1–1.5 days  
**Dependencies:** None  
**Files:** `src/tapps_mcp/server_metrics_tools.py` or report implementation

**Problem:** Avg ~84s, P95 ~30s; too slow for interactive use.

**Tasks:**
1. Use `score_file_quick` with `asyncio.gather` for parallel scoring
2. Add `max_files` parameter to cap report scope
3. Cache recent scores for unchanged files (optional, by mtime or hash)

---

### M7. Scoring Weights Calibration

**Effort:** 1–2 days  
**Dependencies:** M1, M2 (better outcome data from gates)  
**Files:** `src/tapps_mcp/adaptive/scoring_engine.py`, `src/tapps_mcp/scoring/constants.py`

**Problem:** ~15% gap between avg score and gate pass rate; `MIN_OUTCOMES_FOR_ADJUSTMENT = 10` rarely triggers adaptive weights.

**Tasks:**
1. Ship empirically calibrated default weights from historical runs
2. Lower `MIN_OUTCOMES_FOR_ADJUSTMENT` (e.g. 5) or make configurable
3. (Optional) Add `tapps_calibrate` tool for one-off weight tuning

---

### M8. pipeline/init.py CC Reduction

**Effort:** 1 day  
**Dependencies:** None  
**Files:** `src/tapps_mcp/pipeline/init.py`

**Problem:** BootstrapConfig and helpers exist; `bootstrap_pipeline` still has many parameters and high CC.

**Tasks:**
- Further extract `_bootstrap_*` helpers
- Reduce `bootstrap_pipeline` parameter count via nested config objects
- Target CC &lt; 15

---

## Phase 4: Execution Order and Scheduling

### Recommended sequence

```
Week 1 (Quick wins)
├── M3  Docker Compose networks       (0.25 day)
├── M1  persistence.py gate fix      (0.5–1 day)
├── M2  voting_engine.py gate fix    (0.5–1 day)
└── H1  Expert RAG relevance         (2–3 days) — start in parallel

Week 2 (Performance & UX)
├── M4  lookup_docs fallback         (1–1.5 days)
├── M5  Quick check complexity       (1 day)
└── M6  tapps_report performance     (1–1.5 days)

Week 3 (Calibration & cleanup)
├── M7  Scoring calibration          (1–2 days)
└── M8  pipeline/init CC reduction   (1 day)
```

### Dependency graph

```
H1 ──────────────────────────────────────────── (no deps)
M1 ──────────────────────────────────────────── (no deps)
M2 ──────────────────────────────────────────── (no deps)
M3 ──────────────────────────────────────────── (no deps)
M4 ──────────────────────────────────────────── (no deps)
M5 ──────────────────────────────────────────── (no deps)
M6 ──────────────────────────────────────────── (no deps)
M7 ────► M1, M2 (better outcome data) ───────── (soft)
M8 ──────────────────────────────────────────── (no deps)
```

---

## Phase 5: Verification

### Per-task checks

| Task | Verification command / check |
|------|------------------------------|
| H1   | `tapps_consult_expert(domain="testing-strategies", ...)` returns relevant chunks; pytest |
| M1   | `tapps_quality_gate(file_path="src/tapps_mcp/adaptive/persistence.py")` passes |
| M2   | `tapps_quality_gate(file_path="src/tapps_mcp/adaptive/voting_engine.py")` passes |
| M3   | `tapps_validate_config(file_path="docker-compose.yml")` — no network suggestions |
| M4   | Run lookup without API key; verify fallback and clear error message |
| M5   | `tapps_quick_check` emits complexity warning when file has CC&gt;10 |
| M6   | `tapps_report` completes in &lt; 30s for 20 files |
| M7   | Gate pass rate and avg score gap narrows; adaptive weights activate |
| M8   | `tapps_score_file(pipeline/init.py)` shows CC &lt; 15 |

### Full regression

```bash
pytest tests/ -v --ignore=tests/e2e/
tapps_validate_changed
tapps_checklist(task_type="review")
```

---

## Phase 6: Documentation Updates

After each phase:

1. **CHANGELOG.md** — Add entries for user-facing changes
2. **SELF_REVIEW_FINDINGS.md** — Mark items as implemented with date
3. **This plan** — Check off completed tasks in checklist below

---

## Checklist

### High
- [x] H1. Expert RAG relevance (threshold, MCP knowledge) — 2026-02-22

### Medium
- [x] M1. adaptive/persistence.py quality gate — 2026-02-22
- [x] M2. adaptive/voting_engine.py quality gate — 2026-02-22
- [x] M3. Docker Compose explicit networks — 2026-02-22
- [x] M4. tapps_lookup_docs fallback and error messages — 2026-02-22
- [x] M5. Quick check complexity heuristic — Already present
- [x] M6. tapps_report performance — 2026-02-22
- [x] M7. Scoring weights calibration — 2026-02-22
- [x] M8. pipeline/init.py CC reduction — 2026-02-22

### Documentation
- [x] CHANGELOG updated — 2026-02-22
- [ ] SELF_REVIEW_FINDINGS updated (optional)
- [ ] CRITICAL_HIGH_REVIEW_PLAN updated (optional)
