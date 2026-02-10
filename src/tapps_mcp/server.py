"""TappsMCP MCP server entry point.

Creates the FastMCP server instance, registers all tools, and provides
``run_server()`` for the CLI.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.metrics.collector import MetricsHub
    from tapps_mcp.project.session_notes import SessionNoteStore

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
    except AttributeError:
        # Fallback if internal API changes
        available_tools = [
            "tapps_server_info",
            "tapps_score_file",
            "tapps_security_scan",
            "tapps_quality_gate",
            "tapps_lookup_docs",
            "tapps_validate_config",
            "tapps_consult_expert",
            "tapps_list_experts",
            "tapps_checklist",
            "tapps_project_profile",
            "tapps_session_notes",
            "tapps_impact_analysis",
            "tapps_report",
            "tapps_init",
            "tapps_dashboard",
            "tapps_stats",
            "tapps_feedback",
        ]

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    from tapps_mcp.pipeline.models import STAGE_TOOLS, PipelineStage

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
            "pipeline": {
                "name": "TAPPS Quality Pipeline",
                "stages": [s.value for s in PipelineStage],
                "current_hint": (
                    "Start with tapps_pipeline_overview prompt, or follow stages in order."
                ),
                "stage_tools": {s.value: tools for s, tools in STAGE_TOOLS.items()},
                "handoff_file": "docs/TAPPS_HANDOFF.md",
                "runlog_file": "docs/TAPPS_RUNLOG.md",
                "prompts_available": True,
            },
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
# Epic 4: Project Context & Session Management tools
# ---------------------------------------------------------------------------


@mcp.tool()
def tapps_project_profile(
    project_root: str = "",
) -> dict[str, Any]:
    """Call at session start (after tapps_server_info) to detect the project's
    tech stack, type, CI, Docker, test frameworks, and package managers.

    Returns quality recommendations tailored to the detected stack.

    Args:
        project_root: Project root path (default: server's configured root).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_project_profile")

    from tapps_mcp.project.profiler import detect_project_profile

    settings = load_settings()
    root = settings.project_root
    if project_root:
        from pathlib import Path

        root = Path(project_root).resolve()

    try:
        profile = detect_project_profile(root)
    except Exception as exc:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        return {
            "tool": "tapps_project_profile",
            "success": False,
            "elapsed_ms": elapsed_ms,
            "error": {"code": "profile_failed", "message": str(exc)},
        }

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_project_profile",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "project_root": str(root),
            "tech_stack": profile.tech_stack.model_dump(),
            "project_type": profile.project_type,
            "project_type_confidence": round(profile.project_type_confidence, 2),
            "project_type_reason": profile.project_type_reason,
            "has_ci": profile.has_ci,
            "ci_systems": profile.ci_systems,
            "has_docker": profile.has_docker,
            "has_tests": profile.has_tests,
            "test_frameworks": profile.test_frameworks,
            "package_managers": profile.package_managers,
            "quality_recommendations": profile.quality_recommendations,
        },
    }


# Session note store - singleton, created on first use
_session_store: SessionNoteStore | None = None


def _get_session_store() -> SessionNoteStore:
    """Lazily create or return the session note store."""
    global _session_store  # noqa: PLW0603
    if _session_store is None:
        from tapps_mcp.project.session_notes import SessionNoteStore

        settings = load_settings()
        _session_store = SessionNoteStore(settings.project_root)
    return _session_store


@mcp.tool()
def tapps_session_notes(
    action: str,
    key: str = "",
    value: str = "",
) -> dict[str, Any]:
    """Persist notes across the session to avoid losing context.

    Use ``save`` to record a constraint or decision, ``get`` to recall one,
    ``list`` to see all notes, or ``clear`` to reset.

    Args:
        action: "save" | "get" | "list" | "clear".
        key: Note key (required for save/get, optional for clear).
        value: Note value (required for save).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_session_notes")

    store = _get_session_store()
    data: dict[str, Any] = {}

    if action == "save":
        if not key or not value:
            return {
                "tool": "tapps_session_notes",
                "success": False,
                "elapsed_ms": 0,
                "error": {"code": "missing_params", "message": "save requires key and value"},
            }
        note = store.save(key, value)
        data = {"action": "save", "note": note.model_dump()}

    elif action == "get":
        if not key:
            return {
                "tool": "tapps_session_notes",
                "success": False,
                "elapsed_ms": 0,
                "error": {"code": "missing_params", "message": "get requires key"},
            }
        found = store.get(key)
        note_data = found.model_dump() if found else None
        data = {"action": "get", "note": note_data, "found": found is not None}

    elif action == "list":
        notes = store.list_all()
        data = {"action": "list", "notes": [n.model_dump() for n in notes]}

    elif action == "clear":
        cleared = store.clear(key or None)
        data = {"action": "clear", "cleared_count": cleared}

    else:
        return {
            "tool": "tapps_session_notes",
            "success": False,
            "elapsed_ms": 0,
            "error": {
                "code": "invalid_action",
                "message": f"Unknown action: {action}. Use save/get/list/clear.",
            },
        }

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    data.update(store.metadata())

    return {
        "tool": "tapps_session_notes",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": data,
    }


@mcp.tool()
def tapps_impact_analysis(
    file_path: str,
    change_type: str = "modified",
) -> dict[str, Any]:
    """Call before a refactor or file deletion to understand the blast radius.

    Uses AST-based import graph analysis to identify direct dependents,
    transitive dependents, and test files that should be re-run.

    Args:
        file_path: Path to the file being changed.
        change_type: "added" | "modified" | "removed".
    """
    start = time.perf_counter_ns()
    _record_call("tapps_impact_analysis")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return {
            "tool": "tapps_impact_analysis",
            "success": False,
            "elapsed_ms": 0,
            "error": {"code": "path_denied", "message": str(exc)},
        }

    from tapps_mcp.project.impact_analyzer import analyze_impact

    settings = load_settings()
    report = analyze_impact(resolved, settings.project_root, change_type)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_impact_analysis",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "changed_file": report.changed_file,
            "change_type": report.change_type,
            "severity": report.severity,
            "total_affected": report.total_affected,
            "direct_dependents": [d.model_dump() for d in report.direct_dependents],
            "transitive_dependents": [d.model_dump() for d in report.transitive_dependents],
            "test_files": [t.model_dump() for t in report.test_files],
            "recommendations": report.recommendations,
        },
    }


@mcp.tool()
async def tapps_report(
    file_path: str = "",
    report_format: str = "json",
) -> dict[str, Any]:
    """Generate a quality report combining scoring and gate results.

    When *file_path* is provided, scores that single file.
    Supports JSON (default), markdown, and HTML output.

    Args:
        file_path: Path to a Python file (optional - project-wide if omitted).
        report_format: "json" | "markdown" | "html".
    """
    start = time.perf_counter_ns()
    _record_call("tapps_report")

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.project.report import generate_report
    from tapps_mcp.scoring.scorer import CodeScorer

    settings = load_settings()
    scorer = CodeScorer()

    score_results = []
    gate_results = []

    if file_path:
        try:
            resolved = _validate_file_path(file_path)
        except (ValueError, FileNotFoundError) as exc:
            return {
                "tool": "tapps_report",
                "success": False,
                "elapsed_ms": 0,
                "error": {"code": "path_denied", "message": str(exc)},
            }
        result = await scorer.score_file(resolved)
        score_results.append(result)
        gate_results.append(evaluate_gate(result, preset=settings.quality_preset))
    else:
        # Project-wide: score all .py files in project root (max 20)
        from pathlib import Path as _Path

        _skip = {".venv", "venv", "node_modules", "__pycache__", ".git", "dist", "build"}
        py_files = sorted(_Path(settings.project_root).rglob("*.py"))
        py_files = [f for f in py_files if not any(part in _skip for part in f.parts)][:20]

        for pf in py_files:
            try:
                result = await scorer.score_file(pf)
                score_results.append(result)
                gate_results.append(evaluate_gate(result, preset=settings.quality_preset))
            except Exception:
                logger.warning("report_file_skip", file=str(pf), exc_info=True)

    report_data = generate_report(
        score_results,
        gate_results,
        report_format=report_format,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_report",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": report_data,
    }


# ---------------------------------------------------------------------------
# Epic 8: Pipeline Orchestration — MCP Prompts & Bootstrap Tool
# ---------------------------------------------------------------------------


@mcp.prompt()
def tapps_pipeline(stage: str = "discover") -> str:
    """TAPPS quality pipeline - structured 5-stage workflow.

    Get instructions for a specific pipeline stage. Stages run in order:
    discover -> research -> develop -> validate -> verify.

    Args:
        stage: Pipeline stage to get instructions for.
               One of: discover, research, develop, validate, verify.
    """
    from tapps_mcp.prompts.prompt_loader import load_stage_prompt

    return load_stage_prompt(stage)


@mcp.prompt()
def tapps_pipeline_overview() -> str:
    """Get a summary of the full TAPPS 5-stage quality pipeline.

    Returns stage names, tool assignments, flow diagram, and
    handoff file format. Use this to understand the full pipeline
    before starting.
    """
    from tapps_mcp.prompts.prompt_loader import load_overview

    return load_overview()


@mcp.tool()
def tapps_init(
    create_handoff: bool = True,
    create_runlog: bool = True,
    platform: str = "",
) -> dict[str, Any]:
    """Bootstrap TAPPS pipeline in the current project.

    Creates handoff and runlog template files. Optionally generates
    platform-specific rule files for Claude Code or Cursor.

    Call once per project to set up the pipeline workflow.

    Args:
        create_handoff: Create docs/TAPPS_HANDOFF.md template.
        create_runlog: Create docs/TAPPS_RUNLOG.md template.
        platform: Generate platform rules. One of: "claude", "cursor", "".
                  Empty string skips platform-specific files.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_init")

    from tapps_mcp.pipeline.init import bootstrap_pipeline

    settings = load_settings()
    result = bootstrap_pipeline(
        settings.project_root,
        create_handoff=create_handoff,
        create_runlog=create_runlog,
        platform=platform,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_init",
        "success": not result["errors"],
        "elapsed_ms": elapsed_ms,
        "data": result,
    }


# ---------------------------------------------------------------------------
# Epic 7: Metrics, Observability & Dashboard tools
# ---------------------------------------------------------------------------


def _get_metrics_hub() -> MetricsHub:
    """Lazily import and return the global MetricsHub."""
    from tapps_mcp.metrics.collector import get_metrics_hub

    return get_metrics_hub()


@mcp.tool()
async def tapps_dashboard(
    output_format: str = "json",
    time_range: str = "7d",
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a comprehensive metrics dashboard.

    Call this to review how well TappsMCP is performing - scoring accuracy,
    gate pass rates, expert effectiveness, cache performance, quality trends,
    and alerts.

    Args:
        output_format: Output format - "json" (default), "markdown", "html", or "otel".
        time_range: Time range - "1d", "7d", "30d", "90d".
        sections: Specific sections to include (default: all).
            Options: summary, tool_metrics, scoring_trends, expert_metrics,
            cache_metrics, quality_distribution, alerts, business_metrics,
            recommendations.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_dashboard")

    hub = _get_metrics_hub()

    if output_format == "otel":
        from tapps_mcp.metrics.otel_export import export_otel_trace

        recent = hub.execution.get_recent(limit=100)
        otel_data = export_otel_trace(recent)
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        return {
            "tool": "tapps_dashboard",
            "success": True,
            "elapsed_ms": elapsed_ms,
            "data": otel_data,
        }

    dashboard = hub.get_dashboard_generator()

    if output_format == "json":
        data = dashboard.generate_json_dashboard(sections=sections)
    elif output_format == "markdown":
        content = dashboard.generate_markdown_dashboard(sections=sections)
        data = {"format": "markdown", "content": content}
    elif output_format == "html":
        content = dashboard.generate_html_dashboard(sections=sections)
        path = dashboard.save_dashboard(fmt="html", sections=sections)
        data = {"format": "html", "content": content, "saved_to": str(path)}
    else:
        data = dashboard.generate_json_dashboard(sections=sections)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return {
        "tool": "tapps_dashboard",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": data,
    }


@mcp.tool()
def tapps_stats(
    tool_name: str | None = None,
    period: str = "session",
) -> dict[str, Any]:
    """Return usage statistics for TappsMCP tools.

    Shows call counts, success rates, average durations, cache hit rates,
    and gate pass rates.

    Args:
        tool_name: Filter stats to a specific tool (optional).
        period: Stats period - "session", "1d", "7d", "30d", "all".
    """
    start = time.perf_counter_ns()
    _record_call("tapps_stats")

    hub = _get_metrics_hub()

    # Compute time-based filter
    from datetime import UTC, datetime, timedelta

    since: datetime | None = None
    if period == "session":
        since = None  # use in-memory buffer only
    elif period == "1d":
        since = datetime.now(tz=UTC) - timedelta(days=1)
    elif period == "7d":
        since = datetime.now(tz=UTC) - timedelta(days=7)
    elif period == "30d":
        since = datetime.now(tz=UTC) - timedelta(days=30)
    # "all" = no filter

    if period == "session":
        # Use in-memory recent data for session stats
        recent = hub.execution.get_recent(limit=100)
        from tapps_mcp.metrics.execution_metrics import ToolCallMetricsCollector

        summary = ToolCallMetricsCollector._compute_summary(recent)

        # Per-tool breakdown from recent
        by_tool_data: dict[str, list[Any]] = {}
        for m in recent:
            by_tool_data.setdefault(m.tool_name, []).append(m)
        tool_breakdowns = []
        for tname, tmetrics in sorted(by_tool_data.items()):
            if tool_name and tname != tool_name:
                continue
            ts = ToolCallMetricsCollector._compute_summary(tmetrics)
            tool_breakdowns.append(
                {
                    "tool_name": tname,
                    "call_count": ts.total_calls,
                    "success_rate": ts.success_rate,
                    "avg_duration_ms": ts.avg_duration_ms,
                    "p95_duration_ms": ts.p95_duration_ms,
                }
            )
    else:
        summary = hub.execution.get_summary(since=since)
        breakdowns = hub.execution.get_summary_by_tool(since=since)
        tool_breakdowns = [
            {
                "tool_name": b.tool_name,
                "call_count": b.call_count,
                "success_rate": b.success_rate,
                "avg_duration_ms": b.avg_duration_ms,
                "p95_duration_ms": b.p95_duration_ms,
            }
            for b in breakdowns
            if not tool_name or b.tool_name == tool_name
        ]

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_stats",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "period": period,
            "total_calls": summary.total_calls,
            "success_rate": summary.success_rate,
            "avg_duration_ms": summary.avg_duration_ms,
            "p95_duration_ms": summary.p95_duration_ms,
            "gate_pass_rate": summary.gate_pass_rate,
            "avg_score": summary.avg_score,
            "tools": tool_breakdowns,
        },
    }


@mcp.tool()
def tapps_feedback(
    tool_name: str,
    helpful: bool,
    context: str | None = None,
) -> dict[str, Any]:
    """Report whether a tool's output was helpful.

    This feedback improves TappsMCP's adaptive scoring and expert weights
    over time.

    Args:
        tool_name: Which tool to provide feedback on.
        helpful: Was the output helpful?
        context: Additional context about why it was or wasn't helpful.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_feedback")

    from tapps_mcp.metrics.feedback import FeedbackTracker

    hub = _get_metrics_hub()
    tracker = FeedbackTracker(hub.metrics_dir)

    tracker.record(
        tool_name=tool_name,
        helpful=helpful,
        context=context or "",
        session_id=hub.session_id,
    )

    stats = tracker.get_statistics(tool_name=tool_name)
    overall_stats = tracker.get_statistics()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    return {
        "tool": "tapps_feedback",
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": {
            "recorded": True,
            "tool_name": tool_name,
            "helpful": helpful,
            "tool_stats": stats,
            "overall_stats": overall_stats,
        },
    }


# ---------------------------------------------------------------------------
# MCP Resources -- browsable knowledge and configuration
# ---------------------------------------------------------------------------


@mcp.resource("tapps://knowledge/{domain}/{topic}")
def get_knowledge_resource(domain: str, topic: str) -> str:
    """Retrieve expert knowledge for a domain and topic.

    Browse the 119 knowledge files across 16 expert domains.
    """
    import re
    from pathlib import Path

    from tapps_mcp.experts.registry import ExpertRegistry

    if domain not in ExpertRegistry.TECHNICAL_DOMAINS:
        valid = ", ".join(sorted(ExpertRegistry.TECHNICAL_DOMAINS))
        return f"Unknown domain: {domain}. Valid domains: {valid}"

    # Sanitise topic to prevent path traversal (alphanumeric, hyphens, underscores only)
    if not re.match(r"^[a-zA-Z0-9_-]+$", topic):
        return f"Invalid topic name: '{topic}'. Use only alphanumeric, hyphens, underscores."

    knowledge_dir = Path(__file__).parent / "experts" / "knowledge" / domain
    topic_file = knowledge_dir / f"{topic}.md"

    # Verify resolved path stays within the knowledge directory
    try:
        topic_file.resolve().relative_to(knowledge_dir.resolve())
    except ValueError:
        return f"Invalid topic path: '{topic}'."

    if not topic_file.exists():
        # List available topics
        if knowledge_dir.exists():
            available = [f.stem for f in knowledge_dir.glob("*.md")]
            avail_str = ", ".join(sorted(available))
            return f"Topic '{topic}' not found in domain '{domain}'. Available: {avail_str}"
        return f"No knowledge directory for domain '{domain}'."

    return topic_file.read_text(encoding="utf-8")


@mcp.resource("tapps://knowledge/domains")
def list_knowledge_domains() -> str:
    """List all available expert knowledge domains and their topics."""
    from pathlib import Path

    knowledge_base = Path(__file__).parent / "experts" / "knowledge"
    lines = ["# TappsMCP Knowledge Domains\n"]

    for domain_dir in sorted(knowledge_base.iterdir()):
        if not domain_dir.is_dir():
            continue
        topics = sorted(f.stem for f in domain_dir.glob("*.md") if f.stem != "README")
        lines.append(f"\n## {domain_dir.name}")
        lines.append(f"Topics ({len(topics)}):")
        for t in topics:
            lines.append(f"  - {t}")

    return "\n".join(lines)


@mcp.resource("tapps://config/quality-presets")
def get_quality_presets() -> str:
    """Get available quality gate presets and their thresholds."""
    from tapps_mcp.config.settings import PRESETS

    lines = ["# Quality Gate Presets\n"]
    for name, thresholds in PRESETS.items():
        lines.append(f"## {name}")
        for key, value in thresholds.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("tapps://config/scoring-weights")
def get_scoring_weights() -> str:
    """Get current scoring category weights."""
    settings = load_settings()
    w = settings.scoring_weights

    lines = ["# Scoring Weights\n"]
    from tapps_mcp.config.settings import ScoringWeights

    for field_name in ScoringWeights.model_fields:
        lines.append(f"  {field_name}: {getattr(w, field_name)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP Prompts -- workflow guidance
# ---------------------------------------------------------------------------


@mcp.prompt()
def tapps_workflow(task_type: str = "general") -> str:
    """Generate the TappsMCP workflow prompt for a specific task type.

    Provides tool call order and recommendations based on the task type.

    Args:
        task_type: One of: general, feature, bugfix, refactor, security, review.
    """
    workflows = {
        "general": (
            "TappsMCP Workflow - General\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_project_profile - understand the project\n"
            "3. tapps_score_file(quick=True) - quick scoring during edits\n"
            "4. tapps_score_file - full scoring before completion\n"
            "5. tapps_quality_gate - verify quality bar\n"
            "6. tapps_checklist(task_type='review') - verify completeness"
        ),
        "feature": (
            "TappsMCP Workflow - New Feature\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_project_profile - understand the project\n"
            "3. tapps_lookup_docs - check library APIs before coding\n"
            "4. tapps_consult_expert - get domain guidance\n"
            "5. tapps_score_file(quick=True) - quick scoring during edits\n"
            "6. tapps_score_file - full scoring\n"
            "7. tapps_security_scan - check for vulnerabilities\n"
            "8. tapps_quality_gate - verify quality bar\n"
            "9. tapps_checklist(task_type='feature') - verify completeness"
        ),
        "bugfix": (
            "TappsMCP Workflow - Bug Fix\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_impact_analysis - understand blast radius\n"
            "3. tapps_score_file(quick=True) - quick scoring during fix\n"
            "4. tapps_score_file - full scoring after fix\n"
            "5. tapps_quality_gate - verify quality bar\n"
            "6. tapps_checklist(task_type='bugfix') - verify completeness"
        ),
        "refactor": (
            "TappsMCP Workflow - Refactoring\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_impact_analysis - understand dependencies\n"
            "3. tapps_consult_expert(domain='software-architecture') - get guidance\n"
            "4. tapps_score_file(quick=True) - quick scoring during refactor\n"
            "5. tapps_score_file - full scoring\n"
            "6. tapps_quality_gate - verify quality bar\n"
            "7. tapps_checklist(task_type='refactor') - verify completeness"
        ),
        "security": (
            "TappsMCP Workflow - Security Review\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_security_scan - comprehensive security scan\n"
            "3. tapps_consult_expert(domain='security') - get security guidance\n"
            "4. tapps_score_file - full scoring with security focus\n"
            "5. tapps_quality_gate(preset='strict') - strict quality bar\n"
            "6. tapps_checklist(task_type='security') - verify completeness"
        ),
        "review": (
            "TappsMCP Workflow - Code Review\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_score_file - full scoring\n"
            "3. tapps_security_scan - security check\n"
            "4. tapps_quality_gate - verify quality bar\n"
            "5. tapps_checklist(task_type='review') - verify completeness"
        ),
    }
    return workflows.get(task_type, workflows["general"])


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
        from starlette.requests import Request  # noqa: TC002
        from starlette.responses import HTMLResponse
        from starlette.routing import Route

        mcp_app = mcp.streamable_http_app()

        def _root(_request: Request) -> HTMLResponse:
            return HTMLResponse(
                "<!DOCTYPE html><html><head><title>TappMCP</title></head><body>"
                "<h1>TappMCP is running</h1><p>MCP endpoint: <a href='/mcp'>/mcp</a></p>"
                "<p>Version: " + __version__ + "</p></body></html>",
                status_code=200,
            )

        # Add root route directly to the MCP app so its lifespan
        # (task group init) runs properly — wrapping in a parent
        # Starlette breaks the lifespan chain.
        mcp_app.routes.insert(0, Route("/", _root))
        uvicorn.run(mcp_app, host=host, port=port)
    else:
        msg = f"Unsupported transport: {transport}"
        raise ValueError(msg)
