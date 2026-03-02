"""Base config validator and auto-detection logic."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from tapps_core.knowledge.models import ConfigValidationResult

logger = structlog.get_logger(__name__)

# Config type → filename patterns
CONFIG_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "dockerfile": [re.compile(r"^Dockerfile(?:\..+)?$", re.IGNORECASE)],
    "docker_compose": [
        re.compile(r"^docker-compose(?:\..+)?\.ya?ml$", re.IGNORECASE),
        re.compile(r"^compose\.ya?ml$", re.IGNORECASE),
    ],
    "websocket": [re.compile(r"\.py$|\.ts$|\.js$", re.IGNORECASE)],
    "mqtt": [re.compile(r"\.py$|\.ts$|\.js$", re.IGNORECASE)],
    "influxdb": [re.compile(r"\.py$|\.ts$|\.js$", re.IGNORECASE)],
}

# Content signatures for code-file validators
CONTENT_SIGNATURES: dict[str, list[re.Pattern[str]]] = {
    "websocket": [
        re.compile(r"websockets?\.connect|WebSocket|@app\.websocket", re.IGNORECASE),
    ],
    "mqtt": [
        re.compile(r"paho\.mqtt|asyncio_mqtt|mqtt\.Client|MQTT", re.IGNORECASE),
    ],
    "influxdb": [
        re.compile(r"InfluxDBClient|influxdb|from\(bucket:", re.IGNORECASE),
    ],
}


def detect_config_type(file_path: str, content: str | None = None) -> str | None:
    """Auto-detect config type from filename and optionally content.

    Args:
        file_path: Path to the config file.
        content: Optional file content for content-based detection.

    Returns:
        Config type string (e.g., ``"dockerfile"``) or ``None`` if unknown.
    """
    name = Path(file_path).name

    # Filename-based detection (definitive for Dockerfile / docker-compose)
    for config_type, patterns in CONFIG_PATTERNS.items():
        if config_type in ("websocket", "mqtt", "influxdb"):
            continue  # These need content signatures
        for pattern in patterns:
            if pattern.search(name):
                return config_type

    # Content-based detection for code files
    if content is not None:
        for config_type, signatures in CONTENT_SIGNATURES.items():
            for sig in signatures:
                if sig.search(content):
                    return config_type

    return None


def validate_config(
    file_path: str,
    content: str,
    config_type: str | None = None,
) -> ConfigValidationResult:
    """Validate a configuration file.

    Args:
        file_path: Path to the config file.
        content: File content.
        config_type: Explicit config type, or ``None`` for auto-detection.

    Returns:
        ``ConfigValidationResult`` with findings and suggestions.
    """
    from tapps_core.knowledge.models import ConfigValidationResult

    resolved_type = config_type or detect_config_type(file_path, content)

    if resolved_type is None:
        return ConfigValidationResult(
            file_path=file_path,
            config_type="unknown",
            valid=True,
            findings=[],
            suggestions=["Could not detect config type. Specify config_type explicitly."],
        )

    # Import and delegate to type-specific validator
    if resolved_type == "dockerfile":
        from tapps_mcp.validators.dockerfile import validate_dockerfile

        return validate_dockerfile(file_path, content)

    if resolved_type == "docker_compose":
        from tapps_mcp.validators.docker_compose import validate_docker_compose

        return validate_docker_compose(file_path, content)

    if resolved_type == "websocket":
        from tapps_mcp.validators.websocket import validate_websocket

        return validate_websocket(file_path, content)

    if resolved_type == "mqtt":
        from tapps_mcp.validators.mqtt import validate_mqtt

        return validate_mqtt(file_path, content)

    if resolved_type == "influxdb":
        from tapps_mcp.validators.influxdb import validate_influxdb

        return validate_influxdb(file_path, content)

    return ConfigValidationResult(
        file_path=file_path,
        config_type=resolved_type,
        valid=True,
        findings=[],
        suggestions=[f"No validator available for config type '{resolved_type}'."],
    )
