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
    """Call at session start to discover capabilities.

    Returns TappsMCP server version, available tools, installed checkers
    (ruff, mypy, bandit, radon), and configuration.
    """
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
            "recommended_workflow": (
                "Call tapps_server_info at session start; use tapps_score_file(quick=True) "
                "during edits; before declaring work complete call tapps_score_file (full) "
                "and tapps_quality_gate on changed files, then tapps_checklist to ensure "
                "no required steps were skipped. "
                "Call tapps_lookup_docs before using a library to avoid hallucinated APIs; "
                "call tapps_consult_expert for domain-specific decisions (security, testing, etc.)."
            ),
        },
    }


@mcp.tool()
async def tapps_score_file(
    file_path: str,
    quick: bool = False,
    fix: bool = False,
) -> dict[str, Any]:
    """Call when editing or reviewing a Python file to get objective quality metrics.

    Use quick=True during edit-lint-fix loops; use full (quick=False) before
    declaring work complete. Scores across 7 categories (complexity, security,
    maintainability, test coverage, performance, structure, devex).

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
    """Call when the change touches security-sensitive code or before security-focused review.

    Runs bandit and secret detection on a Python file; returns findings with
    redacted context.

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
    """Call before declaring work complete to ensure the file passes the quality bar.

    Runs full scoring then evaluates pass/fail against the preset. Work is not
    done until this passes (or the user explicitly accepts the risk).

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
    """Call before writing code that uses an external library to avoid hallucinated APIs.

    Returns current docs (Context7 + cache). Use the result when implementing
    or fixing library usage. Resolves library names via fuzzy matching; content
    is safety-filtered before return.

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
    """Call when adding or changing Dockerfile, docker-compose, or infra config.

    Validates against best practices (e.g. non-root user, resource limits).
    Supports Dockerfile, docker-compose.yml, and WebSocket/MQTT/InfluxDB patterns.
    Use config_type "auto" to detect type from filename and content.

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
    """Call when making domain-specific decisions (security, testing, APIs, DB, etc.).

    Routes to one of 16 built-in experts, returns RAG-backed answer with
    confidence and sources. Use when unsure about patterns or best practices
    in that domain.

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
    """Call when you need to see which expert domains exist before consulting.

    Returns the 16 built-in experts with domain, description, and
    knowledge-base status. Use before tapps_consult_expert if unsure which domain fits.
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
    """Call before declaring work complete to see if any required steps were skipped.

    Reports which tools were called and which are missing (required/recommended/optional)
    for this task type, with short reasons so you know what to do next.

    Args:
        task_type: "feature" | "bugfix" | "refactor" | "security" | "review".
            Use "review" for general code review.
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
        # Streamable HTTP via uvicorn; wrap so GET / returns a simple "running" page
        import uvicorn
        from starlette.applications import Starlette
        from starlette.requests import Request  # noqa: TC002
        from starlette.responses import HTMLResponse
        from starlette.routing import Mount, Route

        mcp_app = mcp.streamable_http_app()

        def _root(_request: Request) -> HTMLResponse:
            return HTMLResponse(
                "<!DOCTYPE html><html><head><title>TappMCP</title></head><body>"
                "<h1>TappMCP is running</h1><p>MCP endpoint: <a href='/mcp'>/mcp</a></p>"
                "<p>Version: " + __version__ + "</p></body></html>",
                status_code=200,
            )

        app = Starlette(
            routes=[
                Route("/", _root),
                Mount("/mcp", app=mcp_app),
            ],
        )
        uvicorn.run(app, host=host, port=port)
    else:
        msg = f"Unsupported transport: {transport}"
        raise ValueError(msg)
