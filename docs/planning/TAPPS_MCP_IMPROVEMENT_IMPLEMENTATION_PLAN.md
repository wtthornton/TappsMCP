# TappsMCP Expert + Context7 + Retrieval Optimization — Implementation Plan

**Source:** [TAPPS_MCP_IMPROVEMENT_RECOMMENDATIONS.md](../../../HomeIQ/implementation/TAPPS_MCP_IMPROVEMENT_RECOMMENDATIONS.md)
**Created:** 2026-02-18
**Revised:** 2026-02-20 (re-baselined against current code)
**Status:** Implementation-ready (re-baselined against repository state; implementation pending)
**Audience:** TappsMCP maintainers

---

## 1) Validation method used for this re-baseline

This plan revision was validated against current repository code and docs (not assumptions):

- Expert tool surface and response fields: `src/tapps_mcp/server.py`, `src/tapps_mcp/experts/models.py`, `src/tapps_mcp/experts/engine.py`
- Context7 lookup behavior: `src/tapps_mcp/knowledge/lookup.py`, `src/tapps_mcp/knowledge/context7_client.py`
- Fuzzy matching implementation: `src/tapps_mcp/knowledge/fuzzy_matcher.py`
- Retrieval backends: `src/tapps_mcp/experts/rag.py`, `src/tapps_mcp/experts/vector_rag.py`, `src/tapps_mcp/experts/rag_index.py`
- Feedback/metrics foundations for ranking: `src/tapps_mcp/metrics/feedback.py`, `src/tapps_mcp/metrics/expert_metrics.py`, `src/tapps_mcp/metrics/rag_metrics.py`
- Knowledge-base coverage check: `src/tapps_mcp/experts/knowledge/testing/`

> Note: MCP resource servers for Context7/TappsMCP were not attached in this session, so validation is code-and-doc based.

---


## 1.1) Accuracy guardrails for this document

To keep this plan strictly factual, each status claim in Section 2 is tied to observable repository evidence (present/absent symbols, handlers, or files).

- If code implements a capability but no tests exist, status is still reported as implemented with a follow-up validation task.
- If no symbol/handler/file exists in the repository, status is reported as not implemented.
- Where behavior depends on runtime integration (MCP host-attached tools), this document calls out the environment limitation explicitly.

## 1.2) Current implementation snapshot (accurate as of 2026-02-20)

| Capability | Current status | Evidence |
|---|---|---|
| `tapps_consult_expert` basic flow (domain detect, retrieve, confidence, sources) | ✅ Implemented | `experts/engine.py`, `server.py` |
| Low-confidence nudge to call `tapps_lookup_docs` | ✅ Implemented | `experts/engine.py` |
| Automatic Context7 fallback inside expert flow when RAG empty | ❌ Not implemented | no fallback call path in `experts/engine.py` |
| Structured fields `suggested_tool`, `suggested_library`, `suggested_topic` in response model | ❌ Not implemented | absent in `experts/models.py` and `server.py` response mapping |
| Structured fields `fallback_used`, `fallback_library`, `fallback_topic` | ❌ Not implemented | absent in `experts/models.py` and `server.py` |
| Optional `tapps_research` tool | ❌ Not implemented | no tool handler/registration |
| Testing KB file `test-configuration-and-urls.md` | ❌ Not present | missing under `experts/knowledge/testing/` |
| Context7 cache + SWR + stale fallback | ✅ Implemented | `knowledge/lookup.py` |
| Library fuzzy match | ⚠️ Basic only (LCS + alias + prefix) | `knowledge/fuzzy_matcher.py` |
| Retrieval architecture | ⚠️ Dual backend exists; no hybrid fusion/rerank | `experts/rag.py`, `experts/vector_rag.py`, `experts/rag_index.py` |
| Signals for hot-rank/adaptive ranking | ⚠️ Foundations exist; ranking policy not implemented | metrics + feedback modules |

---

### Snapshot summary

- Epic 10 stories started/completed in code: **0 / 5**
- Epic 11 stories started/completed in code: **0 / 5**
- Overall planned stories started/completed: **0 / 10**

---

## 3) What remains from original Epic 10 (still open)

## Epic 10: Expert + Context7 Integration (carry forward)

**Priority:** P1
**Dependencies:** Epic 2, Epic 3

### 10.1 — Auto-fallback to Context7 when expert RAG is empty

**Status:** Not started

**Tasks:**
- [ ] In `experts/engine.py`, when `chunks_used == 0` (or no sources), infer library/topic from domain+question and perform lookup.
- [ ] Bridge sync expert flow with async lookup in a safe helper (`sync_lookup` wrapper).
- [ ] Merge fallback content into expert answer with explicit attribution section.
- [ ] Add response budget limits for merged content.
- [ ] Add config flag (opt-in/out) for auto-fallback behavior.
- [ ] Add fields: `fallback_used`, `fallback_library`, `fallback_topic`.

**DoD:** Empty-RAG consultation can return a combined expert+docs answer in one call.

---

### 10.2 — Workflow coupling updates (expert + docs)

**Status:** Not started

**Tasks:**
- [ ] Update AGENTS/template/research prompts to explicitly require combined expert+lookup for library-specific domain questions.
- [ ] Update `tapps_server_info` recommended workflow wording and stage hints.

**DoD:** Workflow guidance consistently reflects expert+lookup coupling.

---

### 10.3 — Structured “next tool” hints when no RAG

**Status:** Not started

**Tasks:**
- [ ] Extend `ConsultationResult` with: `suggested_tool`, `suggested_library`, `suggested_topic`.
- [ ] Populate those fields when no chunks are found.
- [ ] Return fields through MCP response mapping in `server.py`.
- [ ] Add tests for field population and suggestion correctness.

**DoD:** Clients can parse and automatically follow up with `tapps_lookup_docs`.

---

### 10.4 — Testing knowledge-base expansion

**Status:** Not started

**Tasks:**
- [ ] Add `src/tapps_mcp/experts/knowledge/testing/test-configuration-and-urls.md`.
- [ ] Include patterns for base URL config, env vars, fixtures, monkeypatch, avoiding hardcoded localhost.
- [ ] Validate retrieval returns new content for representative queries.

**DoD:** Testing expert returns relevant chunks for config/URL/env questions.

---

### 10.5 — Optional `tapps_research` combined tool

**Status:** Not started

**Tasks:**
- [ ] Define tool schema and response format.
- [ ] Implement: consult expert → fallback doc lookup (on low confidence or empty RAG) → merged answer.
- [ ] Register tool and document usage.
- [ ] Add tests and latency guardrail checks.

**DoD:** Single call can return combined expert+docs guidance.

---

## 4) New Epic 11 (added): Retrieval quality, hot-rank, fuzzy, references

This epic captures improvements discussed after Epic 10 planning and is not covered deeply by the original file.

## Epic 11: Retrieval & Ranking Optimization

**Priority:** P1/P2 mix
**Dependencies:** Epic 10.3 recommended; can start partially in parallel.

### 11.1 — Hybrid retrieval + rerank

**Goal:** Improve relevance by combining lexical + vector retrieval before final ranking.

**Tasks:**
- [ ] Retrieve candidate sets from both simple keyword and vector backends.
- [ ] Add weighted fusion score (vector, lexical, structural).
- [ ] Add final rerank stage for top-N candidates.
- [ ] Expose retrieval diagnostics (which backend contributed each final chunk).

**DoD:** Better relevance on benchmark prompts vs current single-path behavior.

---

### 11.2 — Hot-rank from usage + feedback

**Goal:** Use real performance data to prioritize chunks/sources/domains that historically help.

**Tasks:**
- [ ] Define hot-rank function with recency decay + helpfulness + confidence trend.
- [ ] Consume metrics from feedback/expert/rag trackers.
- [ ] Apply hot-rank as tie-breaker in retrieval ranking.
- [ ] Add guardrails to avoid popularity-only lock-in.

**DoD:** Repeat queries trend toward higher helpfulness with no quality regressions.

---

### 11.3 — Fuzzy lookup v2 (library/topic resolution)

**Goal:** Reduce mis-resolution and improve recall beyond LCS-only matching.

**Tasks:**
- [ ] Add multi-signal matching (edit distance/token overlap + existing alias/prefix/LCS).
- [ ] Add confidence bands + “did you mean” when low confidence.
- [ ] Incorporate project manifest/library detector priors for disambiguation.
- [ ] Add eval tests for typo, alias, shorthand, and ambiguous library names.

**DoD:** Higher correct-resolution rate and fewer wrong fuzzy hits.

---

### 11.4 — Context7 code-reference quality normalization

**Goal:** Return cleaner, more actionable code references from Context7 content.

**Tasks:**
- [ ] Rank snippets by code completeness + query overlap + language/framework fit.
- [ ] Deduplicate similar snippets.
- [ ] Add compact “reference card” output shape in merged responses.
- [ ] Enforce per-section token budgets to avoid context overflow.

**DoD:** Fewer noisy snippets; stronger practical examples.

---

### 11.5 — Evaluation harness + quality gates for retrieval changes

**Goal:** Prevent regressions while tuning ranking/fuzzy behavior.

**Tasks:**
- [ ] Add benchmark query set (by domain + library).
- [ ] Define metrics: top-k relevance proxy, resolution accuracy, latency p95, fallback rate.
- [ ] Add CI check(s) for regression thresholds.
- [ ] Publish periodic before/after score snapshots.

**DoD:** Retrieval optimization can be tuned safely and measured objectively.

---

## 5) Updated implementation order

1. **10.3** Structured hints (enables deterministic client follow-up)
2. **10.1** Auto-fallback integration
3. **10.2** Workflow/docs coupling updates
4. **10.4** Testing KB expansion
5. **11.5** Baseline eval harness
6. **11.1** Hybrid retrieval + rerank
7. **11.3** Fuzzy v2
8. **11.2** Hot-rank integration
9. **11.4** Context7 code-reference normalization
10. **10.5** Optional `tapps_research` tool

---

## 6) Acceptance criteria (re-baselined)

- [ ] Epic 10 P1 complete: structured hints + auto-fallback + workflow guidance shipped.
- [ ] Expert response supports deterministic next-step automation when RAG is empty.
- [ ] Testing expert covers URL/config/env fixture questions with retrievable knowledge.
- [ ] Retrieval quality improvements from Epic 11 measured against baseline and non-regressive on latency.
- [ ] Fuzzy lookup accuracy improved with explicit ambiguity handling.
- [ ] Context7-derived code references are better ranked, deduplicated, and budgeted.

---

## 7) Validation checklist for maintainers

Run this quick audit before marking this plan complete:

- [ ] Verify new response fields exist in models + server mapping.
- [ ] Verify auto-fallback path exists in `experts/engine.py`.
- [ ] Verify new testing KB file exists and is indexed.
- [ ] Verify `tapps_research` tool exists (if implemented).
- [ ] Verify retrieval/ranking metrics are captured and compared to baseline.

Suggested checks:

```bash
rg -n "suggested_tool|suggested_library|suggested_topic|fallback_used|fallback_library|fallback_topic" src/tapps_mcp
rg -n "tapps_research" src/tapps_mcp
rg --files src/tapps_mcp/experts/knowledge/testing
rg -n "rerank|hybrid|hot-rank|hot_rank|fuzzy" src/tapps_mcp
```

---

## 8) Implementation readiness package (kickoff guide)

This section converts the plan into an immediately executable implementation sequence.

### 8.1) First PR scope (recommended)

Target **Epic 10.3 only** in the first implementation PR to keep risk low and enable deterministic client workflows.

**Files expected to change:**

- `src/tapps_mcp/experts/models.py`
- `src/tapps_mcp/experts/engine.py`
- `src/tapps_mcp/server.py`
- `tests/` files covering expert consultation response structure

**Out-of-scope for PR 1:**

- Any Context7 fallback execution path changes (Epic 10.1)
- New tool registration (`tapps_research`)
- Retrieval/ranking architecture changes (Epic 11)

### 8.2) PR-by-PR rollout plan

1. **PR 1 — Structured hints (10.3)**
   - Add `suggested_tool`, `suggested_library`, `suggested_topic` to result model.
   - Populate when retrieval has no chunks.
   - Ensure MCP response mapping emits fields.
   - Add tests for no-RAG and normal-RAG scenarios.
2. **PR 2 — Auto-fallback execution (10.1)**
   - Add guarded fallback call path + config flag.
   - Add merged-answer attribution and budgets.
   - Add tests for fallback triggered/not-triggered.
3. **PR 3 — Workflow/docs alignment (10.2 + 10.4)**
   - Update AGENTS/workflow hints.
   - Add testing KB file and retrieval tests.
4. **PR 4+ — Retrieval optimization track (11.5 → 11.1/11.3 → 11.2/11.4)**
   - Establish benchmark and regression checks first.
   - Apply retrieval changes incrementally with measurable deltas.

### 8.3) Pre-implementation checks (must pass before PR 1 coding)

- [ ] Confirm response model can add optional fields without breaking existing clients.
- [ ] Identify all server response serialization paths for `tapps_consult_expert`.
- [ ] Freeze a baseline behavior snapshot for no-RAG responses (fixtures/snapshots).
- [ ] Define exact trigger condition for “no RAG” (`chunks_used == 0` and/or `sources == []`).

### 8.4) Risks and mitigations for kickoff

- **Risk:** Introducing structured fields could break strict client parsers.
  - **Mitigation:** Add fields as optional/null; maintain existing fields unchanged.
- **Risk:** False positives on no-RAG condition cause noisy suggestions.
  - **Mitigation:** Gate on both retrieval stats and source list checks.
- **Risk:** Tests become brittle due to response text variability.
  - **Mitigation:** Assert structured fields and invariants, not exact prose.

### 8.5) Definition of ready-to-implement

Implementation should start only when all are true:

- [ ] PR 1 scope agreed (10.3 only).
- [ ] No-RAG trigger condition documented in code comments/tests.
- [ ] Response schema update plan approved (backward-compatible optional fields).
- [ ] Baseline tests identified and runnable locally.

---

## 9) References

- Existing implementation surfaces:
  - `src/tapps_mcp/server.py`
  - `src/tapps_mcp/experts/engine.py`
  - `src/tapps_mcp/experts/models.py`
  - `src/tapps_mcp/knowledge/lookup.py`
  - `src/tapps_mcp/knowledge/fuzzy_matcher.py`
  - `src/tapps_mcp/experts/rag.py`
  - `src/tapps_mcp/experts/vector_rag.py`
  - `src/tapps_mcp/experts/rag_index.py`
- Metrics/adaptive signals:
  - `src/tapps_mcp/metrics/feedback.py`
  - `src/tapps_mcp/metrics/expert_metrics.py`
  - `src/tapps_mcp/metrics/rag_metrics.py`
- Prior plan and epic mapping docs:
  - `docs/planning/epics/README.md`
  - `docs/INIT_AND_UPGRADE_FEATURE_LIST.md`
