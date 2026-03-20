"""Integration test: end-to-end config validation pipeline.

Tests the full validation flow: file creation → auto-detection → validation
→ findings + suggestions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tapps_mcp.validators.base import detect_config_type, validate_config


@pytest.mark.integration
@pytest.mark.slow
class TestDockerfilePipeline:
    """End-to-end Dockerfile validation."""

    def test_good_dockerfile(self, tmp_path: Path):
        content = (
            "FROM python:3.12-slim\n"
            "USER appuser\n"
            "HEALTHCHECK CMD curl -f http://localhost/\n"
            "COPY . /app\n"
            'CMD ["python", "app.py"]\n'
        )
        result = validate_config("Dockerfile", content)

        assert result.config_type == "dockerfile"
        assert result.valid is True
        assert all(f.severity != "critical" for f in result.findings)

    def test_insecure_dockerfile(self, tmp_path: Path):
        content = (
            "FROM python:latest\n"
            "ENV DATABASE_PASSWORD=secret123\n"
            "RUN apt-get update && apt-get install -y curl\n"
            "COPY . /app\n"
        )
        result = validate_config("Dockerfile", content)

        assert result.config_type == "dockerfile"
        # Should have critical findings for secrets + warnings for :latest
        criticals = [f for f in result.findings if f.severity == "critical"]
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert len(criticals) > 0
        assert len(warnings) > 0
        # USER is a finding (warning), HEALTHCHECK is a suggestion
        assert any("USER" in f.message for f in result.findings)
        assert any("HEALTHCHECK" in s for s in result.suggestions)


@pytest.mark.integration
@pytest.mark.slow
class TestDockerComposePipeline:
    """End-to-end docker-compose validation."""

    def test_good_compose(self):
        content = (
            "services:\n"
            "  web:\n"
            "    image: nginx:1.25\n"
            "    healthcheck:\n"
            "      test: curl -f http://localhost/\n"
            "    deploy:\n"
            "      resources:\n"
            "        limits:\n"
            "          memory: 512M\n"
            "  db:\n"
            "    image: postgres:16\n"
            "    healthcheck:\n"
            "      test: pg_isready\n"
            "    deploy:\n"
            "      resources:\n"
            "        limits:\n"
            "          memory: 1G\n"
            "networks:\n"
            "  default:\n"
        )
        result = validate_config("docker-compose.yml", content)

        assert result.config_type == "docker_compose"
        assert result.valid is True

    def test_bad_compose_yaml(self):
        result = validate_config("docker-compose.yml", "{{invalid yaml")

        assert result.valid is False
        assert any(f.severity == "critical" for f in result.findings)

    def test_compose_missing_healthcheck(self):
        content = "services:\n  web:\n    image: nginx\n"
        result = validate_config("docker-compose.yml", content)

        assert any("healthcheck" in s.lower() for s in result.suggestions)


@pytest.mark.integration
@pytest.mark.slow
class TestAutoDetection:
    """Auto-detection from filename and content."""

    def test_detects_dockerfile(self):
        assert detect_config_type("Dockerfile") == "dockerfile"
        assert detect_config_type("Dockerfile.prod") == "dockerfile"

    def test_detects_compose(self):
        assert detect_config_type("docker-compose.yml") == "docker_compose"
        assert detect_config_type("compose.yaml") == "docker_compose"

    def test_detects_websocket_from_content(self):
        content = "async with websockets.connect('ws://host') as ws:"
        assert detect_config_type("client.py", content) == "websocket"

    def test_detects_mqtt_from_content(self):
        content = "import paho.mqtt.client as mqtt\nclient = mqtt.Client()"
        assert detect_config_type("sensor.py", content) == "mqtt"

    def test_detects_influxdb_from_content(self):
        content = "client = InfluxDBClient(url='http://localhost:8086')"
        assert detect_config_type("metrics.py", content) == "influxdb"

    def test_unknown_returns_none(self):
        assert detect_config_type("README.md") is None


@pytest.mark.integration
@pytest.mark.slow
class TestWebSocketValidationPipeline:
    """End-to-end WebSocket config validation."""

    def test_websocket_with_issues(self):
        content = (
            "import websockets\n"
            "async with websockets.connect('ws://localhost') as ws:\n"
            "    data = await ws.recv()\n"
        )
        result = validate_config("client.py", content, config_type="websocket")

        assert result.config_type == "websocket"
        # Should flag missing reconnection logic
        reconnect_findings = [f for f in result.findings if "reconnect" in f.message.lower()]
        assert len(reconnect_findings) > 0


@pytest.mark.integration
@pytest.mark.slow
class TestMQTTValidationPipeline:
    """End-to-end MQTT config validation."""

    def test_mqtt_with_issues(self):
        content = (
            "import paho.mqtt.client as mqtt\n"
            "client = mqtt.Client()\n"
            "client.subscribe('sensors/#')\n"
        )
        result = validate_config("sensor.py", content, config_type="mqtt")

        assert result.config_type == "mqtt"
        # Should flag missing on_connect callback and wildcard
        has_callback = any("on_connect" in f.message for f in result.findings)
        has_wildcard = any("wildcard" in f.message.lower() for f in result.findings)
        assert has_callback
        assert has_wildcard


@pytest.mark.integration
@pytest.mark.slow
class TestInfluxDBValidationPipeline:
    """End-to-end InfluxDB config validation."""

    def test_influxdb_query_issues(self):
        content = (
            "from influxdb_client import InfluxDBClient\n"
            "client = InfluxDBClient(url='http://localhost:8086')\n"
            'query = \'from(bucket: "metrics") |> filter(fn: (r) => r._measurement == "cpu")\'\n'
        )
        result = validate_config("query.py", content, config_type="influxdb")

        assert result.config_type == "influxdb"
        # Should flag missing range and suggest context manager
        has_range = any("range" in f.message.lower() for f in result.findings)
        has_ctx = any("context manager" in f.message.lower() for f in result.findings)
        assert has_range
        assert has_ctx


@pytest.mark.integration
@pytest.mark.slow
class TestUnknownConfigType:
    """Unknown config types pass through cleanly."""

    def test_unknown_type_valid(self):
        result = validate_config("unknown.xyz", "some content")
        assert result.config_type == "unknown"
        assert result.valid is True
        assert len(result.findings) == 0

    def test_explicit_type_override(self):
        # Force a file to be validated as a dockerfile
        result = validate_config("myfile", "FROM python:3.12\n", config_type="dockerfile")
        assert result.config_type == "dockerfile"
