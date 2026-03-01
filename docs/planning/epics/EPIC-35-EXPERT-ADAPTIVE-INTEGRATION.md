# Epic 35: Expert System Adaptive Integration

**Status:** Complete (2026-03-01) — all 4 stories, 72 new tests
**Priority:** P1 — High (adaptive domain detector exists but is not wired into the main consultation flow)
**Estimated LOE:** ~1.5-2 weeks (1 developer)
**Dependencies:** Epic 3 (Expert System), Epic 5 (Adaptive Learning), Epic 7 (Metrics)
**Blocks:** None

> **Monorepo Note:** Expert modules now have dual locations after the tapps-core extraction. The canonical source code is in `packages/tapps-core/src/tapps_core/experts/`, while `packages/tapps-mcp/src/tapps_mcp/experts/` re-exports for backward compatibility. Edits should target the **tapps-core** canonical location. If Tier 2 extraction is incomplete when this epic starts, adjust paths accordingly.

---

## Goal

Integrate the existing `AdaptiveDomainDetector` into the main expert consultation flow, add query expansion with synonym matching to improve domain detection recall, and add knowledge freshness warnings during expert consultations. The adaptive detector was built in Epic 5 but never wired into `engine.py` — questions are still routed through the static `DomainDetector` exclusively. This epic closes that gap and adds two complementary improvements informed by AI OS's hybrid search approach.

## Motivation

The expert engine (`experts/engine.py`) resolves domains in the `_resolve_domain()` function (approximately line 180-191, verify exact line at implementation time):

```python
mappings = DomainDetector.detect_from_question(question)  # <-- static only
resolved_domain = mappings[0].domain if mappings else "software-architecture"
```

The `AdaptiveDomainDetector` in `experts/adaptive_domain_detector.py` learns from `tapps_feedback` outcomes which domains produce good results for which query patterns. **Verified 2026-02-28:** It exists with full implementation (66+ tests), supports prompt-based detection, code pattern detection, and consultation history analysis with 20+ domain/keyword mappings — but nothing calls it from the consultation path. Meanwhile, the static `DomainDetector` uses hardcoded keyword lists that miss common synonyms ("authentication" won't match "auth" keyword, "optimizing" won't match "optimization").

## 2026 Best Practices Applied

- **Adaptive routing** — AI OS routes skills to different models (haiku/sonnet/opus) based on task type. TappsMCP should route questions to the best-fit domain based on learned outcomes, not just static keywords.
- **Feedback loop** — The `tapps_feedback` tool already collects outcome data. This epic connects that data to domain selection, creating a closed learning loop.
- **Query expansion** — Standard IR technique for handling lexical mismatch. A lightweight synonym dict (~50 entries) handles the most common cases without NLP dependencies.
- **Knowledge freshness** — Stale knowledge produces stale answers. TappsMCP already has `knowledge_freshness.py` — this epic adds a freshness caveat to consultation results when top chunks are old.
- **Deterministic** — Synonym expansion is a dict lookup. Adaptive routing uses statistical weights from stored feedback. Both are deterministic.

## Acceptance Criteria

- [ ] `AdaptiveDomainDetector` is used as primary detector when `adaptive.enabled` is True in settings
- [ ] Falls back to static `DomainDetector` when adaptive has insufficient training data (< `min_outcomes`)
- [ ] Query expansion dict (~50 synonym pairs) improves detection recall for common terms
- [ ] "authentication" matches "security" domain, "optimizing" matches "performance-optimization", etc.
- [ ] Knowledge freshness check runs during consultations; results include freshness caveat when chunks are > 1 year old
- [ ] Feedback from `tapps_feedback` trains the adaptive detector via outcome recording
- [ ] All changes backward compatible: no behavior change when `adaptive.enabled` is False (default)
- [ ] Unit tests for adaptive integration, synonym expansion, freshness checking
- [ ] Domain detection accuracy improved on a sample of 20 representative queries

---

## Stories

### 35.1 — Wire Adaptive Domain Detector into Engine

**Points:** 5

Integrate `AdaptiveDomainDetector` as the primary domain resolver when adaptive learning is enabled.

**Source Files:**
- `packages/tapps-core/src/tapps_core/experts/engine.py` (canonical location) (modify)
- `packages/tapps-core/src/tapps_core/experts/adaptive_domain_detector.py` (canonical location) (may need minor interface alignment)

**Tasks:**
- Modify `_resolve_domain()` in `engine.py`:
  - When `load_settings().adaptive.enabled` is True:
    1. Try `AdaptiveDomainDetector.detect(question)` first
    2. If it returns results with confidence above a threshold (0.4), use the top result
    3. Otherwise, fall back to `DomainDetector.detect_from_question(question)`
  - When `adaptive.enabled` is False (default): use static detector only (current behavior)
- Align `AdaptiveDomainDetector` interface with what `_resolve_domain()` expects:
  - Should return `list[DomainMapping]` (same type as static detector)
  - If current return type differs, add a conversion method
- Add `adaptive_domain_used: bool` field to `ConsultationResult` to track when adaptive routing was used
- Ensure `tapps_feedback` outcomes are recorded in the adaptive detector's training data:
  - Verify the existing feedback → adaptive pipeline works end-to-end
  - If not connected, wire `tapps_feedback` handler to call `AdaptiveDomainDetector.record_outcome()`
- Add settings validation: `adaptive.min_outcomes` controls minimum training data before adaptive activates
- Write ~10 unit tests:
  - Adaptive enabled + sufficient data → adaptive detector used
  - Adaptive enabled + insufficient data → falls back to static
  - Adaptive disabled → static only (no behavior change)
  - Adaptive result conversion to DomainMapping
  - Feedback recording integration
  - `adaptive_domain_used` tracking in result

**Definition of Done:** Adaptive detector is the primary router when enabled and trained. Fallback to static is seamless. Feedback loop is complete.

---

### 35.2 — Query Expansion with Synonym Matching

**Points:** 3

Add a synonym/expansion dictionary to improve domain detection recall for common lexical variants.

**Source Files:**
- `packages/tapps-core/src/tapps_core/experts/domain_detector.py` (canonical location) (modify)
- `packages/tapps-core/src/tapps_core/experts/query_expansion.py` (new)

**Tasks:**
- Create `experts/query_expansion.py` with:
  - `SYNONYMS: dict[str, str]` — maps variant → canonical form (~50 entries):
    ```python
    SYNONYMS = {
        "authentication": "auth",
        "authorization": "auth",
        "authenticate": "auth",
        "authorize": "auth",
        "optimizing": "optimization",
        "optimize": "optimization",
        "optimise": "optimization",
        "testing": "test",
        "tests": "test",
        "tested": "test",
        "deploying": "deployment",
        "deploy": "deployment",
        "monitoring": "monitor",
        "caching": "cache",
        "cached": "cache",
        "containerizing": "container",
        "containerize": "container",
        "containerized": "container",
        "securing": "security",
        "secured": "security",
        "debugging": "debug",
        "debugged": "debug",
        "profiling": "profiling",
        "profiled": "profiling",
        "refactoring": "refactor",
        "refactored": "refactor",
        "scaling": "scalability",
        "scaled": "scalability",
        "logging": "log",
        "logged": "log",
        "validating": "validation",
        "validated": "validation",
        "migrating": "migration",
        "migrated": "migration",
        "configuring": "configuration",
        "configured": "configuration",
        "serializing": "serialization",
        "serialized": "serialization",
        "documenting": "documentation",
        "documented": "documentation",
        "vulnerability": "vulnerability",
        "vulnerabilities": "vulnerability",
        "dependency": "dependencies",
        "microservice": "microservices",
        "api": "api",
        "apis": "api",
        "restful": "rest",
        "websockets": "websocket",
        "ci/cd": "ci-cd",
        "cicd": "ci-cd",
    }
    ```
  - `expand_query(query: str) -> str` — expand synonyms in query:
    - Split query into words
    - For each word, if it's in SYNONYMS, add both the original and the canonical form
    - Return expanded query string
  - `expand_keywords(keywords: list[str]) -> list[str]` — expand a keyword list with synonym variants (for domain detector keyword matching)
- Modify `DomainDetector.detect_from_question()`:
  - Call `expand_query()` on the question before keyword matching
  - This means "how do I authenticate users" will expand "authenticate" to include "auth", which matches the security domain's keyword list
- Write ~10 unit tests:
  - Synonym expansion: "authentication" → includes "auth"
  - Multi-word query expansion
  - Unknown words pass through unchanged
  - Case insensitivity
  - Domain detection improvement: "How do I authenticate?" now matches security domain
  - Edge cases: empty query, single word, already-canonical forms

**Definition of Done:** Synonym expansion improves domain detection recall. Common variants are handled. No regressions on existing queries.

---

### 35.3 — Knowledge Freshness Warnings

**Points:** 3

Add freshness checking during expert consultations, with caveats in results when retrieved knowledge is potentially outdated.

**Source Files:**
- `packages/tapps-core/src/tapps_core/experts/engine.py` (canonical location) (modify)
- `packages/tapps-core/src/tapps_core/experts/knowledge_freshness.py` (canonical location) (existing, may need minor extension)

**Tasks:**
- After `_retrieve_knowledge()` in the consultation pipeline, check the age of retrieved knowledge chunks:
  - Use `knowledge_freshness.py` to get the modification timestamp of the source knowledge files
  - If the top 3 chunks all come from files older than 365 days, set a `stale_knowledge: True` flag
  - Compute `oldest_chunk_age_days` from file timestamps
- Add freshness metadata to `ConsultationResult`:
  - `stale_knowledge: bool = False`
  - `oldest_chunk_age_days: int | None = None`
  - `freshness_caveat: str | None = None`
- When `stale_knowledge` is True, set `freshness_caveat` to:
  "Note: Retrieved knowledge may be outdated (oldest source: {age} days). Consider verifying with tapps_lookup_docs() for the latest documentation."
- Include `freshness_caveat` in the tool response (appended to the expert answer)
- Add a nudge in `common/nudges.py` for `tapps_consult_expert` when stale knowledge is detected:
  "Knowledge may be outdated. Call tapps_lookup_docs() for current documentation."
- Write ~8 unit tests:
  - Fresh knowledge (< 365 days) → no caveat
  - Stale knowledge (> 365 days) → caveat present
  - Mixed freshness → uses oldest chunk age
  - Freshness metadata in ConsultationResult
  - Nudge generated for stale knowledge
  - Edge case: no chunks retrieved → no freshness check

**Definition of Done:** Expert consultations include freshness warnings when knowledge is old. Caveat guides users to verify with docs lookup.

---

### 35.4 — Domain Detection Quality Tests

**Points:** 2

Create a test dataset of representative queries and verify improved detection accuracy after synonym expansion and adaptive integration.

**Source Files:**
- `tests/unit/test_domain_detection_quality.py` (new)

**Tasks:**
- Create a test dataset of 20 representative queries across all 17 domains:
  - 10 queries that should match with current static detection (regression guard)
  - 5 queries that fail with current detection but succeed with synonyms
  - 5 queries that demonstrate adaptive routing benefit
- Test structure: `(query, expected_domain, description)` tuples
- Run all 20 queries through:
  - Static detection only → expect ≥ 10/20 correct
  - Static + synonym expansion → expect ≥ 15/20 correct
  - Adaptive (with mocked training data) → expect ≥ 18/20 correct
- Track detection accuracy as a measurable quality metric
- Write ~20 parameterized tests (one per query)

**Definition of Done:** 20-query test suite passes. Synonym expansion improves accuracy by ≥ 25%. Adaptive further improves when trained.

---

## Performance Targets

| Operation | Target (p95) | Notes |
|-----------|-------------|-------|
| Query expansion | < 1ms | Dict lookup per word |
| Static domain detection | < 5ms | Regex matching (unchanged) |
| Adaptive domain detection | < 10ms | Statistical lookup + fallback |
| Knowledge freshness check | < 5ms | File stat() per chunk source |
| Full consultation (with all improvements) | < 200ms | RAG search + scoring + freshness |

## Key Dependencies

- Epic 3 (`experts/engine.py`, `experts/domain_detector.py`, `experts/knowledge_freshness.py`)
- Epic 5 (`experts/adaptive_domain_detector.py`, `adaptive/scoring_engine.py`)
- Epic 7 (`metrics/feedback.py` — for outcome recording)

## Key Design Decisions

1. **Adaptive as opt-in** — `adaptive.enabled` defaults to False. This ensures no behavior change for existing users. Enable explicitly after collecting sufficient feedback data.
2. **Confidence threshold for adaptive (0.4)** — Below this, the adaptive detector's predictions are too uncertain to trust. Fall back to static detection.
3. **Synonym dict over NLP** — A hardcoded dict of ~50 entries is simple, fast, deterministic, and dependency-free. It covers the most common technical English variants. Full NLP (WordNet, spaCy) would be overkill for keyword expansion.
4. **365-day freshness threshold** — Knowledge files older than 1 year may reference outdated versions, deprecated APIs, or superseded practices. This is conservative — 6 months might be more appropriate but would trigger too many warnings for stable knowledge (e.g., OWASP top 10).
5. **Freshness as caveat, not filter** — Old knowledge can still be correct. The caveat prompts verification rather than discarding potentially valid information.
