"""Doctor checks for managed multi-file platform skills (TAP-5496).

Required on ``skill_tier: full``; core tier skips absence. When present on any
tier, require managed-block marker + companions + content fingerprints so
``tapps-mcp upgrade --force`` clears stale copies.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.distribution.doctor_result import CheckResult


def _check_managed_skill_current(
    project_root: Path,
    *,
    skill_name: str,
    check_name: str,
    companions: tuple[str, ...],
    required_phrases: tuple[str, ...],
    phrase_sources: tuple[str, ...] = (),
) -> CheckResult:
    """Shared required-on-full skill freshness check.

    ``phrase_sources`` are paths relative to the skill dir whose text is
    concatenated with SKILL.md when looking for ``required_phrases``. Empty
    means body-only fingerprints.
    """
    from tapps_mcp.distribution.context_budget import _skill_tier
    from tapps_mcp.distribution.doctor_pipeline import _tapps_skill_bases
    from tapps_mcp.distribution.doctor_result import CheckResult

    marker = f"<!-- BEGIN: tapps-skill {skill_name}"
    tier = _skill_tier(project_root)
    valid_hosts: list[str] = []
    problems: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        skill_dir = base / skill_name
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            if tier == "full":
                problems.append(f"{host_label}/{skill_name} missing")
            continue
        content = skill_path.read_text(encoding="utf-8")
        if marker not in content:
            problems.append(f"{host_label}/{skill_name} stale (no managed-block marker)")
            continue
        missing = [c for c in companions if not (skill_dir / c).exists()]
        if missing:
            problems.append(f"{host_label}/{skill_name} missing {', '.join(missing)}")
            continue
        combined = content.lower()
        for rel in phrase_sources:
            combined = f"{combined}\n{(skill_dir / rel).read_text(encoding='utf-8').lower()}"
        missing_phrases = [p for p in required_phrases if p not in combined]
        if missing_phrases:
            problems.append(
                f"{host_label}/{skill_name} stale content "
                f"(missing {', '.join(missing_phrases)}; run upgrade --force)"
            )
            continue
        valid_hosts.append(host_label)

    if problems:
        detail = "Run: tapps-mcp upgrade --force"
        message = problems[0] if len(problems) == 1 else f"Issues: {'; '.join(problems)}"
        return CheckResult(check_name, False, message, detail)
    if valid_hosts:
        return CheckResult(
            check_name,
            True,
            f"{skill_name} skill current on: {', '.join(valid_hosts)}",
        )
    return CheckResult(
        check_name,
        True,
        f"{skill_name} skill not required (skill_tier=core)",
    )


def check_orchestration_prompt_skill_current(project_root: Path) -> CheckResult:
    """Check ``orchestration-prompt`` is deployed with companions (TAP-5496)."""
    return _check_managed_skill_current(
        project_root,
        skill_name="orchestration-prompt",
        check_name="orchestration-prompt skill",
        companions=(
            "assets/prompt-template.md",
            "references/claude-feature-map.md",
            "references/cold-start-and-verify.md",
            "references/host-feature-map.md",
        ),
        required_phrases=(
            "validation contract",
            "expected-fail",
            "shift boundary",
            "host-feature-map",
        ),
        phrase_sources=(
            "assets/prompt-template.md",
            "references/host-feature-map.md",
        ),
    )


def check_wayfind_skill_current(project_root: Path) -> CheckResult:
    """Check ``tapps-wayfind`` is deployed with companions (TAP-5496)."""
    return _check_managed_skill_current(
        project_root,
        skill_name="tapps-wayfind",
        check_name="tapps-wayfind skill",
        companions=(
            "assets/map-template.md",
            "references/ticket-types.md",
            "references/linear-ops.md",
        ),
        required_phrases=("fog", "orchestration-prompt"),
    )


def check_validation_contract_skill_current(project_root: Path) -> CheckResult:
    """Check ``tapps-validation-contract`` is deployed with companions (TAP-5541)."""
    return _check_managed_skill_current(
        project_root,
        skill_name="tapps-validation-contract",
        check_name="tapps-validation-contract skill",
        companions=(
            "assets/contract-template.md",
            "references/assertion-schema.md",
            "references/when-to-use.md",
        ),
        required_phrases=("validation contract",),
    )


def check_skill_asset_drift(project_root: Path) -> CheckResult:
    """Flag SKILL.md-customization-vs-asset drift in scaffolded skills (TAP-6497).

    The dangerous shape: a project customized a skill's ``SKILL.md`` outside its
    managed block — so the operator has learned that customizations survive —
    while the skill's companion assets predate the asset-marker rollout and
    still have no preserved region. The next upgrade honors one expectation and
    silently discards the other. Running ``tapps-mcp upgrade`` migrates the
    assets, preserving whatever is in them today.
    """
    from tapps_mcp.distribution.doctor_pipeline import _tapps_skill_bases
    from tapps_mcp.distribution.doctor_result import CheckResult
    from tapps_mcp.pipeline.platform_skills import (
        SKILL_COMPANION_FILES,
        SMART_MERGE_SKILL_NAMES,
    )
    from tapps_mcp.pipeline.skill_asset_policy import (
        ASSET_MARKER_BEGIN_PREFIX,
        is_delimitable,
    )
    from tapps_mcp.pipeline.skill_managed_block import MARKER_BEGIN_PREFIX, MARKER_END

    drifted: list[str] = []
    checked = 0
    for host_label, base in _tapps_skill_bases(project_root):
        for skill_name in sorted(SMART_MERGE_SKILL_NAMES):
            skill_dir = base / skill_name
            skill_path = skill_dir / "SKILL.md"
            if not skill_path.exists():
                continue
            checked += 1
            body = skill_path.read_text(encoding="utf-8")
            begin = body.find(MARKER_BEGIN_PREFIX)
            end = body.find(MARKER_END, begin) if begin != -1 else -1
            if end == -1:
                continue  # no managed block yet — the freshness check owns this
            outside = body[end + len(MARKER_END) :]
            if not outside.strip():
                continue  # SKILL.md is uncustomized; assets carry no expectation
            unmarked = [
                rel
                for rel in sorted(SKILL_COMPANION_FILES.get(skill_name, {}))
                if is_delimitable(rel)
                and (skill_dir / rel).exists()
                and ASSET_MARKER_BEGIN_PREFIX not in (skill_dir / rel).read_text(encoding="utf-8")
            ]
            drifted.extend(f"{host_label}/{skill_name}/{rel}" for rel in unmarked)

    if drifted:
        return CheckResult(
            "Skill asset drift",
            False,
            f"customized SKILL.md but {len(drifted)} asset(s) have no preserved "
            f"region: {', '.join(drifted)}",
            "These assets are overwritten wholesale today. Run: tapps-mcp upgrade",
            severity="warn",
        )
    if not checked:
        return CheckResult("Skill asset drift", True, "no managed skills installed")
    return CheckResult(
        "Skill asset drift",
        True,
        f"{checked} managed skill(s): SKILL.md and assets share one upgrade policy",
    )


# Checked on every scaffolded ``.claude/workflows/*.js``, regardless of shape: a
# multi-agent fan-out that never checks its own token budget can run away.
_WORKFLOW_BUDGET_INVARIANT = "budget.remaining("

# Checked only on workflows that opt into the val-verify adversarial-verdict
# shape (detected via _is_verdict_pattern below), never on every workflow —
# a read-only evidence pipeline like linear-disposition-verify has no
# negative/positive control or suppression concept to carry.
_WORKFLOW_VERDICT_INVARIANTS: tuple[str, ...] = (
    "negative_control_result",
    "positive_control_result",
    "green_by_suppression",
)

# Structural fingerprint for "this file is a val-verify-pattern workflow": the
# literal GREEN/RED verdict enum, not prose about what the file claims to do.
_VERDICT_ENUM_MARKERS: tuple[str, ...] = ("'GREEN', 'RED'", '"GREEN", "RED"')


def _is_verdict_pattern(content: str) -> bool:
    return any(marker in content for marker in _VERDICT_ENUM_MARKERS)


def check_workflow_scripts_current(project_root: Path) -> CheckResult:
    """Flag scaffolded ``.claude/workflows/*.js`` missing a safety invariant (TAP-6890).

    Fingerprints on the invariants the val-verify pattern exists to enforce —
    ``budget.remaining(`` on every workflow, plus ``negative_control_result``,
    ``positive_control_result``, and ``green_by_suppression`` on any workflow
    that carries a GREEN/RED verdict schema — never on prose describing what a
    workflow claims to check. A workflow that dropped one of these (or never
    had it) went green on fewer guarantees than the pattern promises, the way
    a stale ``SKILL.md`` drifts from its template; this is that check's
    sibling for the executable-asset class.
    """
    from tapps_mcp.distribution.doctor_result import CheckResult

    workflows_dir = project_root / ".claude" / "workflows"
    if not workflows_dir.is_dir():
        return CheckResult("Workflow safety invariants", True, "no .claude/workflows/ present")

    js_paths = sorted(workflows_dir.glob("*.js"))
    if not js_paths:
        return CheckResult("Workflow safety invariants", True, "no .claude/workflows/*.js present")

    problems: list[str] = []
    for js_path in js_paths:
        content = js_path.read_text(encoding="utf-8")
        missing = []
        if _WORKFLOW_BUDGET_INVARIANT not in content:
            missing.append(_WORKFLOW_BUDGET_INVARIANT)
        if _is_verdict_pattern(content):
            missing.extend(inv for inv in _WORKFLOW_VERDICT_INVARIANTS if inv not in content)
        if missing:
            problems.append(f"{js_path.name} (missing {', '.join(missing)})")

    if problems:
        return CheckResult(
            "Workflow safety invariants",
            False,
            f"{len(problems)}/{len(js_paths)} workflow(s) missing a safety invariant: "
            f"{'; '.join(problems)}",
            "Add the missing invariant(s), or fold the script through val-verify's pattern.",
            severity="warn",
        )
    return CheckResult(
        "Workflow safety invariants",
        True,
        f"{len(js_paths)} workflow(s) in .claude/workflows/ carry every safety invariant they need",
    )
