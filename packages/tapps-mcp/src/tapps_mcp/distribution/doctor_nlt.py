"""Doctor checks for NLT tool budget and call-graph diagnostics (TAP-5606 split).

Covers the per-server eager-tool budget model (``_detect_server_tool_count``),
NLT partial-enablement / combined-budget WARNs, and call-graph MCP tool +
index cache checks. Memory pipeline, session sentinel, and quality-tools
checks live in :mod:`tapps_mcp.distribution.doctor_memory`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.distribution.doctor_result import CheckResult

log = get_logger(__name__)


def _resolved_mcp_bundle(project_root: Path) -> str:
    """Bundle from ``.tapps-mcp.yaml`` or inference from MCP config."""
    from tapps_mcp.distribution.nlt_mcp_config import normalize_mcp_bundle
    from tapps_mcp.tools.session_start_helpers import _infer_mcp_bundle

    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=project_root)
        if settings.mcp_bundle is not None:
            return normalize_mcp_bundle(settings.mcp_bundle)
    except Exception:
        log.debug("resolved_mcp_bundle_settings_failed", exc_info=True)
    return normalize_mcp_bundle(_infer_mcp_bundle(project_root))


# ---------------------------------------------------------------------------
# TAP-2026 / TAP-1989: per-server eager-tool budget
# ---------------------------------------------------------------------------

# Known preset tool counts — keep in sync with server.py (ALL_TOOL_NAMES,
# TAPPS_TOOL_PRESET_QUALITY, TAPPS_TOOL_PRESET_ADMIN).
# TAP-1986: counts reflect EAGER tools only (defer_loading=False).
# Non-daily-driver tools carry defer_loading=True and are loaded on-demand via Tool Search.
_TAPPS_MCP_MODE_TOOL_COUNTS: dict[str, int] = {
    # TAP-1986 set 8 eager; tapps_usage added in v3.11.0 (9); tapps_memory eager on full serve (10).
    # Eager set: session_start, validate_changed, score_file, quality_gate,
    # quick_check, lookup_docs, checklist, impact_analysis, usage, tapps_memory (10 total).
    # Deferred: 32 (full=42 total; quality=15 total; admin=13 total).
    "full": 10,  # 10 eager daily-driver tools; 32 deferred via Tool Search (42 total)
    "quality": 9,  # 9 eager (all 9 daily drivers are in the quality preset; 6 deferred)
    "admin": 1,  # 1 eager (tapps_usage); 12 deferred
}
_DOCS_MCP_TOOL_COUNT: int = 7  # TAP-1987: 7 eager tools on full serve; 35 deferred (42 total)
_DEFAULT_TOOL_BUDGET: int = 20


def _profile_flag_value(args: list[str]) -> str | None:
    """Return the value following a ``--profile`` flag in *args*, if present."""
    if "--profile" not in args:
        return None
    idx = args.index("--profile")
    if idx + 1 < len(args):
        return str(args[idx + 1])
    return None


def _tool_count_for_profile_flag(args: list[str]) -> int | None:
    """Return the eager-tool count for a bare ``--profile <nlt-server>`` flag."""
    from tapps_mcp.distribution.nlt_mcp_config import NLT_SERVER_EAGER_COUNTS

    profile = _profile_flag_value(args)
    if profile is not None and profile in NLT_SERVER_EAGER_COUNTS:
        return NLT_SERVER_EAGER_COUNTS[profile]
    return None


def _tool_count_for_tapps_mcp(args: list[str], command: str) -> int | None:
    """Return the eager-tool count for a tapps-mcp family command, if recognized."""
    if "tapps-mcp" in args and "serve" in args:
        mode = "full"
        if "--mode" in args:
            idx = args.index("--mode")
            if idx + 1 < len(args):
                mode = args[idx + 1]
        return _TAPPS_MCP_MODE_TOOL_COUNTS.get(mode, _TAPPS_MCP_MODE_TOOL_COUNTS["full"])
    # uvx tapps-mcp serve (no explicit "run")
    if command == "uvx" and "tapps-mcp" in args:
        return _TAPPS_MCP_MODE_TOOL_COUNTS["full"]
    return None


def _tool_count_for_tapps_platform(args: list[str]) -> int | None:
    """Return the eager-tool count for a tapps-platform NLT profile (Epic 109)."""
    from tapps_mcp.distribution.nlt_mcp_config import NLT_SERVER_EAGER_COUNTS

    if "tapps-platform" not in args or "serve" not in args:
        return None
    profile = _profile_flag_value(args)
    if profile is not None and profile in NLT_SERVER_EAGER_COUNTS:
        return NLT_SERVER_EAGER_COUNTS[profile]
    return None


def _detect_server_tool_count(server_name: str, server_cfg: dict[str, object]) -> int | None:
    """Return the eager-tool count for a known tapps-family MCP server, or None.

    Returns ``None`` for servers that require a live connection to probe
    (e.g. HTTP or unknown stdio servers).
    """
    from tapps_mcp.distribution.nlt_mcp_config import is_nlt_server_id, nlt_eager_count

    if is_nlt_server_id(server_name):
        return nlt_eager_count(server_name)

    raw_args = server_cfg.get("args", [])
    args: list[str] = list(raw_args) if isinstance(raw_args, list) else []
    command: str = str(server_cfg.get("command", ""))

    count = _tool_count_for_profile_flag(args)
    if count is not None:
        return count
    count = _tool_count_for_tapps_mcp(args, command)
    if count is not None:
        return count
    # docs-mcp family: "docsmcp" in args or command
    if "docsmcp" in args or "docsmcp" in command:
        return _DOCS_MCP_TOOL_COUNT
    return _tool_count_for_tapps_platform(args)


_CALL_GRAPH_TOOLS: frozenset[str] = frozenset({"tapps_call_graph", "tapps_diff_impact"})
_CALL_GRAPH_MIN_VERSION: str = "3.12.30"


def _project_uses_nlt_build(servers: dict[str, dict[str, object]]) -> bool:
    """True when MCP config enables nlt-build (or legacy nlt-code-quality)."""
    if "nlt-build" in servers or "nlt-code-quality" in servers:
        return True
    for cfg in servers.values():
        raw_args = cfg.get("args", [])
        args: list[str] = list(raw_args) if isinstance(raw_args, list) else []
        if "--profile" in args:
            idx = args.index("--profile")
            if idx + 1 < len(args) and str(args[idx + 1]) in {"nlt-build", "nlt-code-quality"}:
                return True
        command = str(cfg.get("command", ""))
        if "nlt-build-serve" in command or "nlt-code-quality-serve" in command:
            return True
    return False


def _resolve_nlt_build_allowed_tools(settings: Any) -> frozenset[str]:
    """Tools exposed by the nlt-build MCP server (ignores host process preset)."""
    from tapps_mcp.server import ALL_TOOL_NAMES, TOOL_PROFILE_NLT_BUILD

    if settings.enabled_tools:
        allowed = set(settings.enabled_tools) & ALL_TOOL_NAMES
    else:
        allowed = set(TOOL_PROFILE_NLT_BUILD)
    allowed -= set(settings.disabled_tools)
    return frozenset(allowed)


def check_call_graph_tools_profile(root: Path) -> CheckResult:
    """Epic 114: WARN when call-graph MCP tools are stripped or package is too old."""
    from packaging.version import Version

    from tapps_core.config.settings import load_settings
    from tapps_mcp import __version__

    servers = _collect_project_mcp_servers(root)
    if not _project_uses_nlt_build(servers):
        return CheckResult(
            "Call graph tools",
            True,
            "No nlt-build MCP server configured (skipped)",
        )

    if Version(__version__) < Version(_CALL_GRAPH_MIN_VERSION):
        return CheckResult(
            "Call graph tools",
            False,
            (
                f"tapps-mcp {__version__} < {_CALL_GRAPH_MIN_VERSION} — "
                "call graph unavailable; reinstall globals and reload MCP"
            ),
            "uv tool install --reinstall --from <checkout>/packages/tapps-mcp tapps-mcp",
        )

    try:
        settings = load_settings(project_root=root)
    except Exception as exc:
        return CheckResult(
            "Call graph tools",
            True,
            f"Skipped (could not load settings: {exc})",
        )

    allowed = _resolve_nlt_build_allowed_tools(settings)
    missing = _CALL_GRAPH_TOOLS - allowed
    if missing:
        return CheckResult(
            "Call graph tools",
            False,
            f"Stripped from nlt-build profile: {', '.join(sorted(missing))}",
            "Remove from disabled_tools or widen enabled_tools in .tapps-mcp.yaml",
        )

    return CheckResult(
        "Call graph tools",
        True,
        "tapps_call_graph and tapps_diff_impact registered on nlt-build",
    )


def check_call_graph_index_cache(root: Path) -> CheckResult:
    """Epic 114: informational call-graph cache status (never fails on missing cache)."""
    from tapps_mcp.project.call_graph_cache import (
        load_call_graph_index,
        prune_call_graph_cache,
        summarize_call_graph_cache,
    )
    from tapps_mcp.project.call_graph_types import CALL_GRAPH_CACHE_REL

    cache_path = root / CALL_GRAPH_CACHE_REL
    if not cache_path.is_file():
        return CheckResult(
            "Call graph index",
            True,
            "No cache yet (normal until first tapps_call_graph or tapps_diff_impact call)",
        )

    cached = load_call_graph_index(root)
    if cached is None:
        return CheckResult(
            "Call graph index",
            True,
            "Cache file unreadable — will rebuild on next graph tool call",
            str(cache_path),
        )

    summary = summarize_call_graph_cache(root)
    parts = [
        f"Cache present ({len(cached.symbols)} symbols, {len(cached.edges)} edges)",
    ]
    prune = prune_call_graph_cache(root, dry_run=True)
    would = prune.get("would_remove") or []
    if would and isinstance(would, (list, tuple)):
        parts.append(f"GC would remove {len(would)} artifact(s) (run maintain/upgrade)")
    if summary is not None:
        parts.extend(_call_graph_cache_summary_parts(summary))

    return CheckResult(
        "Call graph index",
        True,
        "; ".join(parts),
        str(cache_path),
    )


def _call_graph_freshness_part(summary: dict[str, Any]) -> str:
    """Return the freshness label (schema mismatch / stale / fresh) for the cache summary."""
    if summary.get("reason") == "index_version_mismatch":
        return (
            "schema mismatch "
            f"v{summary.get('cached_version')} → v{summary.get('current_version')}"
        )
    if summary.get("stale"):
        from tapps_mcp.pipeline.agent_contract import CALL_GRAPH_STALE_DOCTOR

        return CALL_GRAPH_STALE_DOCTOR
    return "fresh"


def _call_graph_gap_parts(summary: dict[str, Any], gap_count: int) -> list[str]:
    """Return resolution-gap summary parts (TAP-4269 external/in-repo split)."""
    external = summary.get("external_gaps")
    in_repo = summary.get("in_repo_gaps")
    in_repo_rate = summary.get("in_repo_gap_rate")
    if isinstance(external, int) and isinstance(in_repo, int):
        parts = [f"{gap_count} resolution gaps ({external} external/expected noise, {in_repo} in-repo)"]
    else:
        parts = [f"{gap_count} resolution gaps"]
    gap_reasons = summary.get("in_repo_gap_reasons") or summary.get("gap_reasons")
    if isinstance(gap_reasons, dict) and gap_reasons:
        reason_bits = ", ".join(f"{k}={v}" for k, v in gap_reasons.items())
        parts.append(f"in-repo reasons: {reason_bits}")
    if in_repo_rate is not None:
        parts.append(f"in_repo_gap_rate={in_repo_rate}")
    return parts


def _call_graph_cache_summary_parts(summary: dict[str, Any]) -> list[str]:
    """Build the human-readable summary parts for a call-graph cache summary dict."""
    parts = [_call_graph_freshness_part(summary)]
    raw_gaps = summary.get("resolution_gaps", 0)
    gap_count = raw_gaps if isinstance(raw_gaps, int) else 0
    if gap_count:
        parts.extend(_call_graph_gap_parts(summary, gap_count))
    raw_parse_failures = summary.get("parse_failures", 0)
    parse_failures = raw_parse_failures if isinstance(raw_parse_failures, int) else 0
    if parse_failures:
        parts.append(f"{parse_failures} parse failure(s)")
    return parts


def _collect_project_mcp_servers(root: Path) -> dict[str, dict[str, object]]:
    """Load enabled MCP server entries from project-scoped config files."""
    from tapps_mcp.distribution.setup_generator import (
        _get_config_path,
        _get_servers_key,
        _load_mcp_config_json,
    )

    merged: dict[str, dict[str, object]] = {}
    for host in ("claude-code", "cursor", "vscode"):
        path = _get_config_path(host, root)
        if not path.exists():
            continue
        data = _load_mcp_config_json(path)
        servers_key = _get_servers_key(host)
        servers = data.get(servers_key)
        if not isinstance(servers, dict):
            continue
        for name, entry in servers.items():
            if isinstance(entry, dict):
                merged[str(name)] = entry
    return merged


def _nlt_partial_enablement_remediation() -> str:
    """Actionable doctor hint when too many nlt-* servers are enabled (EPIC-112)."""
    from tapps_mcp.distribution.nlt_mcp_config import enabled_servers_for_bundle

    developer = ", ".join(enabled_servers_for_bundle("developer"))
    minimal = ", ".join(enabled_servers_for_bundle("minimal"))
    return (
        f"Opt down with one command (writes yaml + host MCP configs): "
        f"`tapps-mcp mcp-bundle set developer` ({developer}) or "
        f"`tapps-mcp mcp-bundle set minimal` ({minimal}), then reload MCP. "
        "Cursor catalogs every listed tool on an enabled server (eager counts "
        "are Claude Tool Search math only). "
        "ADR-0018 keeps install default at full; use mcp-bundle set to opt down. "
        "See docs/architecture/nlt-mcp-plugin-spec.yaml."
    )


def check_nlt_partial_enablement(root: Path) -> CheckResult:
    """Epic 109.5: WARN when too many ``nlt-*`` MCP servers or combined eager tools.

    Reads ``.mcp.json``, ``.cursor/mcp.json``, and ``.vscode/mcp.json`` when
    present. Targets partial enablement: ≤3 servers and ≤20 combined eager tools.
    """
    from tapps_mcp.distribution.nlt_mcp_config import (
        NLT_MAX_COMBINED_EAGER,
        NLT_MAX_ENABLED_SERVERS,
        NLT_SERVER_ORDER,
        enabled_servers_for_bundle,
        list_nlt_server_ids_in_config,
        nlt_eager_count,
        nlt_total_tool_count,
    )

    servers = _collect_project_mcp_servers(root)
    nlt_ids = list_nlt_server_ids_in_config(servers)
    if not nlt_ids:
        return CheckResult(
            "NLT partial enablement",
            True,
            "No nlt-* MCP servers configured (legacy monolith or not bootstrapped)",
        )

    lines: list[str] = []
    combined_eager = 0
    for server_id in nlt_ids:
        eager = nlt_eager_count(server_id)
        if eager is None:
            detected = _detect_server_tool_count(server_id, servers[server_id])
            eager = detected if detected is not None else 0
        total = nlt_total_tool_count(server_id)
        combined_eager += eager
        total_label = str(total) if total is not None else "?"
        # "listed" = tools/list size Cursor shows; "eager" = Claude Tool Search.
        lines.append(f"{server_id}: {eager} eager / {total_label} listed")

    combined_listed = sum(
        (nlt_total_tool_count(sid) or 0) for sid in nlt_ids
    )
    summary = (
        f"{len(nlt_ids)} server(s); combined eager={combined_eager} "
        f"(Claude); combined listed={combined_listed} (Cursor); "
        + "; ".join(lines)
    )
    if set(nlt_ids) == set(NLT_SERVER_ORDER):
        bundle = _resolved_mcp_bundle(root)
        if bundle == "full":
            return CheckResult(
                "NLT partial enablement",
                True,
                (
                    f"Intentional full bundle (mcp_bundle=full): all six nlt-* servers "
                    f"enabled. {summary}"
                ),
            )
        return CheckResult(
            "NLT partial enablement",
            False,
            (
                f"WARN: all six nlt-* servers enabled in MCP config. "
                f"Recommended active: {', '.join(enabled_servers_for_bundle('developer'))}. "
                f"{summary}"
            ),
            _nlt_partial_enablement_remediation(),
        )

    warnings: list[str] = []
    if len(nlt_ids) > NLT_MAX_ENABLED_SERVERS:
        warnings.append(
            f"{len(nlt_ids)} nlt-* servers enabled (recommended ≤{NLT_MAX_ENABLED_SERVERS})"
        )
    if combined_eager > NLT_MAX_COMBINED_EAGER:
        warnings.append(
            f"{combined_eager} combined eager tools (recommended ≤{NLT_MAX_COMBINED_EAGER})"
        )

    if warnings:
        return CheckResult(
            "NLT partial enablement",
            False,
            f"WARN: {'; '.join(warnings)}. {summary}",
            _nlt_partial_enablement_remediation(),
        )
    return CheckResult(
        "NLT partial enablement",
        True,
        f"Within partial-enablement targets. {summary}",
    )


def _read_tool_budget(root: Path) -> int:
    """Read ``doctor_tool_budget_limit`` from ``.tapps-mcp.yaml`` (default 20)."""
    import yaml  # pyyaml — always available

    config_path = root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return _DEFAULT_TOOL_BUDGET
    try:
        with config_path.open(encoding="utf-8") as fh:
            cfg: dict[str, object] = yaml.safe_load(fh) or {}
        raw = cfg.get("doctor_tool_budget_limit", _DEFAULT_TOOL_BUDGET)
        return int(raw) if isinstance(raw, (int, float, str)) else _DEFAULT_TOOL_BUDGET
    except Exception:
        return _DEFAULT_TOOL_BUDGET


def check_mcp_tool_budget(root: Path) -> CheckResult:
    """TAP-2026/TAP-1989: WARN when a known MCP server exposes more eager tools than budget.

    Reads project MCP configs (``.mcp.json``, ``.cursor/mcp.json``, ``.vscode/mcp.json``),
    computes tool counts for recognized tapps-family servers from their ``--mode`` or
    ``--profile`` flag, and compares against the ``doctor_tool_budget_limit`` in
    ``.tapps-mcp.yaml`` (default 20).

    Only tapps-mcp / docs-mcp / nlt-* servers are probed; unknown or HTTP-only servers
    are skipped (they require a live connection).
    """
    servers = _collect_project_mcp_servers(root)
    if not servers:
        return CheckResult(
            "MCP tool budget",
            True,
            "No project MCP config found — skipping tool budget check",
        )

    budget = _read_tool_budget(root)
    lines: list[str] = []
    over_budget: list[str] = []

    for server_name, server_cfg in servers.items():
        count = _detect_server_tool_count(server_name, server_cfg)
        if count is None:
            continue
        tag = "WARN" if count > budget else "OK"
        lines.append(f"{server_name}: {count} tools [{tag}]")
        if count > budget:
            over_budget.append(f"{server_name}({count})")

    if not lines:
        return CheckResult(
            "MCP tool budget",
            True,
            f"No recognized tapps-family servers in MCP config (budget={budget})",
        )

    summary = f"budget={budget}; " + ", ".join(lines)
    if over_budget:
        return CheckResult(
            "MCP tool budget",
            False,
            f"WARN: {', '.join(over_budget)} exceed eager-tool budget. {summary}",
            "Reduce tool count with --mode quality/admin, disable extra nlt-* servers, "
            "or set doctor_tool_budget_limit in .tapps-mcp.yaml.",
        )
    return CheckResult("MCP tool budget", True, f"All servers within budget. {summary}")


