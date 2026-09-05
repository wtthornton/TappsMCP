"""Skip-token gating and result-shaping helpers for the upgrade pipeline.

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913). Everything here is
pure result bookkeeping — deciding whether an artifact is skip-listed, listing
the consumer files an upgrade leaves alone, and rolling per-component details up
into the dry-run verdict. No generator is invoked from this module.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.upgrade_skip_tokens import (
    SKIP_TOKENS,
    applied_skip_tokens,
    describe_unknown_skip_tokens,
    unknown_skip_tokens,
)

log = get_logger(__name__)


def skipped(artifact: str, skip: set[str]) -> bool:
    """True when *artifact*'s ``upgrade_skip_files`` token is present in *skip*."""
    return bool(SKIP_TOKENS.get(artifact, frozenset()) & skip)


def dry_run_status(name: str, skip: set[str]) -> str:
    """Dry-run status for an artifact that is regenerated unconditionally when not skipped."""
    return "skipped (upgrade_skip_files)" if skipped(name, skip) else "would-regenerate"


def apply_or_skip(
    result: dict[str, Any],
    name: str,
    skip: set[str],
    generate: Callable[[Path], Any],
    project_root: Path,
) -> None:
    """Write ``generate(project_root)`` into ``result["components"][name]``, or the skip marker.

    For artifacts whose dict key equals their ``upgrade_skip_files`` token and
    which take only ``project_root`` — the shape repeated throughout the
    claude-code live upgrade.
    """
    if skipped(name, skip):
        result["components"][name] = "skipped (upgrade_skip_files)"
    else:
        result["components"][name] = generate(project_root)


def record_unknown_skip_tokens(result: dict[str, Any], skip_files: set[str]) -> None:
    """Warn loudly about ``upgrade_skip_files`` entries that protect nothing.

    TAP-6499: these used to land in the result dict and be rendered nowhere, so
    a consumer who wrote file paths instead of tokens watched two upgrades
    overwrite a customized skill in silence.
    """
    unknown = unknown_skip_tokens(skip_files)
    if not unknown:
        return
    explanations = describe_unknown_skip_tokens(unknown)
    result["unknown_skip_tokens"] = unknown
    result["unknown_skip_token_warnings"] = explanations
    result.setdefault("warnings", []).extend(explanations)
    log.warning(
        "upgrade.unknown_skip_tokens",
        unknown=unknown,
        detail="; ".join(explanations),
    )


def record_applied_skip_tokens(result: dict[str, Any], skip_files: set[str]) -> None:
    """Record ``upgrade_skip_files`` entries that matched the vocabulary and were applied.

    Companion to :func:`record_unknown_skip_tokens` (TAP-6891): before this, a
    working entry and an unconfigured project produced identical (silent)
    output — "applied" and "not configured" were indistinguishable in the run.
    """
    applied = applied_skip_tokens(skip_files)
    if not applied:
        return
    result["applied_skip_tokens"] = applied
    log.info("upgrade.applied_skip_tokens", applied=applied)


def lift_asset_overwrite_warnings(
    result: dict[str, Any], platform_results: list[dict[str, Any]]
) -> None:
    """Surface per-host "about to overwrite a customized asset" lines at top level.

    TAP-6497: a scaffolded asset whose format cannot carry a managed-block
    marker is replaced wholesale. Lifting the report here puts it next to the
    skip-token warnings in CLI output instead of burying it per host.
    """
    for host_result in platform_results:
        skills = host_result.get("components", {}).get("skills")
        if isinstance(skills, dict) and skills.get("asset_overwrite_warnings"):
            result.setdefault("warnings", []).extend(skills["asset_overwrite_warnings"])


def record_managed_json_error(result: dict[str, Any], key: str, exc: Any) -> None:
    """Isolate a malformed managed-JSON failure to a single component.

    Records a structured, actionable error under ``result["components"][key]``
    and stashes it on ``component_errors`` so the orchestrator can surface it at
    the top level. The rest of the platform scope keeps upgrading instead of
    aborting on a bare ``JSONDecodeError`` when ``.claude/settings.json`` or
    ``.cursor/hooks.json`` is malformed (e.g. a dropped opening brace).
    """
    result["components"][key] = {
        "action": "error",
        "error": str(exc),
        "hint": getattr(exc, "remediation", ""),
    }
    result.setdefault("component_errors", []).append(f"{key}: {exc}")


def enumerate_preserved(
    target_dir: Path,
    managed_names: frozenset[str],
    *,
    is_dir_target: bool = False,
) -> list[str]:
    """Return existing entries in *target_dir* that upgrade would not touch.

    ``managed_names`` lists the base names tapps-mcp actively manages. Anything
    else in the directory is preserved by the upgrade. The names are returned
    sorted so dry-run output is stable across platforms.
    """
    if not target_dir.is_dir():
        return []
    preserved: list[str] = []
    for entry in target_dir.iterdir():
        if entry.name in managed_names:
            continue
        if is_dir_target and not entry.is_dir():
            continue
        preserved.append(entry.name)
    return sorted(preserved)


def _absorb_component(
    scope: str,
    name: str,
    value: Any,
    *,
    tally: dict[str, Any],
) -> None:
    """Fold one component result into the dry-run ``tally`` accumulator."""
    if isinstance(value, dict):
        if value.get("action") == "error":
            tally["parse_errors"].append(f"{scope}:{name}: {value.get('error', '')}")
        action = value.get("action")
        if isinstance(action, str) and action.startswith(("would-refresh", "would-merge")):
            tally["review"].append(f"{scope}:{name}")
        tally["managed"] += len(value.get("managed_files", [])) + len(
            value.get("managed_skills", [])
        )
        tally["preserved"].extend(
            f"{scope}:{name}/{item}"
            for key in ("preserved_files", "preserved_skills")
            for item in value.get(key, [])
        )
    elif isinstance(value, str):
        if value.startswith("skipped"):
            tally["skipped"].append(f"{scope}:{name}")
        elif value.startswith(("would-refresh", "would-merge")):
            tally["review"].append(f"{scope}:{name}")


def _collect_dry_run_tally(result: dict[str, Any]) -> dict[str, Any]:
    """Walk every dry-run component and accumulate the summary counters."""
    tally: dict[str, Any] = {
        "managed": 0,
        "preserved": [],
        "skipped": [],
        "review": [],
        "parse_errors": [],
    }
    components = result.get("components", {})
    for host_result in components.get("platforms", []):
        host = host_result.get("host", "?")
        for name, value in host_result.get("components", {}).items():
            _absorb_component(host, name, value, tally=tally)

    # Top-level (platform-agnostic) components: GitHub artifacts, Karpathy, etc.
    for name in ("ci_workflows", "github_templates"):
        _absorb_component("repo", name, components.get(name), tally=tally)

    claude_md = components.get("claude_md")
    if isinstance(claude_md, str) and claude_md.startswith("would-merge"):
        tally["review"].append("claude_md")
    agents_md = components.get("agents_md")
    if isinstance(agents_md, dict) and agents_md.get("action", "").startswith("would"):
        tally["review"].append("agents_md")
    return tally


def _dry_run_message(verdict: str, tally: dict[str, Any]) -> str:
    """Render the human-readable one-liner that accompanies *verdict*."""
    preserved_count = len(tally["preserved"])
    if verdict == "blocked":
        return "Managed JSON parse failure — repair before upgrading: " + "; ".join(
            tally["parse_errors"]
        )
    if verdict == "safe-to-run":
        return (
            f"Upgrade is additive: {tally['managed']} tapps-managed files would be "
            f"written, {preserved_count} custom files preserved."
        )
    return (
        f"Upgrade touches user-editable files ({', '.join(tally['review'])}); "
        f"review diffs before running live. {preserved_count} custom "
        "files preserved."
    )


def build_dry_run_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Build a human-readable verdict from per-component dry-run details.

    Walks ``result["components"]["platforms"]`` and aggregates:
    - ``managed_file_count``: tapps-* files the upgrade would write
    - ``preserved_file_count``: consumer-custom files the upgrade would NOT touch
    - ``skipped_components``: components opted out via ``upgrade_skip_files``
    - ``verdict``: one of ``"safe-to-run"``, ``"review-recommended"``, ``"blocked"``

    ``review-recommended`` fires when an upgrade would touch a
    user-editable file (``CLAUDE.md``, settings merge) so the consumer
    should inspect diffs before running live. Pure ``tapps-*`` writes
    plus preserved custom files → ``safe-to-run``.

    ``blocked`` fires when a managed JSON config (``.claude/settings.json``,
    ``.cursor/hooks.json``) fails to parse — repair the file before upgrading.
    """
    tally = _collect_dry_run_tally(result)
    verdict = (
        "blocked"
        if tally["parse_errors"]
        else ("review-recommended" if tally["review"] else "safe-to-run")
    )

    # TAP-2201: Surface would_recreate_deleted_files from github_templates component.
    github_templates = result.get("components", {}).get("github_templates")
    would_recreate: list[dict[str, str]] = (
        list(github_templates.get("would_recreate_deleted_files", []))
        if isinstance(github_templates, dict)
        else []
    )

    return {
        "verdict": verdict,
        "message": _dry_run_message(verdict, tally),
        "managed_file_count": tally["managed"],
        "preserved_file_count": len(tally["preserved"]),
        "preserved_files": sorted(tally["preserved"]),
        "skipped_components": sorted(tally["skipped"]),
        "review_recommended_for": sorted(tally["review"]),
        "parse_errors": sorted(tally["parse_errors"]),
        "would_recreate_deleted_files": would_recreate,
    }
