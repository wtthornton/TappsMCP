# Epic 62: Context7-Assisted Memory Validation & Enrichment

**Status:** Complete
**Priority:** P2 — Medium (improves memory reliability without new user-facing tools)
**Estimated LOE:** ~2.5-3 weeks (1 developer)
**Dependencies:** Epic 23-25 (Memory Foundation/Intelligence/Retrieval), Epic 2 (Knowledge & Docs Lookup), Epic 34 (BM25 Retrieval Upgrade), Epic 58 (Memory Consolidation)

---

## Problem Statement

Memory entries accumulate over sessions but have no mechanism to verify their accuracy against authoritative sources. A memory saved as "FastAPI uses `@app.get()` for route decorators" might become outdated if FastAPI changes its API. Today, the only validation is project-state contradiction detection (`contradictions.py`), which checks file existence, tech stack drift, and branch existence — but never checks whether the *content* of a memory aligns with current library documentation.

### Current Gaps

1. **No documentation cross-reference** — Memories about libraries/frameworks are never validated against Context7 or LlmsTxt docs
2. **Confidence is time-based only** — Decay reduces confidence uniformly regardless of whether content is actually correct
3. **Stale patterns persist** — A memory like "use `requests.get()` with `verify=False` for local testing" will persist at its confidence level until natural decay, even though security docs strongly advise against it
4. **No enrichment** — Memories reference libraries but never link to authoritative documentation that could help future consultations
5. **Seeded memories unverified** — `reseed_from_profile()` creates system-sourced memories from tech stack detection, but never validates that detected frameworks match their documented usage patterns

### Value Proposition

- **Higher trust** — Docs-validated memories carry provable confidence, not just time-based decay
- **Faster contradiction detection** — Catch outdated API patterns, deprecated features, and incorrect usage before they mislead agents
- **Richer expert context** — Memories enriched with doc references give `tapps_consult_expert` better injection material
- **Self-healing memory** — Stale or incorrect memories get flagged proactively instead of lingering until GC

---

## Architecture

### New Module

```
packages/tapps-core/src/tapps_core/memory/doc_validation.py
```

### Data Flow

```
MemoryStore  ──>  ClaimExtractor  ──>  LookupEngine  ──>  DocValidator  ──>  ValidationResult
     │                                                          │
     │              (library, topic, claim)              (similarity score,
     │                                                   doc_confirmed,
     │                                                   doc_contradicted)
     │                                                          │
     └──────────  MemoryStore.update_fields()  <────────────────┘
                  (confidence adjustment,
                   doc_reference tag,
                   validation_reason)
```

### Design Principles

1. **Deterministic** — No LLM calls. Claim extraction uses regex + keyword matching. Validation uses TF-IDF cosine similarity (reuse `similarity.py` patterns).
2. **Non-destructive** — Validation never deletes memories. It adjusts confidence, adds tags, and sets `contradiction_reason` when docs conflict.
3. **Lazy & bounded** — Validation runs on-demand or at session start (configurable). Rate-limited to avoid Context7 API abuse. Capped at N entries per session.
4. **Cache-friendly** — Uses existing `KBCache` for doc lookups. Validated docs are cached; repeat validations are instant.
5. **Engagement-aware** — Validation depth scales with engagement level (high: full scan, medium: stale only, low: disabled).

---

## Stories

### Story 62.1 — Library Claim Extractor

**As a** memory validator, **I want to** extract library/framework references from memory entry values, **so that** I know which documentation to look up for validation.

**Implementation:**

New class `ClaimExtractor` in `doc_validation.py`:

```python
@dataclass
class LibraryClaim:
    library: str          # e.g., "fastapi", "sqlalchemy"
    topic: str            # e.g., "routing", "orm-queries", "overview"
    claim_text: str       # the specific sentence/phrase making the claim
    claim_type: ClaimType # enum: api_usage, version, config, pattern, deprecation

class ClaimExtractor:
    def extract_claims(self, entry: MemoryEntry) -> list[LibraryClaim]:
        """Extract library/framework claims from a memory value."""
```

**Extraction strategies (in priority order):**
1. **Tag-based** — If memory has tags like `["fastapi", "routing"]`, use them directly
2. **Import pattern** — Regex for `import X`, `from X import Y`, `X.method()` patterns
3. **Library name detection** — Reuse `knowledge/library_detector.py` `detect_libraries()` against memory value text
4. **Seeded memory shortcut** — If `seeded_from == "project_profile"`, extract from key (e.g., `framework-fastapi` → library=fastapi)
5. **Version claim** — Regex for `X>=1.0`, `X v2`, `X version 3.x` patterns

**Topic inference:**
- API method mentions → topic="api"
- Config/settings patterns → topic="configuration"
- Security keywords → topic="security"
- Default fallback → topic="overview"

**Acceptance criteria:**
- [ ] `ClaimExtractor` extracts library names from memory values using 5 strategies
- [ ] Returns empty list (not error) for memories with no library references
- [ ] Handles edge cases: multiple libraries per memory, ambiguous names, partial matches
- [ ] Topic inference covers api, configuration, security, testing, overview
- [ ] Unit tests cover all 5 extraction strategies with positive and negative cases
- [ ] Reuses `library_detector.py` for name normalization

---

### Story 62.2 — Documentation Similarity Scorer

**As a** memory validator, **I want to** score how well a memory claim aligns with retrieved documentation, **so that** I can determine if the memory is confirmed, contradicted, or inconclusive.

**Implementation:**

New class `DocSimilarityScorer` in `doc_validation.py`:

```python
@dataclass
class DocAlignment:
    similarity_score: float     # 0.0-1.0 TF-IDF cosine similarity
    alignment: AlignmentLevel   # enum: confirmed, contradicted, inconclusive, no_docs
    matched_snippet: str        # best-matching doc section (≤500 chars)
    doc_source: str             # "cache", "api", "fuzzy_match"
    confidence_delta: float     # suggested confidence adjustment (-0.3 to +0.2)

class DocSimilarityScorer:
    def score_claim(self, claim: LibraryClaim, doc_content: str) -> DocAlignment:
        """Score a memory claim against retrieved documentation."""
```

**Scoring approach:**
- Reuse TF-IDF preprocessing from `similarity.py` (stemming, stop-word removal)
- Compute cosine similarity between claim text and each doc chunk (split on `##` headers)
- Best-matching chunk becomes `matched_snippet`
- Thresholds:
  - `≥ 0.6` → `confirmed` (confidence_delta: +0.1 to +0.2)
  - `0.3–0.6` → `inconclusive` (confidence_delta: 0.0)
  - `< 0.3` → `contradicted` (confidence_delta: -0.1 to -0.3)
  - No docs found → `no_docs` (confidence_delta: 0.0)

**Contradiction detection heuristics (beyond similarity):**
- Deprecation markers in docs (`deprecated`, `removed in`, `no longer supported`) for API claims
- Version mismatch between memory claim and docs (e.g., memory says v1 API, docs show v2)
- Security anti-patterns flagged in docs that memory recommends (e.g., `verify=False`)

**Acceptance criteria:**
- [ ] TF-IDF cosine similarity scoring with configurable thresholds
- [ ] Chunk-level matching against `##`-delimited doc sections
- [ ] Deprecation/version/security heuristic checks
- [ ] Returns `no_docs` alignment when lookup fails (no false contradictions)
- [ ] Confidence delta bounded to [-0.3, +0.2] range
- [ ] Unit tests with known doc content → known alignment outcomes

---

### Story 62.3 — Validation Engine

**As a** memory validator, **I want to** orchestrate claim extraction, doc lookup, and similarity scoring into a single validation pipeline, **so that** I can validate one or many memory entries.

**Implementation:**

New class `MemoryDocValidator` in `doc_validation.py`:

```python
@dataclass
class EntryValidation:
    entry_key: str
    claims: list[LibraryClaim]
    alignments: list[DocAlignment]
    overall_status: ValidationStatus  # enum: validated, flagged, inconclusive, skipped
    confidence_adjustment: float      # net adjustment across all claims
    doc_references: list[str]         # library/topic pairs for tagging
    reason: str                       # human-readable summary

@dataclass
class ValidationReport:
    validated: int
    flagged: int
    inconclusive: int
    skipped: int          # no library claims found
    no_docs: int          # lookup returned no results
    entries: list[EntryValidation]
    elapsed_ms: float

class MemoryDocValidator:
    def __init__(self, store: MemoryStore, lookup_engine: LookupEngine,
                 config: DocValidationConfig):
        ...

    async def validate_entry(self, entry: MemoryEntry) -> EntryValidation:
        """Validate a single entry against documentation."""

    async def validate_batch(self, entries: list[MemoryEntry], *,
                             max_lookups: int = 20) -> ValidationReport:
        """Validate multiple entries with rate limiting."""

    async def validate_stale(self, *, confidence_threshold: float = 0.5,
                             max_entries: int = 10) -> ValidationReport:
        """Validate entries whose effective confidence has decayed below threshold."""
```

**Rate limiting:**
- Max `max_lookups` unique library+topic pairs per batch (default 20)
- Reuse cached docs across entries referencing the same library
- Skip entries already validated within `revalidation_interval_days` (default 7)

**Validation tracking:**
- New optional field on MemoryEntry: `last_validated` (ISO timestamp) — tracked via tags (`doc-validated:YYYY-MM-DD`) to avoid schema changes
- Skip re-validation if tag is present and within interval

**Acceptance criteria:**
- [ ] Single-entry and batch validation with async doc lookup
- [ ] Rate-limited: caps unique lookups per batch via `max_lookups`
- [ ] Skips recently-validated entries (tag-based tracking)
- [ ] `validate_stale()` targets low-confidence entries first (sorted by effective confidence ascending)
- [ ] Returns `ValidationReport` with counts and per-entry details
- [ ] Integration tests with mocked LookupEngine

---

### Story 62.4 — Confidence Adjustment & Enrichment

**As a** memory system, **I want to** apply validation results back to memory entries, **so that** confirmed memories gain confidence and contradicted ones are flagged.

**Implementation:**

New method on `MemoryDocValidator`:

```python
async def apply_results(self, report: ValidationReport, *,
                        dry_run: bool = False) -> ApplyResult:
    """Apply validation results to memory store."""
```

**Actions per alignment:**

| Alignment | Confidence | Tags | Contradiction |
|---|---|---|---|
| `confirmed` | Boost by `+delta` (max source ceiling) | Add `doc-validated:{date}`, `doc-ref:{library}` | Clear if previously set by validation |
| `contradicted` | Reduce by `delta` (min 0.1 floor) | Add `doc-contradicted:{date}` | Set `contradicted=True`, `contradiction_reason="Conflicts with {library} docs: {snippet}"` |
| `inconclusive` | No change | Add `doc-checked:{date}` | No change |
| `no_docs` | No change | No change | No change |

**Enrichment:**
- Confirmed entries get `doc-ref:{library}/{topic}` tags for future retrieval boosting
- Expert injection (`inject_memories()`) can prioritize doc-validated memories (+0.05 score bonus)

**Dry-run mode:**
- Returns what *would* change without modifying the store
- Useful for `tapps_memory validate` action preview

**Acceptance criteria:**
- [ ] Confidence adjustments respect source ceilings and decay floor (0.1)
- [ ] Tags added/updated without exceeding 10-tag limit (evict oldest `doc-*` tag if needed)
- [ ] `contradicted` field set with reason including doc snippet
- [ ] Dry-run returns complete diff without store mutation
- [ ] Confirmed entries previously marked contradicted get cleared
- [ ] Unit tests cover all 4 alignment outcomes and edge cases

---

### Story 62.5 — MCP Tool Integration (`validate` action)

**As an** AI coding assistant, **I want to** validate memory entries against documentation via `tapps_memory`, **so that** I can proactively check memory accuracy.

**Implementation:**

New action `validate` in `server_memory_tools.py`:

```python
# tapps_memory(action="validate", ...)
# Parameters:
#   key: str (optional) — validate a single entry
#   query: str (optional) — validate entries matching search
#   scope: str (optional) — validate all entries in scope
#   stale_only: bool (default False) — only validate low-confidence entries
#   dry_run: bool (default True) — preview without applying changes
#   max_entries: int (default 10) — cap on entries to validate
```

**Response format:**
```json
{
  "action": "validate",
  "report": {
    "validated": 5,
    "flagged": 1,
    "inconclusive": 2,
    "skipped": 2,
    "no_docs": 0
  },
  "entries": [
    {
      "key": "framework-fastapi-routing",
      "status": "confirmed",
      "library": "fastapi",
      "similarity": 0.78,
      "confidence_delta": "+0.15",
      "matched_snippet": "FastAPI uses @app.get() decorators for route..."
    }
  ],
  "applied": false,
  "timing_ms": 1234
}
```

**Acceptance criteria:**
- [ ] `validate` action registered in tool dispatch with `_record_call`
- [ ] Supports single key, query-based, scope-based, and stale-only targeting
- [ ] `dry_run=True` by default (safe to call without side effects)
- [ ] Response includes per-entry validation details with snippets
- [ ] Rate-limited to `max_entries` (default 10, max 50)
- [ ] Added to AGENTS.md tapps_memory actions list
- [ ] Unit tests for all parameter combinations

---

### Story 62.6 — Session-Start Validation Pass

**As a** project, **I want** stale memories to be automatically validated against docs at session start, **so that** contradictions are caught early without manual intervention.

**Implementation:**

New function in `server_pipeline_tools.py`:

```python
async def _maybe_validate_memories(store: MemoryStore, settings: TappsMCPSettings) -> dict | None:
    """Run doc validation on stale memories at session start (once per session)."""
```

**Trigger conditions (all must be true):**
1. `settings.memory.doc_validation.enabled` is True (default: True)
2. `settings.memory.doc_validation.validate_on_session_start` is True (default: True at high engagement, False at medium/low)
3. Session state guard: `_session_state["validation_done"]` is False
4. Memory store has entries with effective confidence below `validation_confidence_threshold` (default 0.5)

**Behavior:**
- Runs after auto-GC and consolidation scan in `tapps_session_start`
- Validates up to `session_start_max_entries` (default 5) stale entries
- Auto-applies results (not dry-run) for session-start validation
- Returns summary dict included in session start response: `"memory_validation": {"validated": 3, "flagged": 1, ...}`

**Configuration:**

New settings section in `MemorySettings`:
```python
class DocValidationSettings(BaseModel):
    enabled: bool = True
    validate_on_session_start: bool = True  # overridden by engagement level
    validation_confidence_threshold: float = 0.5
    session_start_max_entries: int = 5
    revalidation_interval_days: int = 7
    max_lookups_per_batch: int = 20
    confirmed_boost: float = 0.15
    contradicted_penalty: float = 0.2
```

**Acceptance criteria:**
- [ ] Validation runs at session start when enabled and stale entries exist
- [ ] Session-state guarded (runs once per session)
- [ ] Engagement-level aware: auto at high, opt-in at medium, disabled at low
- [ ] Summary included in `tapps_session_start` response
- [ ] `DocValidationSettings` added to `MemorySettings` with sensible defaults
- [ ] Integration tests with mocked lookup engine

---

### Story 62.7 — Documentation & Testing

**As a** developer, **I want** Epic 62 thoroughly documented and tested, **so that** the feature is maintainable and discoverable.

**Deliverables:**

1. **CLAUDE.md** — Add "Memory doc validation" subsection under Memory subsystem
2. **AGENTS.md** — Add `validate` to tapps_memory actions list, describe behavior
3. **README.md** — Update tapps_memory description to mention doc validation
4. **Unit tests** — Target: 80+ tests covering:
   - ClaimExtractor: all 5 strategies, edge cases, empty inputs
   - DocSimilarityScorer: all 4 alignment levels, threshold boundaries, heuristics
   - MemoryDocValidator: single + batch + stale validation, rate limiting, skip logic
   - Confidence adjustment: boost/reduce/ceiling/floor, tag management, dry-run
   - MCP action: parameter combinations, response format
   - Session-start: trigger conditions, engagement levels, state guard
5. **Integration tests** — End-to-end with mocked Context7 responses

**Acceptance criteria:**
- [ ] All documentation files updated
- [ ] 80+ unit tests passing
- [ ] Integration tests with realistic mock data
- [ ] mypy --strict passes on new module
- [ ] ruff check passes

---

## Technical Notes

### Reuse Opportunities

| Existing Code | Reuse In Epic 62 |
|---|---|
| `memory/similarity.py` — TF-IDF + Jaccard | `DocSimilarityScorer` TF-IDF cosine scoring |
| `knowledge/library_detector.py` — library name detection | `ClaimExtractor` strategy #3 |
| `knowledge/lookup.py` — `LookupEngine.lookup()` | Core doc retrieval for validation |
| `memory/contradictions.py` — project-state checks | Complement (62 adds doc-state checks) |
| `memory/reinforcement.py` — confidence boost pattern | Confirmed-entry confidence boost |
| `memory/decay.py` — effective confidence calculation | Stale-entry targeting |
| `memory/store.py` — `update_fields()` | Apply validation results |
| `security/content_safety.py` — RAG safety | Filter retrieved docs before comparison |

### Schema Impact

**No schema changes required.** Validation state is tracked entirely through:
- Existing fields: `contradicted`, `contradiction_reason`, `confidence`
- Tags: `doc-validated:YYYY-MM-DD`, `doc-contradicted:YYYY-MM-DD`, `doc-ref:{library}/{topic}`
- Settings: New `DocValidationSettings` section in config YAML

### Performance Budget

| Operation | Target | Notes |
|---|---|---|
| Claim extraction | < 5ms per entry | Regex + keyword matching, no I/O |
| Doc lookup (cached) | < 10ms per library | KBCache file read |
| Doc lookup (API) | < 2s per library | Context7 HTTP, cached after first call |
| Similarity scoring | < 20ms per claim | TF-IDF cosine, in-memory |
| Full session-start validation (5 entries) | < 5s total | Most lookups cached from previous sessions |

### Risk Mitigation

| Risk | Mitigation |
|---|---|
| Context7 API rate limits | `max_lookups_per_batch` cap (default 20); cache-first strategy |
| False contradictions from bad docs | `no_docs` alignment returns 0.0 delta; min similarity threshold for contradiction (0.3) |
| Tag overflow (10-tag limit) | Evict oldest `doc-*` tags first; never remove user-set tags |
| Memory store lock contention | Batch updates with single `update_fields()` call per entry |
| Circular dependency (validation triggers consolidation) | Non-reentrant guard similar to `auto_consolidation.py` |

---

## Estimated Effort

| Story | LOE | Notes |
|---|---|---|
| 62.1 — Claim Extractor | 2 days | Regex + library_detector reuse |
| 62.2 — Similarity Scorer | 2 days | TF-IDF reuse from similarity.py |
| 62.3 — Validation Engine | 3 days | Async orchestration, rate limiting, batch |
| 62.4 — Confidence Adjustment | 2 days | Store updates, tag management, dry-run |
| 62.5 — MCP Tool Integration | 2 days | Action dispatch, response formatting |
| 62.6 — Session-Start Integration | 1.5 days | Config, engagement levels, state guard |
| 62.7 — Documentation & Testing | 2.5 days | 80+ tests, docs updates |
| **Total** | **~15 days (~3 weeks)** | |

---

## Dependencies

```
Epic 62
  ├── Epic 23 (Memory Foundation) — MemoryStore, MemoryEntry model
  ├── Epic 24 (Memory Intelligence) — Decay, contradictions, GC
  ├── Epic 25 (Memory Retrieval) — BM25 retrieval, injection
  ├── Epic 34 (BM25 Upgrade) — Ranked search, reinforcement
  ├── Epic 58 (Consolidation) — Similarity scoring, consolidation state
  └── Epic 2 (Knowledge & Docs) — LookupEngine, KBCache, Context7Client
```

All dependencies are complete. No blocking issues.
