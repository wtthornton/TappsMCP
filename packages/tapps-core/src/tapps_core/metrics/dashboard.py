"""Dashboard generation for metrics visualization.

Generates dashboards in JSON, Markdown, and HTML formats from
collected metrics data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from datetime import datetime

from tapps_core.common.utils import utc_now
from tapps_core.metrics.alerts import AlertManager
from tapps_core.metrics.business_metrics import BusinessMetricsCollector
from tapps_core.metrics.confidence_metrics import ConfidenceMetricsTracker
from tapps_core.metrics.execution_metrics import ToolCallMetricsCollector
from tapps_core.metrics.expert_metrics import ExpertPerformanceTracker
from tapps_core.metrics.outcome_tracker import OutcomeTracker
from tapps_core.metrics.rag_metrics import RAGMetricsTracker
from tapps_core.metrics.trends import calculate_trend
from tapps_core.metrics.visualizer import AnalyticsVisualizer

logger = structlog.get_logger(__name__)


class DashboardGenerator:
    """Generates metrics dashboards in multiple formats."""

    def __init__(
        self,
        metrics_dir: Path,
        execution_collector: ToolCallMetricsCollector | None = None,
        outcome_tracker: OutcomeTracker | None = None,
        expert_tracker: ExpertPerformanceTracker | None = None,
        confidence_tracker: ConfidenceMetricsTracker | None = None,
        rag_tracker: RAGMetricsTracker | None = None,
        business_collector: BusinessMetricsCollector | None = None,
    ) -> None:
        self._metrics_dir = metrics_dir
        self._dashboard_dir = metrics_dir.parent / "dashboard"
        self._dashboard_dir.mkdir(parents=True, exist_ok=True)

        self._execution = execution_collector or ToolCallMetricsCollector(metrics_dir)
        self._outcomes = outcome_tracker or OutcomeTracker(metrics_dir)
        self._experts = expert_tracker or ExpertPerformanceTracker(metrics_dir)
        self._confidence = confidence_tracker or ConfidenceMetricsTracker(metrics_dir)
        self._rag = rag_tracker or RAGMetricsTracker(metrics_dir)
        self._business = business_collector or BusinessMetricsCollector(
            metrics_dir,
            execution_collector=self._execution,
            outcome_tracker=self._outcomes,
            expert_tracker=self._experts,
            confidence_tracker=self._confidence,
            rag_tracker=self._rag,
        )
        self._alert_manager = AlertManager()
        self._visualizer = AnalyticsVisualizer()

    @staticmethod
    def _parse_time_range(time_range: str) -> datetime | None:
        """Parse a time_range string into a cutoff datetime, or None for 'all'."""
        from datetime import UTC, timedelta
        from datetime import datetime as dt

        days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
        days = days_map.get(time_range)
        if days is not None:
            return dt.now(tz=UTC) - timedelta(days=days)
        return None

    def generate_json_dashboard(
        self,
        sections: list[str] | None = None,
        *,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """Generate a comprehensive JSON dashboard.

        When *since* is provided, execution metrics are filtered to only
        include data recorded after that timestamp.
        """
        all_sections = sections or [
            "summary",
            "tool_metrics",
            "scoring_trends",
            "expert_metrics",
            "cache_metrics",
            "provider_stats",
            "quality_distribution",
            "coverage_metrics",
            "alerts",
            "business_metrics",
            "recommendations",
        ]

        data: dict[str, Any] = {"timestamp": utc_now().isoformat()}

        builders: dict[str, Any] = {
            "summary": lambda: self._build_summary(since=since),
            "tool_metrics": lambda: self._build_tool_metrics(since=since),
            "scoring_trends": lambda: self._build_scoring_trends(since=since),
            "expert_metrics": self._build_expert_metrics,
            "cache_metrics": self._build_cache_metrics,
            "provider_stats": self._build_provider_stats,
            "quality_distribution": lambda: self._build_quality_distribution(since=since),
            "coverage_metrics": self._build_coverage_metrics,
            "alerts": self._build_alerts,
            "business_metrics": self._build_business_metrics,
            "recommendations": self._build_recommendations,
        }

        for section in all_sections:
            builder = builders.get(section)
            if builder is not None:
                data[section] = builder()

        return data

    def generate_markdown_dashboard(
        self,
        sections: list[str] | None = None,
        *,
        since: datetime | None = None,
    ) -> str:
        """Generate a markdown-formatted dashboard."""
        json_data = self.generate_json_dashboard(sections, since=since)
        lines: list[str] = []

        lines.append("# TappsMCP Dashboard")
        lines.append(f"\nGenerated: {json_data.get('timestamp', '')}\n")

        # Summary
        if "summary" in json_data:
            summary = json_data["summary"]
            lines.append("## Summary")
            lines.append(f"- Total tool calls: {summary.get('total_tool_calls', 0)}")
            lines.append(f"- Gate pass rate: {summary.get('gate_pass_rate', 0):.1%}")
            lines.append(f"- Average score: {summary.get('avg_score', 0):.1f}")
            lines.append(f"- Cache hit rate: {summary.get('cache_hit_rate', 0):.1%}")
            lines.append(f"- Expert confidence avg: {summary.get('expert_confidence_avg', 0):.2f}")
            lines.append(f"- Active alerts: {summary.get('active_alerts', 0)}")
            lines.append("")

        # Tool metrics chart
        if "tool_metrics" in json_data:
            tool_data = json_data["tool_metrics"]
            if tool_data:
                chart_data = {t["tool_name"]: float(t["call_count"]) for t in tool_data}
                chart = self._visualizer.create_bar_chart(chart_data, title="## Tool Usage")
                lines.append(chart)
                lines.append("")

        # Alerts
        if "alerts" in json_data:
            alerts = json_data["alerts"]
            if alerts:
                lines.append("## Active Alerts")
                for alert in alerts:
                    if not isinstance(alert, dict):
                        continue
                    severity = str(alert.get("severity", "info")).upper()
                    lines.append(f"- [{severity}] {alert.get('message', '')}")
                lines.append("")

        # Provider stats
        if "provider_stats" in json_data:
            prov = json_data["provider_stats"]
            if prov and isinstance(prov, dict):
                lines.append("## Documentation Provider Stats")
                for name, s in sorted(prov.items()):
                    if isinstance(s, dict):
                        calls = s.get("total_calls", 0)
                        ok = s.get("total_successes", 0)
                        healthy = s.get("is_healthy", True)
                        lines.append(f"- **{name}**: calls={calls}, successes={ok}, healthy={healthy}")
                lines.append("")

        # Coverage metrics
        if "coverage_metrics" in json_data:
            cov = json_data["coverage_metrics"]
            lines.append("## Coverage Metrics")
            lines.append(f"- Files scored: {cov.get('files_scored', 0)}")
            lines.append(f"- Files gated: {cov.get('files_gated', 0)}")
            lines.append(f"- Files scanned: {cov.get('files_scanned', 0)}")
            lines.append(f"- Gate skip rate: {cov.get('gate_skip_rate', 0):.1%}")
            lines.append(f"- Docs lookup calls: {cov.get('docs_lookup_calls', 0)}")
            lines.append(f"- Checklist calls: {cov.get('checklist_calls', 0)}")
            unused = cov.get("core_tools_unused", [])
            if unused:
                lines.append(f"- Unused core tools: {', '.join(unused)}")
            lines.append("")

        # Recommendations
        if "recommendations" in json_data:
            recs = json_data["recommendations"]
            if recs:
                lines.append("## Recommendations")
                for rec in recs:
                    lines.append(f"- {rec}")
                lines.append("")

        return "\n".join(lines)

    def generate_html_dashboard(
        self,
        sections: list[str] | None = None,
        *,
        since: datetime | None = None,
    ) -> str:
        """Generate an HTML dashboard with styled metric cards.

        Falls back to a simple HTML rendering if Jinja2 is unavailable.
        """
        json_data = self.generate_json_dashboard(sections, since=since)
        return self._render_html(json_data)

    def save_dashboard(
        self,
        fmt: str = "json",
        sections: list[str] | None = None,
    ) -> Path:
        """Generate and save a dashboard to disk."""
        if fmt == "json":
            data = self.generate_json_dashboard(sections)
            path = self._dashboard_dir / "dashboard.json"
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        elif fmt == "markdown":
            content = self.generate_markdown_dashboard(sections)
            path = self._dashboard_dir / "dashboard.md"
            path.write_text(content, encoding="utf-8")
        elif fmt == "html":
            content = self.generate_html_dashboard(sections)
            path = self._dashboard_dir / "dashboard.html"
            path.write_text(content, encoding="utf-8")
        else:
            msg = f"Unsupported format: {fmt}"
            raise ValueError(msg)

        return path

    # -- Section builders --

    def _build_summary(
        self, *, since: datetime | None = None,
    ) -> dict[str, Any]:
        exec_summary = self._execution.get_summary(since=since)
        conf_stats = self._confidence.get_statistics()
        rag_metrics = self._rag.get_metrics()

        # Get alert count
        current_metrics = self._current_alert_metrics()
        alerts = self._alert_manager.check_alerts(current_metrics)

        return {
            "total_tool_calls": exec_summary.total_calls,
            "gate_pass_rate": exec_summary.gate_pass_rate or 0.0,
            "avg_score": exec_summary.avg_score or 0.0,
            "cache_hit_rate": rag_metrics.cache_hit_rate,
            "expert_confidence_avg": conf_stats.avg_confidence,
            "active_alerts": len(alerts),
            "success_rate": exec_summary.success_rate,
        }

    def _build_tool_metrics(
        self, *, since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        breakdowns = self._execution.get_summary_by_tool(since=since)
        return [
            {
                "tool_name": b.tool_name,
                "call_count": b.call_count,
                "success_rate": b.success_rate,
                "avg_duration_ms": b.avg_duration_ms,
                "p95_duration_ms": b.p95_duration_ms,
                "gate_pass_rate": b.gate_pass_rate,
                "avg_score": b.avg_score,
            }
            for b in breakdowns
        ]

    def _build_scoring_trends(
        self, *, since: datetime | None = None,
    ) -> dict[str, Any]:
        # Build trend from metrics (filtered by time range when provided)
        if since is not None:
            recent = self._execution.get_metrics(since=since)
        else:
            recent = self._execution.get_recent(limit=50)
        scores = [m.score for m in recent if m.score is not None]
        if scores:
            trend = calculate_trend("avg_score", scores)
            return trend.to_dict()
        return {"metric_name": "avg_score", "direction": "stable", "data_points": 0}

    def _build_expert_metrics(self) -> dict[str, Any]:
        domain_breakdown = self._experts.get_domain_breakdown()
        return {"domains": domain_breakdown}

    def _build_cache_metrics(self) -> dict[str, Any]:
        rag_metrics = self._rag.get_metrics()
        return {
            "total_queries": rag_metrics.total_queries,
            "cache_hit_rate": rag_metrics.cache_hit_rate,
            "avg_latency_ms": rag_metrics.avg_latency_ms,
            "by_domain": rag_metrics.by_domain,
        }

    def _build_provider_stats(self) -> dict[str, dict[str, object]]:
        """Per-provider stats from the documentation provider registry."""
        from tapps_core.config.settings import load_settings
        from tapps_core.knowledge.lookup import _build_provider_registry

        settings = load_settings()
        registry = _build_provider_registry(settings=settings)
        return registry.get_stats()

    @staticmethod
    def _normalize_file_path(file_path: str, project_root: Path | None) -> str:
        """Normalize file path for deduplication (Windows case/slash handling)."""
        if not file_path or not file_path.strip():
            return ""
        try:
            p = Path(file_path)
            if not p.is_absolute() and project_root is not None:
                p = (project_root / p).resolve()
            else:
                p = p.resolve()
            return str(p)
        except (OSError, RuntimeError):
            return file_path

    @staticmethod
    def _score_bin(score: float) -> str:
        """Map a score to its distribution bin label."""
        if score >= 90:
            return "90-100"
        if score >= 80:
            return "80-89"
        if score >= 70:
            return "70-79"
        if score >= 60:
            return "60-69"
        return "0-59"

    def _build_quality_distribution(
        self, *, since: datetime | None = None,
    ) -> dict[str, int]:
        if since is not None:
            recent = self._execution.get_metrics(since=since)
        else:
            recent = self._execution.get_recent(limit=100)
        scores = [m.score for m in recent if m.score is not None]

        distribution: dict[str, int] = {
            "90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "0-59": 0,
        }
        for s in scores:
            distribution[self._score_bin(s)] += 1

        return distribution

    def _build_coverage_metrics(self) -> dict[str, Any]:
        """Build tool coverage metrics - which files were scored/gated/scanned."""
        # Use disk data (not in-memory buffer) so metrics are correct after restart
        recent = self._execution.get_recent_from_disk(limit=500)

        # Derive project root for path normalization (project_root/.tapps-mcp/metrics)
        project_root = self._metrics_dir.parent.parent if self._metrics_dir else None

        def _norm(fp: str | None) -> str:
            return self._normalize_file_path(fp or "", project_root)

        scored_files = {
            _norm(m.file_path)
            for m in recent
            if m.tool_name == "tapps_score_file" and m.file_path and _norm(m.file_path)
        }
        gated_files = {
            _norm(m.file_path)
            for m in recent
            if m.tool_name == "tapps_quality_gate" and m.file_path and _norm(m.file_path)
        }
        scanned_files = {
            _norm(m.file_path)
            for m in recent
            if m.tool_name == "tapps_security_scan" and m.file_path and _norm(m.file_path)
        }

        # Gate skip rate: files scored but never gated
        gate_skip_count = len(scored_files - gated_files) if scored_files else 0
        gate_skip_rate = gate_skip_count / len(scored_files) if scored_files else 0.0

        # Tool usage counts
        all_tool_names = {m.tool_name for m in recent}
        core_tools = {
            "tapps_score_file",
            "tapps_quality_gate",
            "tapps_security_scan",
            "tapps_checklist",
        }

        lookup_calls = sum(1 for m in recent if m.tool_name == "tapps_lookup_docs")
        checklist_calls = sum(1 for m in recent if m.tool_name == "tapps_checklist")

        return {
            "files_scored": len(scored_files),
            "files_gated": len(gated_files),
            "files_scanned": len(scanned_files),
            "gate_skip_rate": round(gate_skip_rate, 3),
            "gate_skip_count": gate_skip_count,
            "docs_lookup_calls": lookup_calls,
            "checklist_calls": checklist_calls,
            "core_tools_used": sorted(core_tools & all_tool_names),
            "core_tools_unused": sorted(core_tools - all_tool_names),
        }

    def _build_alerts(self) -> list[dict[str, Any]]:
        current_metrics = self._current_alert_metrics()
        alerts = self._alert_manager.check_alerts(current_metrics)
        return [a.to_dict() for a in alerts]

    def _build_business_metrics(self) -> dict[str, Any]:
        biz = self._business.collect()
        return biz.to_dict()

    def _build_recommendations(self) -> list[str]:
        recommendations: list[str] = []
        exec_summary = self._execution.get_summary()

        if exec_summary.total_calls == 0:
            recommendations.append("Start using TappsMCP tools to begin collecting metrics.")
            return recommendations

        if exec_summary.success_rate < 0.9:
            recommendations.append(
                f"Success rate is {exec_summary.success_rate:.0%}. "
                "Check tool configurations and error logs."
            )

        if exec_summary.gate_pass_rate is not None and exec_summary.gate_pass_rate < 0.5:
            recommendations.append(
                f"Gate pass rate is {exec_summary.gate_pass_rate:.0%}. "
                "Consider running tapps_score_file(quick=True, fix=True) before gating."
            )

        rag_metrics = self._rag.get_metrics()
        if rag_metrics.cache_hit_rate < 0.5 and rag_metrics.total_queries > 5:
            recommendations.append(
                "RAG cache hit rate is low. Consider pre-warming the cache with common libraries."
            )

        if not recommendations:
            recommendations.append("All metrics look healthy. Keep up the good work!")

        return recommendations

    def _current_alert_metrics(self) -> dict[str, float]:
        """Build the current metrics dict for alert evaluation.

        Only includes metrics that have sufficient data behind them to
        avoid false alerts on fresh sessions with zero data points.
        """
        exec_summary = self._execution.get_summary()
        conf_stats = self._confidence.get_statistics()
        rag_metrics = self._rag.get_metrics()

        metrics: dict[str, float] = {}

        # Only alert on rates when there are actual tool calls
        if exec_summary.total_calls > 0:
            metrics["success_rate"] = exec_summary.success_rate
            metrics["error_rate"] = exec_summary.failed_count / exec_summary.total_calls

        if exec_summary.gate_pass_rate is not None:
            metrics["gate_pass_rate"] = exec_summary.gate_pass_rate

        # Only alert on cache hit rate when there have been RAG queries
        if rag_metrics.total_queries > 0:
            metrics["cache_hit_rate"] = rag_metrics.cache_hit_rate

        # Only alert on confidence when there are confidence records
        if conf_stats.total_records > 0:
            metrics["avg_confidence"] = conf_stats.avg_confidence

        return metrics

    @staticmethod
    def _render_html(data: dict[str, Any]) -> str:
        """Render a simple HTML dashboard."""
        summary = data.get("summary", {})
        alerts = data.get("alerts", [])
        tool_metrics = data.get("tool_metrics", [])
        recommendations = data.get("recommendations", [])
        if not isinstance(alerts, list):
            alerts = []
        if not isinstance(tool_metrics, list):
            tool_metrics = []
        if not isinstance(recommendations, list):
            recommendations = []

        severity_colors = {"critical": "#dc3545", "warning": "#ffc107", "info": "#17a2b8"}
        alert_parts = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            color = severity_colors.get(str(alert.get("severity", "info")), "#17a2b8")
            alert_parts.append(
                f'<div style="background:{color};color:#fff;padding:8px;'
                f'margin:4px 0;border-radius:4px">'
                f"{alert.get('message', '')}</div>"
            )
        alert_html = "".join(alert_parts)

        tool_rows = "".join(
            (
                f"<tr><td>{t.get('tool_name', '')}</td>"
                f"<td>{t.get('call_count', 0)}</td>"
                f"<td>{t.get('success_rate', 0):.0%}</td>"
                f"<td>{t.get('avg_duration_ms', 0):.0f}ms</td></tr>"
            )
            for t in tool_metrics
            if isinstance(t, dict)
        )

        rec_html = "".join(f"<li>{r}</li>" for r in recommendations)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TappsMCP Dashboard</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 900px; margin: 40px auto; padding: 0 20px; color: #333; }}
h1 {{ color: #2c3e50; }}
.card {{ background: #f8f9fa; border-radius: 8px; padding: 16px;
         margin: 12px 0; display: inline-block; min-width: 140px;
         text-align: center; }}
.card .value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
.card .label {{ font-size: 12px; color: #666; margin-top: 4px; }}
table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f1f1f1; }}
</style>
</head>
<body>
<h1>TappsMCP Dashboard</h1>
<p>Generated: {data.get("timestamp", "")}</p>

<div>
<div class="card">
  <div class="value">{summary.get("total_tool_calls", 0)}</div>
  <div class="label">Total Calls</div>
</div>
<div class="card">
  <div class="value">{summary.get("gate_pass_rate", 0):.0%}</div>
  <div class="label">Gate Pass Rate</div>
</div>
<div class="card">
  <div class="value">{summary.get("avg_score", 0):.1f}</div>
  <div class="label">Avg Score</div>
</div>
<div class="card">
  <div class="value">{summary.get("cache_hit_rate", 0):.0%}</div>
  <div class="label">Cache Hit Rate</div>
</div>
<div class="card">
  <div class="value">{summary.get("active_alerts", 0)}</div>
  <div class="label">Active Alerts</div>
</div>
</div>

{f"<h2>Alerts</h2>{alert_html}" if alerts else ""}

<h2>Tool Metrics</h2>
<table>
<tr><th>Tool</th><th>Calls</th><th>Success Rate</th><th>Avg Duration</th></tr>
{tool_rows}
</table>

{f"<h2>Recommendations</h2><ul>{rec_html}</ul>" if recommendations else ""}

</body>
</html>"""
