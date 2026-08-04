"""Doctor check registry + CLI/MCP entry points (TAP-5606 split).

Wires every ``check_*`` function from the ``doctor_*`` sibling modules into
:func:`_collect_checks`, then exposes :func:`run_doctor` (CLI report) and
:func:`run_doctor_structured` (MCP tool payload) — the two public entry
points every other doctor caller uses.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from tapps_core.common.logging import get_logger
from tapps_mcp.distribution.doctor_brain_http import (
    check_brain_http_auth,
    check_brain_probe_latency,
    check_brain_profile,
    check_stale_exe_backups,
    check_tapps_brain,
)
from tapps_mcp.distribution.doctor_brain_version import (
    check_brain_health,
    check_brain_version_delta,
    check_brain_version_floor,
)
from tapps_mcp.distribution.doctor_consumer import (
    _build_requirements_summary,
    check_legacy_doc_cache,
    check_linear_sdlc,
    check_plaintext_secrets,
    check_report_studio,
    check_uv_path_mismatch,
)
from tapps_mcp.distribution.doctor_context7 import (
    check_brain_docs_tools,
    check_consumer_context7_env,
    check_context7_live,
    check_mcp_operator_secrets,
)
from tapps_mcp.distribution.doctor_fleet import (
    check_fleet_crash_loop,
    check_http_fleet_liveness,
    check_mcp_transport_drift,
)
from tapps_mcp.distribution.doctor_hooks import (
    check_agents_md,
    check_karpathy_guidelines,
    check_scope_recommendation,
    check_tapps_mcp_yaml,
)
from tapps_mcp.distribution.doctor_hooks_cursor import (
    check_claude_settings,
    check_cursor_mcp_zombie_cleanup,
    check_hooks,
    check_managed_json_parseable,
)
from tapps_mcp.distribution.doctor_install import (
    check_binary_on_path,
    check_binary_version_mismatch,
    check_blue_green_deploy,
    check_docsmcp_binary_version_mismatch,
    check_global_local_install,
)
from tapps_mcp.distribution.doctor_mcp import (
    check_brain_mcp_entry,
    check_claude_code_project,
    check_claude_code_user,
    check_cursor_config,
    check_mcp_client_config,
    check_mcp_config_unresolved_project_root,
    check_vscode_config,
)
from tapps_mcp.distribution.doctor_memory import (
    check_dual_memory_server,
    check_memory_cli_http_mode,
    check_memory_pipeline_config,
    check_memory_profile_resolvable,
    check_quality_tools,
    check_session_sentinel,
)
from tapps_mcp.distribution.doctor_nlt import (
    check_call_graph_index_cache,
    check_call_graph_tools_profile,
    check_mcp_tool_budget,
    check_nlt_partial_enablement,
)
from tapps_mcp.distribution.doctor_pipeline import (
    check_deprecated_wrapper_skills,
    check_finish_task_skill,
    check_session_handoff_schema,
    check_session_handoff_skills,
    check_tapps_memory_skill,
)
from tapps_mcp.distribution.doctor_platform import (
    check_autonomy_rule,
    check_claude_hook_scripts,
    check_claude_md,
    check_claude_md_stamp,
    check_config_files_rule,
    check_cursor_rules,
    check_linear_issue_skill_current,
    check_linear_standards_rule,
    check_pretooluse_matchers,
    check_retired_hooks,
    check_security_rule,
    check_test_quality_rule,
)
from tapps_mcp.distribution.doctor_result import CheckResult, doctor_facade_attr
from tapps_mcp.distribution.doctor_skills import (
    check_orchestration_prompt_skill_current,
    check_validation_contract_skill_current,
    check_wayfind_skill_current,
)
from tapps_mcp.distribution.doctor_telemetry import (
    _read_engagement_level,
    check_cache_gate_block_hint,
    check_continuous_learning_v2_skill,
    check_cursor_loop_metrics_telemetry,
    check_cursor_stop_completion_gate,
    check_install_git_hooks_hint,
    check_lookup_docs_discipline,
)
from tapps_mcp.distribution.doctor_telemetry_pipeline import (
    check_pipeline_enforce_recommendations,
)

log = get_logger(__name__)


def _safe_check(name: str, fn: Callable[[], CheckResult]) -> CheckResult:
    """Run one doctor check; convert crashes into a failed CheckResult."""
    try:
        return fn()
    except Exception as exc:
        log.exception("doctor_check_crashed", check=name)
        return CheckResult(name, False, f"Check crashed: {type(exc).__name__}: {exc}")


def _collect_checks(root: Path, *, quick: bool = False) -> list[CheckResult]:
    from tapps_mcp.distribution import context_budget as _cb

    """Collect all diagnostic checks for the given project root.

    Args:
        root: Project root directory.
        quick: When True, skip quality tool version checks for faster results.
    """
    specs: list[tuple[str, Callable[[], CheckResult]]] = [
        ("tapps-mcp binary", check_binary_on_path),
        ("tapps-mcp binary version", check_binary_version_mismatch),
        ("docsmcp binary version", check_docsmcp_binary_version_mismatch),
        ("blue-green deploy", check_blue_green_deploy),
        ("global/local install", check_global_local_install),
        ("Claude Code (user)", lambda: check_claude_code_user(project_root=root)),
        ("Claude Code (project)", lambda: check_claude_code_project(root)),
        ("Cursor config", lambda: check_cursor_config(root)),
        ("VS Code config", lambda: check_vscode_config(root)),
        ("MCP transport drift", lambda: check_mcp_transport_drift(root)),
        ("HTTP fleet liveness", lambda: check_http_fleet_liveness(root)),
        ("Fleet crash loop", check_fleet_crash_loop),
        ("MCP client config", lambda: check_mcp_client_config(root)),
        ("MCP tool budget", lambda: check_mcp_tool_budget(root)),
        ("CLAUDE.md size", lambda: _cb.check_claude_md_size(root)),
        ("AGENTS.md size", lambda: _cb.check_agents_md_size(root)),
        ("alwaysApply rules weight", lambda: _cb.check_always_apply_rules_weight(root)),
        ("Skill inventory budget", lambda: _cb.check_skill_inventory_budget(root)),
        ("Karpathy dual install", lambda: _cb.check_karpathy_dual_install(root)),
        ("Call graph tools profile", lambda: check_call_graph_tools_profile(root)),
        (
            "Call graph index cache",
            lambda: check_call_graph_index_cache(root),
        ),
        ("NLT partial enablement", lambda: check_nlt_partial_enablement(root)),
        (
            "MCP unresolved project_root",
            lambda: check_mcp_config_unresolved_project_root(root),
        ),
        ("Brain MCP entry", lambda: check_brain_mcp_entry(root)),
        ("Scope recommendation", lambda: check_scope_recommendation(root)),
        ("CLAUDE.md rules", lambda: check_claude_md(root)),
        ("CLAUDE.md stamp", lambda: check_claude_md_stamp(root)),
        ("Cursor rules", lambda: check_cursor_rules(root)),
        ("Linear standards rule", lambda: check_linear_standards_rule(root)),
        ("Retired hooks", lambda: check_retired_hooks(root)),
        ("Autonomy rule", lambda: check_autonomy_rule(root)),
        ("Security rule", lambda: check_security_rule(root)),
        ("Test quality rule", lambda: check_test_quality_rule(root)),
        ("Config files rule", lambda: check_config_files_rule(root)),
        ("linear-issue skill", lambda: check_linear_issue_skill_current(root)),
        (
            "orchestration-prompt skill",
            lambda: check_orchestration_prompt_skill_current(root),
        ),
        (
            "tapps-wayfind skill",
            lambda: check_wayfind_skill_current(root),
        ),
        (
            "tapps-validation-contract skill",
            lambda: check_validation_contract_skill_current(root),
        ),
        ("finish-task skill", lambda: check_finish_task_skill(root)),
        ("Deprecated wrapper skills", lambda: check_deprecated_wrapper_skills(root)),
        ("tapps-memory skill", lambda: check_tapps_memory_skill(root)),
        ("Session handoff skills", lambda: check_session_handoff_skills(root)),
        ("Session handoff schema", lambda: check_session_handoff_schema(root)),
        ("Cache gate block hint", lambda: check_cache_gate_block_hint(root)),
        ("Install git hooks hint", lambda: check_install_git_hooks_hint(root)),
        (
            "Pipeline enforce recommendations",
            lambda: check_pipeline_enforce_recommendations(root),
        ),
        ("lookup_docs discipline", lambda: check_lookup_docs_discipline(root)),
        (
            "Cursor loop metrics telemetry",
            lambda: check_cursor_loop_metrics_telemetry(root),
        ),
        (
            "Cursor stop completion gate",
            lambda: check_cursor_stop_completion_gate(root),
        ),
        (
            "continuous-learning-v2 skill",
            lambda: check_continuous_learning_v2_skill(root),
        ),
        ("PreToolUse matchers", lambda: check_pretooluse_matchers(root)),
        ("AGENTS.md", lambda: check_agents_md(root)),
        ("Karpathy guidelines", lambda: check_karpathy_guidelines(root)),
        (".tapps-mcp.yaml", lambda: check_tapps_mcp_yaml(root)),
        ("Claude settings", lambda: check_claude_settings(root)),
        ("Managed JSON parseable", lambda: check_managed_json_parseable(root)),
        ("Claude hook scripts", lambda: check_claude_hook_scripts(root)),
        ("Hooks", lambda: check_hooks(root)),
        ("Cursor MCP zombie cleanup", lambda: check_cursor_mcp_zombie_cleanup(root)),
        ("Stale exe backups", check_stale_exe_backups),
        ("tapps-brain", check_tapps_brain),
        ("Brain HTTP auth", lambda: check_brain_http_auth(root)),
        ("Brain profile", lambda: check_brain_profile(root)),
        ("Brain probe latency", lambda: check_brain_probe_latency(root)),
        ("Brain health", lambda: check_brain_health(root)),
        ("Brain version floor", lambda: check_brain_version_floor(root)),
        ("Brain version delta", lambda: check_brain_version_delta(root)),
        ("Session sentinel", lambda: check_session_sentinel(root)),
        ("Memory pipeline config", lambda: check_memory_pipeline_config(root)),
        ("Memory profile resolvable", lambda: check_memory_profile_resolvable(root)),
        ("Memory CLI HTTP mode", lambda: check_memory_cli_http_mode(root)),
        ("Dual memory server", lambda: check_dual_memory_server(root)),
        ("Plaintext secrets", lambda: check_plaintext_secrets(root)),
        ("uv path mismatch", lambda: check_uv_path_mismatch(root)),
        ("Linear SDLC", lambda: check_linear_sdlc(root)),
        ("report_studio", lambda: check_report_studio(root)),
        ("Legacy doc cache", lambda: check_legacy_doc_cache(root)),
        ("Brain docs tools", lambda: check_brain_docs_tools(root)),
        ("MCP operator secrets", lambda: check_mcp_operator_secrets(root)),
        ("Consumer Context7 env", lambda: check_consumer_context7_env(root)),
        ("Context7 live", lambda: check_context7_live(root, quick=quick)),
    ]
    checks = [_safe_check(name, fn) for name, fn in specs]
    if quick:
        checks.append(
            CheckResult(
                "Quality tools",
                True,
                "Skipped (quick mode)",
                "Run without --quick for full tool version checks",
            )
        )
    else:
        # check_quality_tools() already ran to completion here, so wrapping each
        # pre-computed result in _safe_check added no protection.
        checks.extend(check_quality_tools())
    return checks


def run_doctor_structured(*, project_root: str = ".", quick: bool = False) -> dict[str, Any]:
    """Run all diagnostic checks and return structured results.

    Returns a dict with ``checks``, ``pass_count``, ``fail_count``,
    ``all_passed``, and ``quick_mode`` for programmatic consumption (MCP tool).

    Args:
        project_root: Project root path.
        quick: When True, skip quality tool version checks.
    """
    root = Path(project_root).resolve()
    log.info("doctor_structured", project_root=str(root))

    checks = doctor_facade_attr("_collect_checks", _collect_checks)(root, quick=quick)

    results: list[dict[str, str | bool]] = []
    pass_count = 0
    fail_count = 0
    warn_count = 0
    for check in checks:
        entry: dict[str, str | bool] = {
            "name": check.name,
            "ok": check.ok,
            "severity": check.severity,
            "message": check.message,
        }
        if check.detail:
            entry["detail"] = check.detail
        results.append(entry)
        if check.severity == "pass":
            pass_count += 1
        elif check.severity == "warn":
            warn_count += 1
        else:
            fail_count += 1

    out: dict[str, Any] = {
        "checks": results,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "all_passed": fail_count == 0,
        "quick_mode": quick,
    }

    # Consumer requirements summary (Epic 50)
    out["requirements_summary"] = _build_requirements_summary(checks)

    # Report engagement level when configured (Epic 18.8)
    engagement = _read_engagement_level(root)
    if engagement is not None:
        out["llm_engagement_level"] = engagement
    return out


def run_doctor(*, project_root: str = ".", quick: bool = False) -> bool:
    """Run all diagnostic checks and print a summary.

    Returns ``True`` if all checks pass, ``False`` otherwise.

    Args:
        project_root: Project root path.
        quick: When True, skip quality tool version checks.
    """
    root = Path(project_root).resolve()
    log.info("doctor_command", project_root=str(root))

    checks = doctor_facade_attr("_collect_checks", _collect_checks)(root, quick=quick)

    # Print report
    click.echo("")
    click.echo(click.style("=== TappsMCP Doctor Report ===", bold=True))
    if quick:
        click.echo(click.style("  (Quick mode — tool version checks skipped)", fg="cyan"))
    click.echo("")

    pass_count = 0
    fail_count = 0
    warn_count = 0
    for check in checks:
        if check.severity == "pass":
            click.echo(click.style(f"  PASS  {check.name}: {check.message}", fg="green"))
            pass_count += 1
        elif check.severity == "warn":
            click.echo(click.style(f"  WARN  {check.name}: {check.message}", fg="yellow"))
            if check.detail:
                click.echo(f"        {check.detail}")
            warn_count += 1
        else:
            click.echo(click.style(f"  FAIL  {check.name}: {check.message}", fg="red"))
            if check.detail:
                click.echo(f"        {check.detail}")
            fail_count += 1

    engagement = _read_engagement_level(root)
    if engagement is not None:
        click.echo(click.style(f"  Config  llm_engagement_level: {engagement}", fg="cyan"))

    click.echo("")
    click.echo(f"Results: {pass_count} passed, {fail_count} failed, {warn_count} warnings")

    if fail_count == 0 and warn_count == 0:
        click.echo(click.style("All checks passed!", fg="green"))
    elif fail_count == 0:
        click.echo(
            click.style(
                f"{warn_count} warning(s) (advisory — non-blocking).",
                fg="yellow",
            )
        )
    else:
        click.echo(
            click.style(
                f"{fail_count} issue(s) found. Run the suggested commands to fix.",
                fg="yellow",
            )
        )

    # Consumer requirements summary (Epic 50)
    click.echo("")
    click.echo(click.style("=== Consumer Requirements Summary ===", bold=True))
    req_summary = _build_requirements_summary(checks)
    for req in req_summary:
        status = req["status"]
        if status == "pass":
            styled = click.style("PASS", fg="green")
        elif status == "fail":
            styled = click.style("FAIL", fg="red")
        elif status == "warn":
            styled = click.style("WARN", fg="yellow")
        elif status == "n/a":
            styled = click.style("N/A", fg="cyan")
        else:
            styled = click.style("INFO", fg="cyan")
        click.echo(f"  {req['requirement']}. {req['name']:24s} {styled}")
    click.echo("")
    click.echo("For the full consumer requirements checklist, see docs/TAPPS_MCP_REQUIREMENTS.md")

    return fail_count == 0
