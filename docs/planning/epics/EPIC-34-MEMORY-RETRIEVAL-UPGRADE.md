# Epic 34: Memory Retrieval & Reinforcement Upgrade

**Status:** Proposed
**Priority:** P1 — High (current word-overlap retrieval produces poor recall; reinforcement logic exists but is inaccessible)
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 23 (Shared Memory Foundation), Epic 24 (Memory Intelligence), Epic 25 (Memory Retrieval & Integration)
**Blocks:** None

> **Monorepo Note:** Memory modules now have dual locations after the tapps-core extraction. The canonical source code is in `packages/tapps-core/src/tapps_core/memory/`, while `packages/tapps-mcp/src/tapps_mcp/memory/` re-exports for backward compatibility. Edits should target the **tapps-core** canonical location. If Tier 2 extraction is incomplete when this epic starts, adjust paths accordingly.

---

## Goal

Upgrade the memory retrieval pipeline from simple word overlap scoring to proper BM25-based ranking with stemming and stop-word filtering, expose the existing reinforcement logic via the `tapps_memory` MCP tool, add an optional auto-capture Stop hook for consuming projects, and integrate automatic GC into `tapps_session_start`. These improvements are informed by AI OS's `smart_search.py` which implements hybrid BM25 + vector + temporal decay + MMR diversity re-ranking, achieving significantly better recall than TappsMCP's current set-intersection approach.

## Motivation

The current `MemoryRetriever._word_overlap_score()` in `memory/retrieval.py` splits on whitespace and counts set intersection. This means:
- "testing" does not match "test" (no stemming)
- "the" and "a" contribute to scores equally with domain terms (no stop words)
- All words are weighted equally (no IDF — rare terms should matter more)
- A memory about "Python unit testing patterns" scores the same for "testing" as for "the"

AI OS's `smart_search.py` solves these with BM25 (which includes IDF weighting), configurable score fusion weights, temporal decay, and MMR diversity re-ranking. TappsMCP already has temporal decay and confidence scoring — the gap is in the text relevance component.

## 2026 Best Practices Applied

- **BM25 (Okapi BM25)** — Standard information retrieval algorithm used by Elasticsearch, SQLite FTS5 (with `rank` function), and most production search systems. Parameters k1=1.2, b=0.75 are well-established defaults. For TappsMCP's small corpus (< 500 entries), custom implementation is preferred over `rank-bm25` library to avoid external dependency for ~80 lines of code.
- **No external dependencies** — BM25 is implementable in ~80 lines of Python using only `math.log` for IDF. Stop words and suffix stemming are pure Python with no libraries needed. This aligns with TappsMCP's zero-external-dependency scoring philosophy.
- **MCP tool surface** — Reinforcement and GC should be accessible via MCP tools, not just internal APIs. This follows the principle that all capabilities should be tool-accessible for agent orchestration.
- **SQLite FTS5 consideration** — TappsMCP's persistence layer already uses SQLite. A future enhancement could leverage FTS5's built-in `rank` function for BM25, but the in-memory approach is simpler for the current corpus size and avoids schema changes.
- **Deterministic** — BM25 scoring, stemming, and stop-word filtering are all deterministic. Same query + same corpus = same results.

## Acceptance Criteria

- [ ] `MemoryRetriever` uses BM25 scoring instead of word-overlap for text relevance
- [ ] BM25 parameters configurable: k1 (default 1.2), b (default 0.75)
- [ ] Stop-word filtering removes ~50 common English words before scoring
- [ ] Basic suffix stemming handles common patterns (ing, ed, ly, tion, ment, ness, er, est, s)
- [ ] Retrieval recall improved: "testing" matches memories containing "test" and vice versa
- [ ] `tapps_memory` tool supports `reinforce` action that calls `boost_confidence()`
- [ ] `tapps_memory` tool supports `gc` action that triggers garbage collection
- [ ] Auto-capture Stop hook template available in `platform_hook_templates.py`
- [ ] `tapps_session_start` runs GC when memory count exceeds 80% of max_memories
- [ ] Native memory documentation in generated AGENTS.md explaining TappsMCP memory vs Claude Code auto memory
- [ ] All new code has unit tests; retrieval quality tests demonstrate stemming/stop-word improvement
- [ ] Backward compatible: existing memory stores work without migration

---

## Stories

### 34.1 — BM25 Scoring Engine

**Points:** 5

Replace word-overlap scoring with proper BM25 (Okapi BM25) in `MemoryRetriever`.

**Source Files:**
- `packages/tapps-core/src/tapps_core/memory/retrieval.py` (modify — canonical location)
- `packages/tapps-core/src/tapps_core/memory/bm25.py` (new)
- _Fallback if Tier 2 extraction incomplete:_ `packages/tapps-mcp/src/tapps_mcp/memory/` equivalents

**Tasks:**
- Create `memory/bm25.py` with:
  - `BM25Scorer` class:
    - `__init__(k1: float = 1.2, b: float = 0.75)` — BM25 parameters
    - `build_index(documents: list[str])` — compute IDF values and average document length from corpus
    - `score(query: str, document: str) -> float` — BM25 score for a single document
    - `score_batch(query: str, documents: list[str]) -> list[float]` — scores for all documents
  - IDF calculation: `log((N - df + 0.5) / (df + 0.5) + 1)` where N = total docs, df = document frequency
  - TF-saturation: `(tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))` where dl = doc length, avgdl = average doc length
  - Pure Python — no numpy or scipy required for 500-entry corpus
- Create `_STOP_WORDS` set (~50 common English words): "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "can", "shall", "must", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "during", "before", "after", "above", "below", "between", "out", "off", "over", "under", "again", "further", "then", "once", "this", "that", "these", "those", "it", "its"
- Create `stem(word: str) -> str` function — basic suffix stripping:
  - Remove trailing "ing" (if remaining > 3 chars)
  - Remove trailing "ed" (if remaining > 3 chars)
  - Remove trailing "ly" (if remaining > 3 chars)
  - Remove trailing "tion" → replace with "te" (if remaining > 2 chars)
  - Remove trailing "ment" (if remaining > 3 chars)
  - Remove trailing "ness" (if remaining > 3 chars)
  - Remove trailing "er" (if remaining > 3 chars)
  - Remove trailing "est" (if remaining > 3 chars)
  - Remove trailing "s" (if remaining > 3 chars and not ending in "ss")
  - This is intentionally simple — not a full Porter stemmer, but handles 80% of cases
- Create `preprocess(text: str) -> list[str]` — lowercase, split, remove stop words, stem
- Write ~15 unit tests: BM25 scoring correctness (compare with known values), IDF weighting (rare terms score higher), stemming rules, stop-word removal, empty input handling, single-document corpus

**Definition of Done:** BM25 scorer produces correct scores. IDF weights rare terms higher. Stemming handles common suffixes. Stop words filtered.

---

### 34.2 — Integrate BM25 into MemoryRetriever

**Points:** 3

Replace `_word_overlap_score` with `BM25Scorer` in the retrieval pipeline while maintaining the composite scoring formula.

**Current State (verified 2026-02-28):** `_word_overlap_score()` at line 202 of retrieval.py splits on whitespace, computes set intersection, and normalizes via `score / (score + 1)` sigmoid. The composite weights are: relevance 40%, confidence 30%, recency 15%, frequency 15%.

**Source Files:**
- `packages/tapps-core/src/tapps_core/memory/retrieval.py` (modify — canonical location)
- _Fallback:_ `packages/tapps-mcp/src/tapps_mcp/memory/retrieval.py`

**Tasks:**
- In `MemoryRetriever.__init__`, initialize `BM25Scorer` with configurable parameters
- Replace `_word_overlap_score()` calls in `_get_candidates()` with `BM25Scorer.score()`
- Build BM25 index from corpus on first search call (lazy initialization):
  - Corpus = all memory entries' `f"{entry.key} {entry.value} {' '.join(entry.tags)}"`
  - Invalidate index when store size changes (simple length check)
- Update `_normalize_relevance()` to handle BM25's score range (typically 0-15+, not 0-1):
  - Use `score / (score + k)` sigmoid normalization with k=5.0 (tunable)
- Keep the composite scoring formula unchanged:
  ```python
  composite = (
      _W_RELEVANCE * bm25_normalized
      + _W_CONFIDENCE * eff_conf
      + _W_RECENCY * recency
      + _W_FREQUENCY * frequency
  )
  ```
- Ensure backward compatibility: if BM25 index fails to build, fall back to word overlap
- Remove the old `_word_overlap_score()` static method (or keep as private fallback)
- Update `_like_search()` fallback to also use BM25 when possible
- Write ~10 unit tests: integration tests showing "testing" matches "test", IDF boosts rare terms, composite scoring still works, fallback to word overlap on error, index invalidation

**Definition of Done:** MemoryRetriever uses BM25 for text relevance. Composite scoring unchanged. Stemming and stop-words active. Backward compatible fallback.

---

### 34.3 — Expose Reinforcement and GC via MCP Tool

**Points:** 3

Add `reinforce` and `gc` actions to the `tapps_memory` MCP tool, surfacing existing internal logic.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/memory/store.py` (modify — add `reinforce()` method if not present)

**Tasks:**
- Add `reinforce` action to `tapps_memory` tool:
  - Parameters: `key` (required)
  - Calls `store.get(key)` to fetch the entry, then `boost_confidence()` from `memory/reinforcement.py`
  - Updates the entry via `store.update_fields(key, confidence=boosted, last_reinforced=now, reinforce_count=count+1)`
  - Returns the updated entry with old vs new confidence
- Add `gc` action to `tapps_memory` tool:
  - Parameters: none (uses settings for thresholds)
  - Calls `gc_collect()` from `memory/gc.py` with the store
  - Returns count of archived/evicted entries and remaining entry count
- Add a convenience method `MemoryStore.reinforce(key: str) -> MemoryEntry | None` that wraps the get → boost → update sequence
- Update tool description to document the two new actions
- Update checklist registration if needed
- Write ~8 unit tests: reinforce success, reinforce missing key, reinforce increases confidence, gc evicts stale entries, gc returns count, integration with MCP tool handler

**Definition of Done:** `tapps_memory reinforce` and `tapps_memory gc` work from any MCP client. Reinforcement boosts confidence. GC evicts stale entries.

---

### 34.4 — Auto-GC in Session Start

**Points:** 2

Trigger automatic garbage collection during `tapps_session_start` when memory usage is high.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (modify — `tapps_session_start` handler)
- `packages/tapps-mcp/src/tapps_mcp/server_helpers.py` (modify — if session init logic is here)

**Tasks:**
- In `tapps_session_start`, after initializing the memory store:
  - Check `store.count()` against `settings.memory.max_memories * 0.8` (80% threshold)
  - If above threshold, run `gc_collect()` automatically
  - Log the GC result (entries evicted) at INFO level
  - Include GC summary in `tapps_session_start` response metadata
- Make the 80% threshold configurable via `MemorySettings.gc_auto_threshold` (default 0.8)
- Ensure GC only runs once per session (use a flag in session state)
- Write ~5 unit tests: GC triggers at threshold, doesn't trigger below, only runs once, config override works

**Definition of Done:** `tapps_session_start` auto-runs GC when memory is near capacity. Configurable threshold. Runs once per session.

---

### 34.5 — Auto-Capture Stop Hook Template

**Points:** 3

Add an optional Stop hook template that captures session quality data to memory in consuming projects.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (modify)

**Important:** The Stop hook does NOT support calling MCP tools directly (hooks are shell scripts). The auto-capture approach must either:
1. Write session data to a JSON file that `tapps_session_start` reads on next session, OR
2. Use the `tapps_memory` CLI interface if available, OR
3. Write to the `.tapps-mcp/memory/` SQLite database directly (fragile, not recommended)

Option 1 (deferred capture via JSON file) is recommended for robustness.

**Tasks:**
- Create `tapps-memory-capture.sh` hook script template:
  - Fires on Stop event (async, non-blocking)
  - Reads environment for `CLAUDE_PROJECT_DIR`
  - Writes session summary to `.tapps-mcp/session-capture.json` (for next session pickup)
  - Extracts basic metrics from marker files: validation marker presence, quality tool call count
  - JSON format: `{"date": "YYYY-MM-DD", "validated": true/false, "files_edited": N}`
  - Graceful degradation: if extraction fails, log and exit 0
- In `tapps_session_start`, check for `.tapps-mcp/session-capture.json` and persist to memory via `store.save()` if found
- Add `memory_capture` parameter to `tapps_init` (default: `false`)
- Add corresponding hook config to settings.json generation
- Guard against `stop_hook_active` infinite loop (same pattern as existing `tapps-stop.sh`)
- Write ~5 tests: hook script content, init parameter, session-capture.json format, session_start pickup, stop_hook_active guard

**Definition of Done:** Optional memory capture hook available. Generates when `memory_capture=true`. Captures session quality data to memory.

---

### 34.6 — Native Memory Documentation in Templates

**Points:** 2

Update generated AGENTS.md and platform rules to explain the relationship between TappsMCP memory and Claude Code's native auto memory.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template.md` (modify)
- `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_high.md` (modify)
- `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_medium.md` (modify)
- `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_low.md` (modify)

**Tasks:**
- Add a "Memory Systems" section to all AGENTS.md templates explaining:
  - **Claude Code auto memory** (`~/.claude/projects/<project>/memory/MEMORY.md`): Session learnings, user preferences, debugging insights. Auto-managed by Claude Code. Use for personal workflow notes.
  - **TappsMCP memory** (`tapps_memory` MCP tool): Quality patterns, architecture decisions, expert consultation findings. Structured, typed by tier (architectural/pattern/context), with confidence scoring. Use for cross-agent knowledge that should persist across all sessions and agents.
  - **When to use which**: "Save build commands and IDE preferences to auto memory. Save architecture decisions and quality patterns to `tapps_memory`."
- Adjust language per engagement level:
  - `high`: "REQUIRED: Use tapps_memory for all architecture decisions."
  - `medium`: "Use tapps_memory for architecture decisions and quality patterns."
  - `low`: "Consider using tapps_memory for important architecture decisions."
- Write ~4 tests: template content at each engagement level includes memory section

**Definition of Done:** All AGENTS.md templates explain both memory systems. Guidance is engagement-level appropriate.

---

## Performance Targets

| Operation | Target (p95) | Notes |
|-----------|-------------|-------|
| BM25 index build (500 entries) | < 50ms | One-time per search session |
| BM25 search (500 entries) | < 10ms | Includes preprocessing + scoring |
| Stemming (per word) | < 0.01ms | Simple suffix rules |
| Stop-word filter (per query) | < 0.1ms | Set membership check |
| Reinforce action | < 15ms | Get + boost + update |
| GC action (500 entries) | < 100ms | Scan + evict + archive |
| Auto-GC in session_start | < 200ms | Only when threshold exceeded |

## Key Dependencies

- Epic 23 (`memory/models.py`, `memory/persistence.py`, `memory/store.py`)
- Epic 24 (`memory/reinforcement.py`, `memory/gc.py`, `memory/decay.py`)
- Epic 25 (`memory/retrieval.py`)
- No new external dependencies — BM25, stemming, and stop words are pure Python

## Key Design Decisions

1. **Custom BM25 over library** — `rank-bm25` PyPI package exists but adds an external dependency for ~80 lines of code. TappsMCP's corpus is small (500 entries max), so a custom implementation is simpler and dependency-free.
2. **Basic stemming over Porter/Snowball** — Full stemmer libraries (nltk, PyStemmer) are heavy dependencies. Basic suffix stripping handles 80% of cases for English technical text and is ~30 lines of code.
3. **Lazy BM25 index** — Index builds on first search call and invalidates on corpus size change. This avoids startup cost when memory isn't used in a session.
4. **80% GC threshold** — Running GC at 400/500 entries gives a comfortable buffer before hitting the hard limit. The value is configurable via settings.
5. **Auto-capture is opt-in** — Session transcript parsing is fragile (format may change). Making it opt-in via `memory_capture=true` in `tapps_init` avoids breaking consuming projects.
