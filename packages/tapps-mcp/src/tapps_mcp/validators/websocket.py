"""WebSocket validator — connection pattern checks for Python/JS/TS code."""

from __future__ import annotations

import re

from tapps_core.knowledge.models import ConfigValidationResult, ValidationFinding

# Detection patterns
_WS_PATTERN = re.compile(
    r"websockets?\.connect|WebSocket|@app\.websocket",
    re.IGNORECASE,
)

# Check patterns
_CONTEXT_MANAGER = re.compile(r"async\s+with.*websocket", re.IGNORECASE)
_RECONNECTION = re.compile(r"retry|reconnect|backoff", re.IGNORECASE)
_ERROR_HANDLING = re.compile(r"except\s+.*(?:Error|Exception)|\.catch\(|try\s*\{", re.IGNORECASE)
_ASYNC_AWAIT = re.compile(r"async\s+def|await\s+|\.then\(")
_MSG_VALIDATION = re.compile(r"json\.loads|JSON\.parse|validate|schema", re.IGNORECASE)
_HEARTBEAT = re.compile(r"ping|pong|heartbeat|keep.?alive", re.IGNORECASE)


def validate_websocket(file_path: str, content: str) -> ConfigValidationResult:
    """Validate WebSocket patterns in source code."""
    findings: list[ValidationFinding] = []
    suggestions: list[str] = []

    if not _WS_PATTERN.search(content):
        return ConfigValidationResult(
            file_path=file_path,
            config_type="websocket",
            valid=True,
            findings=[],
            suggestions=["No WebSocket patterns detected in this file."],
        )

    # Context manager usage
    if not _CONTEXT_MANAGER.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message="Use 'async with' for WebSocket connections to ensure proper cleanup.",
                category="connection",
            )
        )

    # Reconnection logic
    if not _RECONNECTION.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message="No reconnection logic detected. WebSocket connections can drop.",
                category="connection",
            )
        )

    # Error handling
    if not _ERROR_HANDLING.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message="Add error handling for WebSocket connection and message errors.",
                category="reliability",
            )
        )

    # Message validation
    if not _MSG_VALIDATION.search(content):
        suggestions.append("Validate incoming WebSocket messages before processing.")

    # Heartbeat
    if not _HEARTBEAT.search(content):
        suggestions.append("Implement heartbeat/ping-pong to detect stale connections.")

    return ConfigValidationResult(
        file_path=file_path,
        config_type="websocket",
        valid=True,
        findings=findings,
        suggestions=suggestions,
    )
