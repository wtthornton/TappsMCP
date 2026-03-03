# Epic Prioritization & Story Ranking

**Date:** 2026-03-02
**Scope:** TappsMCP complete; DocsMCP build-out remaining
**Method:** Prioritized by value delivery, dependency readiness, risk reduction, and effort efficiency

---

## Executive Summary

All TappsMCP core epics (0-37) and promotion tiers (P0-P4) are **COMPLETE**, delivering 28 MCP tools, 5100+ tests, and a comprehensive code quality pipeline.

DocsMCP has reached near-complete status: **18/18 MCP tools implemented**, 42 source files, and **965 tests passing**. Epics 0-9 and 11 are **COMPLETE** (Epic 9 closed per [DOCSMCP_OPEN_EPICS_RESEARCH.md](DOCSMCP_OPEN_EPICS_RESEARCH.md): resources and prompts implemented; docs://templates and AGENTS.md generation deferred). Only **2 epics remain open**: Epic 10 (Distribution & CLI — PyPI required; Docker/npm/CI optional) and Epic 12 (Multi-Language Support, post-MVP). Remaining required work: ~1 week for docs-mcp PyPI publish.

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

## DocsMCP: Status

DocsMCP MVP and beyond is **nearly complete**. All 18 PRD tools are implemented across 42 source files with 965 tests passing. Epic 9 closed complete per research; **2 epics remain open** (10, 12).

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
| 9 | Project Scan & Workflow | **Complete** | Resources (docs://status, config, coverage), prompts (docs_workflow_overview, docs_workflow). docs://templates and AGENTS.md gen deferred. | -- |
| 10 | Distribution & CLI | **Open** | PyPI for docs-mcp (required); Docker publish, npm, CI gen optional/deferred | -- |
| 11 | TappsMCP Integration | **Complete** | Enrichment in project_scan/drift/readme | 36 |
| 12 | Multi-Language Support | **Open (post-MVP)** | tree-sitter extractors | -- |

### Remaining Work

| Tier | Epic | Priority | LOE | Rationale |
|------|------|----------|-----|-----------|
| **Tier 1: Required for standalone install** | Epic 10 (Distribution) | P1 | ~1 week | PyPI packaging and publish for docs-mcp (per INSTALLATION.md). Docker publish, CLI `check`, CI workflow generator optional; npm wrapper deferred. |
| **Tier 2: Post-MVP** | Epic 12 (Multi-Language) | P3 | ~2 weeks | tree-sitter for TypeScript, Go, Rust, Java; Python-only sufficient for MVP. |

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

### Remaining Open Epics

| Epic | Focus | LOE | Notes |
|------|-------|-----|-------|
| 10 | Distribution & CLI | ~1 week | **Required:** PyPI for docs-mcp. Optional: Docker publish, CLI `check`, CI workflow generator. Deferred: npm wrapper. |
| 12 | Multi-Language Support | ~2 weeks (post-MVP) | tree-sitter for TypeScript, Go, Rust, Java; Python-only sufficient for MVP. |

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

Epic 10 (Distribution)            <- OPEN (PyPI required; Docker/npm/CI optional)
Epic 12 (Multi-Language)           <- OPEN, post-MVP (depends on Epic 1)
```

### Critical Path (Remaining)

```
Epic 10 (PyPI for docs-mcp) = ~1 week required
Epic 12 (2w) = post-MVP, independent
```

### Remaining LOE

With 1 developer: ~1 week for required work (Epic 10 PyPI). Optional: Docker publish, CLI check, CI generator. Epic 12 deferred to post-MVP.

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

1. **Epic 9 is complete.** Per [DOCSMCP_OPEN_EPICS_RESEARCH.md](DOCSMCP_OPEN_EPICS_RESEARCH.md), MCP resources (docs://status, config, coverage) and prompts (docs_workflow_overview, docs_workflow) are implemented. docs://templates and AGENTS.md generation are deferred (low ROI; host support for resources is inconsistent).

2. **Epic 10 (Distribution):** Add PyPI build and publish for the **docs-mcp** package so `pip install docs-mcp` / `uv add docs-mcp` (documented in INSTALLATION.md) works. Docker image exists; publishing to a registry and adding CLI `check` / CI workflow generator are optional. npm wrapper is deferred (Python distribution via PyPI/pipx is sufficient).

3. **Epic 12 (Multi-Language)** remains post-MVP. Python-only is sufficient for launch.

4. **DocsMCP is MVP-complete.** All 18 MCP tools are implemented with 965 tests. Remaining required work: PyPI for docs-mcp (~1 week). Optional: Docker publish, CLI check, CI generator.
