# TappsMCP Epics

**Source:** Broken out from [TAPPS_MCP_PLAN.md](../TAPPS_MCP_PLAN.md) on 2026-02-07
**TappsCodingAgents Source:** `C:\cursor\TappsCodingAgents`

## Epic Overview

| Epic | Name | Priority | LOE | Dependencies | Status |
|---|---|---|---|---|---|
| [Epic 0](EPIC-0-FOUNDATION.md) | Foundation & Security Hardening | P0 | ~1 week | None | **Complete** |
| [Epic 1](EPIC-1-CORE-QUALITY-MVP.md) | Core Quality MVP | P0 | ~2-3 weeks | Epic 0 | **Complete** |
| [Epic 2](EPIC-2-KNOWLEDGE-DOCS.md) | Knowledge & Documentation Lookup | P1 | ~2 weeks | Epic 0 | **Complete** |
| [Epic 3](EPIC-3-EXPERT-SYSTEM.md) | Expert System & Domain Knowledge | P1 | ~3-4 weeks | Epic 0 | **Complete** |
| [Epic 4](EPIC-4-PROJECT-CONTEXT.md) | Project Context & Session Management | P2 | ~2 weeks | Epic 0, Epic 1 | **Complete** |
| [Epic 5](EPIC-5-ADAPTIVE-LEARNING.md) | Adaptive Learning & Intelligence | P2 | ~2-3 weeks | Epic 1, Epic 3 | **Complete** |
| [Epic 6](EPIC-6-DISTRIBUTION.md) | Distribution & Production Readiness | P3 | ~2-3 weeks | Epic 1+ | **Complete** |
| [Epic 7](EPIC-7-METRICS-DASHBOARD.md) | Metrics, Observability & Dashboard | P1 | ~3-4 weeks | Epic 1, Epic 3, Epic 5 | **Complete** |
| [Epic 8](EPIC-8-PIPELINE-ORCHESTRATION.md) | Pipeline Orchestration & Workflow Prompts | P1 | ~1.5-2 weeks | Epic 0-4 | **Complete** |
| [Epic 10+11](../TAPPS_MCP_IMPROVEMENT_IMPLEMENTATION_PLAN.md) | Expert + Context7 Integration & Retrieval Optimization | P1 | ~2-3 weeks | Epic 2, Epic 3 | **Complete** |
| [Epic 12](EPIC-12-PLATFORM-INTEGRATION/README.md) | Platform Integration & Feature Gaps | P1 | ~4-6 weeks | Epic 0, Epic 6, Epic 8 | **Complete** |
| [Epic 13](EPIC-13-STRUCTURED-OUTPUTS.md) | Structured Tool Outputs (MCP 2025-11-25) | P0 | ~1-2 weeks | Epic 0, Epic 1 | **Complete** — 12 tools wired with structuredContent + outputSchema |
| [Epic 14](EPIC-14-DEAD-CODE-DETECTION.md) | Dead Code Detection (Vulture) | P0 | ~2-3 weeks | Epic 0, Epic 1 | **Complete** |
| [Epic 15](EPIC-15-DEPENDENCY-VULNERABILITY-SCANNING.md) | Dependency Vulnerability Scanning (pip-audit) | P0 | ~2 weeks | Epic 0, Epic 1 | **Complete** — 2 source files, 47 tests, tapps_dependency_scan tool |
| [Epic 16](EPIC-16-DOCUMENTATION-BACKEND-RESILIENCE.md) | Documentation Backend Resilience (Multi-Provider) | P0 | ~2-3 weeks | Epic 2 | **Complete** — 5 source files, 39 tests, multi-provider architecture |
| [Epic 17](EPIC-17-CIRCULAR-DEPENDENCY-DETECTION.md) | Circular Dependency Detection | P0 | ~1.5-2 weeks | Epic 0, Epic 4 | **Complete** — 3 source files, 57 tests, tapps_dependency_graph tool |
| [Epic 19](EPIC-19-GITHUB-ISSUE-PR-TEMPLATES.md) | GitHub Issue & PR Templates | P1 | ~1.5-2 weeks | Epic 8, Epic 12 | **Complete** |
| [Epic 20](EPIC-20-GITHUB-ACTIONS-CI-ENHANCEMENT.md) | GitHub Actions CI Enhancement | P1 | ~2-2.5 weeks | Epic 8, Epic 12 | **Complete** |
| [Epic 21](EPIC-21-GITHUB-COPILOT-AGENT-INTEGRATION.md) | GitHub Copilot Agent Integration + GitHub Expert | P0 | ~2.5-3 weeks | Epic 8, Epic 12, Epic 20 | **Complete** |
| [Epic 22](EPIC-22-GITHUB-GOVERNANCE-SECURITY-CONFIG.md) | GitHub Governance & Security Config | P2 | ~1.5-2 weeks | Epic 19, Epic 20, Epic 21 | **Complete** |
| [Epic 23](EPIC-23-SHARED-MEMORY-FOUNDATION.md) | Shared Memory Foundation | P1 | ~2-3 weeks | Epic 0, Epic 4 | **Complete** |
| [Epic 24](EPIC-24-MEMORY-INTELLIGENCE.md) | Memory Intelligence (Decay, Contradictions) | P1 | ~2-3 weeks | Epic 23, Epic 4, Epic 5 | **Complete** |
| [Epic 25](EPIC-25-MEMORY-RETRIEVAL-INTEGRATION.md) | Memory Retrieval & Integration | P2 | ~2-3 weeks | Epic 23, Epic 24, Epic 3, Epic 4 | **Complete** |
| [Epic 26-27](EPIC-26-EXPERT-KNOWLEDGE-ENHANCEMENT.md) | Expert Knowledge Enhancement & Skills | P1 | ~2-3 weeks | Epic 3, Epic 8 | **Complete** |
| [Epic 28](EPIC-28-QUALITY-REVIEW-REMEDIATION.md) | Quality Review Remediation | P0 | ~10 days | Epic 1 | **Complete** — all phases (1-5), 6 failing files remediated |
| [Epic 29](EPIC-29-DOC-PROVIDER-SIMPLIFICATION.md) | Doc Provider Simplification | P2 | ~1 week | Epic 2, Epic 16 | **Complete** |
| [Epic 30](EPIC-30-BENCHMARK-INFRASTRUCTURE.md) | Benchmark Infrastructure & AGENTBench Integration | P1 | ~3-4 weeks | Epic 8, Epic 18, Epic 28 | **Complete** — 12 modules, 203 tests |
| [Epic 31](EPIC-31-TEMPLATE-SELF-OPTIMIZATION.md) | Template Self-Optimization Loop | P1 | ~3-4 weeks | Epic 30, Epic 18, Epic 5 | **Complete** — 6 modules, 54 tests |
| [Epic 32](EPIC-32-MCP-TOOL-EFFECTIVENESS.md) | MCP Tool Effectiveness Benchmarking | P2 | ~3-4 weeks | Epic 30, Epic 7, Epic 5 | **Complete** — 7 modules, 60 tests |
| [Epic 33](EPIC-33-PLATFORM-ARTIFACT-CORRECTNESS.md) | Platform Artifact Correctness | P0 | ~1.5-2 weeks | Epic 8, Epic 12 | **Complete** — all 5 stories, 142 tests |
| [Epic 34](EPIC-34-MEMORY-RETRIEVAL-UPGRADE.md) | Memory Retrieval & Reinforcement Upgrade | P1 | ~2 weeks | Epic 23, Epic 24, Epic 25 | **Complete** — all 6 stories, 110 tests |
| [Epic 35](EPIC-35-EXPERT-ADAPTIVE-INTEGRATION.md) | Expert System Adaptive Integration | P1 | ~1.5-2 weeks | Epic 3, Epic 5, Epic 7 | **Complete** — all 4 stories, 72 tests |
| [Epic 36](EPIC-36-HOOK-PLATFORM-EXPANSION.md) | Hook & Platform Generation Expansion | P1 | ~2-2.5 weeks | Epic 33, Epic 8, Epic 18 | **Complete** |
| [Epic 37](EPIC-37-PIPELINE-ONBOARDING-DISTRIBUTION.md) | Pipeline Onboarding & Distribution | P1 | ~2.5-3 weeks | Epic 33, Epic 36, Epic 6, Epic 8 | **Complete** |
| [Epic 42](EPIC-42-TAPPS-MEMORY-2026-ENHANCEMENTS.md) | tapps_memory 2026 Enhancements | P1 | ~1.5-2 weeks | Epic 23, 24, 25, 34 | **Complete** — 4 stories, 21 new tests, 42 total |
| [Epic 46](EPIC-46-DOCKER-MCP-DISTRIBUTION.md) | Docker MCP Toolkit Distribution | P1 | ~3-4 weeks | Epic 6, Epic 37 | **Complete** — 8 stories, 79 new tests |
| [Epic 47](EPIC-47-WORKSPACE-SCOPED-INIT.md) | Workspace-Scoped Init | P1 | ~1-1.5 weeks | None | **Complete** |
| [Epic 48](EPIC-48-MCP-HOST-VISIBILITY-AGENT-FALLBACKS.md) | MCP Host Visibility & Agent Fallbacks | P1 | ~1 week | None | **Complete** — 2 stories, docs + template content |
| [Epic 49](EPIC-49-DOCTOR-ROBUSTNESS-QUICK-MODE.md) | Doctor Robustness & Quick Mode | P2 | ~1-1.5 weeks | None | **Complete** — 3 stories, mypy timeout + quick mode + docs |
| [Epic 50](EPIC-50-CONSUMER-REQUIREMENTS-VERIFICATION.md) | Consumer Requirements & Verification | P1 | ~1-1.5 weeks | Epic 48, Epic 49 | **Complete** |
| [Epic 51](EPIC-51-CONFIG-UX-TECH-STACK-PRESERVATION.md) | Configuration UX & TECH_STACK Preservation | P1 | ~1 week | None | **Complete** |
| [Epic 52](EPIC-52-SESSION-STARTUP-PERFORMANCE.md) | Session Startup Performance | P2 | ~3-4 days | None | **Complete** |
| [Epic 53](EPIC-53-CLI-PARITY-MCP-TOOLS.md) | CLI Parity for MCP-Only Tools | P1 | ~1 week | None | **Complete** |
| [Epic 54](EPIC-54-NON-PYTHON-RAG-CUSTOM-DOC-SOURCES.md) | Non-Python RAG & Custom Doc Sources | P2 | ~1 week | None | **Complete** |
| [Epic 55](EPIC-55-MEMORY-DASHBOARD-ENHANCEMENTS.md) | Memory & Dashboard Enhancements | P3 | ~3-4 days | None | **Complete** |
| DocsMCP Epic 10 | Distribution & CLI (PyPI publish) | P1 | ~1 week | DocsMCP Epic 0 | **Complete** — reduced scope (PyPI publish workflow) |
| Platform Epic 12 | FastMCP Composition Layer | P2 | ~3-4 days | Epic 6, DocsMCP | **Complete** — combined server, platform CLI, 25 integration tests |
| Platform Epic 13 | Distribution & Publishing | P2 | ~3-4 days | Platform Epic 12 | **Complete** — PyPI workflow (all 3 packages), combined Dockerfile, npm wrappers, version coordination, AGENTS.md DocsMCP awareness |

| [Epic 56](EPIC-56-NON-PYTHON-LANGUAGE-SCORING.md) | Non-Python Language Scoring | P1 | ~3-4 weeks | DocsMCP Epic 12 | **Complete** — 5 source files, 77+ tests, TypeScript/Go/Rust scorers |
| [Epic 57](EPIC-57-ADAPTIVE-BUSINESS-DOMAIN-LEARNING.md) | Adaptive Business Domain Learning | P1 | ~2 weeks | Epic 43-45 | **Complete** — 5 stories, 116 tests, business domain weight learning |
| [Epic 58](EPIC-58-MEMORY-CONSOLIDATION.md) | Memory Consolidation | P2 | ~2 weeks | Epic 23-25, 34 | **Complete** — 7 stories, 114+ tests, consolidate/unconsolidate actions |
| [Epic 59](EPIC-59-MCP-REGISTRY-SUBMISSION.md) | MCP Registry Submission | P1 | ~1 week | Epic 6, Epic 37 | **Complete** — server.json for both servers, registry CI publishing |
| [Epic 63](EPIC-63-AUTO-EXPERT-GENERATOR.md) | Auto Expert Generator | P2 | ~1-2 weeks | Epic 43-45 | **Complete** — 49 tests, gap analysis, config generation, knowledge scaffolding |
| [Epic 64](EPIC-64-CROSS-PROJECT-MEMORY-FEDERATION.md) | Cross-Project Memory Federation | P2 | ~2 weeks | Epic 23-25, 34, 42 | **Complete** — 56 tests, federated hub, publish/subscribe/search actions |

**Total LOE:** ~65-85 weeks — All TappsMCP Epics (0-64) + Platform Epics 12-13 complete (P0-P4), all DocsMCP Epics (0-17) complete. 6,200+ tests passing.

> **Epic 10+11** implements enhancements from [TAPPS_MCP_IMPROVEMENT_RECOMMENDATIONS.md](../../../HomeIQ/implementation/TAPPS_MCP_IMPROVEMENT_RECOMMENDATIONS.md): auto-fallback to Context7 when expert RAG is empty, structured lookup hints, workflow coupling, broader testing KB, `tapps_research` tool, hybrid fusion + rerank, hot-rank adaptive ranking, fuzzy matcher v2, content normalization, and retrieval eval harness. All 10 stories shipped and tested (230 tests passing).

## Dependency Graph

```
Epic 0 (Foundation)
  ├── Epic 1 (Core Quality MVP)
  │     ├── Epic 4 (Project Context)
  │     │     └── Epic 8 (Pipeline Orchestration) ← also depends on Epic 0-3
  │     ├── Epic 5 (Adaptive Learning) ← also depends on Epic 3
  │     │     └── Epic 7 (Metrics & Dashboard) ← also depends on Epic 1, Epic 3
  │     └── Epic 6 (Distribution)
  ├── Epic 2 (Knowledge & Docs)     ← can parallel with Epic 1
  └── Epic 3 (Expert System)         ← can parallel with Epic 1, Epic 2

Epic 12 (Platform Integration)       ← depends on Epic 0, Epic 6, Epic 8
  ├── Tier 1 (12.1-12.4) — Tool annotations, config, permissions
  ├── Tier 2 (12.5-12.8) — Hooks, subagents, skills
  ├── Tier 3 (12.9-12.12) — Plugin bundles, rule types, teams
  └── Tier 4 (12.13-12.18) — VS Code, BugBot, elicitation, CI, marketplace

--- Next Wave (Epics 13-17) ---

Epic 13 (Structured Outputs)         ← depends on Epic 0, Epic 1
Epic 14 (Dead Code Detection)        ← depends on Epic 0, Epic 1 (parallel with 13, 15)
Epic 15 (Dependency Vulnerability)   ← depends on Epic 0, Epic 1 (parallel with 13, 14)
Epic 16 (Doc Backend Resilience)     ← depends on Epic 2 (parallel with 13-15, 17)
Epic 17 (Circular Dep Detection)     ← depends on Epic 0, Epic 4 (parallel with 13-16)

--- GitHub Agent-Friendly Wave (Epics 19-22) ---

Epic 19 (Issue & PR Templates)       ← depends on Epic 8, Epic 12 (parallel with 20)
Epic 20 (Actions CI Enhancement)     ← depends on Epic 8, Epic 12 (parallel with 19)
Epic 21 (Copilot Agent Integration)  ← depends on Epic 20 (after setup-steps)
Epic 22 (Governance & Security)      ← depends on Epic 19, Epic 20, Epic 21 (final wave)

--- Shared Memory Wave (Epics 23-25) ---

Epic 23 (Shared Memory Foundation)   ← depends on Epic 0, Epic 4
  └── Epic 24 (Memory Intelligence)  ← also depends on Epic 5
        └── Epic 25 (Memory Retrieval & Integration) ← also depends on Epic 3, Epic 8, Epic 18

--- Doc Provider Simplification ---

Epic 29 (Doc Provider Simplification) ← depends on Epic 2, Epic 16
  Context7 + LlmsTxt only; deprecate Deepcon, Docfork

--- Self-Improvement & Benchmarking Wave (Epics 30-32) ---

Epic 30 (Benchmark Infrastructure)      ← depends on Epic 8, Epic 18, Epic 28
  │  AGENTBench dataset, Docker evaluation, context injection
  ├── Epic 31 (Template Self-Optimization) ← also depends on Epic 5
  │     Redundancy analysis, ablation, engagement calibration, promotion gate
  └── Epic 32 (MCP Tool Effectiveness)    ← also depends on Epic 7
        Tool impact measurement, checklist calibration, adaptive feedback loop

--- AI OS-Informed Improvements Wave (Epics 33-37) ---

Epic 33 (Platform Artifact Correctness) ← depends on Epic 8, Epic 12
  │  Fix skill/subagent frontmatter, path-scoped rules, permission rules
  ├── Epic 36 (Hook & Platform Expansion)  ← also depends on Epic 18
  │     SubagentStop/SessionEnd/PostToolUseFailure, prompt hooks, blocking hooks
  └── Epic 37 (Pipeline Onboarding & Distribution) ← also depends on Epic 6, Epic 36
        Interactive wizard, plugin packaging, upgrade rollback, cache eviction

Epic 34 (Memory Retrieval Upgrade)       ← depends on Epic 23, Epic 24, Epic 25
  BM25 scoring, reinforcement endpoint, auto-capture hook, auto-GC

Epic 42 (tapps_memory 2026 Enhancements)  ← depends on Epic 23, 24, 25, 34
  Ranked search in MCP tool, wire contradictions/reseed/import/export, curated responses, quality gate fix

Epic 35 (Expert Adaptive Integration)    ← depends on Epic 3, Epic 5, Epic 7
  Adaptive domain detector wiring, synonym expansion, knowledge freshness

--- Docker MCP Distribution ---

Epic 46 (Docker MCP Toolkit Distribution)  ← depends on Epic 6, Epic 37
  Docker MCP Catalog publishing, custom catalogs, gateway config in tapps_init
  Dockerfiles, server.yaml, tools.json, GHCR CI, expert knowledge updates

--- Consuming-Project Feedback (Epics 48-50) ---

Epic 48 (MCP Host Visibility & Agent Fallbacks)  ← no deps (docs + content)
  OpenClawAgents feedback: document MCP server visibility, CLI fallback in tapps-init skill

Epic 49 (Doctor Robustness & Quick Mode)  ← no deps
  OpenClawAgents feedback: mypy version timeout, doctor duration docs, doctor --quick mode

Epic 50 (Consumer Requirements & Verification)  ← Epic 48, Epic 49
  OpenClawAgents TAPPS_MCP_REQUIREMENTS.md: canonical "what you need" doc, doctor mapping, init/upgrade pointers

```

**Note:** Epics 30-32 form a "Self-Improvement & Benchmarking" wave. Epic 30 provides infrastructure. Epics 31 and 32 can run in parallel after Epic 30 completes.

**Note:** Epics 33-37 form an "AI OS-Informed Improvements" wave based on cross-referencing AI OS architectural patterns against TappsMCP and validating against 2026 Claude Code docs. See [TAPPMCP_IMPROVEMENTS.md](../../reviews/TAPPMCP_IMPROVEMENTS.md) for the analysis. Epic 33 (P0) should be implemented first. Epics 34 and 35 are independent and can run in parallel. Epic 36 depends on Epic 33. Epic 37 depends on Epics 33 and 36.

**Note:** Epics 13-17 are fully independent and can all be developed in parallel.

**Note:** Epics 19-22 form a new "GitHub Agent-Friendly" wave. Epics 19 and 20 can run in parallel. Epic 21 depends on Epic 20 (copilot-setup-steps). Epic 22 is the capstone that references all generated files.

**Note:** Epic 7 can start partially after Epic 1 (execution metrics, tool call tracking, basic dashboard) and grow incrementally as Epic 3 and Epic 5 deliver expert metrics and adaptive learning data. Stories 7.1, 7.4, 7.5, 7.6, 7.7 can begin after Epic 1. Stories 7.3 requires Epic 3. Story 7.2 benefits from Epic 5.

---

## DocsMCP Epics

DocsMCP is the documentation MCP server that complements TappsMCP's code quality tools. See the [DocsMCP PRD](../DOCSMCP_PRD.md) for full details and the [Epic Prioritization](../EPIC_PRIORITIZATION.md) for priority ranking.

**Status:** 19/19 MCP tools implemented, 43 source files, 1171+ tests passing. All epics (0-17) complete.

| Epic | Name | Status |
|------|------|--------|
| 0 | Foundation & Security | **Complete** -- `docs_session_start`, `docs_project_scan`, `docs_config` |
| 1 | Code Extraction Engine | **Complete** -- `docs_module_map`, `docs_api_surface` |
| 2 | Git Analysis Engine | **Complete** -- `docs_git_summary` |
| 3 | README Generation | **Complete** -- `docs_generate_readme` |
| 4 | API Documentation Generation | **Complete** -- `docs_generate_api` |
| 5 | Changelog & Release Notes | **Complete** -- `docs_generate_changelog`, `docs_generate_release_notes` |
| 6 | Diagram Generation | **Complete** -- `docs_generate_diagram` |
| 7 | Documentation Validation | **Complete** -- `docs_check_drift`, `docs_check_completeness`, `docs_check_links`, `docs_check_freshness` |
| 8 | ADR & Guides | **Complete** -- `docs_generate_adr`, `docs_generate_onboarding`, `docs_generate_contributing` |
| 9 | Project Scan & Workflow | **Complete** — resources (docs://status, config, coverage), prompts (docs_workflow_overview, docs_workflow). docs://templates and AGENTS.md generation deferred (see [DOCSMCP_OPEN_EPICS_RESEARCH.md](../DOCSMCP_OPEN_EPICS_RESEARCH.md)). |
| 10 | Distribution & CLI | **Complete** (reduced scope) — PyPI publish workflow for docs-mcp added to CI; Docker publish via Epic 46; npm wrapper, CI generator deferred |
| 11 | TappsMCP Integration | **Complete** -- Quality data enrichment in project_scan/drift/readme |
| 12 | Multi-Language Support | **Complete** — tree-sitter extractors for TypeScript, Go, Rust, Java + dispatcher |
| 14 | Diagram Generation Quality | **Complete** — source dir auto-detection, SKIP_DIRS, package-scoped diagrams |
| 15 | API Reference Enhancement | **Complete** — full docstrings, return schemas, per-package splitting, noise filtering |
| 16 | Intelligent Content Generation | **Complete** — smart description fallback, framework detection, key concepts |
| 17 | Documentation Polish & Validation | **Complete** — re-export filtering, freshness hints, quality scores |

## Parallelization Opportunities

With 2 developers:
- **Dev A:** Epic 0 → Epic 1 → Epic 4 → Epic 7 (partial) → Epic 6
- **Dev B:** (after Epic 0) Epic 2 → Epic 3 → Epic 5 → Epic 7 (expert/adaptive metrics)

## Tool Delivery Timeline

| Tool | Epic | Available After |
|---|---|---|
| `tapps_server_info` | Epic 0 | Week 1 |
| `tapps_score_file` | Epic 1 | Week 3-4 |
| `tapps_security_scan` | Epic 1 | Week 3-4 |
| `tapps_quality_gate` | Epic 1 | Week 3-4 |
| `tapps_checklist` | Epic 1 | Week 3-4 |
| `tapps_lookup_docs` | Epic 2 | Week 5-6 |
| `tapps_validate_config` | Epic 2 | Week 5-6 |
| `tapps_consult_expert` | Epic 3 | Week 8-10 |
| `tapps_list_experts` | Epic 3 | Week 8-10 |
| `tapps_project_profile` | Epic 4 | Week 10-12 |
| `tapps_session_notes` | Epic 4 | Week 10-12 |
| `tapps_impact_analysis` | Epic 4 | Week 10-12 |
| `tapps_report` | Epic 4 | Week 10-12 |
| `tapps_pipeline` (prompt) | Epic 8 | Week 12-14 |
| `tapps_pipeline_overview` (prompt) | Epic 8 | Week 12-14 |
| `tapps_init` | Epic 8 | Week 12-14 |
| `tapps_feedback` | Epic 7 | Week 14-17 |
| `tapps_stats` | Epic 7 | Week 14-17 |
| `tapps_dashboard` | Epic 7 | Week 16-20 |
| `tapps_session_start` | Epic 8 | Week 12-14 |
| `tapps_quick_check` | Epic 8 | Week 12-14 |
| `tapps_validate_changed` | Epic 8 | Week 12-14 |
| `tapps_workflow` | Epic 8 | Week 12-14 |
| `tapps_research` | Epic 10 | Week 20-22 |
| Structured `outputSchema` on all tools | Epic 13 | Week 24-25 |
| `tapps_dead_code` | Epic 14 | Week 24-27 |
| `tapps_dependency_scan` | Epic 15 | Week 24-26 |
| Multi-provider `tapps_lookup_docs` | Epic 16 | Week 24-27 |
| `tapps_dependency_graph` | Epic 17 | Week 24-26 |
| GitHub Issue/PR templates in `tapps_init` | Epic 19 | Week 34-36 |
| Enhanced CI workflows in `tapps_init` | Epic 20 | Week 36-38 |
| Copilot agent profiles in `tapps_init` | Epic 21 | Week 38-40 |
| Governance configs in `tapps_init` | Epic 22 | Week 40-42 |
| `tapps_memory` (CRUD, search) | Epic 23 | Week 43-45 |
| Memory decay, reinforcement, contradiction detection | Epic 24 | Week 45-48 |
| Ranked retrieval, expert injection, profile seeding, import/export | Epic 25 | Week 48-51 |

## Metrics Infrastructure (Epic 7 — carried from TappsCodingAgents)

The following TappsCodingAgents metrics systems are carried over in Epic 7:

| TappsCodingAgents Module | TappsMCP Target | What It Tracks |
|---|---|---|
| `workflow/execution_metrics.py` | `metrics/execution_metrics.py` | Every tool call: timing, status, errors |
| `core/outcome_tracker.py` | `metrics/outcome_tracker.py` | Initial vs. final scores, iterations to quality |
| `experts/performance_tracker.py` | `metrics/expert_metrics.py` | Expert accuracy, domain coverage, weaknesses |
| `experts/confidence_metrics.py` | `metrics/confidence_metrics.py` | Confidence calibration, threshold compliance |
| `experts/rag_metrics.py` | `metrics/rag_metrics.py` | RAG latency, similarity, cache hits |
| `experts/history_logger.py` | `metrics/consultation_logger.py` | Full consultation history (append-only) |
| `experts/observability.py` | `metrics/expert_observability.py` | Weak areas, improvement proposals |
| `experts/business_metrics.py` | `metrics/business_metrics.py` | Adoption, effectiveness, ROI, operational health |
| `core/analytics_dashboard.py` | `metrics/analytics_collector.py` | Central aggregation, trend data |
| `agents/reviewer/aggregator.py` | `metrics/quality_aggregator.py` | Multi-file score aggregation |
| `workflow/analytics_alerts.py` | `metrics/alerts.py` | Threshold alerting, severity levels |
| `health/metrics.py` | `metrics/trends.py` | Trend detection (improving/stable/degrading) |
| `workflow/analytics_visualizer.py` | `metrics/visualizer.py` | ASCII charts, metric comparisons |
| `workflow/observability_dashboard.py` | `metrics/otel_export.py` | OpenTelemetry trace export |
| `dashboard/generator.py` | `metrics/dashboard.py` | JSON/Markdown/HTML dashboards |
| `agents/reviewer/templates/*.j2` | `templates/quality-dashboard.html.j2` | HTML dashboard template |

## 2026 Best Practices Applied Across All Epics

- **Python 3.12+** with `pyproject.toml` only (PEP 621)
- **`uv`** as package manager with lockfile (`uv add "mcp[cli]"`)
- **Ruff** for linting AND formatting (replaces black + isort + flake8)
- **`mypy --strict`** from day one
- **Pydantic v2** for all config and data models
- **`structlog`** for JSON-structured logging
- **MCP Protocol `2025-11-25`** (latest stable) with **Streamable HTTP** transport (SSE deprecated)
- **FastMCP** decorator pattern (`@mcp.tool()`) — type annotations auto-generate JSON schemas
- **MCP Python SDK v1.26.0+** — both sync and async tool handlers supported
- **PyPI trusted publishing** via GitHub Actions OIDC
- **Multi-stage Docker builds** with `python:3.12-slim`
- **Local-first telemetry** — all metrics on-machine, OTEL export optional
- **JSONL for audit logs** — append-only, easy to grep/jq
- **Configurable retention** — 90-day default for metric logs

## Key MCP SDK References (from Context7)

- MCP Python SDK: `mcp[cli]>=1.26.0` on PyPI
- FastMCP: high-level API with `@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()` decorators
- Protocol version: `2025-11-25` (latest stable, released Nov 2025)
- Transports: **stdio** (local dev), **Streamable HTTP** (remote/container). SSE is deprecated.
- Error handling: `from fastmcp.exceptions import ToolError`
- Progress tracking: `await ctx.report_progress(progress=0.5, total=1.0)`
- Production deployment: `mcp.http_app()` returns ASGI app for uvicorn/gunicorn
