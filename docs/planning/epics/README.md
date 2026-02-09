# TappsMCP Epics

**Source:** Broken out from [TAPPS_MCP_PLAN.md](../TAPPS_MCP_PLAN.md) on 2026-02-07
**TappsCodingAgents Source:** `C:\cursor\TappsCodingAgents`

## Epic Overview

| Epic | Name | Priority | LOE | Dependencies | Status |
|---|---|---|---|---|---|
| [Epic 0](EPIC-0-FOUNDATION.md) | Foundation & Security Hardening | P0 | ~1 week | None | Not Started |
| [Epic 1](EPIC-1-CORE-QUALITY-MVP.md) | Core Quality MVP | P0 | ~2-3 weeks | Epic 0 | Not Started |
| [Epic 2](EPIC-2-KNOWLEDGE-DOCS.md) | Knowledge & Documentation Lookup | P1 | ~2 weeks | Epic 0 | Not Started |
| [Epic 3](EPIC-3-EXPERT-SYSTEM.md) | Expert System & Domain Knowledge | P1 | ~3-4 weeks | Epic 0 | Not Started |
| [Epic 4](EPIC-4-PROJECT-CONTEXT.md) | Project Context & Session Management | P2 | ~2 weeks | Epic 0, Epic 1 | Not Started |
| [Epic 5](EPIC-5-ADAPTIVE-LEARNING.md) | Adaptive Learning & Intelligence | P2 | ~2-3 weeks | Epic 1, Epic 3 | Not Started |
| [Epic 6](EPIC-6-DISTRIBUTION.md) | Distribution & Production Readiness | P3 | ~2-3 weeks | Epic 1+ | Not Started |
| [Epic 7](EPIC-7-METRICS-DASHBOARD.md) | Metrics, Observability & Dashboard | P1 | ~3-4 weeks | Epic 1, Epic 3, Epic 5 | Not Started |

**Total estimated LOE:** ~17-22 weeks (1 developer), ~9-12 weeks (2 developers with parallelized epics)

## Dependency Graph

```
Epic 0 (Foundation)
  ├── Epic 1 (Core Quality MVP)
  │     ├── Epic 4 (Project Context)
  │     ├── Epic 5 (Adaptive Learning) ← also depends on Epic 3
  │     │     └── Epic 7 (Metrics & Dashboard) ← also depends on Epic 1, Epic 3
  │     └── Epic 6 (Distribution)
  ├── Epic 2 (Knowledge & Docs)     ← can parallel with Epic 1
  └── Epic 3 (Expert System)         ← can parallel with Epic 1, Epic 2
```

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
| `tapps_feedback` | Epic 7 | Week 12-15 |
| `tapps_stats` | Epic 7 | Week 12-15 |
| `tapps_dashboard` | Epic 7 | Week 14-18 |

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
