"""TappsMCP MCP server entry point.

Creates the FastMCP server instance, registers all tools, and provides
``run_server()`` for the CLI.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import structlog
from mcp.server.fastmcp import FastMCP

from tapps_mcp import __version__
from tapps_mcp.common.logging import setup_logging
from tapps_mcp.config.settings import load_settings
from tapps_mcp.tools.tool_detection import detect_installed_tools

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("TappsMCP")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_file_path(file_path: str) -> Path:
    """Validate *file_path* against the project root boundary.

    Raises ``ValueError`` (surfaced by FastMCP as a tool error) on failure.
    """
    from tapps_mcp.security.path_validator import PathValidator

    settings = load_settings()
    validator = PathValidator(settings.project_root)
    return validator.validate_read_path(file_path)


def _record_call(tool_name: str) -> None:
    """Record a tool call in the session checklist tracker."""
    from tapps_mcp.tools.checklist import CallTracker

    CallTracker.record(tool_name)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def tapps_server_info() -> dict[str, Any]:
    """Return TappsMCP server version, available tools, installed checkers, and configuration."""
    start = time.perf_counter_ns()
    _record_call("tapps_server_info")

    settings = load_settings()
    installed = detect_installed_tools()

    # Build tool list from the MCP server itself
    available_tools: list[str] = []
    try:
        tool_manager = mcp._tool_manager
        available_tools = list(tool_manager._tools.keys())
    except Exception:
        available_tools = ["tapps_server_info"]

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_server_info",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "server": {
                "name": "TappsMCP",
                "version": __version__,
                "protocol_version": "2025-11-25",
            },
            "configuration": {
                "project_root": str(settings.project_root),
                "quality_preset": settings.quality_preset,
                "log_level": settings.log_level,
            },
            "available_tools": available_tools,
            "installed_checkers": [t.model_dump() for t in installed],
        },
    }


@mcp.tool()
async def tapps_score_file(
    file_path: str,
    quick: bool = False,
    fix: bool = False,
) -> dict[str, Any]:
    """Score a Python file across 7 quality categories.

    Args:
        file_path: Path to the Python file to score.
        quick: If True, run ruff-only scoring (< 500 ms).
        fix: If True (requires quick=True), apply ruff auto-fixes first.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_score_file")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return {
            "tool": "tapps_score_file",
            "success": False,
            "elapsed_ms": 0,
            "error": {"code": "path_denied", "message": str(exc)},
        }

    from tapps_mcp.scoring.scorer import CodeScorer

    scorer = CodeScorer()
    fixes_applied = 0

    if quick:
        if fix:
            from tapps_mcp.tools.ruff import run_ruff_fix

            fixes_applied = run_ruff_fix(str(resolved), cwd=str(resolved.parent))

        result = scorer.score_file_quick(resolved)
    else:
        result = await scorer.score_file(resolved)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "file_path": result.file_path,
        "overall_score": round(result.overall_score, 2),
        "categories": {
            name: {
                "score": round(cat.score, 2),
                "weight": cat.weight,
                "details": cat.details,
            }
            for name, cat in result.categories.items()
        },
        "lint_issue_count": len(result.lint_issues),
        "type_issue_count": len(result.type_issues),
        "security_issue_count": len(result.security_issues),
    }

    if quick and fix:
        data["fixes_applied"] = fixes_applied

    if result.lint_issues:
        data["lint_issues"] = [i.model_dump() for i in result.lint_issues[:20]]
    if result.type_issues:
        data["type_issues"] = [i.model_dump() for i in result.type_issues[:20]]
    if result.security_issues:
        data["security_issues"] = [i.model_dump() for i in result.security_issues[:20]]

    return {
        "tool": "tapps_score_file",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": data,
        "degraded": result.degraded,
    }


@mcp.tool()
def tapps_security_scan(
    file_path: str,
    scan_secrets: bool = True,
) -> dict[str, Any]:
    """Run a security scan on a Python file (bandit + secret detection).

    Args:
        file_path: Path to the Python file to scan.
        scan_secrets: Whether to scan for hardcoded secrets (default: True).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_security_scan")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return {
            "tool": "tapps_security_scan",
            "success": False,
            "elapsed_ms": 0,
            "error": {"code": "path_denied", "message": str(exc)},
        }

    from tapps_mcp.security.security_scanner import run_security_scan

    settings = load_settings()
    result = run_security_scan(
        str(resolved),
        scan_secrets=scan_secrets,
        cwd=str(settings.project_root),
        timeout=settings.tool_timeout,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_security_scan",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "file_path": str(resolved),
            "passed": result.passed,
            "total_issues": result.total_issues,
            "critical_count": result.critical_count,
            "high_count": result.high_count,
            "medium_count": result.medium_count,
            "low_count": result.low_count,
            "bandit_available": result.bandit_available,
            "bandit_issues": [i.model_dump() for i in result.bandit_issues[:30]],
            "secret_findings": [f.model_dump() for f in result.secret_findings[:30]],
        },
        "degraded": not result.bandit_available,
    }


@mcp.tool()
async def tapps_quality_gate(
    file_path: str,
    preset: str = "standard",
) -> dict[str, Any]:
    """Evaluate a Python file against quality gate thresholds.

    Runs full scoring then evaluates pass/fail against the specified preset.

    Args:
        file_path: Path to the Python file to evaluate.
        preset: Quality preset — "standard" (70+), "strict" (80+), or "framework" (75+).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_quality_gate")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return {
            "tool": "tapps_quality_gate",
            "success": False,
            "elapsed_ms": 0,
            "error": {"code": "path_denied", "message": str(exc)},
        }

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.scoring.scorer import CodeScorer

    scorer = CodeScorer()
    score_result = await scorer.score_file(resolved)
    gate_result = evaluate_gate(score_result, preset=preset)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_quality_gate",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "file_path": str(resolved),
            "passed": gate_result.passed,
            "preset": gate_result.preset,
            "overall_score": round(score_result.overall_score, 2),
            "scores": {k: round(v, 2) for k, v in gate_result.scores.items()},
            "thresholds": gate_result.thresholds.model_dump(),
            "failures": [f.model_dump() for f in gate_result.failures],
            "warnings": gate_result.warnings,
        },
        "degraded": score_result.degraded,
    }


@mcp.tool()
async def tapps_lookup_docs(
    library: str,
    topic: str = "overview",
    mode: str = "code",
) -> dict[str, Any]:
    """Look up current documentation for a library.

    Resolves library names via fuzzy matching, checks local cache first,
    then fetches from Context7 API on cache miss.  All retrieved content
    passes prompt-injection safety filtering before returning.

    Args:
        library: Library name (fuzzy-matched, e.g. "fastapi", "react").
        topic: Specific topic within the library (default "overview").
        mode: "code" for API references, "info" for conceptual guides.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_lookup_docs")

    from tapps_mcp.knowledge.cache import KBCache
    from tapps_mcp.knowledge.lookup import LookupEngine

    settings = load_settings()
    cache_dir = settings.project_root / ".tapps-mcp-cache"
    cache = KBCache(cache_dir)
    engine = LookupEngine(cache, api_key=settings.context7_api_key)

    try:
        result = await engine.lookup(library, topic, mode=mode)
    finally:
        await engine.close()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "library": result.library,
        "topic": result.topic,
        "source": result.source,
        "cache_hit": result.cache_hit,
        "response_time_ms": result.response_time_ms,
    }

    if result.content is not None:
        data["content"] = result.content
        data["token_estimate"] = len(result.content) // 4
    if result.context7_id is not None:
        data["context7_id"] = result.context7_id
    if result.fuzzy_score is not None:
        data["fuzzy_score"] = result.fuzzy_score

    response: dict[str, Any] = {
        "tool": "tapps_lookup_docs",
        "success": result.success,
        "elapsed_ms": elapsed_ms,
        "data": data,
    }

    if result.error:
        response["error"] = {"code": "lookup_failed", "message": result.error}
    if result.warning:
        response["warning"] = result.warning

    return response


@mcp.tool()
def tapps_validate_config(
    file_path: str,
    config_type: str = "auto",
) -> dict[str, Any]:
    """Validate a configuration file against best practices.

    Supports Dockerfile, docker-compose.yml, and code files with
    WebSocket, MQTT, or InfluxDB patterns.  When config_type is "auto",
    the type is detected from the filename and content.

    Args:
        file_path: Path to the config file to validate.
        config_type: Config type or "auto" for auto-detection.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_validate_config")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return {
            "tool": "tapps_validate_config",
            "success": False,
            "elapsed_ms": 0,
            "error": {"code": "path_denied", "message": str(exc)},
        }

    content = resolved.read_text(encoding="utf-8")

    from tapps_mcp.validators.base import validate_config

    explicit_type = None if config_type == "auto" else config_type
    result = validate_config(str(resolved), content, config_type=explicit_type)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_validate_config",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "file_path": result.file_path,
            "config_type": result.config_type,
            "valid": result.valid,
            "findings": [f.model_dump() for f in result.findings],
            "suggestions": result.suggestions,
            "finding_count": len(result.findings),
            "critical_count": sum(1 for f in result.findings if f.severity == "critical"),
            "warning_count": sum(1 for f in result.findings if f.severity == "warning"),
        },
    }


@mcp.tool()
def tapps_consult_expert(
    question: str,
    domain: str = "",
) -> dict[str, Any]:
    """Consult a domain expert with a technical question.

    Routes the question to the best-matching expert out of 16 technical
    domains, retrieves relevant knowledge via RAG, and returns an
    authoritative answer with confidence scoring.

    Args:
        question: The technical question to ask (natural language).
        domain: Optional domain override (e.g. "security", "testing-strategies").
            When empty, the best domain is auto-detected from the question.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_consult_expert")

    from tapps_mcp.experts.engine import consult_expert

    result = consult_expert(
        question=question,
        domain=domain or None,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_consult_expert",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "domain": result.domain,
            "expert_id": result.expert_id,
            "expert_name": result.expert_name,
            "answer": result.answer,
            "confidence": round(result.confidence, 4),
            "factors": result.factors.model_dump(),
            "sources": result.sources,
            "chunks_used": result.chunks_used,
        },
    }


@mcp.tool()
def tapps_list_experts() -> dict[str, Any]:
    """List all available domain experts and their knowledge-base status.

    Returns the 16 built-in experts with their domain, description, and
    the number of knowledge files loaded for each.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_list_experts")

    from tapps_mcp.experts.engine import list_experts

    experts = list_experts()
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_list_experts",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "expert_count": len(experts),
            "experts": [e.model_dump() for e in experts],
        },
    }


@mcp.tool()
def tapps_checklist(
    task_type: str = "review",
) -> dict[str, Any]:
    """Check which TappsMCP tools have been called this session.

    Reports called, missing required, and missing recommended tools
    for the given task type.

    Args:
        task_type: One of "feature", "bugfix", "refactor", "security", "review".
    """
    start = time.perf_counter_ns()
    _record_call("tapps_checklist")

    from tapps_mcp.tools.checklist import CallTracker

    result = CallTracker.evaluate(task_type)
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_checklist",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": result.model_dump(),
    }


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------


def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start the TappsMCP MCP server.

    Args:
        transport: ``"stdio"`` for local MCP hosts, ``"http"`` for remote.
        host: Bind address for HTTP transport.
        port: Bind port for HTTP transport.
    """
    settings = load_settings()
    setup_logging(level=settings.log_level, json_output=settings.log_json)

    logger.info(
        "tapps_mcp_starting",
        version=__version__,
        transport=transport,
        project_root=str(settings.project_root),
        quality_preset=settings.quality_preset,
    )

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "http":
        # Streamable HTTP via uvicorn
        import uvicorn

        app = mcp.streamable_http_app()
        uvicorn.run(app, host=host, port=port)
    else:
        msg = f"Unsupported transport: {transport}"
        raise ValueError(msg)
