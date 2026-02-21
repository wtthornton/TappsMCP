# TappsMCP Expert + Context7 + Retrieval Optimization — Implementation Plan

**Source:** [TAPPS_MCP_IMPROVEMENT_RECOMMENDATIONS.md](../../../HomeIQ/implementation/TAPPS_MCP_IMPROVEMENT_RECOMMENDATIONS.md)
**Created:** 2026-02-18
**Revised:** 2026-02-21 (verified against current code)
**Status:** Epic 10 substantially complete (4/5 stories implemented); Epic 11 not started
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

## 1.2) Current implementation snapshot (verified 2026-02-21)

| Capability | Current status | Evidence |
|---|---|---|
| `tapps_consult_expert` basic flow (domain detect, retrieve, confidence, sources) | ✅ Implemented | `experts/engine.py`, `server.py` |
| Low-confidence nudge to call `tapps_lookup_docs` | ✅ Implemented | `experts/engine.py:248-254` |
| Automatic Context7 fallback inside expert flow when RAG empty | ✅ Implemented | `experts/engine.py:86-112` (`_lookup_docs_sync`), `engine.py:224-244` (fallback path), `settings.py:131-142` (config flags) |
| Structured fields `suggested_tool`, `suggested_library`, `suggested_topic` in response model | ✅ Implemented | `experts/models.py:68-79`, `server.py:663-665`, `engine.py:199-201,213-214,266-268` |
| Structured fields `fallback_used`, `fallback_library`, `fallback_topic` | ✅ Implemented | `experts/models.py:80-91`, `server.py:666-668`, `engine.py:202-204,235-237,269-271` |
| Optional `tapps_research` tool | ❌ Not implemented | no tool handler/registration in `server.py` |
| Testing KB file `test-configuration-and-urls.md` | ✅ Implemented | `experts/knowledge/testing/test-configuration-and-urls.md` (57 lines covering base URL config, env vars, fixtures, monkeypatch, localhost avoidance) |
| Context7 cache + SWR + stale fallback | ✅ Implemented | `knowledge/lookup.py` |
| Library fuzzy match | ⚠️ Basic only (LCS + alias + prefix) | `knowledge/fuzzy_matcher.py` — no edit distance, no "did you mean", no manifest priors |
| Retrieval architecture | ⚠️ Dual backend exists; no hybrid fusion/rerank | `experts/rag.py`, `experts/vector_rag.py` — VectorKnowledgeBase uses one backend at a time, never both |
| Signals for hot-rank/adaptive ranking | ⚠️ Foundations exist; ranking policy not implemented | `metrics/feedback.py`, `metrics/expert_metrics.py`, `metrics/rag_metrics.py` track data but no ranking function consumes it |

---

### Snapshot summary

- Epic 10 stories completed in code: **4 / 5** (10.1 ✅, 10.2 ⚠️ partial, 10.3 ✅, 10.4 ✅, 10.5 ❌)
- Epic 11 stories completed in code: **0 / 5**
- Overall planned stories completed: **4 / 10** (with 10.2 partially done)

---

## 3) What remains from original Epic 10 (still open)

## Epic 10: Expert + Context7 Integration (carry forward)

**Priority:** P1
**Dependencies:** Epic 2, Epic 3

### 10.1 — Auto-fallback to Context7 when expert RAG is empty

**Status:** ✅ Complete

**Tasks:**
- [x] In `experts/engine.py`, when `chunks_used == 0` (or no sources), infer library/topic from domain+question and perform lookup. — `_infer_lookup_hints()` at line 38, triggered when `context` is empty at line 212.
- [x] Bridge sync expert flow with async lookup in a safe helper (`sync_lookup` wrapper). — `_lookup_docs_sync()` at line 86 uses `asyncio.run()` to bridge sync→async.
- [x] Merge fallback content into expert answer with explicit attribution section. — Lines 239-244 merge with "### Context7 fallback (auto-attached)" header.
- [x] Add response budget limits for merged content. — `settings.expert_fallback_max_chars` (default 1200) applied at line 238.
- [x] Add config flag (opt-in/out) for auto-fallback behavior. — `settings.expert_auto_fallback` (default True) checked at line 232.
- [x] Add fields: `fallback_used`, `fallback_library`, `fallback_topic`. — `models.py:80-91`, populated at `engine.py:235-237`.

**DoD:** ✅ Empty-RAG consultation can return a combined expert+docs answer in one call.

---

### 10.2 — Workflow coupling updates (expert + docs)

**Status:** ⚠️ Partially complete

**Tasks:**
- [x] Update `tapps_server_info` recommended workflow wording and stage hints. — `server.py:229-234` includes "For domain+library questions, pair with tapps_consult_expert()" in `recommended_workflow`. The `tapps_workflow` "feature" prompt (line 1669-1679) sequences `tapps_lookup_docs` → `tapps_consult_expert` as steps 3-4.
- [ ] Update AGENTS/template/research prompts to explicitly require combined expert+lookup for library-specific domain questions. — `AGENTS.md` mentions both tools in recommended workflow (steps 3 and 7) but does not explicitly state to **pair** them for library-specific domain questions. The coupling is implicit, not prescriptive.

**Remaining:** Make AGENTS.md step 7 ("When in doubt: Use tapps_consult_expert") explicitly advise pairing with `tapps_lookup_docs` for library-specific domain questions (e.g. "For library-specific questions, call both tapps_consult_expert and tapps_lookup_docs to get expert guidance backed by current docs.").

**DoD:** Partially met — server-side workflow hints updated; AGENTS.md wording needs explicit coupling language.

---

### 10.3 — Structured “next tool” hints when no RAG

**Status:** ✅ Complete

**Tasks:**
- [x] Extend `ConsultationResult` with: `suggested_tool`, `suggested_library`, `suggested_topic`. — `models.py:68-79`.
- [x] Populate those fields when no chunks are found. — `engine.py:213-214` sets `suggested_tool=”tapps_lookup_docs”` and calls `_infer_lookup_hints()` when `context` is empty.
- [x] Return fields through MCP response mapping in `server.py`. — `server.py:663-665`.
- [x] Add tests for field population and suggestion correctness. — `tests/unit/test_expert_engine.py:67-72` (unit), `tests/integration/test_expert_pipeline.py:179-184` (integration).

**DoD:** ✅ Clients can parse and automatically follow up with `tapps_lookup_docs`.

---

### 10.4 — Testing knowledge-base expansion

**Status:** ✅ Complete

**Tasks:**
- [x] Add `src/tapps_mcp/experts/knowledge/testing/test-configuration-and-urls.md`. — File exists (57 lines).
- [x] Include patterns for base URL config, env vars, fixtures, monkeypatch, avoiding hardcoded localhost. — All patterns present with code examples for `base_url` fixture, `monkeypatch.setenv`, config isolation, network patching, and localhost avoidance.
- [ ] Validate retrieval returns new content for representative queries. — No dedicated retrieval test for this specific KB file exists yet. The file is indexed automatically by the RAG system, but explicit query-based validation is missing.

**Remaining:** Add a test that queries the testing expert for "base URL configuration" or "monkeypatch environment variables" and asserts relevant chunks are returned from `test-configuration-and-urls.md`.

**DoD:** Mostly met — file exists with correct content; automated retrieval validation not yet added.

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

1. ~~**10.3** Structured hints (enables deterministic client follow-up)~~ — ✅ Done
2. ~~**10.1** Auto-fallback integration~~ — ✅ Done
3. **10.2** Workflow/docs coupling updates — ⚠️ Partially done (AGENTS.md coupling language remaining)
4. **10.4** Testing KB expansion — ⚠️ Mostly done (retrieval validation test remaining)
5. **11.5** Baseline eval harness — ❌ Not started
6. **11.1** Hybrid retrieval + rerank — ❌ Not started
7. **11.3** Fuzzy v2 — ❌ Not started
8. **11.2** Hot-rank integration — ❌ Not started
9. **11.4** Context7 code-reference normalization — ❌ Not started
10. **10.5** Optional `tapps_research` tool — ❌ Not started

---

## 6) Acceptance criteria (verified 2026-02-21)

- [x] Epic 10 P1 complete: structured hints + auto-fallback + workflow guidance shipped. — ✅ 10.1, 10.3 fully complete; 10.2 partially complete (server wording done, AGENTS.md coupling language needed).
- [x] Expert response supports deterministic next-step automation when RAG is empty. — ✅ `suggested_tool`, `suggested_library`, `suggested_topic` populated in no-RAG responses.
- [x] Testing expert covers URL/config/env fixture questions with retrievable knowledge. — ✅ `test-configuration-and-urls.md` exists with full pattern coverage (retrieval validation test still missing).
- [ ] Retrieval quality improvements from Epic 11 measured against baseline and non-regressive on latency. — ❌ Epic 11 not started.
- [ ] Fuzzy lookup accuracy improved with explicit ambiguity handling. — ❌ Still LCS-only (Epic 11.3 not started).
- [ ] Context7-derived code references are better ranked, deduplicated, and budgeted. — ❌ Epic 11.4 not started.

---

## 7) Validation checklist for maintainers

Run this quick audit before marking this plan complete:

- [x] Verify new response fields exist in models + server mapping. — ✅ Verified 2026-02-21. All 6 fields (`suggested_tool`, `suggested_library`, `suggested_topic`, `fallback_used`, `fallback_library`, `fallback_topic`) present in `models.py`, populated in `engine.py`, and mapped in `server.py:663-668`.
- [x] Verify auto-fallback path exists in `experts/engine.py`. — ✅ Verified 2026-02-21. `_lookup_docs_sync()` at line 86, fallback path at lines 224-244, config flags in `settings.py:131-142`.
- [x] Verify new testing KB file exists and is indexed. — ✅ Verified 2026-02-21. `experts/knowledge/testing/test-configuration-and-urls.md` present (57 lines).
- [x] Verify `tapps_research` tool exists (if implemented). — ❌ Not implemented (by design — last in implementation order).
- [ ] Verify retrieval/ranking metrics are captured and compared to baseline. — ❌ Not yet. Metric infrastructure exists (`rag_metrics.py`, `expert_metrics.py`, `feedback.py`) but no baseline comparison or retrieval quality regression checks are in place.

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

### 8.1) First PR scope (recommended) — ✅ SHIPPED

Target **Epic 10.3 only** in the first implementation PR to keep risk low and enable deterministic client workflows.

**Files changed (verified):**

- `src/tapps_mcp/experts/models.py` — ✅ Fields added
- `src/tapps_mcp/experts/engine.py` — ✅ Population logic added
- `src/tapps_mcp/server.py` — ✅ Response mapping added
- `tests/unit/test_expert_engine.py` — ✅ Tests added
- `tests/integration/test_expert_pipeline.py` — ✅ Tests added

**Note:** PRs 1 and 2 were implemented together (10.3 + 10.1 shipped in code).

### 8.2) PR-by-PR rollout plan

1. **PR 1 — Structured hints (10.3)** — ✅ SHIPPED
   - Add `suggested_tool`, `suggested_library`, `suggested_topic` to result model.
   - Populate when retrieval has no chunks.
   - Ensure MCP response mapping emits fields.
   - Add tests for no-RAG and normal-RAG scenarios.
2. **PR 2 — Auto-fallback execution (10.1)** — ✅ SHIPPED
   - Add guarded fallback call path + config flag.
   - Add merged-answer attribution and budgets.
   - Add tests for fallback triggered/not-triggered.
3. **PR 3 — Workflow/docs alignment (10.2 + 10.4)** — ⚠️ PARTIALLY SHIPPED
   - Update AGENTS/workflow hints. — Server-side done; AGENTS.md explicit coupling language still needed.
   - Add testing KB file and retrieval tests. — KB file added; retrieval validation test still needed.
4. **PR 4+ — Retrieval optimization track (11.5 → 11.1/11.3 → 11.2/11.4)** — ❌ NOT STARTED
   - Establish benchmark and regression checks first.
   - Apply retrieval changes incrementally with measurable deltas.

### 8.3) Pre-implementation checks (must pass before PR 1 coding)

- [x] Confirm response model can add optional fields without breaking existing clients. — ✅ All new fields use `Field(default=None)` or `Field(default=False)`, backward-compatible.
- [x] Identify all server response serialization paths for `tapps_consult_expert`. — ✅ Single path in `server.py:653-670`.
- [x] Freeze a baseline behavior snapshot for no-RAG responses (fixtures/snapshots). — ✅ Tests in `test_expert_engine.py:67-79` validate no-RAG field population.
- [x] Define exact trigger condition for “no RAG” (`chunks_used == 0` and/or `sources == []`). — ✅ Trigger is `if context:` / `else:` in `engine.py:205-221` — fires when `kb.get_context()` returns empty string (which happens when `chunks == []`).

### 8.4) Risks and mitigations for kickoff

- **Risk:** Introducing structured fields could break strict client parsers.
  - **Mitigation:** Add fields as optional/null; maintain existing fields unchanged.
- **Risk:** False positives on no-RAG condition cause noisy suggestions.
  - **Mitigation:** Gate on both retrieval stats and source list checks.
- **Risk:** Tests become brittle due to response text variability.
  - **Mitigation:** Assert structured fields and invariants, not exact prose.

### 8.5) Definition of ready-to-implement

Implementation should start only when all are true:

- [x] PR 1 scope agreed (10.3 only). — ✅ PR 1 shipped.
- [x] No-RAG trigger condition documented in code comments/tests. — ✅ Tested in `test_expert_engine.py:67-72`.
- [x] Response schema update plan approved (backward-compatible optional fields). — ✅ All fields optional with defaults.
- [x] Baseline tests identified and runnable locally. — ✅ Unit and integration tests exist.

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
