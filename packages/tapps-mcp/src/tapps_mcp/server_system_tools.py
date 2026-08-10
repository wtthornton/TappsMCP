"""System and verification tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.

This module contains:
- tapps_server_info: server version, tools, checkers, config
- tapps_security_scan: bandit + secret detection on single file
- tapps_validate_config: Dockerfile, docker-compose, MCP config validation

``tapps_checklist`` lives in :mod:`tapps_mcp.server_checklist_tools`.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server_helpers import (
    error_response,
    serialize_issues,
    success_response,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = structlog.get_logger(__name__)

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_SECURITY_SCAN_FINDING_LIMIT: int = 50
_VALID_CONFIG_TYPES: frozenset[str] = frozenset(
    {
        "dockerfile",
        "docker_compose",
        "mcp",
        "yaml_manifest",
        "websocket",
        "mqtt",
        "influxdb",
    }
)
_MAX_CONFIG_FILE_SIZE: int = 1_048_576  # 1 MB
_SECURITY_EMISSION_SEVERITIES: frozenset[str] = frozenset({"critical", "high", "medium"})


# ===== Helper functions =====


def _resolve_config_type(config_type: str) -> str | None | dict[str, Any]:
    """Resolve config_type. Returns None for 'auto', the type string, or error_response."""
    if config_type == "auto":
        return None
    if config_type not in _VALID_CONFIG_TYPES:
        return error_response(
            "tapps_validate_config",
            "invalid_config_type",
            f"Invalid config_type '{config_type}'. "
            f"Must be 'auto' or one of: {', '.join(sorted(_VALID_CONFIG_TYPES))}",
        )
    return config_type


def _read_config_content(resolved: Path) -> str | dict[str, Any]:
    """Read config file with size and encoding validation.

    Returns file content string on success, or error_response dict on failure.
    """
    try:
        file_size = resolved.stat().st_size
    except OSError as exc:
        return error_response("tapps_validate_config", "file_error", str(exc))
    if file_size > _MAX_CONFIG_FILE_SIZE:
        return error_response(
            "tapps_validate_config",
            "file_too_large",
            f"Config file is {file_size:,} bytes, "
            f"exceeding the {_MAX_CONFIG_FILE_SIZE:,} byte limit.",
        )
    try:
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return error_response(
            "tapps_validate_config",
            "decode_error",
            f"Cannot decode file as UTF-8: {exc}",
        )


def _build_config_response_data(result: Any) -> dict[str, Any]:
    """Build the response data dict from a validation result."""
    finding_count = len(result.findings)
    critical_count = sum(1 for f in result.findings if f.severity == "critical")
    warning_count = sum(1 for f in result.findings if f.severity == "warning")
    return {
        "file_path": result.file_path,
        "config_type": result.config_type,
        "valid": result.valid,
        "findings": [f.model_dump() for f in result.findings],
        "suggestions": result.suggestions,
        "finding_count": finding_count,
        "critical_count": critical_count,
        "warning_count": warning_count,
    }


def _attach_config_structured_output(resp: dict[str, Any], result: Any) -> None:
    """Attach structured output to config validation response in-place."""
    try:
        from tapps_mcp.common.output_schemas import (
            ConfigFindingOutput,
            ValidateConfigOutput,
        )

        config_findings = [
            ConfigFindingOutput(
                severity=f.severity,
                message=f.message,
                line=f.line,
                category=f.category,
            )
            for f in result.findings
        ]
        data = resp.get("data", {})
        structured = ValidateConfigOutput(
            file_path=result.file_path,
            config_type=result.config_type,
            valid=result.valid,
            finding_count=data.get("finding_count", len(result.findings)),
            critical_count=data.get("critical_count", 0),
            warning_count=data.get("warning_count", 0),
            findings=config_findings,
            suggestions=result.suggestions,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.warning("structured_output_failed", tool="tapps_validate_config", exc_info=True)


# ===== Tool handlers =====


async def tapps_server_info() -> dict[str, Any]:
    """Returns server version, available tools, installed checkers, and config.

    Use this for a lightweight discovery probe — e.g., when verifying a remote
    deployment is reachable, or when a session is already initialized and you
    just want the toolset/checker matrix. For project bootstrap call
    ``tapps_session_start`` instead; it returns this payload plus brain auth,
    cache health, memory status, and pipeline progress.
    """
    # Resolved through ``tapps_mcp.server`` at call time so tests that patch
    # ``tapps_mcp.server._server_info_async`` still intercept this tool.
    from tapps_mcp.server import _server_info_async

    return await _server_info_async()


def tapps_security_scan(
    file_path: str,
    scan_secrets: bool = True,
    domain: str | None = None,
) -> dict[str, Any]:
    """Runs bandit + secret detection on a single Python file and returns
    per-finding severity, line numbers, and remediation hints.

    Call this on any edit that touches auth, payment, upload, API, or
    data-handling code paths — even for "obvious" changes, since bandit
    catches B-rule violations (B301 pickle, B608 SQL injection, B113 timeout)
    that grep-style review misses. For multi-file changes prefer
    ``tapps_quick_check`` (which embeds a security pass) or
    ``tapps_validate_changed`` with ``security_depth='full'``.

    Args:
        file_path: Path to a single Python file inside the project root.
            Symlinks and absolute paths outside the root are rejected
            with ``error.code=path_denied``.
        scan_secrets: Detect hardcoded API keys, tokens, and credentials
            using regex + entropy heuristics. Default ``True``; disable
            only for fixture files where literal secrets are intentional.
        domain: Domain-specific rule bundle to layer on top of bandit.
            One of: ``"auth"``, ``"payments"``, ``"uploads"``, ``"api"``,
            ``"data"``. Omit (default) to auto-detect from the file path
            and contents. Pass ``""`` (empty string) to skip domain
            checks entirely. ``None`` is treated the same as omitting.
    """
    # ``_fire_security_scan_events`` is resolved through ``tapps_mcp.server`` so
    # its ``_get_brain_bridge`` / ``asyncio`` collaborators stay patchable there.
    from tapps_mcp.server import (
        _fire_security_scan_events,
        _record_call,
        _record_execution,
        _validate_file_path,
        _with_nudges,
    )
    from tapps_mcp.server_helpers import ensure_session_initialized_sync

    start = time.perf_counter_ns()
    _record_call("tapps_security_scan")
    ensure_session_initialized_sync()

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        _record_call("tapps_security_scan", success=False)
        return error_response("tapps_security_scan", "path_denied", str(exc))

    from tapps_mcp.security.security_scanner import run_security_scan

    settings = load_settings()
    result = run_security_scan(
        str(resolved),
        scan_secrets=scan_secrets,
        cwd=str(settings.project_root),
        timeout=settings.tool_timeout,
    )

    if not result.passed:
        _record_call("tapps_security_scan", success=False)

    # Domain-specific checks (TAP-477) — additive on top of generic scan
    domain_data: dict[str, object] | None = None
    if domain != "":  # empty string skips; None triggers auto-detect
        try:
            from tapps_mcp.security.domain_patterns import (
                SUPPORTED_DOMAINS,
                detect_domain,
                run_domain_scan,
            )

            source_text = resolved.read_text(encoding="utf-8", errors="replace")
            effective_domain: str | None = domain
            auto_detected = False
            if effective_domain is None:
                effective_domain = detect_domain(resolved, source_text)
                auto_detected = True

            if effective_domain and effective_domain in SUPPORTED_DOMAINS:
                findings = run_domain_scan(resolved, source_text, effective_domain)
                domain_data = {
                    "domain": effective_domain,
                    "auto_detected": auto_detected,
                    "findings": [
                        {
                            "pattern": f.pattern,
                            "severity": f.severity,
                            "description": f.description,
                            "fail_example": f.fail_example,
                            "fix": f.fix,
                            "line": f.line,
                            "matched_text": f.matched_text,
                        }
                        for f in findings
                    ],
                }
            elif effective_domain and effective_domain not in SUPPORTED_DOMAINS:
                domain_data = {
                    "domain": effective_domain,
                    "auto_detected": auto_detected,
                    "error": f"Unknown domain '{effective_domain}'. "
                    f"Supported: {sorted(SUPPORTED_DOMAINS)}. Generic scan still ran.",
                    "findings": [],
                }
            else:
                domain_data = {
                    "domain": None,
                    "auto_detected": True,
                    "note": "Domain could not be inferred from file path or content.",
                    "findings": [],
                }
        except Exception:
            logger.debug("domain_scan_failed", exc_info=True)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_security_scan",
        start,
        file_path=str(resolved),
        degraded=not result.bandit_available,
    )

    resp_payload: dict[str, object] = {
        "file_path": str(resolved),
        "passed": result.passed,
        "total_issues": result.total_issues,
        "critical_count": result.critical_count,
        "high_count": result.high_count,
        "medium_count": result.medium_count,
        "low_count": result.low_count,
        "bandit_available": result.bandit_available,
        "bandit_issues": serialize_issues(result.bandit_issues, limit=_SECURITY_SCAN_FINDING_LIMIT),
        "secret_findings": serialize_issues(
            result.secret_findings, limit=_SECURITY_SCAN_FINDING_LIMIT
        ),
    }
    if domain_data is not None:
        resp_payload["domain_scan"] = domain_data

    resp = success_response(
        "tapps_security_scan",
        elapsed_ms,
        resp_payload,
        degraded=not result.bandit_available,
    )

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import (
            SecurityFindingOutput,
            SecurityScanOutput,
        )

        sec_findings: list[SecurityFindingOutput] = [
            SecurityFindingOutput(
                code=i.code,
                message=i.message,
                file=i.file,
                line=i.line,
                severity=i.severity,
                confidence=i.confidence,
            )
            for i in result.bandit_issues[:_SECURITY_SCAN_FINDING_LIMIT]
        ]
        sec_findings.extend(
            SecurityFindingOutput(
                code=f.secret_type,
                message=f.context or f.secret_type,
                file=f.file_path,
                line=f.line_number,
                severity=f.severity,
                confidence="medium",
            )
            for f in result.secret_findings[:_SECURITY_SCAN_FINDING_LIMIT]
        )
        structured = SecurityScanOutput(
            file_path=str(resolved),
            passed=result.passed,
            total_issues=result.total_issues,
            critical_count=result.critical_count,
            high_count=result.high_count,
            medium_count=result.medium_count,
            low_count=result.low_count,
            bandit_available=result.bandit_available,
            findings=sec_findings,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.warning("structured_output_failed", tool="tapps_security_scan", exc_info=True)

    _fire_security_scan_events(str(resolved), result.bandit_issues, result.secret_findings)
    return _with_nudges("tapps_security_scan", resp)


def tapps_validate_config(file_path: str, config_type: str = "auto") -> dict[str, Any]:
    """Validates Dockerfile, docker-compose, MCP server configs, and other
    infra config files against a curated rule set (pinned base images,
    non-root user, no plaintext secrets, schema conformance).

    Call this after editing ``Dockerfile``, ``docker-compose*.yaml``,
    ``.mcp.json`` / ``.cursor/mcp.json`` / ``.vscode/mcp.json``, or a
    Kubernetes-style manifest. Skip for application Python code (use
    ``tapps_quick_check``) and for ``.tapps-mcp.yaml`` itself (use
    ``tapps_doctor``).

    MCP entries are checked per transport: stdio needs ``command``,
    remote (``http`` / ``sse``) needs ``url`` and carries no ``command``.

    Args:
        file_path: Path to the config file inside the project root.
            Returns ``error.code=path_denied`` for paths outside the
            root or with traversal segments.
        config_type: One of ``"dockerfile"``, ``"docker_compose"``,
            ``"mcp"``, ``"yaml_manifest"``, ``"websocket"``, ``"mqtt"``,
            ``"influxdb"``, or ``"auto"`` (default) to detect from file
            name and content. Any other value returns
            ``error.code=invalid_config_type``.
    """
    from tapps_mcp.server import (
        _record_call,
        _record_execution,
        _validate_file_path,
        _with_nudges,
    )

    start = time.perf_counter_ns()
    _record_call("tapps_validate_config")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_validate_config", "path_denied", str(exc))

    explicit_type = _resolve_config_type(config_type)
    if isinstance(explicit_type, dict):
        return explicit_type  # error_response

    content_or_err = _read_config_content(resolved)
    if isinstance(content_or_err, dict):
        return content_or_err  # error_response

    from tapps_mcp.validators.base import validate_config

    result = validate_config(str(resolved), content_or_err, config_type=explicit_type)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_validate_config", start, file_path=str(resolved))

    resp = success_response(
        "tapps_validate_config",
        elapsed_ms,
        _build_config_response_data(result),
    )

    _attach_config_structured_output(resp, result)

    return _with_nudges("tapps_validate_config", resp)


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register system tools on the shared *mcp_instance* (Epic 79.1: conditional)."""
    if "tapps_server_info" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_server_info,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta={"defer_loading": True},
        )
    if "tapps_security_scan" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_security_scan,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta={"defer_loading": True},
        )
    if "tapps_validate_config" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_validate_config,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta={"defer_loading": True},
        )
