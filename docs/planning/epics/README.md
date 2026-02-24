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

**Completed LOE:** ~32-42 weeks (Epics 0-17, all complete)
**Total estimated LOE:** ~32-42 weeks (1 developer)

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
```

**Note:** Epics 13-17 are fully independent and can all be developed in parallel.

**Note:** Epic 7 can start partially after Epic 1 (execution metrics, tool call tracking, basic dashboard) and grow incrementally as Epic 3 and Epic 5 deliver expert metrics and adaptive learning data. Stories 7.1, 7.4, 7.5, 7.6, 7.7 can begin after Epic 1. Stories 7.3 requires Epic 3. Story 7.2 benefits from Epic 5.

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
