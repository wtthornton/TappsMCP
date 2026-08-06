"""MCP server config validator - structure and best-practice checks."""

from __future__ import annotations

import json
import re
from typing import Any

from tapps_core.knowledge.models import ConfigValidationResult, ValidationFinding


def validate_mcp_config(file_path: str, content: str) -> ConfigValidationResult:
    """Validate an MCP server configuration file.

    Checks for valid JSON structure, the fields required by each server's
    transport, and common misconfigurations like empty ``env`` objects.

    Required fields are transport-dependent: stdio servers need ``command``
    (and should declare ``args``), while remote servers (``http`` / ``sse``)
    need ``url`` and legitimately carry no ``command``. Transport is read
    from ``type``, and inferred from the presence of ``url`` when ``type``
    is absent or spelled a way this validator does not recognize. Whichever
    field the transport requires must be a non-empty string.

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
    # Standard:  {"mcpServers": {"name": {...}}}
    # VS Code:   {"servers": {"name": {...}}}
    # Flat:      {"name": {...}}
    # Prefer explicit keys over the whole document so a VS Code `servers`
    # key is not treated as a server named "servers" (TAP-5359).
    mcp_servers = data.get("mcpServers")
    vscode_servers = data.get("servers")
    if isinstance(mcp_servers, dict):
        servers: Any = mcp_servers
        format_kind = "mcpServers"
    elif isinstance(vscode_servers, dict):
        servers = vscode_servers
        format_kind = "servers"
    else:
        servers = data
        format_kind = "flat"

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

    if format_kind == "flat":
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

        # Transport decides which fields are required. Remote servers
        # (`http`/`sse`) carry `url` + `headers` and legitimately have no
        # `command`; only stdio servers spawn a process. Infer from `url`
        # when `type` is absent, since `type` is optional in practice.
        # Spellings vary across hosts (`http`, `sse`, `streamable-http`,
        # Cursor's `streamableHttp`), so match on normalized letters rather
        # than an enumerated list that breaks on the next variant.
        transport = str(config.get("type", "")).strip()
        normalized = re.sub(r"[^a-z]", "", transport.lower())
        if "http" in normalized or normalized == "sse":
            remote = True
        elif normalized == "stdio":
            remote = False
        else:
            # `type` is absent or spelled a way we do not recognize. Fall back
            # to the entry's shape rather than guessing stdio: remote entries
            # are the ones that carry a `url`.
            remote = "url" in config
        if not transport:
            transport = "http" if remote else "stdio"

        if remote:
            url = config.get("url")
            if "url" not in config:
                findings.append(
                    ValidationFinding(
                        severity="critical",
                        message=f"Server '{name}' ({transport}) missing 'url' field",
                        category="structure",
                    )
                )
            elif not isinstance(url, str) or not url.strip():
                # A blank or non-string `url` is as unusable as a missing one;
                # a presence check alone would score it clean.
                findings.append(
                    ValidationFinding(
                        severity="critical",
                        message=f"Server '{name}' ({transport}) has an empty or non-string 'url'",
                        category="structure",
                    )
                )
            if "command" in config:
                findings.append(
                    ValidationFinding(
                        severity="warning",
                        message=(
                            f"Server '{name}' ({transport}) has 'command'; "
                            "ignored for remote transports"
                        ),
                        category="structure",
                    )
                )
        else:
            command = config.get("command")
            if "command" not in config:
                findings.append(
                    ValidationFinding(
                        severity="critical",
                        message=f"Server '{name}' missing 'command' field",
                        category="structure",
                    )
                )
            elif not isinstance(command, str) or not command.strip():
                findings.append(
                    ValidationFinding(
                        severity="critical",
                        message=f"Server '{name}' has an empty or non-string 'command'",
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
