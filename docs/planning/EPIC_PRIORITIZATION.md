# Epic Prioritization & Story Ranking

**Date:** 2026-03-02
**Scope:** TappsMCP complete; DocsMCP build-out remaining
**Method:** Prioritized by value delivery, dependency readiness, risk reduction, and effort efficiency

---

## Executive Summary

All TappsMCP core epics (0-37) and promotion tiers (P0-P4) are **COMPLETE**, delivering 28 MCP tools, 5100+ tests, and a comprehensive code quality pipeline. The only remaining open work is **DocsMCP build-out** -- the documentation MCP server that complements TappsMCP's code quality tools.

DocsMCP Epic 0 (Foundation) is complete with 107 tests and 3 initial tools (`docs_session_start`, `docs_project_scan`, `docs_config`). Epics 1-12 from the [DocsMCP PRD](DOCSMCP_PRD.md) remain, covering code extraction, git analysis, README generation, API docs, changelogs, diagrams, validation, and multi-language support.

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

## DocsMCP: Open Work

DocsMCP Epic 0 (Foundation & Security) is complete. Epics 1-12 remain, totaling approximately 18-20 weeks of work for 1 developer. The priority order below is based on delivering a usable MVP as quickly as possible, then expanding capabilities.

### Priority Tier Summary

| Tier | Epic | Priority | LOE | Rationale |
|------|------|----------|-----|-----------|
| **Tier 1: Do Now** | Epic 1 (Code Extraction) | P0 | ~2 weeks | Foundation for all doc generation; blocks Epics 3, 4, 6, 7 |
| **Tier 2: Do Next** | Epic 2 (Git Analysis, slimmed) | P0 | ~1.5 weeks | Required for changelogs, drift detection; high user value |
| **Tier 3: Do Next** | Epic 7 (Doc Validation) | P1 | ~2 weeks | Drift detection is DocsMCP's key differentiator |
| **Tier 4: MVP Features** | Epic 3 (README Generation) | P1 | ~1.5 weeks | Most-requested doc generation feature |
| **Tier 5: MVP Features** | Epic 5 (Changelog) | P1 | ~1.5 weeks | Depends on Epic 2; immediate user value |
| **Tier 6: MVP Features** | Epic 4 (API Docs, slim) | P2 | ~2 weeks | Depends on Epic 1; valuable but lower priority than README/changelog |
| **Tier 7: Post-MVP** | Epics 6, 8-12 | P2-P3 | ~8 weeks | Diagrams, ADRs, distribution, TappsMCP integration, multi-language |

---

### Tier 1: Do Now -- DocsMCP Epic 1 (Code Extraction Engine)

**Why first?**

- **Foundation for everything**: Every doc generation tool (README, API docs, diagrams, validation) depends on being able to parse and understand code structure.
- **No blockers**: Epic 0 (Foundation) is complete, providing the project scaffold, config system, and security sandbox.
- **High impact-to-effort ratio**: 2 weeks yields the AST extraction, docstring parsing, type annotation extraction, import graph, and public API detection that all downstream epics consume.

**Recommended Story Order:**

| Priority | Story | LOE | Impact |
|----------|-------|-----|--------|
| 1 | 1.1: Python AST extractor | 8h | Core: functions, classes, methods, decorators |
| 2 | 1.2: Docstring parser (Google/NumPy/Sphinx) | 6h | Required for API docs and README generation |
| 3 | 1.3: Type annotation extractor | 4h | Enriches API documentation |
| 4 | 1.4: Module structure analyzer | 4h | Required for module maps and diagrams |
| 5 | 1.5: Public API surface detector | 4h | Identifies what to document |
| 6 | 1.6: Import graph builder | 6h | Required for dependency diagrams and validation |
| 7 | 1.7: Generic/regex-based fallback extractor | 4h | Multi-language extensibility |
| 8 | 1.8: `docs_module_map` and `docs_api_surface` MCP tools | 4h | First user-facing tools from this epic |

---

### Tier 2: Do Next -- DocsMCP Epic 2 (Git Analysis Engine)

**Why second?**

- **Required for changelogs and drift detection**: Both Epic 5 (Changelog) and Epic 7 (Doc Validation) need git history analysis.
- **Can be slimmed for MVP**: Stories 2.5 (git blame for staleness) and 2.6 (git diff for drift) can be deferred to Epic 7, reducing initial LOE.
- **High user value**: Understanding commit history and version boundaries is essential for automated documentation.

**Recommended Story Order:**

| Priority | Story | LOE | Impact |
|----------|-------|-----|--------|
| 1 | 2.1: Git log parser with structured output | 4h | Foundation for all git analysis |
| 2 | 2.2: Conventional commits parser | 6h | Required for changelog generation |
| 3 | 2.4: Tag/version boundary detection | 3h | Required for version-scoped changelogs |
| 4 | 2.3: Non-conventional commit classifier | 4h | Handles repos without conventional commits |
| 5 | 2.7: `docs_git_summary` MCP tool | 3h | User-facing git analysis tool |
| 6 | 2.5: Git blame for staleness (defer to Epic 7) | 4h | Can be built later with drift detection |
| 7 | 2.6: Git diff for drift detection (defer to Epic 7) | 4h | Natural fit with validation epic |

---

### Tier 3: Do Next -- DocsMCP Epic 7 (Documentation Validation)

**Why third?**

- **Key differentiator**: Drift detection is DocsMCP's unique selling point -- no other MCP server provides this.
- **Quality gate for docs**: Parallels TappsMCP's quality gate for code. Teams can enforce documentation freshness in CI.
- **Dependencies met**: Epic 1 provides code structure; Epic 2 provides git analysis. Together they enable drift detection, completeness checking, and freshness scoring.

**Recommended Story Order:**

| Priority | Story | LOE | Impact |
|----------|-------|-----|--------|
| 1 | 7.1: Drift detection engine | 8h | Core differentiator: code changes vs doc state |
| 2 | 7.2: Completeness checker | 6h | Coverage scoring across documentation categories |
| 3 | 7.4: Freshness scorer | 4h | Git blame + modification date analysis |
| 4 | 7.3: Link validator | 6h | Validates internal references and file paths |
| 5 | 7.5: Consistency checker | 4h | Cross-document terminology validation |
| 6 | 7.6: MCP tools (`docs_check_drift`, etc.) | 6h | User-facing validation tools |

---

### Tier 4: MVP Features -- DocsMCP Epic 3 (README Generation)

**Why fourth?**

- **Most-requested feature**: README generation is the most visible documentation task.
- **Dependencies met**: Epic 1 provides code structure extraction; project metadata extraction is self-contained.
- **Smart-merge is critical**: Must update existing READMEs without destroying human-written content, following the same pattern as TappsMCP's AGENTS.md smart-merge.

---

### Tier 5: MVP Features -- DocsMCP Epic 5 (Changelog & Release Notes)

**Why fifth?**

- **Depends on Epic 2**: Requires git analysis (conventional commits, version boundaries).
- **Immediate user value**: Automated changelogs are a high-demand feature that reduces manual toil.
- **Moderate complexity**: Keep-a-Changelog format and conventional changelog format are well-defined standards.

---

### Tier 6: MVP Features -- DocsMCP Epic 4 (API Documentation, slim)

**Why sixth?**

- **Depends on Epic 1**: Requires the full code extraction engine.
- **Can be slimmed for MVP**: Focus on module-level and function-level docs first; class hierarchy and cross-references can follow.
- **Valuable but lower priority**: API docs are important for libraries/frameworks but less urgent than README and changelog for most projects.

---

### Tier 7: Post-MVP -- DocsMCP Epics 6, 8-12

These epics are valuable but not required for MVP:

| Epic | Focus | LOE | Notes |
|------|-------|-----|-------|
| 6 | Diagram Generation (Mermaid/PlantUML) | ~1.5 weeks | Nice-to-have; dependency/class diagrams |
| 8 | ADR & Guides | ~1 week | ADR templates, onboarding/contributing guides |
| 9 | Project Scan & Workflow | ~1 week | Comprehensive audit; MCP resources/prompts |
| 10 | Distribution & CLI | ~1 week | PyPI, Docker, npm wrapper, CI workflows |
| 11 | TappsMCP Integration | ~1 week | Consume TappsMCP data for enriched docs |
| 12 | Multi-Language Support | ~2 weeks | tree-sitter for TypeScript, Go, Rust, Java |

---

## Dependency Graph (DocsMCP Epics)

```
DocsMCP Epic 0 (Foundation)  <- COMPLETE
  |
  +---> Epic 1 (Code Extraction)
  |       |
  |       +---> Epic 3 (README Generation)
  |       +---> Epic 4 (API Documentation)
  |       +---> Epic 6 (Diagram Generation)
  |       +---> Epic 7 (Documentation Validation) <- also needs Epic 2
  |
  +---> Epic 2 (Git Analysis)
          |
          +---> Epic 5 (Changelog & Release Notes)
          +---> Epic 7 (Documentation Validation) <- also needs Epic 1

Epic 8 (ADR & Guides)       <- Independent (can be done anytime after Epic 0)
Epic 9 (Project Scan)       <- Depends on Epics 1, 7
Epic 10 (Distribution)      <- Independent (can be done anytime)
Epic 11 (TappsMCP Integration) <- Depends on Epics 1, 7
Epic 12 (Multi-Language)    <- Depends on Epic 1
```

### Critical Path

```
Epic 1 (2w) -> Epic 2 (1.5w) -> Epic 7 (2w) -> Epic 3 (1.5w) -> Epic 5 (1.5w) = ~8.5 weeks to MVP
```

### Parallelization Opportunities

With 2 developers:
- **Dev A**: Epic 1 -> Epic 3 -> Epic 4
- **Dev B**: Epic 2 -> Epic 5 -> Epic 7

With 1 developer:
- Epic 1 -> Epic 2 -> Epic 7 -> Epic 3 -> Epic 5 -> Epic 4 -> Epics 6, 8-12
- Total: ~18-20 weeks sequential

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

1. **Start DocsMCP Epic 1 immediately**. Code extraction is the foundation for everything. All downstream epics depend on it.

2. **Slim Epic 2 for speed**. Defer git blame (2.5) and git diff (2.6) stories to Epic 7, where they naturally belong. This saves ~1 week.

3. **Prioritize validation (Epic 7) over generation (Epics 3-5)**. Drift detection is the key differentiator. Many tools generate docs; few detect when docs go stale.

4. **Ship MVP after Epics 1, 2, 3, 5, 7**. This delivers code extraction, git analysis, README generation, changelog generation, and documentation validation -- a compelling standalone product.

5. **Defer Epic 12 (Multi-Language) until post-MVP**. Python-first is sufficient for initial adoption. tree-sitter integration adds significant complexity for marginal initial value.

6. **Consider Epic 8 (ADR & Guides) as a quick win**. ADR templates and onboarding guides are independent of the code extraction pipeline and could be slotted in anytime for quick user value.
