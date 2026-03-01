"""Tests for the central metrics collector hub."""

from unittest.mock import patch

import pytest

from tapps_core.metrics.collector import (
    MetricsHub,
    get_metrics_hub,
    reset_metrics_hub,
)


@pytest.fixture
def project_root(tmp_path):
    return tmp_path


@pytest.fixture
def hub(project_root):
    return MetricsHub(project_root)


class TestMetricsHub:
    def test_creates_metrics_dir(self, hub, project_root):
        assert (project_root / ".tapps-mcp" / "metrics").is_dir()

    def test_has_all_trackers(self, hub):
        assert hub.execution is not None
        assert hub.outcomes is not None
        assert hub.experts is not None
        assert hub.confidence is not None
        assert hub.rag is not None
        assert hub.consultations is not None
        assert hub.business is not None

    def test_session_id(self, hub):
        assert len(hub.session_id) == 12

    def test_get_dashboard_generator(self, hub):
        gen = hub.get_dashboard_generator()
        assert gen is not None

    def test_metrics_dir_property(self, hub, project_root):
        assert hub.metrics_dir == project_root / ".tapps-mcp" / "metrics"


class TestGetMetricsHub:
    def test_singleton(self, tmp_path):
        reset_metrics_hub()
        with patch("tapps_core.config.settings.load_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            hub1 = get_metrics_hub()
            hub2 = get_metrics_hub()
            assert hub1 is hub2
        reset_metrics_hub()

    def test_reset(self, tmp_path):
        reset_metrics_hub()
        with patch("tapps_core.config.settings.load_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            hub1 = get_metrics_hub()
            reset_metrics_hub()
            hub2 = get_metrics_hub()
            assert hub1 is not hub2
        reset_metrics_hub()
