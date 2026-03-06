# TappsMCP Roadmap

**Date:** 2026-03-06
**Status:** All formal epics complete; this document tracks future enhancement opportunities

---

## Current State

TappsMCP has completed all planned epics:

| Package | Epics | Tools | Tests |
|---------|-------|-------|-------|
| **tapps-mcp** | 55 epics (0-55) + P0-P4 promotions | 29 tools | 3,420+ |
| **tapps-core** | Shared infrastructure | -- | 1,269+ |
| **docs-mcp** | 17 epics (0-17) | 19 tools | 1,171+ |
| **Platform** | 2 epics (12-13) | Combined server | 25+ |
| **Total** | 74 epics | 48 tools | 5,995+ |

---

## Future Enhancements

### Tier 1: High Impact, Medium Effort

| Epic | Name | Priority | LOE | Rationale |
|------|------|----------|-----|-----------|
| **56** | [Non-Python Language Scoring](epics/EPIC-56-NON-PYTHON-LANGUAGE-SCORING.md) | P1 | ~3-4 weeks | Extend quality scoring to TypeScript, JavaScript, Go, Rust. DocsMCP already has tree-sitter extractors. |
| **57** | [Adaptive Business Domain Learning](epics/EPIC-57-ADAPTIVE-BUSINESS-DOMAIN-LEARNING.md) | P1 | ~2 weeks | Extend `AdaptiveDomainDetector` to learn business expert routing from feedback. |
| **58** | [Memory Consolidation](epics/EPIC-58-MEMORY-CONSOLIDATION.md) | P2 | ~2 weeks | Auto-consolidate related memories into summaries to prevent context bloat. |

### Tier 2: Distribution & Adoption

| Epic | Name | Priority | LOE | Rationale |
|------|------|----------|-----|-----------|
| **59** | MCP Registry Submission | P1 | ~1 week | List TappsMCP and DocsMCP in official MCP server registry for discoverability. |
| **60** | Video & Tutorial Content | P2 | ~2 weeks | Demo videos, getting-started guides, use-case walkthroughs. |
| **61** | VS Code Native Extension | P3 | ~4-6 weeks | Native VS Code extension beyond MCP for broader reach. |

### Tier 3: Advanced Features

| Epic | Name | Priority | LOE | Rationale |
|------|------|----------|-----|-----------|
| **62** | Context7-Assisted Memory Validation | P2 | ~2 weeks | Use docs lookup to validate/enrich memory entries. |
| **63** | Auto Expert Generator | P3 | ~2-3 weeks | Analyze codebase patterns to suggest/create domain experts. |
| **64** | Cross-Project Memory Federation | P3 | ~3-4 weeks | Share memory across related projects (monorepo packages). |

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

---

## Contributing

To propose a new enhancement:

1. Create an epic document in `docs/planning/epics/EPIC-NN-NAME.md`
2. Add it to the appropriate tier in this roadmap
3. Include: Status, Priority, LOE, Dependencies, Stories, Acceptance Criteria
