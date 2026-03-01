"""Unit tests for validators/ — config file validation."""

from __future__ import annotations

from tapps_mcp.validators.base import detect_config_type, validate_config
from tapps_mcp.validators.docker_compose import validate_docker_compose
from tapps_mcp.validators.dockerfile import validate_dockerfile
from tapps_mcp.validators.influxdb import validate_influxdb
from tapps_mcp.validators.mqtt import validate_mqtt
from tapps_mcp.validators.websocket import validate_websocket


class TestDetectConfigType:
    def test_dockerfile(self):
        assert detect_config_type("Dockerfile") == "dockerfile"
        assert detect_config_type("Dockerfile.prod") == "dockerfile"

    def test_docker_compose(self):
        assert detect_config_type("docker-compose.yml") == "docker_compose"
        assert detect_config_type("docker-compose.yaml") == "docker_compose"
        assert detect_config_type("compose.yml") == "docker_compose"

    def test_websocket_by_content(self):
        content = 'async with websockets.connect("ws://...") as ws:'
        assert detect_config_type("app.py", content) == "websocket"

    def test_mqtt_by_content(self):
        content = "import paho.mqtt.client as mqtt"
        assert detect_config_type("sensors.py", content) == "mqtt"

    def test_influxdb_by_content(self):
        content = "client = InfluxDBClient(url='...')"
        assert detect_config_type("metrics.py", content) == "influxdb"

    def test_unknown(self):
        assert detect_config_type("README.md") is None
        assert detect_config_type("app.py") is None


class TestValidateConfig:
    def test_auto_detect_dockerfile(self):
        result = validate_config("Dockerfile", "FROM python:3.12\nCOPY . /app\n")
        assert result.config_type == "dockerfile"

    def test_unknown_type(self):
        result = validate_config("unknown.xyz", "content")
        assert result.config_type == "unknown"
        assert result.valid is True

    def test_explicit_type(self):
        content = "FROM python:3.12\n"
        result = validate_config("myfile", content, config_type="dockerfile")
        assert result.config_type == "dockerfile"


class TestDockerfileValidator:
    def test_valid_dockerfile(self):
        content = (
            "FROM python:3.12-slim\n"
            "USER appuser\n"
            "HEALTHCHECK CMD curl -f http://localhost/\n"
            "COPY . /app\n"
        )
        result = validate_dockerfile("Dockerfile", content)
        assert result.valid is True

    def test_missing_from(self):
        result = validate_dockerfile("Dockerfile", "COPY . /app\n")
        assert any(f.severity == "critical" and "FROM" in f.message for f in result.findings)

    def test_latest_tag_warning(self):
        result = validate_dockerfile("Dockerfile", "FROM python:latest\n")
        assert any(f.severity == "warning" and "latest" in f.message for f in result.findings)

    def test_no_user_warning(self):
        result = validate_dockerfile("Dockerfile", "FROM python:3.12\n")
        assert any("USER" in f.message for f in result.findings)

    def test_secret_in_env(self):
        content = "FROM python:3.12\nENV SECRET_KEY=mysecret\n"
        result = validate_dockerfile("Dockerfile", content)
        assert any(
            f.severity == "critical" and "secret" in f.message.lower() for f in result.findings
        )

    def test_healthcheck_suggestion(self):
        result = validate_dockerfile("Dockerfile", "FROM python:3.12\n")
        assert any("HEALTHCHECK" in s for s in result.suggestions)

    def test_many_run_commands(self):
        runs = "".join(f"RUN echo step{i}\n" for i in range(7))
        result = validate_dockerfile("Dockerfile", f"FROM python:3.12\n{runs}")
        assert any("RUN" in s for s in result.suggestions)


class TestDockerComposeValidator:
    def test_valid_compose(self):
        content = (
            "services:\n"
            "  web:\n"
            "    image: nginx\n"
            "    healthcheck:\n"
            "      test: curl -f http://localhost/\n"
            "networks:\n"
            "  default:\n"
        )
        result = validate_docker_compose("docker-compose.yml", content)
        assert result.valid is True

    def test_invalid_yaml(self):
        result = validate_docker_compose("docker-compose.yml", "{{invalid")
        assert result.valid is False
        assert any(f.severity == "critical" for f in result.findings)

    def test_missing_services(self):
        result = validate_docker_compose("docker-compose.yml", "version: '3'\n")
        assert result.valid is False

    def test_healthcheck_suggestion(self):
        content = "services:\n  web:\n    image: nginx\n"
        result = validate_docker_compose("docker-compose.yml", content)
        assert any("healthcheck" in s for s in result.suggestions)

    def test_network_suggestion(self):
        content = "services:\n  web:\n    image: nginx\n"
        result = validate_docker_compose("docker-compose.yml", content)
        assert any("network" in s.lower() for s in result.suggestions)


class TestWebSocketValidator:
    def test_no_websocket(self):
        result = validate_websocket("app.py", "print('hello')")
        assert result.valid is True
        assert any("No WebSocket" in s for s in result.suggestions)

    def test_missing_reconnection(self):
        content = "async with websockets.connect('ws://...') as ws:\n    pass\n"
        result = validate_websocket("app.py", content)
        # Should have a finding about reconnection
        has_reconnect = any("reconnect" in f.message.lower() for f in result.findings)
        assert has_reconnect

    def test_has_reconnection(self):
        content = (
            "async with websockets.connect('ws://...') as ws:\n"
            "    try:\n"
            "        await ws.recv()\n"
            "    except Exception:\n"
            "        retry()\n"
        )
        result = validate_websocket("app.py", content)
        reconnect_findings = [f for f in result.findings if "reconnect" in f.message.lower()]
        assert len(reconnect_findings) == 0


class TestMQTTValidator:
    def test_no_mqtt(self):
        result = validate_mqtt("app.py", "print('hello')")
        assert result.valid is True

    def test_missing_callbacks(self):
        content = "import paho.mqtt.client as mqtt\nclient = mqtt.Client()\n"
        result = validate_mqtt("sensors.py", content)
        assert any("on_connect" in f.message for f in result.findings)

    def test_wildcard_warning(self):
        content = (
            "import paho.mqtt.client as mqtt\n"
            "client.subscribe('sensors/#')\n"
            "client.on_connect = handler\n"
        )
        result = validate_mqtt("sensors.py", content)
        assert any("wildcard" in f.message.lower() for f in result.findings)


class TestInfluxDBValidator:
    def test_no_influxdb(self):
        result = validate_influxdb("app.py", "print('hello')")
        assert result.valid is True

    def test_missing_range(self):
        content = "from(bucket: 'my-bucket')\n  |> filter(fn: (r) => r._measurement == 'cpu')\n"
        result = validate_influxdb("query.py", content)
        assert any("range" in f.message.lower() for f in result.findings)

    def test_context_manager_warning(self):
        content = "client = InfluxDBClient(url='http://localhost:8086')\n"
        result = validate_influxdb("app.py", content)
        assert any("context manager" in f.message.lower() for f in result.findings)

    def test_timestamp_in_tag(self):
        content = (
            "from influxdb_client import InfluxDBClient, Point\n"
            "p = Point('cpu').tag('timestamp', '2024').field('value', 1.0)\n"
        )
        result = validate_influxdb("write.py", content)
        assert any("timestamp" in f.message.lower() for f in result.findings)
