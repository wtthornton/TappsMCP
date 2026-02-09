"""MQTT validator — connection and topic pattern checks."""

from __future__ import annotations

import re

from tapps_mcp.knowledge.models import ConfigValidationResult, ValidationFinding

# Detection patterns
_MQTT_PATTERN = re.compile(r"paho\.mqtt|asyncio_mqtt|mqtt\.Client|MQTT", re.IGNORECASE)

# Check patterns
_ON_CONNECT = re.compile(r"on_connect|on_message", re.IGNORECASE)
_RECONNECT = re.compile(r"reconnect|retry|backoff", re.IGNORECASE)
_ERROR_HANDLING = re.compile(r"except\s+|\.catch\(|try\s*\{", re.IGNORECASE)
_QOS = re.compile(r"qos\s*=|QoS", re.IGNORECASE)
_WILDCARD_MULTI = re.compile(r"""subscribe\([^)]*['"].*#""")
_WILDCARD_SINGLE = re.compile(r"""subscribe\([^)]*['"].*\+""")
_WILL = re.compile(r"will_set|last.?will", re.IGNORECASE)
_TOPIC_DEEP = re.compile(r"""['"][\w/]+/[\w/]+/[\w/]+/[\w/]+/[\w/]+/[\w/]+""")


def validate_mqtt(file_path: str, content: str) -> ConfigValidationResult:
    """Validate MQTT patterns in source code."""
    findings: list[ValidationFinding] = []
    suggestions: list[str] = []

    if not _MQTT_PATTERN.search(content):
        return ConfigValidationResult(
            file_path=file_path,
            config_type="mqtt",
            valid=True,
            findings=[],
            suggestions=["No MQTT patterns detected in this file."],
        )

    # on_connect callback
    if not _ON_CONNECT.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message="Missing on_connect/on_message callbacks.",
                category="connection",
            )
        )

    # Reconnection
    if not _RECONNECT.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message="No reconnection logic detected. MQTT connections can drop.",
                category="connection",
            )
        )

    # Error handling
    if not _ERROR_HANDLING.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message="Add error handling for MQTT operations.",
                category="reliability",
            )
        )

    # QoS specification
    if not _QOS.search(content):
        suggestions.append("Specify QoS level (0, 1, or 2) for publish and subscribe.")

    # Wildcard usage
    if _WILDCARD_MULTI.search(content):
        findings.append(
            ValidationFinding(
                severity="info",
                message="Multi-level wildcard '#' in subscribe — ensure this is intentional.",
                category="topic",
            )
        )

    if _WILDCARD_SINGLE.search(content):
        suggestions.append("Single-level wildcard '+' used — verify topic structure.")

    # Deep topic nesting
    if _TOPIC_DEEP.search(content):
        suggestions.append("Topic nesting >5 levels deep. Consider flattening topic hierarchy.")

    # Will message
    if not _WILL.search(content):
        suggestions.append("Set a 'last will' message for unexpected disconnects.")

    return ConfigValidationResult(
        file_path=file_path,
        config_type="mqtt",
        valid=True,
        findings=findings,
        suggestions=suggestions,
    )
