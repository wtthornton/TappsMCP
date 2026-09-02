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
) -> CheckResult:
    """Shared required-on-full skill freshness check (TAP-6948).

    Fingerprints the deployed managed block against what the *current*
    emitter would produce for *skill_name* — a content comparison (normalized
    for the version stamp), not a probe for a handful of representative
    phrases. A block that shrank, grew, or was hand-edited fails even when it
    still happens to contain every phrase the old check probed for.

    Companions and the expected body are both read from the emitter's own
    registries (``SKILL_COMPANION_FILES``, ``CLAUDE_SKILLS`` / ``CURSOR_SKILLS``)
    rather than duplicated here as literal lists, so a new managed skill only
    needs a thin wrapper — this worker already knows how to check it.
    """
    from tapps_mcp.distribution.context_budget import _skill_tier
    from tapps_mcp.distribution.doctor_pipeline import _tapps_skill_bases
    from tapps_mcp.distribution.doctor_result import CheckResult
    from tapps_mcp.pipeline.platform_skills import (
        CLAUDE_SKILLS,
        CURSOR_SKILLS,
        SKILL_COMPANION_FILES,
    )
    from tapps_mcp.pipeline.skill_managed_block import (
        extract_block,
        normalize_block_version,
        wrap_with_markers,
    )

    tier = _skill_tier(project_root)
    companions = tuple(sorted(SKILL_COMPANION_FILES.get(skill_name, {})))
    emitter_bodies = {"claude": CLAUDE_SKILLS, "cursor": CURSOR_SKILLS}

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
        deployed_block = extract_block(content)
        if deployed_block is None:
            problems.append(f"{host_label}/{skill_name} stale (no managed-block marker)")
            continue
        missing = [c for c in companions if not (skill_dir / c).exists()]
        if missing:
            problems.append(f"{host_label}/{skill_name} missing {', '.join(missing)}")
            continue
        body = emitter_bodies.get(host_label, {}).get(skill_name)
        expected_block = (
            extract_block(wrap_with_markers(body, skill_name)) if body is not None else None
        )
        if expected_block is None or normalize_block_version(
            deployed_block
        ) != normalize_block_version(expected_block):
            problems.append(
                f"{host_label}/{skill_name} stale content "
                "(managed block no longer matches the current emitter; run upgrade --force)"
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
    """Check ``orchestration-prompt`` is deployed current, by content (TAP-5496, TAP-6948)."""
    return _check_managed_skill_current(
        project_root,
        skill_name="orchestration-prompt",
        check_name="orchestration-prompt skill",
    )


def check_wayfind_skill_current(project_root: Path) -> CheckResult:
    """Check ``tapps-wayfind`` is deployed current, by content (TAP-5496, TAP-6948)."""
    return _check_managed_skill_current(
        project_root,
        skill_name="tapps-wayfind",
        check_name="tapps-wayfind skill",
    )


def check_validation_contract_skill_current(project_root: Path) -> CheckResult:
    """Check ``tapps-validation-contract`` is deployed current, by content (TAP-5541, TAP-6948)."""
    return _check_managed_skill_current(
        project_root,
        skill_name="tapps-validation-contract",
        check_name="tapps-validation-contract skill",
    )


def check_skill_mirror_parity(project_root: Path) -> CheckResult:
    """Compare each managed skill's block across every deployed host mirror (TAP-6944).

    The Claude and Cursor copies of a smart-merge skill are generated from the
    same host-agnostic body (see the ``CLAUDE_SKILLS["orchestration-prompt"] =
    ...`` / ``CURSOR_SKILLS["orchestration-prompt"] = ...`` pair in
    platform_skills), so wherever a project deploys both, their managed blocks
    should be byte-identical. A divergence means one mirror drifted — hand-edited,
    or refreshed at a different time than its sibling — without anyone
    noticing: the TAP-6948 freshness check only ever compares a host against
    the emitter, never against the other host.
    """
    from tapps_mcp.distribution.doctor_pipeline import _tapps_skill_bases
    from tapps_mcp.distribution.doctor_result import CheckResult
    from tapps_mcp.pipeline.platform_skills import SMART_MERGE_SKILL_NAMES
    from tapps_mcp.pipeline.skill_managed_block import extract_block

    bases = _tapps_skill_bases(project_root)
    mismatches: list[str] = []
    compared = 0
    for skill_name in sorted(SMART_MERGE_SKILL_NAMES):
        blocks: dict[str, tuple[Path, str]] = {}
        for host_label, base in bases:
            skill_path = base / skill_name / "SKILL.md"
            if not skill_path.exists():
                continue
            block = extract_block(skill_path.read_text(encoding="utf-8"))
            if block is not None:
                blocks[host_label] = (skill_path, block)
        if len(blocks) < 2:
            continue
        compared += 1
        hosts = sorted(blocks)
        reference_host = hosts[0]
        reference_path, reference_block = blocks[reference_host]
        for host_label in hosts[1:]:
            other_path, other_block = blocks[host_label]
            if other_block != reference_block:
                mismatches.append(
                    f"{skill_name}: {reference_path} ({reference_host}) != "
                    f"{other_path} ({host_label})"
                )

    if mismatches:
        return CheckResult(
            "Skill mirror parity",
            False,
            f"{len(mismatches)} skill mirror(s) diverge: {'; '.join(mismatches)}",
            "Run: tapps-mcp upgrade --force to re-sync every host mirror",
        )
    if not compared:
        return CheckResult("Skill mirror parity", True, "no skill deployed to more than one host")
    return CheckResult(
        "Skill mirror parity",
        True,
        f"{compared} managed skill(s) match byte-for-byte across every deployed host",
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
