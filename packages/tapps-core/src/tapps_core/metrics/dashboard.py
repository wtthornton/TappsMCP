"""Dashboard generation for metrics visualization.

Generates dashboards in JSON, Markdown, and HTML formats from
collected metrics data.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from datetime import datetime

    from tapps_core.memory.store import MemoryStore

from tapps_core.common.utils import utc_now
from tapps_core.metrics.alerts import AlertManager
from tapps_core.metrics.confidence_metrics import ConfidenceMetricsTracker
from tapps_core.metrics.execution_metrics import ToolCallMetricsCollector
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
        confidence_tracker: ConfidenceMetricsTracker | None = None,
        rag_tracker: RAGMetricsTracker | None = None,
        memory_store: MemoryStore | None = None,
        # Deprecated params kept for backward compat — ignored
        expert_tracker: object | None = None,
        business_collector: object | None = None,
    ) -> None:
        self._metrics_dir = metrics_dir
        self._dashboard_dir = metrics_dir.parent / "dashboard"
        self._dashboard_dir.mkdir(parents=True, exist_ok=True)

        self._execution = execution_collector or ToolCallMetricsCollector(metrics_dir)
        self._outcomes = outcome_tracker or OutcomeTracker(metrics_dir)
        self._confidence = confidence_tracker or ConfidenceMetricsTracker(metrics_dir)
        self._rag = rag_tracker or RAGMetricsTracker(metrics_dir)
        self._memory_store = memory_store
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
            "memory_metrics",
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
            "memory_metrics": self._build_memory_metrics,
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

        self._render_md_summary(json_data, lines)
        self._render_md_tool_metrics(json_data, lines)
        self._render_md_alerts(json_data, lines)
        self._render_md_provider_stats(json_data, lines)
        self._render_md_coverage_metrics(json_data, lines)
        self._render_md_memory_metrics(json_data, lines)
        self._render_md_recommendations(json_data, lines)

        return "\n".join(lines)

    def _render_md_summary(self, json_data: dict[str, Any], lines: list[str]) -> None:
        """Append summary section lines to *lines*."""
        if "summary" not in json_data:
            return
        summary = json_data["summary"]
        lines.append("## Summary")
        lines.append(f"- Total tool calls: {summary.get('total_tool_calls', 0)}")
        lines.append(f"- Gate pass rate: {summary.get('gate_pass_rate', 0):.1%}")
        lines.append(f"- Average score: {summary.get('avg_score', 0):.1f}")
        lines.append(f"- Cache hit rate: {summary.get('cache_hit_rate', 0):.1%}")
        lines.append(f"- Expert confidence avg: {summary.get('expert_confidence_avg', 0):.2f}")
        lines.append(f"- Active alerts: {summary.get('active_alerts', 0)}")
        lines.append("")

    def _render_md_tool_metrics(self, json_data: dict[str, Any], lines: list[str]) -> None:
        """Append tool metrics bar-chart section lines to *lines*."""
        if "tool_metrics" not in json_data:
            return
        tool_data = json_data["tool_metrics"]
        if tool_data:
            chart_data = {t["tool_name"]: float(t["call_count"]) for t in tool_data}
            chart = self._visualizer.create_bar_chart(chart_data, title="## Tool Usage")
            lines.append(chart)
            lines.append("")

    def _render_md_alerts(self, json_data: dict[str, Any], lines: list[str]) -> None:
        """Append active alerts section lines to *lines*."""
        if "alerts" not in json_data:
            return
        alerts = json_data["alerts"]
        if not alerts:
            return
        lines.append("## Active Alerts")
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            severity = str(alert.get("severity", "info")).upper()
            lines.append(f"- [{severity}] {alert.get('message', '')}")
        lines.append("")

    def _render_md_provider_stats(self, json_data: dict[str, Any], lines: list[str]) -> None:
        """Append provider stats section lines to *lines*."""
        if "provider_stats" not in json_data:
            return
        prov = json_data["provider_stats"]
        if not prov or not isinstance(prov, dict):
            return
        lines.append("## Documentation Provider Stats")
        for name, s in sorted(prov.items()):
            if isinstance(s, dict):
                calls = s.get("total_calls", 0)
                ok = s.get("total_successes", 0)
                healthy = s.get("is_healthy", True)
                lines.append(f"- **{name}**: calls={calls}, successes={ok}, healthy={healthy}")
        lines.append("")

    def _render_md_coverage_metrics(self, json_data: dict[str, Any], lines: list[str]) -> None:
        """Append coverage metrics section lines to *lines*."""
        if "coverage_metrics" not in json_data:
            return
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

    def _render_md_memory_metrics(self, json_data: dict[str, Any], lines: list[str]) -> None:
        """Append memory metrics section lines to *lines*."""
        if "memory_metrics" not in json_data:
            return
        mem = json_data["memory_metrics"]
        if not mem.get("available", False):
            return
        lines.append("## Memory Metrics")
        lines.append(f"- Total entries: {mem.get('total_entries', 0)}")
        by_tier = mem.get("by_tier", {})
        if by_tier:
            lines.append(
                f"- By tier: architectural={by_tier.get('architectural', 0)}, "
                f"pattern={by_tier.get('pattern', 0)}, "
                f"context={by_tier.get('context', 0)}"
            )
        lines.append(f"- Stale count: {mem.get('stale_count', 0)}")
        lines.append(f"- Avg confidence: {mem.get('avg_confidence', 0):.4f}")
        lines.append(f"- Capacity: {mem.get('capacity_pct', 0):.1f}%")
        if mem.get("consolidation_groups", 0) > 0:
            lines.append(
                f"- Consolidation: {mem.get('consolidated_count', 0)} groups, "
                f"{mem.get('source_entries_count', 0)} sources"
            )
        fed = mem.get("federation")
        if fed:
            lines.append(
                f"- Federation: registered={fed.get('hub_registered', False)}, "
                f"published={fed.get('published_count', 0)}, "
                f"synced={fed.get('synced_count', 0)}"
            )
        lines.append("")

    def _render_md_recommendations(self, json_data: dict[str, Any], lines: list[str]) -> None:
        """Append recommendations section lines to *lines*."""
        if "recommendations" not in json_data:
            return
        recs = json_data["recommendations"]
        if not recs:
            return
        lines.append("## Recommendations")
        for rec in recs:
            lines.append(f"- {rec}")
        lines.append("")

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
        self,
        *,
        since: datetime | None = None,
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
        self,
        *,
        since: datetime | None = None,
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
        self,
        *,
        since: datetime | None = None,
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
        return {"domains": {}, "note": "Expert system removed (EPIC-94)"}

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
        self,
        *,
        since: datetime | None = None,
    ) -> dict[str, int]:
        if since is not None:
            recent = self._execution.get_metrics(since=since)
        else:
            recent = self._execution.get_recent(limit=100)
        scores = [m.score for m in recent if m.score is not None]

        distribution: dict[str, int] = {
            "90-100": 0,
            "80-89": 0,
            "70-79": 0,
            "60-69": 0,
            "0-59": 0,
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

        scored_files, gated_files, scanned_files = self._collect_file_sets(recent, _norm)

        # Gate skip rate: files scored but never gated
        gate_skip_count = len(scored_files - gated_files) if scored_files else 0
        gate_skip_rate = gate_skip_count / len(scored_files) if scored_files else 0.0

        lookup_calls, checklist_calls = self._count_tool_calls(recent)

        # Tool usage counts
        all_tool_names = {m.tool_name for m in recent}
        core_tools = {
            "tapps_score_file",
            "tapps_quality_gate",
            "tapps_security_scan",
            "tapps_checklist",
        }

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

    @staticmethod
    def _collect_file_sets(
        recent: list[Any],
        norm: Callable[[str | None], str],
    ) -> tuple[set[str], set[str], set[str]]:
        """Return ``(scored_files, gated_files, scanned_files)`` from *recent* metrics."""
        scored_files = {
            norm(m.file_path)
            for m in recent
            if m.tool_name == "tapps_score_file" and m.file_path and norm(m.file_path)
        }
        gated_files = {
            norm(m.file_path)
            for m in recent
            if m.tool_name == "tapps_quality_gate" and m.file_path and norm(m.file_path)
        }
        scanned_files = {
            norm(m.file_path)
            for m in recent
            if m.tool_name == "tapps_security_scan" and m.file_path and norm(m.file_path)
        }
        return scored_files, gated_files, scanned_files

    @staticmethod
    def _count_tool_calls(recent: list[Any]) -> tuple[int, int]:
        """Return ``(lookup_calls, checklist_calls)`` counts from *recent* metrics."""
        lookup_calls = sum(1 for m in recent if m.tool_name == "tapps_lookup_docs")
        checklist_calls = sum(1 for m in recent if m.tool_name == "tapps_checklist")
        return lookup_calls, checklist_calls

    def _build_memory_metrics(self) -> dict[str, Any]:
        """Build memory subsystem metrics from live MemoryStore data.

        Epic 65.1: Adds consolidation stats (consolidated_count, source_entries_count,
        consolidation_groups) and optional federation subsection.
        """
        if self._memory_store is None:
            return {
                "available": False,
                "total_entries": 0,
                "by_tier": {},
                "by_scope": {},
                "stale_count": 0,
                "avg_confidence": 0.0,
                "capacity_pct": 0.0,
            }

        try:
            from tapps_core.config.settings import load_settings

            snapshot = self._memory_store.snapshot()
            entries = snapshot.entries

            by_tier: dict[str, int] = {
                "architectural": 0,
                "pattern": 0,
                "procedural": 0,  # Epic 65.11
                "context": 0,
            }
            by_scope: dict[str, int] = {"project": 0, "branch": 0, "session": 0}
            confidences: list[float] = []
            stale_count = 0

            for entry in entries:
                tier_val = entry.tier if isinstance(entry.tier, str) else entry.tier.value
                by_tier[tier_val] = by_tier.get(tier_val, 0) + 1

                scope_val = entry.scope if isinstance(entry.scope, str) else entry.scope.value
                by_scope[scope_val] = by_scope.get(scope_val, 0) + 1

                confidences.append(entry.confidence)

                if entry.contradicted:
                    stale_count += 1

            avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

            settings = load_settings()
            max_memories = settings.memory.max_memories
            capacity_pct = round((snapshot.total_count / max_memories) * 100, 1)

            result: dict[str, Any] = {
                "available": True,
                "total_entries": snapshot.total_count,
                "by_tier": by_tier,
                "by_scope": by_scope,
                "stale_count": stale_count,
                "avg_confidence": avg_confidence,
                "capacity_pct": capacity_pct,
            }

            # Epic 65.1: Consolidation stats
            result.update(self._compute_consolidation_stats(entries))

            # Epic 65.1: Federation stats (optional, when federation available)
            fed = self._build_federation_stats(settings.project_root, entries)
            if fed:
                result["federation"] = fed

            return result
        except Exception:
            logger.debug("memory_metrics_build_failed", exc_info=True)
            return {
                "available": False,
                "total_entries": 0,
                "by_tier": {},
                "by_scope": {},
                "stale_count": 0,
                "avg_confidence": 0.0,
                "capacity_pct": 0.0,
            }

    @staticmethod
    def _compute_consolidation_stats(entries: list[Any]) -> dict[str, int]:
        """Compute consolidation stats from entries (Epic 65.1).

        - source_entries_count: entries with contradiction_reason containing
          'consolidated into'
        - consolidated_count / consolidation_groups: unique target keys from
          those source entries (each target = one consolidated entry / group).
        """
        source_entries = [
            e for e in entries if (e.contradiction_reason or "").find("consolidated into") >= 0
        ]
        source_entries_count = len(source_entries)

        consolidated_keys: set[str] = set()
        for e in source_entries:
            reason = (e.contradiction_reason or "").strip()
            idx = reason.lower().find("consolidated into")
            if idx >= 0:
                rest = reason[idx + len("consolidated into") :].strip()
                if rest:
                    key = rest.split()[0] if rest.split() else rest
                    consolidated_keys.add(key)

        # Also count entries with is_consolidated=True (ConsolidatedEntry)
        for e in entries:
            if getattr(e, "is_consolidated", False):
                consolidated_keys.add(e.key)

        consolidated_count = len(consolidated_keys)
        consolidation_groups = consolidated_count

        return {
            "consolidated_count": consolidated_count,
            "source_entries_count": source_entries_count,
            "consolidation_groups": consolidation_groups,
        }

    def _build_federation_stats(
        self, project_root: Path, entries: list[Any]
    ) -> dict[str, Any] | None:
        """Build federation subsection when federation is available (Epic 65.1)."""
        try:
            from tapps_core.memory.federation import (
                FederatedStore,
                load_federation_config,
            )

            config = load_federation_config()
            project_root_str = str(project_root)

            # Find if this project is registered
            matching = next(
                (p for p in config.projects if p.project_root == project_root_str),
                None,
            )
            hub_registered = matching is not None
            project_id = matching.project_id if matching else ""

            if not hub_registered:
                return {
                    "hub_registered": False,
                    "published_count": 0,
                    "subscribed_projects": 0,
                    "synced_count": 0,
                }

            hub = FederatedStore()
            try:
                stats = hub.get_stats()
                projects_counts = stats.get("projects", {})
                published_count = projects_counts.get(project_id, 0)
            finally:
                hub.close()

            subs = [s for s in config.subscriptions if s.subscriber == project_id]
            if subs:
                sub = subs[0]
                subscribed_projects = (
                    len(sub.sources) if sub.sources else max(0, len(config.projects) - 1)
                )
            else:
                subscribed_projects = 0

            synced_count = sum(1 for e in entries if "federated" in (e.tags or []))

            return {
                "hub_registered": True,
                "published_count": published_count,
                "subscribed_projects": subscribed_projects,
                "synced_count": synced_count,
            }
        except Exception:
            logger.debug("federation_stats_build_failed", exc_info=True)
            return None

    def _build_alerts(self) -> list[dict[str, Any]]:
        current_metrics = self._current_alert_metrics()
        alerts = self._alert_manager.check_alerts(current_metrics)
        return [a.to_dict() for a in alerts]

    def _build_business_metrics(self) -> dict[str, Any]:
        return {"note": "Business metrics removed (EPIC-94)"}

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

        # Memory capacity alert
        if self._memory_store is not None:
            try:
                from tapps_core.config.settings import load_settings as _load_settings

                mem_count = self._memory_store.count()
                mem_settings = _load_settings()
                max_mem = mem_settings.memory.max_memories
                if max_mem > 0:
                    metrics["memory_capacity_pct"] = mem_count / max_mem
            except (OSError, ValueError) as exc:
                logger.warning("metrics_memory_capacity_failed", error=str(exc))

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
