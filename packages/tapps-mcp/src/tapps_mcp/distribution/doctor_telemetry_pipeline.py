"""Doctor pipeline-enforcement recommendation check (TAP-5606 split).

Recommends git-hooks and Linear cache-gate block promotion from rolling
7-day loop-metrics (gate skip rate, lookup-docs usage, cache-gate misses).
Split out of :mod:`tapps_mcp.distribution.doctor_telemetry` to keep both
modules under the per-file maintainability budget.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_pipeline import (
    _count_cache_gate_violations_24h,
    _detect_cache_gate_mode,
)
from tapps_mcp.distribution.doctor_result import CheckResult
from tapps_mcp.distribution.doctor_telemetry import (
    _CACHE_GATE_BLOCK_HINT_THRESHOLD,
    _PIPELINE_ENFORCE_LOOKUP_THRESHOLD,
    _PIPELINE_ENFORCE_MIN_LOOPS,
    _read_engagement_level,
)

_PIPELINE_ENFORCE_SKIP_THRESHOLD = 0.30


def _hook_install_hint(
    project_root: Path,
    settings: object | None,
    engagement: str,
    loops: int,
    skip_rate: float,
    skip_pct: int,
) -> str | None:
    """Return the git-hooks-enforcement hint text, or None when not warranted."""
    if not (
        loops >= _PIPELINE_ENFORCE_MIN_LOOPS
        and skip_rate >= _PIPELINE_ENFORCE_SKIP_THRESHOLD
        and engagement in ("medium", "high")
    ):
        return None
    install_hooks = bool(getattr(settings, "install_git_hooks", False)) if settings else False
    hook_path = project_root / ".githooks" / "pre-commit"
    if install_hooks or hook_path.is_file():
        return None
    return (
        f"Chronic gate skips ({skip_pct}% ≥ {_PIPELINE_ENFORCE_SKIP_THRESHOLD:.0%}) "
        f"at {engagement} engagement — enforce validate-changed on commit"
    )


def _lookup_ratio_hint(
    loops: int, lookup_ratio: float, lookup_pct: int, engagement: str
) -> str | None:
    """Return the lookup-docs-underuse hint text, or None when not warranted."""
    if not (
        loops >= _PIPELINE_ENFORCE_MIN_LOOPS
        and lookup_ratio < _PIPELINE_ENFORCE_LOOKUP_THRESHOLD
        and engagement in ("medium", "high")
    ):
        return None
    return (
        f"Low tapps_lookup_docs usage ({lookup_pct}% of edit loops) — call "
        "tapps_lookup_docs before the first edit on external library APIs"
    )


def _cache_gate_promote_hint(
    project_root: Path,
    settings: object | None,
    cache_mode: str,
    viol_24h: int,
) -> tuple[str | None, str | None]:
    """Return (yaml_snippet, hint) recommending cache-gate block promotion."""
    from tapps_mcp.tools.loop_metrics import should_auto_promote_cache_gate

    if cache_mode == "block":
        return None, None
    if viol_24h >= _CACHE_GATE_BLOCK_HINT_THRESHOLD:
        return (
            "linear_enforce_cache_gate: block",
            f"{viol_24h} Linear cache-gate misses in 24h while mode={cache_mode}",
        )
    if settings is not None and getattr(settings, "linear_enforce_cache_gate_auto_promote", False):
        promote, _telemetry = should_auto_promote_cache_gate(
            project_root,
            current_mode=cache_mode,
            auto_promote_enabled=True,
        )
        if promote:
            return (
                "linear_enforce_cache_gate: block",
                "TAP-1333 auto-promote criteria met (stable pipeline, low skip rate)",
            )
    return None, None


def _build_pipeline_enforce_result(
    message: str, hints: list[str], yaml_snippets: list[str]
) -> CheckResult:
    """Assemble the final CheckResult from collected hints/snippets."""
    detail_parts = list(hints)
    if yaml_snippets:
        detail_parts.append("Suggested .tapps-mcp.yaml:\n" + "\n".join(yaml_snippets))
    detail = "\n".join(detail_parts)

    suffix = (
        f"; {len(yaml_snippets)} enforcement snippet(s)"
        if yaml_snippets
        else "; no enforcement changes suggested"
    )
    return CheckResult(
        "Pipeline enforcement recommendations",
        True,
        message + suffix,
        detail,
    )


def check_pipeline_enforce_recommendations(project_root: Path) -> CheckResult:
    """Recommend git hooks / cache-gate block from 7d loop-metrics (TAP-3923)."""
    from tapps_core.config.settings import load_settings
    from tapps_mcp.tools.loop_metrics import (
        _PROMOTE_WINDOW_DAYS,
        compute_rolling_stats,
    )

    stats = compute_rolling_stats(project_root, window_days=_PROMOTE_WINDOW_DAYS)
    skip_rate = float(stats.get("gate_skip_rate", 0.0))
    lookup_ratio = float(stats.get("lookup_docs_to_edit_ratio", 0.0))
    loops = int(stats.get("loops", 0))
    skip_pct = round(skip_rate * 100)
    lookup_pct = round(lookup_ratio * 100)
    message = (
        f"7d gate_skip_rate={skip_pct}% lookup_docs_to_edit_ratio={lookup_pct}% "
        f"({loops} loops in loop-metrics)"
    )

    engagement = _read_engagement_level(project_root) or "medium"
    settings = None
    try:
        settings = load_settings(project_root=project_root)
        engagement = settings.llm_engagement_level
    except Exception:
        pass

    yaml_snippets: list[str] = []
    hints: list[str] = []

    hook_hint = _hook_install_hint(project_root, settings, engagement, loops, skip_rate, skip_pct)
    if hook_hint:
        yaml_snippets.append("install_git_hooks: true")
        hints.append(hook_hint)

    lookup_hint = _lookup_ratio_hint(loops, lookup_ratio, lookup_pct, engagement)
    if lookup_hint:
        hints.append(lookup_hint)

    cache_mode = _detect_cache_gate_mode(project_root)
    if settings is not None:
        cache_mode = settings.linear_enforce_cache_gate_resolved()

    viol_24h = _count_cache_gate_violations_24h(project_root)
    cache_snippet, cache_hint = _cache_gate_promote_hint(
        project_root, settings, cache_mode, viol_24h
    )
    if cache_snippet:
        yaml_snippets.append(cache_snippet)
    if cache_hint:
        hints.append(cache_hint)

    return _build_pipeline_enforce_result(message, hints, yaml_snippets)
