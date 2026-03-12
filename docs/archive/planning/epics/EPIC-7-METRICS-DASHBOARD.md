# Epic 7: Metrics, Observability & Dashboard

**Status:** Complete - 9 stories, 15 source files, 150 new tests (1102 total), 7 skipped
**Priority:** P1 — High Value (the user's primary way to review how TappsMCP is performing)
**Estimated LOE:** ~3-4 weeks (1 developer)
**Dependencies:** Epic 1 (Core Quality), Epic 3 (Expert System), Epic 5 (Adaptive Learning for outcome tracking)
**Blocks:** None (but enriches all other epics)

---

## Goal

Provide a comprehensive metrics, analytics, and dashboard system so the user can **review how well all metrics are performing** across TappsMCP — scoring accuracy, gate pass/fail rates, expert effectiveness, cache performance, quality trends, and business ROI. This epic carries over the full observability infrastructure from TappsCodingAgents (40+ files across analytics, dashboards, alerts, and tracking systems).

## Why This Epic Exists

TappsCodingAgents has a production-grade observability layer spanning:
- **AnalyticsDashboard** — agent/workflow/system metrics with trend analysis
- **ObservabilityDashboard** — correlated traces, metrics, logs with OpenTelemetry export
- **BusinessMetricsCollector** — adoption, effectiveness, ROI, operational metrics
- **OutcomeTracker** — correlates initial/final scores for adaptive learning
- **AnalyticsVisualizer** — ASCII charts for text-based dashboards
- **AnalyticsAlertManager** — threshold-based alerting
- **HealthDashboard** — system health status rendering
- **HTML Quality Dashboard** — Jinja2 template with CSS-styled metric cards
- **Execution/Confidence/RAG/Expert metrics trackers** — per-domain metric collection

Without this epic, the user has no way to answer: "Is TappsMCP actually improving my code quality? Are the experts useful? Are the gates too strict? Which tools are providing value?"

## LLM Error Sources Addressed

| Error Source | How Metrics Help |
|---|---|
| Inconsistent quality | Track gate pass/fail rates over time to detect regression |
| Self-review bias | Track initial vs. final scores — measure actual improvement |
| Wrong domain patterns | Track expert consultation accuracy — are domain suggestions helpful? |
| Hallucinated APIs | Track `tapps_lookup_docs` cache hit rates and doc freshness |

## 2026 Best Practices Applied

- **OpenTelemetry compatibility**: Export traces in OTEL format for integration with Grafana, Datadog, Honeycomb, etc. Don't build a proprietary format.
- **Local-first telemetry**: All metrics data stays on-machine by default. No data leaves unless explicitly exported. Privacy-respecting by design.
- **JSONL for audit logs**: Append-only JSONL files for high-volume metrics (execution logs, consultation history). Easy to `grep`, `jq`, or stream.
- **JSON for snapshots**: JSON files for last-N-records snapshots (confidence metrics, RAG metrics). Bounded memory usage.
- **MCP tool for dashboard access**: `tapps_dashboard` surfaces all metrics as structured JSON the LLM can interpret and report to the user.
- **Thread-safe writes**: All metric writers use `threading.Lock` or `asyncio.Lock` for concurrent access safety.
- **Configurable retention**: Default 90-day retention for JSONL files, configurable per metric type.

## Acceptance Criteria

- [x] `tapps_dashboard` MCP tool returns comprehensive metrics across all subsystems
- [x] `tapps_stats` MCP tool returns tool call counts, cache hit rates, gate pass/fail rates, avg scores
- [x] `tapps_feedback` MCP tool records user/LLM feedback for adaptive learning
- [x] Execution metrics track every MCP tool call with timing, status, and error info
- [x] Outcome tracker correlates initial scores with final scores for adaptive weight learning
- [x] Expert performance tracker measures consultation accuracy and domain coverage
- [x] Confidence metrics track expert agreement levels and threshold compliance
- [x] RAG metrics track retrieval precision, latency, cache hit rates, similarity distributions
- [x] Cache analytics track hit/miss rates per library with trend detection
- [x] Business metrics aggregate adoption, effectiveness, ROI, and operational health
- [x] Alert system detects when gate pass rates drop, scores regress, or cache hit rates fall
- [x] HTML quality dashboard generated with Jinja2 template (or JSON/Markdown fallback)
- [x] Historical trend analysis: improving / stable / degrading detection
- [x] OpenTelemetry trace export for external observability tools
- [x] All metrics persist to `{PROJECT_ROOT}/.tapps-mcp/metrics/` with configurable retention
- [x] Unit tests: 150 new tests covering all metric collectors, aggregators, and alerting (1102 total)

---

## Stories

### 7.1 — Execution Metrics Collector

**Points:** 5

Adapt `workflow/execution_metrics.py` for MCP tool call tracking.

**Source Files:**
- `C:\cursor\TappsCodingAgents\tapps_agents\workflow\execution_metrics.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\workflow\metrics_enhancements.py`

**Tasks:**
- Create `tapps_mcp/metrics/execution_metrics.py`:
  - `ToolCallMetric` dataclass:
    ```python
    @dataclass
    class ToolCallMetric:
        call_id: str
        tool_name: str           # tapps_score_file, tapps_quality_gate, etc.
        status: str              # success, failed, timeout, degraded
        duration_ms: float
        started_at: datetime
        completed_at: datetime
        file_path: str | None    # target file (if applicable)
        gate_passed: bool | None # for quality gate calls
        score: float | None      # for scoring calls
        error_code: str | None   # tool_unavailable, path_denied, etc.
        degraded: bool           # partial result due to missing tools
        session_id: str
    ```
  - `ToolCallMetricsCollector`:
    - `record_call()` — record every MCP tool invocation
    - `get_metrics()` — query with filters (tool_name, status, session, date range)
    - `get_summary()` — counts, success rates, avg duration by tool
    - `get_summary_by_tool()` — per-tool breakdown with gate pass rates
    - `cleanup_old_metrics(days_to_keep=90)` — retention management
  - Storage: `.tapps-mcp/metrics/tool_calls_YYYY-MM-DD.jsonl` (daily JSONL)
  - In-memory cache: last 100 calls (thread-safe with `_write_lock`)
  - Automatic recording: wrap all MCP tool handlers with metrics decorator

**Definition of Done:** Every MCP tool call is recorded with timing, status, and outcome. Queryable by tool, status, date range.

---

### 7.2 — Outcome Tracker

**Points:** 5

Adapt `core/outcome_tracker.py` for tracking code quality outcomes across MCP tool sessions.

**Source Files:**
- `C:\cursor\TappsCodingAgents\tapps_agents\core\outcome_tracker.py`

**Tasks:**
- Create `tapps_mcp/metrics/outcome_tracker.py`:
  - `CodeOutcome` dataclass:
    ```python
    @dataclass
    class CodeOutcome:
        session_id: str
        file_path: str
        initial_scores: dict[str, float]    # Scores from first tapps_score_file call
        final_scores: dict[str, float]      # Scores from last tapps_score_file call
        iterations: int                      # Number of score/gate cycles
        expert_consultations: list[str]      # Domains consulted
        time_to_quality: float               # Seconds from first score to gate pass
        first_pass_success: bool             # Did first scoring pass the gate?
        gate_preset: str                     # standard/strict/framework
        timestamp: datetime
    ```
  - `OutcomeTracker`:
    - `track_initial_scores()` — record first scoring of a file
    - `track_iteration()` — record subsequent re-scoring
    - `finalize_outcome()` — mark file as done (gate passed or abandoned)
    - `load_outcomes()` — query with filters
    - `get_learning_data()` — returns outcomes for adaptive scoring engine (min 10 required)
  - Storage: `.tapps-mcp/metrics/outcomes.jsonl`
  - Correlates with adaptive scoring in Epic 5

**Definition of Done:** Outcome tracker captures the full lifecycle of file quality improvement across MCP tool sessions.

---

### 7.3 — Expert & Confidence Metrics

**Points:** 5

Carry over expert performance tracking, confidence metrics, and RAG metrics from TappsCodingAgents.

**Source Files:**
- `C:\cursor\TappsCodingAgents\tapps_agents\experts\performance_tracker.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\experts\confidence_metrics.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\experts\rag_metrics.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\experts\history_logger.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\experts\observability.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\experts\business_metrics.py`

**Tasks:**
- Create `tapps_mcp/metrics/expert_metrics.py`:
  - `ExpertPerformance` dataclass — consultations, avg confidence, first-pass success, domain coverage, weaknesses
  - `ExpertPerformanceTracker` — correlates consultations with outcomes, identifies weak domains
  - Storage: `.tapps-mcp/metrics/expert_performance.jsonl`
- Create `tapps_mcp/metrics/confidence_metrics.py`:
  - `ConfidenceMetric` dataclass — domain, confidence, threshold, meets_threshold, agreement_level, num_experts
  - `ConfidenceMetricsTracker` — record, query, get_statistics (avg confidence, threshold meet rate)
  - Storage: `.tapps-mcp/metrics/confidence_metrics.json` (last 1000 records)
- Create `tapps_mcp/metrics/rag_metrics.py`:
  - `RAGQueryMetrics` — query, domain, latency_ms, num_results, similarity scores, cache_hit, backend_type
  - `RAGPerformanceMetrics` — aggregates by domain, backend (vector/simple), similarity buckets
  - `RAGMetricsTracker` — record_query, get_metrics (hit rate, avg latency, similarity distribution)
  - `RAGQueryTimer` — context manager for timing queries
  - Storage: `.tapps-mcp/metrics/rag_metrics.json` (last 100 queries)
- Create `tapps_mcp/metrics/consultation_logger.py`:
  - `ConsultationEntry` — expert_id, domain, confidence, reasoning, context_summary
  - `ConsultationLogger` — log_consultation, get_recent, get_by_expert, get_statistics, rotate(keep_recent=1000)
  - Storage: `.tapps-mcp/metrics/expert-history.jsonl`
- Create `tapps_mcp/metrics/expert_observability.py`:
  - `ObservabilitySystem` — correlates consultation, Context7, and RAG metrics
  - `identify_weak_areas(threshold)` — finds domains with low RAG quality
  - `generate_improvement_proposals()` — templates for knowledge base enhancement
  - Storage: `.tapps-mcp/metrics/weak_areas.json`, `improvement_proposals.json`

**Definition of Done:** Expert performance tracked end-to-end. Weak domains identified automatically. Confidence calibrated against outcomes.

---

### 7.4 — Business & Aggregate Metrics

**Points:** 5

Carry over business metrics collection and aggregation from TappsCodingAgents.

**Source Files:**
- `C:\cursor\TappsCodingAgents\tapps_agents\experts\business_metrics.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\core\analytics_dashboard.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\core\analytics_enhancements.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\agents\reviewer\aggregator.py`

**Tasks:**
- Create `tapps_mcp/metrics/business_metrics.py`:
  - `AdoptionMetrics` — total consultations, per-day rate, domain usage, tool usage percentages
  - `EffectivenessMetrics` — code quality improvements (before/after scores), bug prevention rate, time savings
  - `QualityMetrics` — avg confidence, confidence trend, agreement level, RAG quality, cache hit rate, avg latency
  - `ROIMetrics` — estimated time saved, cost per consultation, total value, ROI percentage
  - `OperationalMetrics` — cache hit rate, Context7 hit rate, error rate, KB size
  - `BusinessMetricsData` — combined snapshot of all business metrics
  - `BusinessMetricsCollector` — aggregates from all metric trackers into business metrics
  - Storage: `.tapps-mcp/metrics/business_metrics.json` with daily rollover
- Create `tapps_mcp/metrics/analytics_collector.py`:
  - `AnalyticsCollector` — central aggregation hub
  - `record_tool_call()` — feeds execution metrics
  - `record_outcome()` — feeds outcome tracker
  - `get_dashboard_data()` — comprehensive dashboard snapshot with all metrics + trends
  - Thread-safe aggregation with `threading.Lock`
- Create `tapps_mcp/metrics/quality_aggregator.py`:
  - `QualityAggregator` — aggregate scores across multiple files/services
  - `aggregate_scores()` — per-category averages, file counts, violation totals
  - `compare_files()` — rankings, best/worst by metric, range statistics
  - `generate_quality_report()` — combined aggregation + comparison

**Definition of Done:** Business metrics show adoption, effectiveness, ROI. Quality aggregation works across multi-file projects.

---

### 7.5 — Analytics Alerting & Trend Detection

**Points:** 3

Carry over analytics alerting and trend detection from TappsCodingAgents.

**Source Files:**
- `C:\cursor\TappsCodingAgents\tapps_agents\workflow\analytics_alerts.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\health\metrics.py` (trend calculation)

**Tasks:**
- Create `tapps_mcp/metrics/alerts.py`:
  - `AlertSeverity` enum — info, warning, critical
  - `AlertCondition` — metric_type, threshold, condition (above/below/change), severity, enabled
  - `Alert` — condition, current_value, threshold, message, timestamp, severity
  - `AlertManager`:
    - Default alert conditions:
      - Gate pass rate < 50% → warning
      - Gate pass rate < 25% → critical
      - Avg score dropping > 10% week-over-week → warning
      - Cache hit rate < 60% → warning
      - Expert confidence avg < 0.5 → warning
      - Tool call error rate > 20% → critical
    - `check_alerts()` — evaluate all conditions against current metrics
    - `get_active_alerts()` — return triggered alerts
    - Custom alert conditions via config
- Create `tapps_mcp/metrics/trends.py`:
  - `TrendData` — metric_name, timestamps[], values[], unit
  - `calculate_trend()` — returns improving / stable / degrading based on linear regression
  - `get_trend_for_metric()` — trend analysis for any metric over configurable time window
  - Support hourly, daily, weekly intervals

**Definition of Done:** Alerts fire when quality metrics degrade. Trends detected across all metric types.

---

### 7.6 — Dashboard & Visualization

**Points:** 5

Create the dashboard tools and visualization output.

**Source Files:**
- `C:\cursor\TappsCodingAgents\tapps_agents\core\analytics_dashboard.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\workflow\observability_dashboard.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\workflow\analytics_visualizer.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\dashboard\generator.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\dashboard\data_collector.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\health\dashboard.py`
- `C:\cursor\TappsCodingAgents\tapps_agents\agents\reviewer\templates\quality-dashboard.html.j2`
- `C:\cursor\TappsCodingAgents\tapps_agents\agents\reviewer\report_generator.py`

**Tasks:**
- Create `tapps_mcp/metrics/dashboard.py`:
  - `DashboardDataCollector` — gathers data from all metric trackers
  - `DashboardGenerator`:
    - `generate_json_dashboard()` — comprehensive JSON structure:
      ```json
      {
        "timestamp": "...",
        "summary": {
          "total_tool_calls": 247,
          "gate_pass_rate": 0.78,
          "avg_score": 76.3,
          "cache_hit_rate": 0.85,
          "expert_confidence_avg": 0.72,
          "active_alerts": 1
        },
        "tool_metrics": { ... per-tool breakdown ... },
        "scoring_trends": { ... 7-day trend data ... },
        "expert_metrics": { ... domain breakdown ... },
        "cache_metrics": { ... hit/miss by library ... },
        "quality_distribution": { ... score histogram ... },
        "alerts": [ ... active alerts ... ],
        "business_metrics": { ... adoption, ROI ... },
        "recommendations": [ ... improvement suggestions ... ]
      }
      ```
    - `generate_markdown_dashboard()` — text tables with ASCII charts
    - `generate_html_dashboard()` — styled HTML with metric cards (carry over Jinja2 template)
    - `save_dashboard()` — write to `.tapps-mcp/dashboard/`
  - Copy and adapt Jinja2 template from `quality-dashboard.html.j2`
- Create `tapps_mcp/metrics/visualizer.py`:
  - `AnalyticsVisualizer`:
    - `create_bar_chart()` — ASCII bar charts (Windows-compatible characters)
    - `create_line_chart()` — ASCII line/sparkline charts
    - `create_metric_comparison()` — side-by-side metric tables
    - Used by markdown dashboard and MCP tool responses

**Definition of Done:** Dashboard generates in JSON, Markdown, HTML formats. HTML dashboard has styled metric cards with trend indicators.

---

### 7.7 — Wire MCP Tools

**Points:** 5

Wire `tapps_dashboard`, `tapps_stats`, and `tapps_feedback` into the MCP server.

**Tasks:**
- Implement `tapps_dashboard` MCP tool:
  ```python
  @mcp.tool()
  async def tapps_dashboard(
      format: Annotated[str, Field(description="Output format")] = "json",
      time_range: Annotated[str, Field(description="Time range")] = "7d",
      sections: Annotated[list[str] | None, Field(description="Dashboard sections to include")] = None,
  ) -> dict:
      """Generate a comprehensive metrics dashboard. Call this to review how well
      TappsMCP is performing — scoring accuracy, gate pass rates, expert effectiveness,
      cache performance, quality trends, and alerts."""
  ```
  - Sections: `summary`, `tool_metrics`, `scoring_trends`, `expert_metrics`, `cache_metrics`, `quality_distribution`, `alerts`, `business_metrics`, `recommendations`
  - Supports `format`: json (default), markdown, html
  - Supports `time_range`: 1d, 7d, 30d, 90d
  - Returns active alerts inline
- Implement `tapps_stats` MCP tool:
  ```python
  @mcp.tool()
  async def tapps_stats(
      tool_name: Annotated[str | None, Field(description="Filter by tool")] = None,
      period: Annotated[str, Field(description="Stats period")] = "session",
  ) -> dict:
      """Return usage statistics for TappsMCP tools. Shows call counts, success rates,
      average durations, cache hit rates, and gate pass rates."""
  ```
  - `period`: session (current), 1d, 7d, 30d, all
  - Per-tool breakdown: call count, success rate, avg duration, p95 duration
  - Aggregate: total calls, overall success rate, gate pass rate, avg score
- Implement `tapps_feedback` MCP tool:
  ```python
  @mcp.tool()
  async def tapps_feedback(
      tool_name: Annotated[str, Field(description="Which tool to provide feedback on")],
      helpful: Annotated[bool, Field(description="Was the output helpful?")],
      context: Annotated[str | None, Field(description="Additional context")] = None,
  ) -> dict:
      """Report whether a tool's output was helpful. This feedback improves
      TappsMCP's adaptive scoring and expert weights over time."""
  ```
  - Records feedback with session ID, timestamp, tool name
  - Feeds into adaptive weight adjustment (Epic 5)
  - Returns acknowledgment with current feedback stats
- Automatic metrics recording:
  - Create a decorator/middleware that wraps all MCP tool handlers
  - Records `ToolCallMetric` for every tool invocation automatically
  - No manual instrumentation needed in each tool handler

**Definition of Done:** All three tools callable via MCP. Automatic metrics recording wraps all tool handlers. Dashboard shows real-time metrics.

---

### 7.8 — OpenTelemetry Export

**Points:** 3

Export trace data in OpenTelemetry format for external observability tools.

**Source Files:**
- `C:\cursor\TappsCodingAgents\tapps_agents\workflow\observability_dashboard.py` (export_otel_trace)

**Tasks:**
- Create `tapps_mcp/metrics/otel_export.py`:
  - `export_otel_trace()` — convert tool call metrics to OTEL `resourceSpans/scopeSpans` format
  - `export_to_file()` — write OTEL JSON to `.tapps-mcp/metrics/traces/`
  - Support OTLP HTTP endpoint export (optional, for users with Grafana/Datadog/etc.)
  - Include: tool name as span name, duration, status, attributes (file_path, score, gate_passed)
- Add `tapps_dashboard` export option:
  - `tapps_dashboard(format="otel")` returns OTEL-formatted trace data

**Definition of Done:** Metrics exportable in OTEL format. Users with external observability tools can ingest TappsMCP data.

---

### 7.9 — Tests

**Points:** 5

Comprehensive tests for all metrics infrastructure.

**Tasks:**
- Execution metrics tests (~10): recording, querying, filtering, retention cleanup
- Outcome tracker tests (~8): initial/iteration/finalize lifecycle, correlation with scores
- Expert metrics tests (~8): performance tracking, confidence calibration, RAG metrics
- Business metrics tests (~5): adoption, effectiveness, ROI calculation
- Alert tests (~5): threshold triggering, severity levels, custom conditions
- Trend tests (~5): improving/stable/degrading detection across time windows
- Dashboard tests (~5): JSON/Markdown/HTML generation, section filtering
- OTEL export tests (~3): valid OTEL format, attribute mapping
- Integration tests (~5): end-to-end tool call → metric recording → dashboard display
- Thread-safety tests (~3): concurrent metric writes, lock contention

**Definition of Done:** ~50+ tests pass. All metric collectors, aggregators, alerting, and dashboard generation tested.

---

## Code Extraction Map

### From TappsCodingAgents → TappsMCP

| Source File | Target File | Adaptation |
|---|---|---|
| `workflow/execution_metrics.py` | `tapps_mcp/metrics/execution_metrics.py` | Rewrite for MCP tool calls (not workflow steps) |
| `workflow/metrics_enhancements.py` | merge into above | Gate quality tracking |
| `core/outcome_tracker.py` | `tapps_mcp/metrics/outcome_tracker.py` | Adapt for MCP sessions |
| `experts/performance_tracker.py` | `tapps_mcp/metrics/expert_metrics.py` | Decouple from agent base |
| `experts/confidence_metrics.py` | `tapps_mcp/metrics/confidence_metrics.py` | Standalone |
| `experts/rag_metrics.py` | `tapps_mcp/metrics/rag_metrics.py` | Standalone |
| `experts/history_logger.py` | `tapps_mcp/metrics/consultation_logger.py` | Standalone |
| `experts/observability.py` | `tapps_mcp/metrics/expert_observability.py` | Decouple from agent context |
| `experts/business_metrics.py` | `tapps_mcp/metrics/business_metrics.py` | Decouple from ExpertEngine |
| `core/analytics_dashboard.py` | `tapps_mcp/metrics/analytics_collector.py` | Rewrite for MCP context |
| `core/analytics_enhancements.py` | merge into above | MetricsAggregator |
| `agents/reviewer/aggregator.py` | `tapps_mcp/metrics/quality_aggregator.py` | Standalone |
| `workflow/analytics_alerts.py` | `tapps_mcp/metrics/alerts.py` | Decouple from Cursor chat |
| `health/metrics.py` | `tapps_mcp/metrics/trends.py` | Standalone trend calc |
| `workflow/analytics_visualizer.py` | `tapps_mcp/metrics/visualizer.py` | Decouple from visual_feedback |
| `workflow/observability_dashboard.py` | `tapps_mcp/metrics/otel_export.py` | Extract OTEL export only |
| `dashboard/generator.py` | `tapps_mcp/metrics/dashboard.py` | Rewrite for MCP context |
| `dashboard/data_collector.py` | merge into above | Data collection |
| `health/dashboard.py` | merge into above | Health rendering |
| `agents/reviewer/report_generator.py` | `tapps_mcp/metrics/report_generator.py` | Already in Epic 1 — extend |
| `agents/reviewer/templates/quality-dashboard.html.j2` | `tapps_mcp/templates/quality-dashboard.html.j2` | Copy + adapt |

### What NOT to copy (framework-specific analytics)

| Source File | Why Not |
|---|---|
| `workflow/analytics_dual_write.py` | Cursor-specific dual-write pattern |
| `workflow/analytics_integration.py` | Cursor workflow integration |
| `workflow/analytics_accessor.py` | Cursor-specific data access |
| `workflow/analytics_dashboard_cursor.py` | Cursor-specific dashboard |
| `workflow/analytics_query_parser.py` | Cursor command parsing — MCP uses tool params instead |
| `core/resource_monitor.py` | System resource monitoring — optional, defer |
| `core/estimation_tracker.py` | Estimation accuracy — framework-specific |
| `agents/tester/performance_monitor.py` | Multi-agent parallelism — framework-specific |
| `core/learning_dashboard.py` | Learning effectiveness — needs full learning system |
| `core/meta_learning.py` | Meta-learning tracker — framework-specific |
| `core/learning_explainability.py` | Learning impact reporter — framework-specific |

---

## Data Persistence Layout

```
{TAPPS_MCP_PROJECT_ROOT}/.tapps-mcp/
├── metrics/
│   ├── tool_calls_YYYY-MM-DD.jsonl      # Daily tool call logs (90-day retention)
│   ├── outcomes.jsonl                     # Code quality outcomes (unlimited)
│   ├── expert_performance.jsonl           # Expert consultation tracking
│   ├── expert-history.jsonl               # Consultation history (rotatable, 1000 entries)
│   ├── confidence_metrics.json            # Last 1000 confidence records
│   ├── rag_metrics.json                   # Last 100 RAG query records
│   ├── business_metrics.json              # Business metrics snapshots
│   ├── weak_areas.json                    # Identified weak expert domains
│   ├── improvement_proposals.json         # KB improvement suggestions
│   ├── consultation_metrics.json          # Last 100 consultation records
│   ├── context7_metrics.json              # Last 100 Context7 KB records
│   └── traces/                            # OpenTelemetry trace exports
│       └── trace_YYYY-MM-DD.json
├── dashboard/
│   ├── dashboard.json                     # Latest dashboard snapshot
│   └── dashboard.html                     # Latest HTML dashboard
├── reports/
│   ├── quality/
│   │   ├── quality-report.json            # Latest quality report
│   │   └── historical/                    # Timestamped historical reports
│   └── weekly/
│       └── weekly-report-YYYY-WW.json     # Weekly summary reports
└── adaptive/
    ├── scoring_weights.json               # Learned scoring weights (Epic 5)
    └── expert_weights.json                # Expert voting weights (Epic 5)
```

---

## Performance Targets

| Tool | Target (p95) | Notes |
|---|---|---|
| `tapps_dashboard` (json) | < 500ms | Aggregation from in-memory + recent files |
| `tapps_dashboard` (html) | < 2s | Jinja2 template rendering |
| `tapps_stats` | < 100ms | In-memory aggregation |
| `tapps_feedback` | < 100ms | Write to local file |
| Metric recording (per call) | < 5ms | Non-blocking append to JSONL |
| Alert check | < 50ms | In-memory threshold comparison |

## Key Dependencies
- `jinja2` — HTML dashboard template rendering (optional, graceful degradation to JSON/Markdown)
- `structlog` — all metric recording uses structured logging
- No external observability services required (local-first)

## Optional Dependencies
- OTLP exporter library — for pushing to Grafana/Datadog/etc.
