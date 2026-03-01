"""Integration tests for the metrics subsystem.

Tests end-to-end flows: tool call -> metric recording -> dashboard display.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest

from tapps_core.metrics.collector import MetricsHub


@pytest.fixture
def project_root(tmp_path):
    return tmp_path


@pytest.fixture
def hub(project_root):
    return MetricsHub(project_root)


class TestEndToEndMetrics:
    """Tests simulating a real workflow through metrics."""

    def test_tool_call_to_dashboard(self, hub):
        """Simulate tool calls and verify they appear in dashboard."""
        now = datetime.now(tz=UTC)

        # Simulate several tool calls
        hub.execution.record(
            "tapps_score_file",
            now,
            now + timedelta(milliseconds=100),
            status="success",
            score=80.0,
            gate_passed=True,
        )
        hub.execution.record(
            "tapps_quality_gate",
            now,
            now + timedelta(milliseconds=200),
            status="success",
            gate_passed=True,
        )
        hub.execution.record(
            "tapps_consult_expert",
            now,
            now + timedelta(milliseconds=50),
            status="success",
        )

        # Generate dashboard
        gen = hub.get_dashboard_generator()
        data = gen.generate_json_dashboard()

        assert data["summary"]["total_tool_calls"] == 3
        assert data["summary"]["gate_pass_rate"] > 0

    def test_outcome_tracking_flow(self, hub):
        """Simulate initial score -> iteration -> finalize."""
        hub.outcomes.track_initial_scores("s1", "/tmp/test.py", {"overall": 60.0})
        hub.outcomes.track_iteration("s1", "/tmp/test.py", {"overall": 75.0}, "security")
        hub.outcomes.finalize_outcome("s1", "/tmp/test.py", gate_passed=True)

        stats = hub.outcomes.get_statistics()
        assert stats["total_outcomes"] == 1
        assert "security" in stats["expert_usage"]

    def test_expert_consultation_flow(self, hub):
        """Simulate expert consultation with confidence tracking."""
        hub.experts.track_consultation("sec_expert", "security", 0.85, "test query")
        hub.confidence.record("security", 0.85, 0.6, agreement_level=0.9)
        hub.consultations.log_consultation(
            "sec_expert",
            "security",
            0.85,
            "Used OWASP patterns",
        )

        # Verify all trackers got the data
        perf = hub.experts.get_performance()
        assert len(perf) == 1

        conf_stats = hub.confidence.get_statistics()
        assert conf_stats.total_records == 1

        consult_stats = hub.consultations.get_statistics()
        assert consult_stats["total_consultations"] == 1

    def test_business_metrics_collection(self, hub):
        """Collect business metrics after populating other trackers."""
        now = datetime.now(tz=UTC)

        # Populate execution data
        for i in range(5):
            hub.execution.record(
                "tapps_score_file",
                now,
                now + timedelta(milliseconds=100),
                status="success" if i < 4 else "failed",
                score=70.0 + i * 5,
            )

        # Populate confidence data
        hub.confidence.record("security", 0.8, 0.6)

        # Collect business metrics
        biz = hub.business.collect()
        assert biz.adoption.total_consultations == 5
        assert biz.operational.error_rate > 0

    def test_full_dashboard_with_all_data(self, hub):
        """Generate a complete dashboard with data from all subsystems."""
        now = datetime.now(tz=UTC)

        # Execution data
        hub.execution.record(
            "tapps_score_file",
            now,
            now + timedelta(milliseconds=100),
            status="success",
            score=85.0,
            gate_passed=True,
        )

        # Expert data
        hub.experts.track_consultation("exp1", "security", 0.8)
        hub.confidence.record("security", 0.8, 0.6)
        hub.rag.record_query("test", "security", 20.0, 3, [0.8], True)

        # Generate all formats
        gen = hub.get_dashboard_generator()
        json_data = gen.generate_json_dashboard()
        md = gen.generate_markdown_dashboard()
        html = gen.generate_html_dashboard()

        assert json_data["summary"]["total_tool_calls"] == 1
        assert "# TappsMCP Dashboard" in md
        assert "<!DOCTYPE html>" in html


class TestThreadSafety:
    """Tests for concurrent metric writes."""

    def test_concurrent_execution_recording(self, hub):
        """Multiple threads recording metrics simultaneously."""
        errors = []

        def record_metrics(thread_id):
            try:
                now = datetime.now(tz=UTC)
                for i in range(20):
                    hub.execution.record(
                        f"tool_{thread_id}",
                        now,
                        now + timedelta(milliseconds=i),
                        session_id=f"thread_{thread_id}",
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_metrics, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        # Verify all records were written
        recent = hub.execution.get_recent(limit=100)
        assert len(recent) == 100

    def test_concurrent_confidence_recording(self, hub):
        """Multiple threads recording confidence metrics."""
        errors = []

        def record_confidence(thread_id):
            try:
                for i in range(10):
                    hub.confidence.record(
                        f"domain_{thread_id}",
                        0.5 + i * 0.05,
                        0.6,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_confidence, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_read_write(self, hub):
        """One thread writing while another reads."""
        errors = []
        stop = threading.Event()

        def writer():
            try:
                now = datetime.now(tz=UTC)
                for i in range(50):
                    if stop.is_set():
                        break
                    hub.execution.record(
                        "test_tool",
                        now,
                        now + timedelta(milliseconds=i),
                    )
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(10):
                    if stop.is_set():
                        break
                    hub.execution.get_recent(limit=10)
                    hub.execution.get_summary()
            except Exception as e:
                errors.append(e)

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)
        writer_thread.start()
        reader_thread.start()
        writer_thread.join()
        reader_thread.join()
        stop.set()

        assert len(errors) == 0
