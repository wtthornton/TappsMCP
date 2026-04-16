"""MCP server config validator - structure and best-practice checks."""

from __future__ import annotations

import json
from typing import Any

from tapps_core.knowledge.models import ConfigValidationResult, ValidationFinding


def validate_mcp_config(file_path: str, content: str) -> ConfigValidationResult:
    """Validate an MCP server configuration file.

    Checks for valid JSON structure, required fields (``command``, ``args``),
    and common misconfigurations like empty ``env`` objects.

    Args:
        file_path: Path to the config file.
        content: Raw file content.

    Returns:
        ``ConfigValidationResult`` with findings and suggestions.
    """
    findings: list[ValidationFinding] = []
    suggestions: list[str] = []

    # --- Parse JSON ---
    try:
        data: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        findings.append(
            ValidationFinding(
                severity="critical",
                message=f"Invalid JSON: {exc}",
                category="syntax",
            )
        )
        return ConfigValidationResult(
            file_path=file_path,
            config_type="mcp",
            valid=False,
            findings=findings,
            suggestions=suggestions,
        )

    if not isinstance(data, dict):
        findings.append(
            ValidationFinding(
                severity="critical",
                message="MCP config must be a JSON object",
                category="structure",
            )
        )
        return ConfigValidationResult(
            file_path=file_path,
            config_type="mcp",
            valid=False,
            findings=findings,
            suggestions=suggestions,
        )

    # --- Detect format ---
    # Standard: {"mcpServers": {"name": {...}}}
    # Flat:     {"name": {...}}
    servers: Any = data.get("mcpServers", data)

    if not isinstance(servers, dict):
        findings.append(
            ValidationFinding(
                severity="critical",
                message="No server entries found",
                category="structure",
            )
        )
        return ConfigValidationResult(
            file_path=file_path,
            config_type="mcp",
            valid=False,
            findings=findings,
            suggestions=suggestions,
        )

    if "mcpServers" not in data:
        suggestions.append(
            "Consider wrapping server entries under 'mcpServers' key for standard MCP format."
        )

    if not servers:
        findings.append(
            ValidationFinding(
                severity="warning",
                message="No servers defined in configuration",
                category="structure",
            )
        )

    # --- Validate each server entry ---
    for name, config in servers.items():
        if not isinstance(config, dict):
            findings.append(
                ValidationFinding(
                    severity="warning",
                    message=f"Server '{name}' is not an object",
                    category="structure",
                )
            )
            continue

        if "command" not in config:
            findings.append(
                ValidationFinding(
                    severity="critical",
                    message=f"Server '{name}' missing 'command' field",
                    category="structure",
                )
            )

        if "args" not in config:
            findings.append(
                ValidationFinding(
                    severity="warning",
                    message=f"Server '{name}' has no 'args' list",
                    category="structure",
                )
            )
        elif not isinstance(config["args"], list):
            findings.append(
                ValidationFinding(
                    severity="warning",
                    message=f"Server '{name}' 'args' should be a list",
                    category="structure",
                )
            )

        env = config.get("env")
        if isinstance(env, dict) and not env:
            suggestions.append(f"Server '{name}' has empty 'env' object; can be removed.")

    valid = not any(f.severity == "critical" for f in findings)
    return ConfigValidationResult(
        file_path=file_path,
        config_type="mcp",
        valid=valid,
        findings=findings,
        suggestions=suggestions,
    )
