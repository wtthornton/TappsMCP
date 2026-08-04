"""Doctor checks for managed multi-file platform skills (TAP-5496).

Required on ``skill_tier: full``; core tier skips absence. When present on any
tier, require managed-block marker + companions + content fingerprints so
``tapps-mcp upgrade --force`` clears stale copies.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.distribution.doctor import CheckResult


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
    from tapps_mcp.distribution.doctor import CheckResult, _tapps_skill_bases

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
        companions=("assets/prompt-template.md", "references/claude-feature-map.md"),
        required_phrases=("validation contract", "expected-fail"),
        phrase_sources=("assets/prompt-template.md",),
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
