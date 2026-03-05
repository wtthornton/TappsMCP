"""Tests for dashboard memory_metrics and session_start enrichment (Epic 55, Stories 2-3)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_core.metrics.dashboard import DashboardGenerator


@pytest.fixture()
def metrics_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".tapps-mcp" / "metrics"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def memory_store(tmp_path: Path):
    """Create a real MemoryStore with some test data."""
    from tapps_core.memory.store import MemoryStore

    store = MemoryStore(tmp_path / "memory")
    store.save(key="arch-1", value="Architecture decision", tier="architectural")
    store.save(key="pat-1", value="Pattern one", tier="pattern")
    store.save(key="pat-2", value="Pattern two", tier="pattern")
    store.save(key="ctx-1", value="Context entry", tier="context")
    return store


@pytest.fixture()
def generator_with_memory(metrics_dir: Path, memory_store) -> DashboardGenerator:
    return DashboardGenerator(metrics_dir, memory_store=memory_store)


@pytest.fixture()
def generator_no_memory(metrics_dir: Path) -> DashboardGenerator:
    return DashboardGenerator(metrics_dir)


class TestDashboardMemoryMetrics:
    def test_dashboard_includes_memory_metrics(
        self, generator_with_memory: DashboardGenerator,
    ) -> None:
        data = generator_with_memory.generate_json_dashboard()
        assert "memory_metrics" in data

    def test_dashboard_memory_metrics_shape(
        self, generator_with_memory: DashboardGenerator,
    ) -> None:
        data = generator_with_memory.generate_json_dashboard(
            sections=["memory_metrics"],
        )
        mem = data["memory_metrics"]
        assert mem["available"] is True
        assert mem["total_entries"] == 4
        assert mem["by_tier"]["architectural"] == 1
        assert mem["by_tier"]["pattern"] == 2
        assert mem["by_tier"]["context"] == 1
        assert "avg_confidence" in mem
        assert "capacity_pct" in mem
        assert isinstance(mem["capacity_pct"], float)
        assert mem["stale_count"] >= 0

    def test_dashboard_memory_alert_high_capacity(
        self, metrics_dir: Path, tmp_path: Path,
    ) -> None:
        """Verify alert fires when memory capacity > 80%."""
        from tapps_core.memory.store import MemoryStore

        store = MemoryStore(tmp_path / "mem_alert")
        # Save enough entries to exceed 80% of a small max_memories
        for i in range(45):
            store.save(key=f"k{i}", value=f"v{i}")

        gen = DashboardGenerator(metrics_dir, memory_store=store)

        # Mock max_memories to 50 so 45/50 = 90% > 80%
        mock_settings = MagicMock()
        mock_settings.memory.max_memories = 50

        with patch(
            "tapps_core.config.settings.load_settings",
            return_value=mock_settings,
        ):
            data = gen.generate_json_dashboard(sections=["alerts", "memory_metrics"])

        alerts = data.get("alerts", [])
        memory_alerts = [
            a for a in alerts
            if isinstance(a, dict) and a.get("metric_type") == "memory_capacity_pct"
        ]
        assert len(memory_alerts) >= 1

    def test_dashboard_memory_empty_store(
        self, generator_no_memory: DashboardGenerator,
    ) -> None:
        data = generator_no_memory.generate_json_dashboard(
            sections=["memory_metrics"],
        )
        mem = data["memory_metrics"]
        assert mem["available"] is False
        assert mem["total_entries"] == 0

    def test_dashboard_memory_in_markdown(
        self, generator_with_memory: DashboardGenerator,
    ) -> None:
        md = generator_with_memory.generate_markdown_dashboard(
            sections=["memory_metrics"],
        )
        assert "## Memory Metrics" in md
        assert "Total entries:" in md

    def test_dashboard_memory_metrics_default_sections(
        self, generator_with_memory: DashboardGenerator,
    ) -> None:
        """memory_metrics should be in the default sections list."""
        data = generator_with_memory.generate_json_dashboard()
        assert "memory_metrics" in data


@pytest.mark.asyncio()
class TestSessionStartEnrichedMemory:
    """Tests for enriched memory_status in tapps_session_start (Story 55.3)."""

    async def test_session_start_enriched_memory_stats(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        mock_entry_arch = MagicMock()
        mock_entry_arch.tier = "architectural"
        mock_entry_arch.scope = "project"
        mock_entry_arch.confidence = 0.9
        mock_entry_arch.contradicted = False

        mock_entry_pat = MagicMock()
        mock_entry_pat.tier = "pattern"
        mock_entry_pat.scope = "project"
        mock_entry_pat.confidence = 0.7
        mock_entry_pat.contradicted = False

        mock_entry_ctx = MagicMock()
        mock_entry_ctx.tier = "context"
        mock_entry_ctx.scope = "session"
        mock_entry_ctx.confidence = 0.5
        mock_entry_ctx.contradicted = True

        mock_store = MagicMock()
        snapshot = MagicMock()
        snapshot.total_count = 3
        snapshot.entries = [mock_entry_arch, mock_entry_pat, mock_entry_ctx]
        mock_store.snapshot.return_value = snapshot
        mock_store.count.return_value = 3

        mock_settings = MagicMock()
        mock_settings.memory.enabled = True
        mock_settings.memory.gc_enabled = False
        mock_settings.memory.max_memories = 500
        mock_settings.memory.gc_auto_threshold = 0.8
        mock_settings.business_experts_enabled = False

        with (
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings",
                return_value=mock_settings,
            ),
            patch(
                "tapps_mcp.server_helpers._get_memory_store",
                return_value=mock_store,
            ),
        ):
            result = await tapps_session_start()

        data = result["data"]
        mem = data["memory_status"]

        # Existing fields still present
        assert mem["enabled"] is True
        assert mem["total"] == 3
        assert mem["contradicted"] == 1

        # New enriched fields
        assert mem["by_tier"]["architectural"] == 1
        assert mem["by_tier"]["pattern"] == 1
        assert mem["by_tier"]["context"] == 1
        assert abs(mem["avg_confidence"] - 0.7) < 0.01
        assert mem["capacity_pct"] == 0.6  # 3/500 * 100
