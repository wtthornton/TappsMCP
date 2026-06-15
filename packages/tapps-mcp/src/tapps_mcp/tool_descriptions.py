"""Concise MCP tool descriptions for tapps-mcp (TAP-1963).

Long-form guidance lives in AGENTS.md, server ``instructions``, and handler
docstrings. These strings are the wire catalog only.
"""

from __future__ import annotations

MEDIAN_MAX_CHARS = 200
HARD_MAX_CHARS = 500

TOOL_DESCRIPTIONS: dict[str, str] = {
    "tapps_server_info": (
        "Lightweight discovery: version, tool list, installed checkers, and config."
    ),
    "tapps_session_start": (
        "First call each session: bootstrap project context, brain health, and pipeline state."
    ),
    "tapps_session_end": (
        "End-of-session brain feedback loop: flush events and optional session summary."
    ),
    "tapps_handoff_save": (
        "Write session-handoff.md, mirror full markdown to brain, lint schema; optional session-end."
    ),
    "tapps_score_file": (
        "Score one file across 7 quality categories (0-100) with per-category breakdown."
    ),
    "tapps_security_scan": (
        "Run Bandit and secret detection on one Python file; returns findings by severity."
    ),
    "tapps_quality_gate": (
        "Score one file and return a binding pass/fail verdict against the active preset."
    ),
    "tapps_lookup_docs": (
        "Fetch library documentation and examples via Context7 or local llms.txt cache."
    ),
    "tapps_validate_config": (
        "Validate Dockerfile, docker-compose, GitHub Actions, and other infra config files."
    ),
    "tapps_validate_changed": (
        "Batch score + quality gate across comma-separated changed file paths."
    ),
    "tapps_quick_check": (
        "Fast post-edit bundle: score + gate + basic security for one Python file."
    ),
    "tapps_checklist": (
        "Verify required TAPPS pipeline tools ran for the current task type."
    ),
    "tapps_session_notes": (
        "Save or recall short-lived session notes in the local KV store."
    ),
    "tapps_memory": (
        "Slim brain memory on nlt-memory: search, save, get, health, related (not full 42-action catalog)."
    ),
    "tapps_impact_analysis": (
        "Module-level import blast radius before API changes (symbol callers: tapps_call_graph, ADR-0017)."
    ),
    "tapps_report": (
        "Generate a quality report for one file or the whole project (JSON/Markdown/HTML)."
    ),
    "tapps_init": (
        "Bootstrap TAPPS scaffolding: AGENTS.md, hooks, agents, skills, and MCP config."
    ),
    "tapps_upgrade": (
        "Refresh tapps-managed generated files after a tapps-mcp version upgrade."
    ),
    "tapps_doctor": (
        "Diagnose MCP config, checker install, brain connectivity, and hook wiring."
    ),
    "tapps_set_engagement_level": (
        "Persist engagement level (high/medium/low) to .tapps-mcp.yaml."
    ),
    "tapps_dashboard": (
        "Render TappsMCP metrics dashboard: usage, gate pass rate, and trends."
    ),
    "tapps_stats": (
        "Per-tool usage statistics: call counts, success rates, and latency percentiles."
    ),
    "tapps_feedback": (
        "Record thumbs-up/down on a tool response for adaptive learning."
    ),
    "tapps_usage": (
        "Session gap report: tools called vs TAPPS pipeline expectations."
    ),
    "tapps_dead_code": (
        "Find unused Python functions, classes, imports, and variables (vulture-backed)."
    ),
    "tapps_dependency_scan": (
        "Scan project dependencies for known CVEs via pip-audit."
    ),
    "tapps_dependency_graph": (
        "Build import graph, report circular imports, and module coupling metrics."
    ),
    "tapps_audit_campaign": (
        "Plan, dispatch, or convert a file-scope audit campaign to a fix plan."
    ),
    "tapps_pipeline": (
        "Show TAPPS pipeline stage progress and the next recommended tool call."
    ),
    "tapps_decompose": (
        "Break a vague task into ordered, verifiable TAPPS tool-call steps."
    ),
    "tapps_linear_snapshot_get": (
        "Cache-first Linear read: return cached issues or signal a cache miss."
    ),
    "tapps_linear_snapshot_put": (
        "Write a Linear issue list into the local snapshot cache."
    ),
    "tapps_linear_snapshot_invalidate": (
        "Evict cached Linear snapshots for a team/project prefix."
    ),
    "tapps_linear_count": (
        "Count Linear issues in a cached snapshot slice without a live API call."
    ),
    "tapps_release_update": (
        "Generate and validate a Linear release-update body from CHANGELOG/git."
    ),
    "brain_propose_hive_elevation": (
        "Propose promoting a memory key to hive scope (operator approval required)."
    ),
    "brain_approve_hive_elevation": (
        "Approve a pending hive elevation proposal by proposal_id."
    ),
    "tapps_linear_list_issues": (
        "Pre-list gate: verify a recent snapshot_get before Linear list_issues."
    ),
    "tapps_finding_to_story": (
        "Convert an audit finding into an agent-ready Linear fix-story payload."
    ),
    "tapps_audit_close_coverage": (
        "Close an audit finding by updating its brain coverage record after a fix."
    ),
}
