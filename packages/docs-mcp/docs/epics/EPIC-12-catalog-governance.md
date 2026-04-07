# Epic 12: Agent Catalog Governance — Deduplication, Overlap Prevention, and Lifecycle

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** EPIC-2 (hybrid matcher with embeddings — see `EPIC-2-hybrid-matcher.md`)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that the agent catalog stays lean and well-organized as it grows, preventing redundant agents from being created, merging overlapping capabilities into existing agents, and providing lifecycle management for agent quality.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Implement a semantic deduplication gate in the proposal engine, upgrade the existing keyword-based dedup to use embedding similarity, add capability merging as an alternative to new agent creation, and provide catalog health monitoring.

**Tech Stack:** docs-mcp, Python >=3.12

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The proposal engine automatically creates new agents when no match is found. With 14+ agents, the risk of overlapping agents increases — e.g., the weather-alerts proposal overlapped heavily with the existing weather agent. The current dedup check uses keyword overlap scoring which misses semantic similarity. Without governance, the catalog will bloat with near-duplicate agents that confuse routing and waste resources.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Proposal engine checks embedding similarity >= 0.85 before creating new agents
- [ ] When overlap detected the proposer suggests merging capabilities into existing agent
- [ ] Agent catalog health endpoint reports overlap scores between all agent pairs
- [ ] Deprecated/unused agents can be soft-deleted with automatic cleanup after retention period
- [ ] Embedding-based dedup replaces keyword-overlap dedup in _handle_no_match

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 12.1 -- Embedding-based deduplication gate

**Points:** 5

Replace the keyword-overlap dedup check in _handle_no_match (tasks.py) with embedding similarity using the HybridMatcher. Before proposing a new agent, score the prompt against all existing agents via embeddings. If any agent scores >= 0.85 cosine similarity, suggest modifying that agent instead of creating a new one.

**Tasks:**
- [ ] Implement embedding-based deduplication gate
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Embedding-based deduplication gate is implemented, tests pass, and documentation is updated.

---

### 12.2 -- Capability merge suggestions in proposals

**Points:** 3

When the dedup gate fires, instead of just saying 'consider modifying X', generate a specific merge suggestion: which keywords/utterances to add to the existing agent, what system prompt additions would cover the new capability. Return this as structured data in the TaskResponse.

**Tasks:**
- [ ] Implement capability merge suggestions in proposals
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Capability merge suggestions in proposals is implemented, tests pass, and documentation is updated.

---

### 12.3 -- Catalog health endpoint

**Points:** 3

Add GET /agents/health that computes pairwise embedding similarity between all agents and flags pairs above 0.7 as potential overlaps. Returns a sorted list of overlap pairs with similarity scores and merge recommendations.

**Tasks:**
- [ ] Implement catalog health endpoint
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Catalog health endpoint is implemented, tests pass, and documentation is updated.

---

### 12.4 -- Agent soft-delete and lifecycle

**Points:** 2

Add a deprecated flag to AgentConfig. Deprecated agents are excluded from matching but retained on disk for reference. Add a cleanup task that removes deprecated agents after a configurable retention period (default 30 days).

**Tasks:**
- [ ] Implement agent soft-delete and lifecycle
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Agent soft-delete and lifecycle is implemented, tests pass, and documentation is updated.

---

### 12.5 -- Proposer overlap guard

**Points:** 2

Before the LLM proposer runs, inject the top-3 most similar existing agents into the proposer prompt so the LLM knows what already exists. This reduces proposals that overlap with existing agents at the source.

**Tasks:**
- [ ] Implement proposer overlap guard
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Proposer overlap guard is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- HybridMatcher._embeddings already has embedding vectors for all agents — reuse for dedup scoring
- Cosine similarity threshold 0.85 balances precision (avoiding false merges) vs recall (catching real overlaps)
- The weather-alerts proposal (denied) is the canonical example — it had 0.85+ similarity to weather
- Catalog health computation is O(n^2) but trivial for 50 agents (~1ms)

**Project Structure:** 6 packages, 63 modules, 230 public APIs

**Key Dependencies:** tapps-core>=1.0.0, mcp[cli]>=1.26.0,<2, click>=8.3.1,<9, jinja2>=3.1.6,<4, gitpython>=3.1.44,<4, pydantic>=2.12.5,<3, structlog>=25.5.0,<26, pyyaml>=6.0.3,<7

### Expert Recommendations

- **Software Architecture Expert** (66%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*
- **Security Expert** (74%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Automatic merging without human approval
- Cross-instance agent catalog federation
- Agent versioning or rollback

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

> **Note (2026-04-07):** Original paths referenced a `backend/` directory that does not
> exist in docs-mcp. Corrected to actual/planned docs-mcp paths below.

| File | Status | Purpose |
|------|--------|---------|
| `packages/docs-mcp/src/docs_mcp/agents/matcher.py` | From EPIC-2 | HybridMatcher with `pairwise_similarity()` |
| `packages/docs-mcp/src/docs_mcp/agents/models.py` | From EPIC-2 | AgentConfig with deprecated flag |
| `packages/docs-mcp/src/docs_mcp/agents/dedup.py` | New | Embedding dedup gate for proposals |
| `packages/docs-mcp/src/docs_mcp/agents/merge.py` | New | Capability merge suggestion generator |
| `packages/docs-mcp/src/docs_mcp/agents/health.py` | New | Catalog health endpoint |
| `packages/docs-mcp/src/docs_mcp/agents/lifecycle.py` | New | Agent soft-delete and cleanup |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 5 acceptance criteria met | 0/5 | 5/5 | Checklist review |
| All 5 stories completed | 0/5 | 5/5 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 12.1: Embedding-based deduplication gate
2. Story 12.2: Capability merge suggestions in proposals
3. Story 12.3: Catalog health endpoint
4. Story 12.4: Agent soft-delete and lifecycle
5. Story 12.5: Proposer overlap guard

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| False positive merges — two agents that are semantically similar but functionally distinct (crypto vs stocks) | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Merge suggestions may be wrong if the proposer LLM misunderstands the existing agent's scope | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Health endpoint could expose internal agent details if not properly scoped | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

**Expert-Identified Risks:**

- **Security Expert**: *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Quality gate score | N/A | >= 70/100 | tapps_quality_gate |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
