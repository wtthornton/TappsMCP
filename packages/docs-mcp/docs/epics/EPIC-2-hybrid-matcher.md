# Epic 2: Hybrid Matcher — Embedding-Based Agent Matching Infrastructure

<!-- docsmcp:start:metadata -->
**Status:** Complete
**Priority:** P0 - Critical
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** None (greenfield)
**Blocks:** EPIC-12 (catalog governance)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that docs-mcp has a semantic agent matching system that can route
prompts to the best agent using embedding similarity instead of keyword overlap alone,
enabling accurate deduplication (EPIC-12).

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Build a hybrid matching engine that combines keyword scoring with embedding-based cosine
similarity to match user prompts against the agent catalog. Support pluggable embedding
backends (local sentence-transformers default, optional API-based). Provide the foundation
for EPIC-11's agent discovery via hive and EPIC-12's deduplication gate.

**Tech Stack:** docs-mcp, Python >=3.12, sentence-transformers (optional)

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The current agent matching in docs-mcp (if any exists) uses keyword overlap scoring.
This misses semantic similarity — e.g., "deploy infrastructure" and "provision servers"
have zero keyword overlap but high semantic similarity. EPIC-12 (catalog governance) depends on embedding-based matching that doesn't exist yet.
Without this foundation, that epic cannot proceed.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] HybridMatcher class accepts a list of AgentConfig entries and builds keyword + embedding indices
- [ ] `match(prompt)` returns ranked agents with combined keyword + embedding scores
- [ ] Embedding backend is pluggable: local sentence-transformers (default) or API-based
- [ ] Graceful degradation: if no embedding model available, falls back to keyword-only matching
- [ ] `pairwise_similarity()` returns cosine similarity matrix for all agent pairs (needed by EPIC-12)
- [ ] Matching threshold is configurable (default 0.7 for match, 0.85 for dedup)
- [ ] Embedding vectors are cached to disk to avoid recomputation on restart
- [ ] 80%+ test coverage with unit tests for all matching modes

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 2.1 -- AgentConfig model and catalog loader

**Points:** 3

Define the AgentConfig Pydantic model for docs-mcp agents. Include: name, description,
keywords, system_prompt_path, capabilities list, and the new memory_profile enum
(full/readonly/none, default full). Build a catalog loader that reads AGENT.md files
from a configurable directory and returns a list of AgentConfig instances.

**Tasks:**
- [ ] Create `packages/docs-mcp/src/docs_mcp/agents/models.py` with AgentConfig model
- [ ] Create `packages/docs-mcp/src/docs_mcp/agents/catalog.py` with catalog loader
- [ ] Parse AGENT.md frontmatter (YAML between `---` markers) into AgentConfig
- [ ] Write unit tests for model validation and catalog loading

**Definition of Done:** AgentConfig model and catalog loader are implemented, tests pass,
and documentation is updated.

---

### 2.2 -- Keyword matcher baseline

**Points:** 2

Implement keyword-based matching as the baseline scorer. Tokenize agent keywords and
prompt, compute TF-IDF or simple overlap score. This is the fallback when embeddings
are unavailable.

**Tasks:**
- [ ] Create `packages/docs-mcp/src/docs_mcp/agents/keyword_matcher.py`
- [ ] Implement tokenization with stopword removal
- [ ] Implement overlap scoring with configurable weight
- [ ] Write unit tests with known agent/prompt pairs

**Definition of Done:** Keyword matcher is implemented with tests.

---

### 2.3 -- Embedding backend abstraction

**Points:** 5

Create an embedding backend interface and two implementations: LocalEmbeddingBackend
(sentence-transformers, all-MiniLM-L6-v2) and StubEmbeddingBackend (returns zero vectors,
for testing). The interface: `embed(texts: list[str]) -> list[list[float]]`.
Include disk-based vector caching keyed by content hash.

**Tasks:**
- [ ] Create `packages/docs-mcp/src/docs_mcp/agents/embeddings.py` with backend interface
- [ ] Implement LocalEmbeddingBackend with sentence-transformers
- [ ] Implement StubEmbeddingBackend for testing
- [ ] Implement disk cache in `.docsmcp/embedding_cache/` with content-hash keys
- [ ] Write unit tests with stub backend; integration test with real model (mark slow)

**Definition of Done:** Embedding backends are implemented with caching and tests.

---

### 2.4 -- HybridMatcher core

**Points:** 5

Combine keyword and embedding scores into a single ranking. HybridMatcher takes a catalog
and embedding backend, pre-computes agent embeddings on init. `match(prompt)` embeds the
prompt, scores against all agents, returns sorted results above threshold. Configurable
weight split (default 0.3 keyword + 0.7 embedding).

**Tasks:**
- [ ] Create `packages/docs-mcp/src/docs_mcp/agents/matcher.py` with HybridMatcher
- [ ] Implement `match(prompt, threshold=0.7) -> list[MatchResult]`
- [ ] Implement `pairwise_similarity() -> dict[tuple[str,str], float]` for EPIC-12
- [ ] Implement score combination with configurable weights
- [ ] Write unit tests covering: exact match, semantic match, no match, degraded mode

**Definition of Done:** HybridMatcher is implemented with combined scoring and tests.

---

### 2.5 -- Integration and graceful degradation

**Points:** 2

Wire HybridMatcher into docs-mcp's agent infrastructure. Ensure graceful fallback:
if sentence-transformers is not installed, log a warning and use keyword-only matching.
Add `sentence-transformers` as an optional dependency (`docs-mcp[agents]`).

**Tasks:**
- [ ] Add `sentence-transformers` to optional dependencies in pyproject.toml
- [ ] Create `packages/docs-mcp/src/docs_mcp/agents/__init__.py` with public API
- [ ] Implement try/except import for graceful degradation
- [ ] Write integration test verifying degraded mode
- [ ] Update docs-mcp CLAUDE.md with agents module documentation

**Definition of Done:** Integration complete, degradation verified, documentation updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- sentence-transformers `all-MiniLM-L6-v2` is ~80MB, runs on CPU, ~5ms per embedding
- Embedding cache uses SHA256 of concatenated keywords+description as key
- For 50 agents, pairwise similarity is 1,225 comparisons (~10ms)
- HybridMatcher._embeddings stores pre-computed vectors (referenced by EPIC-12)
- Consider numpy for cosine similarity if available, pure-Python fallback otherwise

**Key Dependencies:** sentence-transformers>=2.0 (optional), numpy (optional, pulled by sentence-transformers)

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- GPU acceleration for embeddings
- Fine-tuned embedding models
- Cross-project agent matching
- Real-time embedding updates (batch reindex is sufficient)
- LLM-based matching (EPIC-12 story 12.5 covers proposer overlap guard separately)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Status | Purpose |
|------|--------|---------|
| `packages/docs-mcp/src/docs_mcp/agents/__init__.py` | New | Public API for agent matching |
| `packages/docs-mcp/src/docs_mcp/agents/models.py` | New | AgentConfig Pydantic model |
| `packages/docs-mcp/src/docs_mcp/agents/catalog.py` | New | AGENT.md catalog loader |
| `packages/docs-mcp/src/docs_mcp/agents/keyword_matcher.py` | New | Keyword-based scoring |
| `packages/docs-mcp/src/docs_mcp/agents/embeddings.py` | New | Embedding backend abstraction |
| `packages/docs-mcp/src/docs_mcp/agents/matcher.py` | New | HybridMatcher core |
| `packages/docs-mcp/pyproject.toml` | Modified | Add optional `agents` extra |
| `packages/docs-mcp/tests/unit/test_matcher.py` | New | Unit tests |
| `packages/docs-mcp/tests/unit/test_catalog.py` | New | Catalog loader tests |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 8 acceptance criteria met | 0/8 | 8/8 | Checklist review |
| All 5 stories completed | 0/5 | 5/5 | Sprint board |
| Test coverage | 0% | >= 80% | pytest --cov |
| EPIC-12 unblocked | Blocked | Unblocked | Dependency check |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 2.1: AgentConfig model and catalog loader
2. Story 2.2: Keyword matcher baseline
3. Story 2.3: Embedding backend abstraction
4. Story 2.4: HybridMatcher core
5. Story 2.5: Integration and graceful degradation

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| sentence-transformers model download in CI | Medium | Low | Cache model in CI artifacts or use stub backend |
| Embedding quality for short agent descriptions | Medium | Medium | Concatenate name+description+keywords for richer embedding input |
| Disk cache corruption | Low | Low | Content-hash keys are self-healing — stale entries are ignored |

<!-- docsmcp:end:risk-assessment -->
