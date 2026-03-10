# Epic 68: Expert & Research Effectiveness

<!-- docsmcp:start:metadata -->
- **Status:** Complete
- **Priority:** P1
- **Estimated LOE:** ~2 weeks (1 developer)
- **Dependencies:** None (builds on existing expert/research infrastructure)
- **Blocks:** None
- **Source:** MCP tool usage reviews (EPIC-67 review, TheStudio Epic 9 review)
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Fix the expert consultation and research tool pipeline so that `tapps_consult_expert` and `tapps_research` return high-confidence, actionable results for all registered knowledge domains — especially infrastructure, CI/CD, and testing topics where both reviews showed confidence 0.3 with zero RAG chunks despite knowledge files existing on disk.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Two independent MCP tool usage reviews (Epic 67 review on TappMCP, Epic 9 review on TheStudio) both found:

1. **`tapps_consult_expert` returned 0.3 confidence with zero RAG chunks** for cloud-infrastructure, testing-strategies, and development-workflow domains — even though knowledge files exist (200-560 lines each) in those domains. The RAG indices are never warmed.
2. **`tapps_research` Context7 fallback was unhelpful** for operational topics (Docker Compose testing, GitHub Actions CI). Context7 returns API reference docs, not operational patterns.
3. **37.5% tool usefulness rate** (3/8 calls useful) in the TheStudio review, with 0 new issues found by MCP tools vs the review agent finding all issues directly.
4. **`tapps-research` was the single highest-value call** in the TappMCP review — when it worked, it changed 2 stories and killed 1 bad story. But for infrastructure topics, it returned nothing.

The root cause is a gap between knowledge content (which exists) and knowledge retrieval (which fails because RAG indices aren't built at session start for all domains).
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `tapps_consult_expert` returns confidence ≥ 0.6 with ≥ 1 RAG chunk for any domain that has knowledge files on disk
- [ ] RAG indices are built/warmed for all registered domains during `tapps_session_start`
- [ ] `tapps_research` provides useful results for Docker, GitHub Actions, and CI/CD queries
- [ ] `tapps_session_start` completes in < 10s with warm cache (currently 60.9s observed)
- [ ] New `tapps_checklist(task_type="epic")` variant validates epic document structure
- [ ] All existing tests pass; new tests cover each story
<!-- docsmcp:end:acceptance-criteria -->

---

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Expert confidence (infra domains) | 0.3 | ≥ 0.6 | `tapps_consult_expert` on cloud-infrastructure, testing queries |
| RAG chunks returned | 0 | ≥ 2 | Same queries as above |
| Session start (warm cache) | 60.9s | < 10s | Timed `tapps_session_start(quick=True)` |
| Tool usefulness rate | 37.5% | ≥ 70% | Review audit methodology |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| RAG warming adds latency to session start | Medium | Medium | Lazy warming — warm on first query, not at startup |
| Context7 still returns generic docs for ops topics | High | Low | Fallback to local knowledge base; don't depend on Context7 for ops |
| Large RAG index memory usage | Low | Medium | BM25 text search as lightweight fallback when embedder unavailable |

---

<!-- docsmcp:start:stories -->
## Stories

### Story 68.1: Fix RAG Index Warming for All Domains

> **As a** TappsMCP user, **I want** expert consultation to return relevant knowledge chunks for all domains that have knowledge files, **so that** I get high-confidence answers instead of generic fallbacks.

**Points:** 5 | **Size:** M | **Priority:** P0

**Files:**
- `packages/tapps-core/src/tapps_core/experts/rag_warming.py`
- `packages/tapps-core/src/tapps_core/experts/engine.py`
- `packages/tapps-core/src/tapps_core/experts/rag_index.py`
- `packages/tapps-core/tests/unit/test_rag_warming.py`

#### Problem

`warm_expert_rag_indices()` exists but is not reliably called for all domains. When `tapps_consult_expert` is called for `cloud-infrastructure` or `testing-strategies`, the knowledge files on disk (containerization.md, ci-cd-patterns.md, etc.) are never indexed, resulting in 0 chunks and 0.3 confidence.

#### Tasks

- [ ] Audit `warm_expert_rag_indices()` — determine which domains are skipped and why
- [ ] Ensure all domains with knowledge files in `experts/knowledge/<domain>/` are indexed
- [ ] Add lazy warming: if a domain's index is missing at query time, build it on-demand
- [ ] Add index freshness check: rebuild if knowledge files are newer than index
- [ ] Add integration test that queries each domain and asserts ≥ 1 chunk returned

#### Acceptance Criteria

- [ ] All 18 knowledge domains have RAG indices (or BM25 fallback) after session start
- [ ] On-demand warming works when session start is skipped
- [ ] Index freshness check prevents stale indices
- [ ] Integration test covers all domains

---

### Story 68.2: Optimize Session Start Performance

> **As a** TappsMCP user, **I want** session initialization to complete in under 10 seconds, **so that** the tool doesn't feel sluggish at the start of every workflow.

**Points:** 3 | **Size:** S | **Priority:** P1

**Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (session_start handler)
- `packages/tapps-mcp/src/tapps_mcp/server_helpers.py`
- `packages/tapps-core/src/tapps_core/experts/rag_warming.py`
- `packages/tapps-mcp/tests/unit/test_session_start.py`

#### Problem

`tapps_session_start(quick=True)` was observed at 60.9s latency. Epic 52 (Session Startup Performance) targeted < 1s with warm cache, but the observed time suggests warm cache isn't being used or RAG warming is blocking.

#### Tasks

- [ ] Profile `tapps_session_start` to identify the bottleneck (tool detection? RAG warming? disk I/O?)
- [ ] Move RAG warming to background/lazy — don't block session_start
- [ ] Ensure disk-based tool version cache (from Epic 52) is being used
- [ ] Add timing instrumentation to session_start that reports per-phase durations
- [ ] Add performance regression test: session_start(quick=True) < 10s

#### Acceptance Criteria

- [ ] `tapps_session_start(quick=True)` completes in < 10s with warm cache
- [ ] RAG warming does not block session initialization
- [ ] Per-phase timing visible in session_start response

---

### Story 68.3: Improve Context7 Fallback for Operational Topics

> **As a** TappsMCP user, **I want** `tapps_research` to provide useful results for Docker, GitHub Actions, and CI/CD queries, **so that** I don't get empty or generic results for operational questions.

**Points:** 3 | **Size:** S | **Priority:** P1

**Files:**
- `packages/tapps-core/src/tapps_core/knowledge/lookup.py`
- `packages/tapps-core/src/tapps_core/knowledge/context7_client.py`
- `packages/tapps-core/src/tapps_core/knowledge/library_detector.py`
- `packages/tapps-core/tests/unit/test_lookup.py`

#### Problem

`tapps_research` for Docker/CI topics falls back to Context7, which returns generic API reference (build images, Dockerfile writing) instead of operational patterns (GitHub Actions service containers, docker compose test rigs, CI caching strategies). The library_detector resolves "docker" to generic Docker docs.

#### Tasks

- [ ] Add library aliases: `docker-compose` → docker compose v2 docs, `github-actions` → workflow syntax reference
- [ ] When Context7 returns only table-of-contents / index content, detect and mark as `degraded: true`
- [ ] Prefer local expert knowledge over Context7 for operational topics (CI, Docker, infrastructure)
- [ ] Add fallback priority: local knowledge → Context7 → graceful "no results" with domain suggestion
- [ ] Test with the exact queries from the reviews: "Docker Compose integration testing patterns", "GitHub Actions CI job design"

#### Acceptance Criteria

- [ ] `tapps_research` for Docker/CI topics returns ≥ 1 actionable result
- [ ] Local expert knowledge is checked before Context7 for operational domains
- [ ] Generic/TOC-only Context7 results are flagged as degraded

---

### Story 68.4: Add Epic-Level Checklist Validation

> **As a** TappsMCP user, **I want** `tapps_checklist(task_type="epic")` to validate epic document structure, **so that** I can programmatically check that my epics have all required sections before starting implementation.

**Points:** 3 | **Size:** S | **Priority:** P2

**Files:**
- `packages/tapps-mcp/src/tapps_mcp/tools/checklist.py`
- `packages/tapps-mcp/tests/unit/test_checklist.py`

#### Problem

`tapps_checklist` supports `task_type` values like `feature`, `bugfix`, `review`, but has no `epic` variant. During epic reviews, there's no way to validate:
- All stories have acceptance criteria
- Story sizes are consistent with point estimates
- Dependencies form a DAG (no cycles)
- Files-affected table is complete
- Implementation order respects dependency chains

#### Tasks

- [ ] Add `task_type="epic"` to checklist task map
- [ ] Define epic validation checks: required sections (Goal, Motivation, AC, Stories), story completeness, dependency DAG
- [ ] Accept `file_path` parameter pointing to the epic markdown file
- [ ] Parse epic markdown to extract stories, points, dependencies, files
- [ ] Report validation results with specific actionable findings

#### Acceptance Criteria

- [ ] `tapps_checklist(task_type="epic", file_path="...")` validates epic documents
- [ ] Reports missing sections, incomplete stories, dependency cycles
- [ ] Works on existing epics in `docs/planning/epics/`

---

### Story 68.5: Expert Knowledge Content Gaps — Docker Integration Testing

> **As a** TappsMCP user consulting the expert system about Docker integration testing, **I want** comprehensive knowledge coverage for container-based testing patterns, **so that** expert consultations return actionable, specific guidance.

**Points:** 2 | **Size:** S | **Priority:** P2

**Files:**
- `packages/tapps-core/src/tapps_core/experts/knowledge/testing/container-testing-patterns.md` (new)
- `packages/tapps-core/src/tapps_core/experts/knowledge/cloud-infrastructure/docker-compose-testing.md` (new)
- `packages/tapps-core/src/tapps_core/experts/knowledge/development-workflow/github-actions-service-containers.md` (new)

#### Problem

Both reviews identified specific knowledge gaps:
- Docker Compose integration testing patterns (service health checks, network isolation, volume mounts for test fixtures)
- GitHub Actions CI job design (caching, artifact upload, concurrency groups, service containers)
- pytest markers and fixture patterns for container-based tests
- httpx usage for smoke testing live services

Existing files cover Docker concepts generically but lack the testing-specific operational patterns that users actually ask about.

#### Tasks

- [ ] Create `container-testing-patterns.md` in testing domain: pytest-docker fixtures, health check waits, container cleanup, network isolation
- [ ] Create `docker-compose-testing.md` in cloud-infrastructure: compose file patterns for test rigs, override files, profile-based services
- [ ] Create `github-actions-service-containers.md` in development-workflow: service containers, Docker Compose in CI, caching layers, artifact patterns
- [ ] Ensure all new files follow knowledge file format (frontmatter, sections, code examples)
- [ ] Verify RAG indexing picks up new files (depends on Story 68.1)

#### Acceptance Criteria

- [ ] 3 new knowledge files created with actionable patterns
- [ ] `tapps_consult_expert(domain="testing", question="Docker Compose integration testing")` returns ≥ 2 chunks
- [ ] Knowledge files include code examples, not just prose

---

### Story 68.6: Expose `tapps_consult_expert` as Direct MCP Tool

> **As a** MCP client user, **I want** `tapps_consult_expert` to be directly discoverable via ToolSearch, **so that** I can call it without going through the `tapps-research` skill wrapper.

**Points:** 2 | **Size:** S | **Priority:** P2

**Files:**
- `packages/tapps-mcp/src/tapps_mcp/server.py`
- MCP client configuration (`.cursor/mcp.json`, `.vscode/mcp.json`)
- `AGENTS.md`

#### Problem

In the Epic 67 review, `tapps_consult_expert` was only accessible via the `tapps-research` skill. The MCP tool itself wasn't discoverable via ToolSearch. This is likely a configuration issue (tapps-mcp server not registered in the VSCode extension session) rather than a code issue, but should be documented and tested.

#### Tasks

- [ ] Verify `tapps_consult_expert` is registered as an `@mcp.tool()` handler (should already be)
- [ ] Document MCP client configuration requirements in AGENTS.md troubleshooting section
- [ ] Add `tapps-mcp doctor` check that verifies MCP server registration in common client configs
- [ ] Add example `.cursor/mcp.json` and `.vscode/mcp.json` configurations to distribution docs

#### Acceptance Criteria

- [ ] `tapps_consult_expert` appears in ToolSearch when tapps-mcp server is properly configured
- [ ] `tapps-mcp doctor` warns if MCP server config is missing from common client locations
- [ ] Configuration examples documented

<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:implementation-order -->
## Implementation Order

```
68.1 (RAG warming fix) ──→ 68.5 (knowledge content)
         │
         ↓
68.2 (session perf) ──→ 68.3 (Context7 fallback)
                                    │
68.4 (epic checklist) ←────────────←┘
68.6 (discoverability) — independent
```

1. **68.1** first — fixes the core RAG pipeline that all other stories depend on
2. **68.2** in parallel — independent performance work
3. **68.5** after 68.1 — new content needs working RAG to validate
4. **68.3** after 68.2 — builds on understanding of lookup pipeline
5. **68.4** independent — new checklist variant
6. **68.6** independent — configuration/documentation
<!-- docsmcp:end:implementation-order -->

---

## Files Affected

| File | Stories | Change Type |
|------|---------|-------------|
| `tapps_core/experts/rag_warming.py` | 68.1, 68.2 | Modify |
| `tapps_core/experts/engine.py` | 68.1 | Modify |
| `tapps_core/experts/rag_index.py` | 68.1 | Modify |
| `tapps_core/knowledge/lookup.py` | 68.3 | Modify |
| `tapps_core/knowledge/context7_client.py` | 68.3 | Modify |
| `tapps_core/knowledge/library_detector.py` | 68.3 | Modify |
| `tapps_mcp/server_pipeline_tools.py` | 68.2 | Modify |
| `tapps_mcp/tools/checklist.py` | 68.4 | Modify |
| `tapps_mcp/server.py` | 68.6 | Verify |
| `tapps_core/experts/knowledge/testing/` | 68.5 | New files |
| `tapps_core/experts/knowledge/cloud-infrastructure/` | 68.5 | New files |
| `tapps_core/experts/knowledge/development-workflow/` | 68.5 | New files |
