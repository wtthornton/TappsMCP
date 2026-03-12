# 2026 Best Practices Research & Next Steps Plan

**Date:** 2026-03-11  
**Sources:** TappsMCP experts (code-quality, software-architecture, agent-learning, development-workflow, documentation-knowledge-management), Context7 MCP specification (2025-11-25), repo research (2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md, OPEN-EPICS-AND-STORIES-REVIEW.md, HANDOFF-2026-03-11).

**Status (2026-03-11):** Epic 65 fully complete (17/17). **Epic 78** (canonical persona) implemented: 78.1 tool, 78.2 rule + prompts + subagents, 78.3 docs, 78.4 audit log. Remaining: **Phase 4 optional** — 66.1 already Complete; Epics 70–73 (expert personas) are Draft, lower priority.

---

## 1. Research summary (experts + Context7)

### 1.1 Code quality & MCP (Code Quality Expert, 72% confidence)

- **Quality gates:** Pre-commit hooks, automated linting, required reviews, test coverage.
- **Tool effectiveness:** Use ALL_MINUS_ONE evaluation; cover security, complexity, style, architecture; track call patterns; calibrate per engagement level; set guardrails on adaptation (confidence threshold ~0.4).
- **Static analysis:** Ruff (v0.15+) as single linter/formatter; line-length 100, py312; select E, W, F, I, N, UP, B, A, C4, SIM, TCH, RUF, S, ANN, PT, PL.

### 1.2 Memory & agent learning (Agent Learning Expert, 82% confidence)

- **Retrieval:** Use BM25 over keyword matching; filter stop words; reinforce valuable memories; run GC at session start; seed on first init only.
- **Context injection:** Limit to ~5 memories to avoid overwhelming context; filter by confidence; avoid unbounded retrieval and injecting low-confidence memories.
- **Anti-patterns:** No stemming, unbounded retrieval, no decay, re-seeding every init, injecting low-confidence memories.
- **Cross-project:** Export/import for knowledge transfer; use consolidate with dry_run for preview.

### 1.3 MCP tool count & context (repo research + Context7)

- **Tool count:** &lt;30 tools (large models); &lt;20 for smaller models. 51 (Tapps + Docs) is above safe range; curate by task.
- **Context budget:** Tool definitions &lt;20–40% of context; keep descriptions short and precise; consider progressive disclosure / defer_loading.
- **Good citizen:** Don’t load every tool for every task; separate MCPs by group; enable only what’s needed (e.g. code-quality vs docs vs security).

### 1.4 Documentation & knowledge (Documentation Expert, 83% confidence)

- **Organization:** Logical structure, consistent format, cross-references, tags, search.
- **Maintenance:** Regular reviews, version control, ownership, feedback loop, retire obsolete content.
- **Best practices:** Know your audience; start with outline; use examples; keep it simple; review and revise; peer review.

### 1.5 Roadmap prioritization (Development Workflow Expert)

- **Flow:** Feature branches → PR → main; continuous deployment and fast iteration.
- **Automation:** Prefer declarative config, reproducibility, and automation.

*Note: Context7 doc fetch succeeded (MCP spec 2025-11-25); tapps_research reported cache permission denied in Docker for supplemental docs, but expert RAG and resolve-library-id / get-library-docs were used.*

---

## 2. 2026 best practices applied to this repo

| Area | Practice | Status / action |
|------|----------|------------------|
| **Tool count** | Keep active tools &lt;30; curate by task | Done: enabled_tools, tool_preset, role presets (Epic 79). Document subsets (79.4). |
| **Memory** | Limit injection; context budget; GC at session start | Epic 65.16 (context budget), 65.4 (auto-recall hook). |
| **Quality** | Ruff + gates + guardrails on adaptation | In place; tapps_quick_check, tapps_validate_changed, engagement level. |
| **Docs** | Consistent structure, compact LLM view, maintain | Epic 75 complete (common schema, compact view). |
| **Security** | Defense in depth, input validation, audit | Path validator; Epic 78 (canonical persona) for prompt-injection defense. |

---

## 3. Recommended next steps (prioritized)

### Phase 1: Quick wins (1–2 weeks)

| # | Item | Source | LOE | Rationale |
|---|------|--------|-----|-----------|
| 1 | **Epic 79.4** — Document recommended tool subsets | OPEN-EPICS | 1–2 days | 2026 best practice: curate by use case; already have tiers and presets. |
| 2 | **Epic 65.16** — Context budget for memory injection | Agent expert | 2–3 days | “Limit context injection to 5 memories”; prevents overwhelming context. |
| 3 | **Epic 65.4** — Auto-recall hook | Memory best practices | 1–1.5 wk | “Run GC at session start”; recall on session start from config. |
| 4 | **Reconcile Epic 65 README** — Mark completed 65.x Complete | OPEN-EPICS | 0.5 day | 65.1, 65.2, 65.3, 65.5, 65.6, 65.9, 65.10, 65.12, 65.14, 65.15, 65.17 done in story docs. |

### Phase 2: Memory & retrieval (3–5 weeks)

| # | Item | Source | LOE | Rationale |
|---|------|--------|-----|-----------|
| 5 | **Epic 65.7** — Optional vector/embedding provider | Roadmap | 1.5–2 wk | Enables hybrid and better retrieval. |
| 6 | **Epic 65.8** — Hybrid search with RRF | Roadmap | 2–2.5 wk | BM25 + vector fusion; expert prefers BM25, hybrid improves recall. |
| 7 | **Epic 65.11** — Procedural memory tier | P2 | 1 wk | Richer memory model. |
| 8 | **Epic 65.13** — Relationship-aware retrieval | P2 | 1–1.5 wk | Builds on 65.12 (entity/relationship). |

### Phase 3: UX & safety (2–4 weeks)

| # | Item | Source | LOE | Rationale |
|---|------|--------|-----|-----------|
| 9 | **Epic 79.5** — Role presets in server config | ROLE-PRESETS-IMPLEMENT-FIRST | 2–3 days | reviewer, planner, frontend, developer; aligns with “task-specific” tools. |
| 10 | **Epic 79.6** — Docker MCP role-named profiles | Epic 79 | 2–3 days | Named profiles for Docker consumers. |
| 11 | **Epic 78** — Canonical persona injection | Security / prompt-injection | 1–2 wk | Defense in depth; allowlisted persona, rule prepend, docs. |

### Phase 4: Optional / later

| # | Item | LOE | Note |
|---|------|-----|------|
| 12 | Epic 66.1 — validate_changed path hints | — | **Complete** (per README); no work left. |
| 13 | Epics 70–73 — Expert personas / enrichment | 0 | **Complete** (70: persona + guidelines; 71: critical_rules; 72: content audit; 73: communication_style). See [2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md](2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md) and [EPIC-72/story-72-content-plan.md](../epics/EPIC-72/story-72-content-plan.md). |

---

## 4. Suggested execution order

1. **This week:** 79.4 (doc tool subsets), 65.16 (context budget), reconcile Epic 65 README.  
2. **Next:** 65.4 (auto-recall), then 79.5 / 79.6 (role presets + Docker profiles).  
3. **Then:** 65.7 → 65.8 (vector provider → hybrid RRF).  
4. **Parallel or after:** 65.11, 65.13, Epic 78.

---

## 5. References

- **Experts used:** tapps_research (code-quality-analysis, software-architecture, agent-learning), tapps_consult_expert (development-workflow, documentation-knowledge-management).
- **Context7:** resolve-library-id, get-library-docs (MCP spec 2025-11-25).
- **Repo:** docs/planning/research/2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md, docs/planning/epics/OPEN-EPICS-AND-STORIES-REVIEW.md, docs/planning/epics/HANDOFF-2026-03-11-EPIC-75-76-77.md, docs/planning/epics/README.md.
