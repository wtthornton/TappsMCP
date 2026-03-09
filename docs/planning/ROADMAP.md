# TappsMCP Roadmap

**Date:** 2026-03-09
**Status:** All formal epics complete; this document tracks future enhancement opportunities

---

## Current State

TappsMCP has completed all planned epics:

| Package | Epics | Tools | Tests |
|---------|-------|-------|-------|
| **tapps-mcp** | Epics 0-55, 56-59, 63-64 + P0-P4 promotions | 29 tools | 4,200+ |
| **tapps-core** | Shared infrastructure | -- | 1,700+ |
| **docs-mcp** | Epics 0-12 (13 epics) | 22 tools | 1,300+ |
| **Platform** | 2 epics (12-13) | Combined server | 25+ |
| **Total** | All complete | 51 tools | 7,200+ |

---

## Future Enhancements

### Tier 1: High Impact, Medium Effort

| Epic | Name | Priority | LOE | Rationale |
|------|------|----------|-----|-----------|
| **56** | [Non-Python Language Scoring](epics/EPIC-56-NON-PYTHON-LANGUAGE-SCORING.md) | P1 | ~3-4 weeks | Extend quality scoring to TypeScript, JavaScript, Go, Rust. **Complete** (2026-03-06). |
| **57** | [Adaptive Business Domain Learning](epics/EPIC-57-ADAPTIVE-BUSINESS-DOMAIN-LEARNING.md) | P1 | ~2 weeks | Extend `AdaptiveDomainDetector` to learn business expert routing from feedback. **Complete** (2026-03-06). |
| **58** | [Memory Consolidation](epics/EPIC-58-MEMORY-CONSOLIDATION.md) | P2 | ~2 weeks | Auto-consolidate related memories into summaries to prevent context bloat. **Complete** (2026-03-06). |

### Tier 2: Distribution & Adoption

| Epic | Name | Priority | LOE | Rationale |
|------|------|----------|-----|-----------|
| **59** | [MCP Registry Submission](epics/EPIC-59-MCP-REGISTRY-SUBMISSION.md) | P1 | ~1 week | List TappsMCP and DocsMCP in official MCP server registry for discoverability. **Complete** (2026-03-06). |
| **60** | Video & Tutorial Content | P2 | ~2 weeks | Demo videos, getting-started guides, use-case walkthroughs. |
| **61** | VS Code Native Extension | P3 | ~4-6 weeks | Native VS Code extension beyond MCP for broader reach. |

### Tier 3: Advanced Features

| Epic | Name | Priority | LOE | Rationale |
|------|------|----------|-----|-----------|
| **62** | [Context7-Assisted Memory Validation](epics/EPIC-62-CONTEXT7-MEMORY-VALIDATION.md) | P2 | ~3 weeks | Validate memory entries against authoritative docs via Context7/LlmsTxt lookup. Extract library claims, score similarity, adjust confidence, enrich with doc references. 7 stories. |
| **63** | [Auto Expert Generator](epics/EPIC-63-AUTO-EXPERT-GENERATOR.md) | P3 | ~2-3 weeks | Analyze codebase patterns to suggest/create domain experts. **Complete** (2026-03-09). |
| **64** | [Cross-Project Memory Federation](epics/EPIC-64-CROSS-PROJECT-MEMORY-FEDERATION.md) | P3 | ~3-4 weeks | Share memory across related projects (monorepo packages). **Complete** (2026-03-09). |

### Tier 4: Deferred Items (From Completed Epics)

These items were explicitly deferred during epic implementation:

| Source | Item | Notes |
|--------|------|-------|
| Epic 6 | Full Workflow State Tool | Only if demand exists |
| Epic 9 | docs://templates resource | Low ROI; host support inconsistent |
| Epic 9 | AGENTS.md generation for consuming projects | Optional; manual preferred |
| Epic 10 | npm wrapper for docs-mcp | PyPI/pipx sufficient |
| Epic 10 | CLI `check` command | Optional |
| Epic 10 | CI workflow generator | Optional |

---

## Prioritization Criteria

Enhancements are prioritized by:

1. **User Impact** — How many users benefit? How significant is the improvement?
2. **Effort Efficiency** — LOE vs. value delivered
3. **Strategic Alignment** — Does it expand addressable market or deepen existing value?
4. **Dependency Readiness** — Are prerequisites in place?

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-06 | Created roadmap | All epics complete; need forward-looking document |
| 2026-03-06 | Prioritized Non-Python scoring as Epic 56 | Biggest gap in current offering; DocsMCP extractors provide foundation |
| 2026-03-06 | Prioritized Adaptive Business Learning as Epic 57 | Closes feedback loop on Epic 43-45 business expert system |
| 2026-03-06 | Started Epic 56 Story 56.1 | Created `ScorerBase` ABC; `CodeScorer` now inherits from it; 28 new tests |
| 2026-03-06 | Completed Epic 56 | All 7 stories done: TypeScript, Go, Rust scorers with tree-sitter; tool integration; 77 new tests |
| 2026-03-06 | Completed Epic 57 | All 5 stories done: domain weight storage, adaptive detector with business support, feedback integration, detector delegation, docs; 51 new tests |
| 2026-03-06 | Completed Epic 59 | MCP Registry submission: server.json for both packages, GitHub Actions workflow, README mcp-name verification |
| 2026-03-09 | Completed Epic 63 | Auto Expert Generator: gap analysis, config generation, knowledge scaffolding, MCP tool integration, init suggestion |
| 2026-03-09 | Completed Epic 64 | Cross-Project Memory Federation: hub store, publish/subscribe, federated search, scope extension, 6 MCP actions |

---

## Contributing

To propose a new enhancement:

1. Create an epic document in `docs/planning/epics/EPIC-NN-NAME.md`
2. Add it to the appropriate tier in this roadmap
3. Include: Status, Priority, LOE, Dependencies, Stories, Acceptance Criteria
