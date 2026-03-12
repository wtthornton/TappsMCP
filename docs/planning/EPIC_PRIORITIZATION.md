# Epic Prioritization & Story Ranking

**Date:** 2026-03-12 (updated)
**Scope:** TappsMCP + Platform + DocsMCP — ALL COMPLETE
**Method:** Prioritized by value delivery, dependency readiness, risk reduction, and effort efficiency

---

## Executive Summary

**All epics are COMPLETE.** TappsMCP (Epics 0–79 including Docker Pipeline and Canonical Persona), DocsMCP (Epics 0–21), Platform Epics (12-13), and promotion tiers (P0-P4) are all finished, delivering:

- **49 combined MCP tools** (30 TappsMCP + 19 DocsMCP)
- **7,400+ tests passing**
- **Comprehensive code quality + documentation pipeline**

See [ROADMAP.md](ROADMAP.md) for future enhancement opportunities.

---

## TappsMCP Status: All Complete

| Epic | Focus | Status |
|------|-------|--------|
| 0 | Foundation & Security | Complete |
| 1 | Core Quality MVP | Complete |
| 2 | Knowledge & Docs | Complete |
| 3 | Expert System | Complete |
| 4 | Project Context & Session Notes | Complete |
| 5 | Adaptive Learning | Complete |
| 6 | Distribution | Complete |
| 7 | Metrics & Dashboard | Complete |
| 8 | Pipeline Orchestration | Complete |
| 9 | Scoring Reliability | Complete |
| 13 | Structured Tool Outputs | Complete |
| 14 | Dead Code Detection | Complete |
| 15 | Dependency Vulnerability Scanning | Complete |
| 16 | Documentation Backend Resilience | Complete |
| 17 | Circular Dependency Detection | Complete |
| 18 | LLM Engagement Level | Complete |
| 19 | GitHub Issue & PR Templates | Complete |
| 20 | GitHub Actions CI Enhancement | Complete |
| 21 | GitHub Copilot Agent Integration | Complete |
| 22 | GitHub Governance & Security Config | Complete |
| 23 | Shared Memory Foundation | Complete |
| 24 | Memory Intelligence | Complete |
| 25 | Memory Retrieval & Integration | Complete |
| 26-27 | Expert Knowledge Enhancement & Skills | Complete |
| 28 | Quality Review Remediation (Phases 1-5) | Complete |
| 29 | Doc Provider Simplification | Complete |
| 30 | Benchmark Infrastructure | Complete |
| 31 | Template Self-Optimization | Complete |
| 32 | MCP Tool Effectiveness | Complete |
| 33 | Platform Artifact Correctness | Complete |
| 34 | Memory Retrieval Upgrade | Complete |
| 35 | Expert Adaptive Integration | Complete |
| 36 | Hook & Platform Generation Expansion | Complete |
| 37 | Pipeline Onboarding & Distribution | Complete |
| P0 | Security + Impact in validate_changed | Complete |
| P1 | Checklist auto_run | Complete |
| P2 | Always-on docs + quick_check enrichment | Complete |
| P3 | Project-wide dead code | Complete |
| P4 | Close adaptive feedback loop | Complete |

---

## DocsMCP: Status — ALL COMPLETE

All 19 DocsMCP tools are implemented across 43 source files with 1,171+ tests passing.

### Epic Status Summary

| Epic | Focus | Status | Tools | Tests |
|------|-------|--------|-------|-------|
| 0 | Foundation & Security | **Complete** | `docs_session_start`, `docs_project_scan`, `docs_config` | 107 |
| 1 | Code Extraction Engine | **Complete** | `docs_module_map`, `docs_api_surface` | 375 |
| 2 | Git Analysis Engine | **Complete** | `docs_git_summary` | -- |
| 3 | README Generation | **Complete** | `docs_generate_readme` | -- |
| 4 | API Documentation | **Complete** | `docs_generate_api` | 64 |
| 5 | Changelog & Release Notes | **Complete** | `docs_generate_changelog`, `docs_generate_release_notes` | -- |
| 6 | Diagram Generation | **Complete** | `docs_generate_diagram` | 41 |
| 7 | Documentation Validation | **Complete** | `docs_check_drift`, `docs_check_completeness`, `docs_check_links`, `docs_check_freshness` | 68 |
| 8 | ADR & Guides | **Complete** | `docs_generate_adr`, `docs_generate_onboarding`, `docs_generate_contributing` | 65 |
| 9 | Project Scan & Workflow | **Complete** | Resources (docs://status, config, coverage), prompts (docs_workflow_overview, docs_workflow) | -- |
| 10 | Distribution & CLI | **Complete** | PyPI publish workflow; Docker via Epic 46; npm/CI gen deferred | -- |
| 11 | TappsMCP Integration | **Complete** | Enrichment in project_scan/drift/readme | 36 |
| 12 | Multi-Language Support | **Complete** | tree-sitter extractors for TypeScript, Go, Rust, Java + dispatcher | -- |

---

### Completed Epics (Tiers 1-7)

All MVP and post-MVP epics through Tier 7 have been implemented:

- **Tier 1 (Epic 1 - Code Extraction):** Python AST extractor, docstring parser, type annotations, module structure, API surface, import graph, generic fallback extractor, `docs_module_map` and `docs_api_surface` tools.
- **Tier 2 (Epic 2 - Git Analysis):** Git log parser, conventional commits parser, version detector, `docs_git_summary` tool.
- **Tier 3 (Epic 7 - Doc Validation):** Drift detection, completeness checker, link validator, freshness scorer, `docs_check_drift`, `docs_check_completeness`, `docs_check_links`, `docs_check_freshness` tools.
- **Tier 4 (Epic 3 - README Generation):** Metadata extraction, README templates, smart-merge engine, `docs_generate_readme` tool.
- **Tier 5 (Epic 5 - Changelog):** Keep-a-Changelog and conventional formats, release notes, `docs_generate_changelog` and `docs_generate_release_notes` tools.
- **Tier 6 (Epic 4 - API Docs):** API doc template system, module/class/function generators, `docs_generate_api` tool.
- **Tier 7 (Epics 6, 8, 11):**
  - **Epic 6 (Diagrams):** 4 diagram types (dependency, class, module, ER) x 2 formats (Mermaid, PlantUML), `docs_generate_diagram` tool.
  - **Epic 8 (ADR & Guides):** ADR templates, onboarding/contributing guide generators, `docs_generate_adr`, `docs_generate_onboarding`, `docs_generate_contributing` tools.
  - **Epic 11 (TappsMCP Integration):** Quality data enrichment in project_scan, drift detection, and README generation.

### Recently Completed (Platform Critical Path)

| Epic | Focus | Completed | Deliverables |
|------|-------|-----------|-------------|
| Platform 12 | FastMCP Composition Layer | 2026-03-04 | `tapps_mcp.platform` package, `tapps-platform` CLI, 25 integration tests, composition guide |
| Platform 13 | Distribution & Publishing | 2026-03-04 | PyPI for 3 packages, combined Dockerfile, npm wrappers, version coordination, AGENTS.md templates |

---

## Dependency Graph (DocsMCP Epics)

```
DocsMCP Epic 0 (Foundation)     <- COMPLETE
  |
  +---> Epic 1 (Code Extraction)  <- COMPLETE
  |       |
  |       +---> Epic 3 (README)   <- COMPLETE
  |       +---> Epic 4 (API Docs) <- COMPLETE
  |       +---> Epic 6 (Diagrams) <- COMPLETE
  |       +---> Epic 7 (Validation) <- COMPLETE (also needed Epic 2)
  |
  +---> Epic 2 (Git Analysis)      <- COMPLETE
          |
          +---> Epic 5 (Changelog)  <- COMPLETE
          +---> Epic 7 (Validation) <- COMPLETE (also needed Epic 1)

Epic 8 (ADR & Guides)              <- COMPLETE
Epic 9 (Project Scan & Workflow)   <- COMPLETE (resources, prompts; templates/AGENTS.md deferred)
Epic 11 (TappsMCP Integration)     <- COMPLETE

Epic 10 (Distribution)            <- COMPLETE (PyPI publish workflow)
Epic 12 (Multi-Language)           <- COMPLETE (tree-sitter extractors)

Platform Epic 12 (Composition)    <- COMPLETE (combined server, CLI, 25 tests)
Platform Epic 13 (Publishing)     <- COMPLETE (PyPI 3 packages, Docker, npm, versions)
```

### Critical Path

**All critical path epics are COMPLETE.** No remaining required work.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| AST parsing edge cases (decorators, metaclasses) | Medium | Medium | Use Python's built-in `ast` module; add fallback regex extractor |
| Smart-merge losing human content | Medium | High | Extensive tests; section markers for machine vs human content |
| Git analysis performance on large repos | Medium | Medium | Limit log depth; cache parsed commits |
| Multi-language tree-sitter complexity | High | Low | Deferred to post-MVP (Epic 12) |
| Drift detection false positives | Medium | Medium | Configurable sensitivity thresholds |

---

## Recommendations

All epics are complete. See [ROADMAP.md](ROADMAP.md) for future enhancement opportunities including:

1. **Non-Python Language Scoring** — Extend TappsMCP's quality scoring to TypeScript, JavaScript, Go, Rust
2. **Adaptive Business Domain Learning** — Extend `AdaptiveDomainDetector` to learn business expert routing
3. **Memory Consolidation** — Auto-consolidate related memories to prevent context bloat
4. **MCP Registry Submission** — List TappsMCP and DocsMCP in the official MCP server registry
