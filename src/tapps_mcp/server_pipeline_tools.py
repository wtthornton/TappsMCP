"""Pipeline orchestration and validation tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import (
    Context,  # noqa: TC002 — runtime import required for FastMCP annotation resolution
)
from mcp.types import ToolAnnotations

from tapps_mcp.config.settings import load_settings
from tapps_mcp.server_helpers import success_response

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.server.fastmcp import FastMCP

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


async def tapps_validate_changed(
    file_paths: str = "",
    base_ref: str = "HEAD",
    preset: str = "standard",
    include_security: bool = True,
) -> dict[str, Any]:
    """REQUIRED before declaring work complete on multi-file changes.
    Detects changed Python files (via git diff) or accepts an explicit
    comma-separated list. Runs score + quality gate + security scan on each
    file. Skipping means quality issues in changed files go undetected.

    Args:
        file_paths: Comma-separated file paths (empty = auto-detect via git diff).
        base_ref: Git ref to diff against (default: HEAD for unstaged changes).
        preset: Quality gate preset - "standard", "strict", or "framework".
        include_security: Whether to run security scan on each file.
    """
    from tapps_mcp.server import _record_call, _record_execution, _validate_file_path, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_validate_changed")

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.scoring.scorer import CodeScorer
    from tapps_mcp.tools.batch_validator import (
        MAX_BATCH_FILES,
        detect_changed_python_files,
        format_batch_summary,
    )

    settings = load_settings()

    paths: list[Path] = []
    if file_paths.strip():
        for raw_fp in file_paths.split(","):
            cleaned_fp = raw_fp.strip()
            if not cleaned_fp:
                continue
            with contextlib.suppress(ValueError, FileNotFoundError):
                paths.append(_validate_file_path(cleaned_fp))
    else:
        paths = detect_changed_python_files(settings.project_root, base_ref)

    if not paths:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_validate_changed", start)
        resp = success_response(
            "tapps_validate_changed",
            elapsed_ms,
            {
                "files_validated": 0,
                "all_gates_passed": True,
                "total_security_issues": 0,
                "results": [],
                "summary": "No changed Python files found.",
            },
        )
        return _with_nudges("tapps_validate_changed", resp)

    capped = len(paths) > MAX_BATCH_FILES
    extra_count = len(paths) - MAX_BATCH_FILES if capped else 0
    paths = paths[:MAX_BATCH_FILES]

    scorer = CodeScorer()
    results: list[dict[str, Any]] = []

    for path in paths:
        file_result: dict[str, Any] = {"file_path": str(path)}
        try:
            score = await scorer.score_file(path)
            file_result["overall_score"] = round(score.overall_score, 2)

            gate = evaluate_gate(score, preset=preset)
            file_result["gate_passed"] = gate.passed
            if gate.failures:
                file_result["gate_failures"] = [f.model_dump() for f in gate.failures]

            if include_security:
                from tapps_mcp.security.security_scanner import run_security_scan

                sec = run_security_scan(
                    str(path),
                    scan_secrets=True,
                    cwd=str(settings.project_root),
                    timeout=settings.tool_timeout,
                )
                file_result["security_passed"] = sec.passed
                file_result["security_issues"] = sec.total_issues
        except Exception as exc:
            file_result["errors"] = [str(exc)]

        results.append(file_result)

    all_passed = all(r.get("gate_passed", False) for r in results)
    total_sec = sum(r.get("security_issues", 0) for r in results)

    summary = format_batch_summary(results)
    if capped:
        summary += f" ({extra_count} additional files not validated - cap {MAX_BATCH_FILES})"

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_validate_changed", start, gate_passed=all_passed)

    resp = success_response(
        "tapps_validate_changed",
        elapsed_ms,
        {
            "files_validated": len(results),
            "all_gates_passed": all_passed,
            "total_security_issues": total_sec,
            "results": results,
            "summary": summary,
        },
    )
    return _with_nudges("tapps_validate_changed", resp)


def tapps_session_start(
    project_root: str = "",
) -> dict[str, Any]:
    """REQUIRED as the FIRST call in every session. Combines server info
    and project profile detection in a single call. Skipping means all
    subsequent tools lack project context and recommendations are generic.

    Args:
        project_root: Project root path (default: server's configured root).
    """
    from tapps_mcp.server import (
        _record_call,
        _record_execution,
        _with_nudges,
        tapps_project_profile,
        tapps_server_info,
    )

    start = time.perf_counter_ns()
    _record_call("tapps_session_start")

    info = tapps_server_info()
    profile = tapps_project_profile(project_root=project_root)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_session_start", start)

    data: dict[str, Any] = {
        "server": info["data"]["server"],
        "configuration": info["data"]["configuration"],
        "installed_checkers": info["data"]["installed_checkers"],
        "diagnostics": info["data"]["diagnostics"],
        "quick_start": info["data"].get("quick_start", []),
        "critical_rules": info["data"].get("critical_rules", []),
        "pipeline": info["data"]["pipeline"],
    }

    if profile.get("success"):
        data["project_profile"] = profile["data"]
    else:
        data["project_profile"] = None
        err = profile.get("error")
        if isinstance(err, dict):
            err_msg = err.get("message", "unknown")
        else:
            err_msg = str(err) if err is not None else "unknown"
        data["project_profile_error"] = err_msg

    resp = success_response("tapps_session_start", elapsed_ms, data)
    return _with_nudges("tapps_session_start", resp)


async def tapps_init(
    create_handoff: bool = True,
    create_runlog: bool = True,
    create_agents_md: bool = True,
    create_tech_stack_md: bool = True,
    platform: str = "",
    verify_server: bool = True,
    install_missing_checkers: bool = False,
    warm_cache_from_tech_stack: bool = True,
    warm_expert_rag_from_tech_stack: bool = True,
    overwrite_platform_rules: bool = False,
    overwrite_agents_md: bool = False,
    agent_teams: bool = False,
    dry_run: bool = False,
    verify_only: bool = False,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Bootstrap TAPPS pipeline in the current project.

    Verifies server info and optionally installs missing checkers (ruff, mypy,
    bandit, radon). Creates handoff, runlog, AGENTS.md, and TECH_STACK.md.
    Optionally warms the Context7 cache from the detected tech stack.
    Optionally generates platform-specific rule files for Claude Code or Cursor.

    Call once per project to set up the pipeline workflow.

    Duration: Full init can take 10-35+ seconds (profile, templates, cache/RAG
    warming). For timeout-prone MCP clients, use dry_run or verify_only first,
    or set warm_cache_from_tech_stack=False and warm_expert_rag_from_tech_stack=False
    for a faster init (~5-15s). See docs/MCP_CLIENT_TIMEOUTS.md for timeout guidance.

    Args:
        create_handoff: Create docs/TAPPS_HANDOFF.md template.
        create_runlog: Create docs/TAPPS_RUNLOG.md template.
        create_agents_md: Create AGENTS.md with AI assistant workflow (if missing).
        create_tech_stack_md: Create or update TECH_STACK.md from project profile.
        platform: Generate platform rules. One of: "claude", "cursor", "".
        verify_server: Verify server info and installed checkers.
        install_missing_checkers: Attempt to pip-install missing checkers (opt-in).
        warm_cache_from_tech_stack: Pre-fetch docs for tech stack libraries into cache.
        warm_expert_rag_from_tech_stack: Pre-build expert RAG indices for relevant domains.
        overwrite_platform_rules: When ``True``, refresh platform rule files even if
            they already exist (useful when templates are upgraded).
        overwrite_agents_md: When ``True``, replace AGENTS.md entirely with the latest
            template. When ``False`` (default), validate and smart-merge missing
            sections/tools.
        agent_teams: When ``True`` and platform is ``"claude"``, generate Agent Teams
            hooks (TeammateIdle, TaskCompleted) for quality watchdog teammate.
        dry_run: When ``True``, compute and return what would be created without
            writing files or warming caches. Keeps dry_run lightweight (~2-5s).
        verify_only: When ``True``, run only server verification and return (~1-3s).
            Use for quick connectivity/checker checks without creating files.
    """
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_init")

    # If context available, try elicitation confirmation (skip for verify_only/dry_run)
    if ctx is not None and not verify_only and not dry_run:
        from tapps_mcp.common.elicitation import elicit_init_confirmation

        settings_peek = load_settings()
        confirmed = await elicit_init_confirmation(ctx, str(settings_peek.project_root))
        if confirmed is False:
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            _record_execution("tapps_init", start, status="cancelled")
            return success_response(
                "tapps_init",
                elapsed_ms,
                {"cancelled": True, "message": "tapps_init cancelled — no files were written."},
            )
        # confirmed is True or None (unsupported) — proceed normally

    from tapps_mcp.pipeline.init import bootstrap_pipeline

    settings = load_settings()
    result = bootstrap_pipeline(
        settings.project_root,
        create_handoff=create_handoff,
        create_runlog=create_runlog,
        create_agents_md=create_agents_md,
        create_tech_stack_md=create_tech_stack_md,
        platform=platform,
        verify_server=verify_server,
        install_missing_checkers=install_missing_checkers,
        warm_cache_from_tech_stack=warm_cache_from_tech_stack,
        warm_expert_rag_from_tech_stack=warm_expert_rag_from_tech_stack,
        overwrite_platform_rules=overwrite_platform_rules,
        overwrite_agents_md=overwrite_agents_md,
        agent_teams=agent_teams,
        dry_run=dry_run,
        verify_only=verify_only,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_init",
        start,
        status="success" if not result["errors"] else "failed",
    )

    resp = success_response("tapps_init", elapsed_ms, result)
    resp["success"] = not result["errors"]
    return _with_nudges("tapps_init", resp)


def register(mcp_instance: FastMCP) -> None:
    """Register pipeline/validation tools on *mcp_instance*."""
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_validate_changed)
    mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_session_start)
    mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_init)
