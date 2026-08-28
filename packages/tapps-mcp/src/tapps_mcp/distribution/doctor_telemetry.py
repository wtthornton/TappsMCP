"""Doctor loop-metrics telemetry + enforcement-recommendation checks (TAP-5606 split).

Covers ``.tapps-mcp.yaml`` engagement-level reads, lookup-docs discipline,
Cursor transcript trustworthiness, the Cursor stop completion gate, and the
``continuous-learning-v2`` skill check. The pipeline-enforcement
recommendation engine (git hooks / cache-gate block promotion from 7d
loop-metrics) lives in :mod:`tapps_mcp.distribution.doctor_telemetry_pipeline`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_mcp.distribution.doctor_pipeline import (
    _count_cache_gate_violations_24h,
    _count_completion_gate_violations_24h,
    _detect_cache_gate_mode,
    _detect_completion_gate_mode,
    _memory_skill_content_ok,
    _tapps_skill_bases,
)
from tapps_mcp.distribution.doctor_result import CheckResult


def _read_engagement_level(project_root: Path) -> str | None:
    """Read llm_engagement_level from project_root/.tapps-mcp.yaml if present."""
    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return None
    try:
        import yaml

        raw = config_path.read_text(encoding="utf-8-sig")
        data = yaml.safe_load(raw) if raw.strip() else {}
        level = (data or {}).get("llm_engagement_level")
        if level in ("high", "medium", "low"):
            return str(level)
    except Exception:
        return None
    return None


_CACHE_GATE_BLOCK_HINT_THRESHOLD = 20
_PIPELINE_ENFORCE_LOOKUP_THRESHOLD = 0.20
_PIPELINE_ENFORCE_MIN_LOOPS = 7


def _stale_lookup_scaffolding(project_root: Path) -> list[str]:
    """Return rule/skill paths whose lookup-first scaffolding is stale or missing."""
    from tapps_mcp.pipeline.agent_contract import LOOKUP_FIRST_RULE_MARKERS

    stale: list[str] = []
    rule_paths = (
        project_root / ".claude" / "rules" / "python-quality.md",
        project_root / ".cursor" / "rules" / "tapps-python-quality.mdc",
        project_root / ".cursor" / "rules" / "tapps-pipeline.mdc",
    )
    for path in rule_paths:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        if not all(marker in content for marker in LOOKUP_FIRST_RULE_MARKERS):
            try:
                stale.append(str(path.relative_to(project_root.resolve())))
            except ValueError:
                stale.append(str(path))

    for host_label, base in _tapps_skill_bases(project_root):
        skill_path = base / "tapps-finish-task" / "SKILL.md"
        if skill_path.is_file():
            content = skill_path.read_text(encoding="utf-8")
            if not _memory_skill_content_ok("tapps-finish-task", content):
                stale.append(f"{host_label}/tapps-finish-task")
    return stale


def check_lookup_docs_discipline(project_root: Path) -> CheckResult:
    """Verify lookup-first rules/skills are deployed and report chronic underuse."""
    from tapps_mcp.tools.loop_metrics import (
        _PROMOTE_WINDOW_DAYS,
        compute_rolling_stats,
    )

    stale = _stale_lookup_scaffolding(project_root)

    stats = compute_rolling_stats(project_root, window_days=_PROMOTE_WINDOW_DAYS)
    lookup_ratio = float(stats.get("lookup_docs_to_edit_ratio", 0.0))
    lookup_pct = round(lookup_ratio * 100)
    loops = int(stats.get("loops", 0))

    parts = (f"7d lookup_docs_to_edit_ratio={lookup_pct}% ({loops} loops)",)
    detail_parts: list[str] = []
    if stale:
        detail_parts.append(
            "Stale lookup-first scaffolding: "
            + ", ".join(sorted(stale))
            + ". Run: tapps-mcp upgrade --force"
        )
    if loops >= _PIPELINE_ENFORCE_MIN_LOOPS and lookup_ratio < _PIPELINE_ENFORCE_LOOKUP_THRESHOLD:
        detail_parts.append(
            "Chronic lookup_docs_underused pattern — call tapps_lookup_docs before "
            "the first edit on external library APIs; finish-task must clear "
            "usage_gaps before Done."
        )

    ok = not stale
    return CheckResult(
        "Lookup-docs discipline",
        ok,
        "; ".join(parts),
        "\n".join(detail_parts) if detail_parts else "",
    )


def _count_legacy_unparsed_rows(rows: list[dict[str, Any]]) -> int:
    """Count pre-TAP-4017 Cursor rows with unparsed CallMcpTool wrapping."""
    from tapps_mcp.tools.loop_metrics import _legacy_cursor_unparsed_callmcptool

    return sum(1 for r in rows if _legacy_cursor_unparsed_callmcptool(r))


def _count_callmcptool_and_resolved_gate_rows(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Count rows containing CallMcpTool and rows with a resolved gate-tool call."""
    from tapps_mcp.tools.loop_metrics import is_gate_tool

    callmcptool_rows = sum(
        1 for r in rows if "CallMcpTool" in [str(t) for t in (r.get("tools_used") or [])]
    )
    resolved_gate_rows = 0
    for row in rows:
        tools = [str(t) for t in row.get("tools_used") or []]
        if any(is_gate_tool(t) for t in tools):
            resolved_gate_rows += 1
    return callmcptool_rows, resolved_gate_rows


def check_cursor_loop_metrics_telemetry(project_root: Path) -> CheckResult:
    """Report Cursor CallMcpTool transcript trustworthiness (TAP-4025)."""
    import time

    from tapps_mcp.tools.loop_metrics import (
        _DAY_SECONDS,
        _PROMOTE_WINDOW_DAYS,
        read_loop_metrics,
    )

    cutoff = int(time.time()) - _PROMOTE_WINDOW_DAYS * _DAY_SECONDS
    rows = [r for r in read_loop_metrics(project_root) if int(r.get("ts", 0)) >= cutoff]
    legacy_unparsed = _count_legacy_unparsed_rows(rows)
    callmcptool_rows, resolved_gate_rows = _count_callmcptool_and_resolved_gate_rows(rows)

    parts = [f"7d loops={len(rows)}", "callmcptool_unwrap=active"]
    if legacy_unparsed:
        parts.append(f"legacy_unparsed_callmcptool={legacy_unparsed}")
    detail_parts: list[str] = []
    if legacy_unparsed:
        detail_parts.append(
            f"{legacy_unparsed} pre-TAP-4017 Cursor rows excluded from rolling "
            "gate_skip_rate (is_reliable_edit_loop_row filter)."
        )
    if callmcptool_rows > 0 and resolved_gate_rows == 0:
        detail_parts.append(
            f"{callmcptool_rows} loop-metrics rows contain CallMcpTool but zero "
            "resolved tapps_* gate/checklist calls — gate_skip_rate may be inflated. "
            "See docs/TROUBLESHOOTING.md#cursor-vs-claude-transcript-parsing."
        )
    ok = not (callmcptool_rows > 0 and resolved_gate_rows == 0)
    return CheckResult(
        "Cursor loop-metrics telemetry",
        ok,
        "; ".join(parts),
        "\n".join(detail_parts) if detail_parts else "",
    )


def _stop_gate_hook_note(hook_paths: list[Path]) -> str:
    """Describe stop-hook installation state for the status message."""
    if hook_paths:
        return f"stop hook installed ({', '.join(p.name for p in hook_paths)})"
    return "stop hook missing — run tapps-mcp upgrade"


def _stop_gate_block_result(
    message: str, explicit: str | None, resolved: str
) -> CheckResult | None:
    """Return a failing CheckResult when the gate is (or resolves to) block mode."""
    if explicit == "block":
        return CheckResult(
            "Cursor stop completion gate",
            False,
            message,
            "cursor_stop_completion_gate is block — run tapps-mcp upgrade to migrate to warn",
        )
    if resolved == "block":
        return CheckResult(
            "Cursor stop completion gate",
            False,
            message,
            "Resolved mode is block — set cursor_stop_completion_gate: warn in "
            ".tapps-mcp.yaml or run tapps-mcp upgrade",
        )
    return None


def check_cursor_stop_completion_gate(project_root: Path) -> CheckResult:
    """Report Cursor stop completion gate mode and hook presence (TAP-3921)."""
    from tapps_core.config.settings import load_settings

    claude_hook = project_root / ".claude" / "hooks" / "tapps-stop.sh"
    cursor_hook = project_root / ".cursor" / "hooks" / "tapps-stop.sh"
    hook_paths = [p for p in (claude_hook, cursor_hook) if p.exists()]

    try:
        settings = load_settings(project_root=project_root)
        resolved = settings.cursor_stop_completion_gate_resolved()
        explicit = settings.cursor_stop_completion_gate
    except Exception as exc:
        return CheckResult(
            "Cursor stop completion gate",
            False,
            "Could not load settings",
            str(exc),
        )

    explicit_note = explicit if explicit is not None else "default"
    message = f"mode={resolved} (configured={explicit_note}); {_stop_gate_hook_note(hook_paths)}"

    blocked = _stop_gate_block_result(message, explicit, resolved)
    if blocked:
        return blocked

    detail = ""
    if explicit is None:
        detail = (
            "cursor_stop_completion_gate not pinned in .tapps-mcp.yaml — "
            "run tapps-mcp upgrade --dry-run to add cursor_stop_completion_gate: warn"
        )

    return CheckResult(
        "Cursor stop completion gate",
        True,
        message,
        detail,
    )


def check_completion_gate_violations(project_root: Path) -> CheckResult:
    """Report the completion-gate 24 h violation count (TAP-6586).

    Sibling of :func:`check_cache_gate_block_hint`: the completion gate runs the
    same warn-mode telemetry and, until this check existed, nobody read it — the
    log passed 185 entries unnoticed. Reports the count; the remediation is the
    checklist auto-running its own missing validation, not promoting the gate.
    """
    from tapps_core.config.settings import load_settings

    resolved_mode: str
    try:
        settings = load_settings(project_root=project_root)
        resolved_mode = settings.cursor_stop_completion_gate_resolved()
    except Exception:
        resolved_mode = _detect_completion_gate_mode(project_root)

    viol_24h = _count_completion_gate_violations_24h(project_root)
    message = f"mode={resolved_mode}, {viol_24h} completion-gate violations in 24h"
    if viol_24h == 0:
        return CheckResult("Completion gate violations", True, message)
    return CheckResult(
        "Completion gate violations",
        True,
        message,
        "Sessions ended with edited code and no checklist. Finish with "
        "/tapps-finish-task (or tapps_checklist, which now runs the missing "
        "validation itself) so the gate has real evidence to read.",
    )


def check_cache_gate_block_hint(project_root: Path) -> CheckResult:
    """Recommend ``linear_enforce_cache_gate: block`` on high-traffic projects (TAP-3577)."""
    from tapps_core.config.settings import load_settings

    resolved_mode: str
    try:
        settings = load_settings(project_root=project_root)
        resolved_mode = settings.linear_enforce_cache_gate_resolved()
    except Exception:
        resolved_mode = _detect_cache_gate_mode(project_root)

    if resolved_mode == "block":
        return CheckResult(
            "Linear cache-gate promotion",
            True,
            "linear_enforce_cache_gate is block",
        )

    viol_24h = _count_cache_gate_violations_24h(project_root)
    if resolved_mode == "warn" and viol_24h >= _CACHE_GATE_BLOCK_HINT_THRESHOLD:
        return CheckResult(
            "Linear cache-gate promotion",
            True,
            f"{viol_24h} cache-gate misses in 24h while mode=warn",
            "Set linear_enforce_cache_gate: block in .tapps-mcp.yaml and run "
            "tapps-mcp upgrade --force. Route multi-issue reads through the linear-read skill.",
        )

    if resolved_mode == "off" and viol_24h > 0:
        return CheckResult(
            "Linear cache-gate promotion",
            True,
            f"{viol_24h} raw list_issues gate misses logged while mode=off",
            "Enable linear_enforce_cache_gate: warn (or block for high-traffic repos) "
            "in .tapps-mcp.yaml, then tapps-mcp upgrade --force.",
        )

    return CheckResult(
        "Linear cache-gate promotion",
        True,
        f"mode={resolved_mode}, {viol_24h} gate_miss violations in 24h",
    )


def _git_hooks_gate_pass_result(gate_pass: float | None) -> CheckResult:
    """Build the CheckResult for the final 7d gate-pass-rate recommendation."""
    if gate_pass is None:
        return CheckResult(
            "Git pre-commit hook",
            True,
            "insufficient 7d gate metrics for recommendation",
        )
    pct = round(gate_pass * 100)
    if gate_pass < 0.70:
        return CheckResult(
            "Git pre-commit hook",
            True,
            f"7d gate pass rate {pct}% (<70%) at high engagement",
            "Set install_git_hooks: true in .tapps-mcp.yaml and run tapps-mcp upgrade "
            "to enforce validate-changed on git commit.",
        )
    return CheckResult(
        "Git pre-commit hook",
        True,
        f"7d gate pass rate {pct}% — install_git_hooks not required",
    )


def check_install_git_hooks_hint(project_root: Path) -> CheckResult:
    """Recommend ``install_git_hooks: true`` when high engagement + low gate pass (TAP-3579)."""
    from tapps_core.config.settings import load_settings
    from tapps_mcp.tools.loop_metrics import compute_gate_pass_rate_7d

    try:
        settings = load_settings(project_root=project_root)
        if settings.install_git_hooks:
            return CheckResult(
                "Git pre-commit hook",
                True,
                "install_git_hooks is enabled",
            )
    except Exception:
        settings = None

    hook_path = project_root / ".githooks" / "pre-commit"
    if hook_path.is_file():
        return CheckResult(
            "Git pre-commit hook",
            True,
            ".githooks/pre-commit present",
        )

    engagement = _read_engagement_level(project_root) or "medium"
    if engagement != "high":
        return CheckResult(
            "Git pre-commit hook",
            True,
            f"optional at llm_engagement_level={engagement}",
        )

    gate_pass = compute_gate_pass_rate_7d(project_root)
    return _git_hooks_gate_pass_result(gate_pass)


def check_continuous_learning_v2_skill(project_root: Path) -> CheckResult:
    """Check the ``continuous-learning-v2`` skill is deployed (ECC v2.1).

    The skill bundles instinct-based session observation, project-scoped
    instinct storage, and evolution commands (instinct-status, evolve,
    promote, projects).  Hooks fire deterministically (100%) vs the v1
    skill-based observation (~50-80%).
    """
    present: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        skill_path = base / "continuous-learning-v2" / "SKILL.md"
        if skill_path.exists():
            present.append(host_label)

    if present:
        return CheckResult(
            "continuous-learning-v2 skill",
            True,
            f"Present on: {', '.join(present)}",
        )
    return CheckResult(
        "continuous-learning-v2 skill",
        False,
        "continuous-learning-v2/SKILL.md not found on any skill host",
        "Run: tapps-mcp upgrade",
    )
