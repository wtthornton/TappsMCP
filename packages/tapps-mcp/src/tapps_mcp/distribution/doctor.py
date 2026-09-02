"""TappsMCP doctor: diagnose configuration, rules, and connectivity.

Split under TAP-5606 — this module is a thin facade over eleven siblings:

* :mod:`tapps_mcp.distribution.doctor_result` — :class:`CheckResult` (leaf).
* :mod:`tapps_mcp.distribution.doctor_install` — binary/version drift,
  blue/green deploy, and local-checkout install-source checks.
* :mod:`tapps_mcp.distribution.doctor_mcp` — MCP host config and brain-MCP
  entry checks (+ :func:`strip_brain_mcp_entries`).
* :mod:`tapps_mcp.distribution.doctor_fleet` — HTTP fleet liveness,
  crash-loop, and transport-drift checks.
* :mod:`tapps_mcp.distribution.doctor_platform` — retired hooks,
  CLAUDE.md/AGENTS.md stamps, Cursor/scoped rules, and linear-issue skill.
* :mod:`tapps_mcp.distribution.doctor_hooks` — AGENTS.md, Karpathy
  guidelines, ``.tapps-mcp.yaml``, and config-scope checks.
* :mod:`tapps_mcp.distribution.doctor_hooks_cursor` — Claude settings,
  managed-JSON parseability, and Cursor hooks/zombie-cleanup checks.
* :mod:`tapps_mcp.distribution.doctor_pipeline` — gate-mode detection,
  skill-deployment checks, and session-handoff checks.
* :mod:`tapps_mcp.distribution.doctor_telemetry` — lookup-docs discipline,
  Cursor loop-metrics/stop-gate telemetry, cache-gate/git-hooks hints.
* :mod:`tapps_mcp.distribution.doctor_telemetry_pipeline` — pipeline
  enforcement recommendations (git hooks / cache-gate block from loop-metrics).
* :mod:`tapps_mcp.distribution.doctor_skills` — managed multi-file skill
  freshness checks (orchestration-prompt, wayfind, validation-contract).
* :mod:`tapps_mcp.distribution.doctor_brain_http` — tapps-brain HTTP auth,
  capability-profile probe, and probe-latency checks.
* :mod:`tapps_mcp.distribution.doctor_brain_version` — tapps-brain health
  summary and version-floor/delta checks.
* :mod:`tapps_mcp.distribution.doctor_nlt` — NLT tool-budget and
  call-graph checks.
* :mod:`tapps_mcp.distribution.doctor_memory` — memory-config, session
  sentinel, dual-memory-server guard, and quality-tools checks.
* :mod:`tapps_mcp.distribution.doctor_consumer` — consumer requirements
  summary, secrets, and report-studio/Linear-SDLC checks.
* :mod:`tapps_mcp.distribution.doctor_context7` — operator secrets,
  brain-docs, and Context7 checks.
* :mod:`tapps_mcp.distribution.doctor_runner` — the check registry
  (:func:`_collect_checks`) and the two public entry points
  (:func:`run_doctor`, :func:`run_doctor_structured`).

This facade re-exports the public (and doctor-private) API so existing
imports of ``tapps_mcp.distribution.doctor`` stay stable. It also keeps
``shutil``, ``sys``, and ``Path`` importable here: existing tests patch
``tapps_mcp.distribution.doctor.shutil.which`` / ``.sys.platform`` /
``.Path.home``, which mutate the real shared ``shutil``/``sys`` module
objects and the real ``pathlib.Path`` class — those patches work from any
module that also imports them, so keeping the names here (unused by this
module itself) preserves that test-time behavior without touching the
sibling modules that actually call them.
"""

from __future__ import annotations

import shutil as shutil
import sys as sys
from pathlib import Path as Path

import httpx as httpx

from tapps_mcp.distribution.doctor_brain_http import (
    _TOOLS_CATALOG_CACHE as _TOOLS_CATALOG_CACHE,
)
from tapps_mcp.distribution.doctor_brain_http import (
    _fetch_exposed_tools as _fetch_exposed_tools,
)
from tapps_mcp.distribution.doctor_brain_http import (
    _fetch_exposed_tools_rest as _fetch_exposed_tools_rest,
)
from tapps_mcp.distribution.doctor_brain_http import (
    _parse_histogram_quantiles as _parse_histogram_quantiles,
)
from tapps_mcp.distribution.doctor_brain_http import (
    _probe_warm_cache_status as _probe_warm_cache_status,
)
from tapps_mcp.distribution.doctor_brain_http import (
    _ProfileProbeError as _ProfileProbeError,
)
from tapps_mcp.distribution.doctor_brain_http import (
    _ProfileProbeFallbackError as _ProfileProbeFallbackError,
)
from tapps_mcp.distribution.doctor_brain_http import (
    _run_auth_probe as _run_auth_probe,
)
from tapps_mcp.distribution.doctor_brain_http import (
    check_brain_http_auth,
    check_brain_probe_latency,
    check_brain_profile,
    check_stale_exe_backups,
    check_tapps_brain,
)
from tapps_mcp.distribution.doctor_brain_version import (
    _parse_version_tuple as _parse_version_tuple,
)
from tapps_mcp.distribution.doctor_brain_version import (
    _read_brain_floor_pin as _read_brain_floor_pin,
)
from tapps_mcp.distribution.doctor_brain_version import (
    _requires as _requires,
)
from tapps_mcp.distribution.doctor_brain_version import (
    check_brain_health,
    check_brain_version_delta,
    check_brain_version_floor,
)
from tapps_mcp.distribution.doctor_consumer import (
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
    _brain_http_url_for_checks as _brain_http_url_for_checks,
)
from tapps_mcp.distribution.doctor_mcp import (
    check_brain_mcp_entry,
    check_claude_code_project,
    check_claude_code_user,
    check_cursor_config,
    check_json_config,
    check_mcp_client_config,
    check_mcp_config_unresolved_project_root,
    check_vscode_config,
    strip_brain_mcp_entries,
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
    _tapps_skill_bases as _tapps_skill_bases,
)
from tapps_mcp.distribution.doctor_pipeline import (
    check_deprecated_wrapper_skills,
    check_finish_task_skill,
    check_session_handoff_schema,
    check_session_handoff_skills,
    check_tapps_memory_skill,
)
from tapps_mcp.distribution.doctor_platform import (
    check_agent_to_agent_rule,
    check_agents_md_stamp_matches_package,
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
    check_upgrade_skip_tokens,
)
from tapps_mcp.distribution.doctor_result import CheckResult
from tapps_mcp.distribution.doctor_runner import (
    _collect_checks as _collect_checks,
)
from tapps_mcp.distribution.doctor_runner import (
    _safe_check as _safe_check,
)
from tapps_mcp.distribution.doctor_runner import (
    run_doctor,
    run_doctor_structured,
)
from tapps_mcp.distribution.doctor_skills import (
    check_orchestration_prompt_skill_current,
    check_skill_asset_drift,
    check_skill_mirror_parity,
    check_validation_contract_skill_current,
    check_wayfind_skill_current,
)
from tapps_mcp.distribution.doctor_telemetry import (
    _read_engagement_level as _read_engagement_level,
)
from tapps_mcp.distribution.doctor_telemetry import (
    check_cache_gate_block_hint,
    check_completion_gate_violations,
    check_continuous_learning_v2_skill,
    check_cursor_loop_metrics_telemetry,
    check_cursor_stop_completion_gate,
    check_install_git_hooks_hint,
    check_lookup_docs_discipline,
)
from tapps_mcp.distribution.doctor_telemetry_pipeline import (
    check_pipeline_enforce_recommendations,
)

__all__ = [
    "CheckResult",
    "check_agent_to_agent_rule",
    "check_agents_md",
    "check_agents_md_stamp_matches_package",
    "check_autonomy_rule",
    "check_binary_on_path",
    "check_binary_version_mismatch",
    "check_blue_green_deploy",
    "check_brain_docs_tools",
    "check_brain_health",
    "check_brain_http_auth",
    "check_brain_mcp_entry",
    "check_brain_probe_latency",
    "check_brain_profile",
    "check_brain_version_delta",
    "check_brain_version_floor",
    "check_cache_gate_block_hint",
    "check_call_graph_index_cache",
    "check_call_graph_tools_profile",
    "check_claude_code_project",
    "check_claude_code_user",
    "check_claude_hook_scripts",
    "check_claude_md",
    "check_claude_md_stamp",
    "check_claude_settings",
    "check_completion_gate_violations",
    "check_config_files_rule",
    "check_consumer_context7_env",
    "check_context7_live",
    "check_continuous_learning_v2_skill",
    "check_cursor_config",
    "check_cursor_loop_metrics_telemetry",
    "check_cursor_mcp_zombie_cleanup",
    "check_cursor_rules",
    "check_cursor_stop_completion_gate",
    "check_deprecated_wrapper_skills",
    "check_docsmcp_binary_version_mismatch",
    "check_dual_memory_server",
    "check_finish_task_skill",
    "check_fleet_crash_loop",
    "check_global_local_install",
    "check_hooks",
    "check_http_fleet_liveness",
    "check_install_git_hooks_hint",
    "check_json_config",
    "check_karpathy_guidelines",
    "check_legacy_doc_cache",
    "check_linear_issue_skill_current",
    "check_linear_sdlc",
    "check_linear_standards_rule",
    "check_lookup_docs_discipline",
    "check_managed_json_parseable",
    "check_mcp_client_config",
    "check_mcp_config_unresolved_project_root",
    "check_mcp_operator_secrets",
    "check_mcp_tool_budget",
    "check_mcp_transport_drift",
    "check_memory_cli_http_mode",
    "check_memory_pipeline_config",
    "check_memory_profile_resolvable",
    "check_nlt_partial_enablement",
    "check_orchestration_prompt_skill_current",
    "check_pipeline_enforce_recommendations",
    "check_plaintext_secrets",
    "check_pretooluse_matchers",
    "check_quality_tools",
    "check_report_studio",
    "check_retired_hooks",
    "check_scope_recommendation",
    "check_security_rule",
    "check_session_handoff_schema",
    "check_session_handoff_skills",
    "check_session_sentinel",
    "check_skill_asset_drift",
    "check_skill_mirror_parity",
    "check_stale_exe_backups",
    "check_tapps_brain",
    "check_tapps_mcp_yaml",
    "check_tapps_memory_skill",
    "check_test_quality_rule",
    "check_upgrade_skip_tokens",
    "check_uv_path_mismatch",
    "check_validation_contract_skill_current",
    "check_vscode_config",
    "check_wayfind_skill_current",
    "run_doctor",
    "run_doctor_structured",
    "strip_brain_mcp_entries",
]
