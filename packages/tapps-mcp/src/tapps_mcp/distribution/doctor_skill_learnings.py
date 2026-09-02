"""Doctor check: skill learnings hygiene (TAP-6861).

``tapps_skill_learnings`` (:mod:`tapps_mcp.server_skill_tools`) exists but is
opt-in — nothing surfaced its findings unless the operator remembered to call
it. This module wires the same deterministic
:func:`tapps_mcp.pipeline.skill_learnings.audit` into the doctor chain so a
near-duplicate or self-contradicting skill ``learnings.md``/``SKILL.md`` pair
shows up on a routine ``tapps_doctor`` run without being asked for.

Scoped to ``near_duplicate`` and ``contradiction`` only — deliberately *not*
size/ceiling, which
:func:`tapps_mcp.distribution.doctor_skills.check_orchestration_prompt_learnings_ceiling`
(TAP-6854) already owns via the shared
:func:`tapps_mcp.pipeline.skill_managed_block.learnings_size_finding`. Both
checks landed independently and would otherwise double-report the same
over-ceiling ``learnings.md`` under two different check names; this module
cedes size/ceiling to that check rather than repeat it. ``already_covered``
and ``region`` are informational classifications, not defects, and are left
to the interactive ``audit`` action.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_result import CheckResult

CHECK_NAME = "Skill learnings hygiene"


def _skill_dirs_with_learnings(project_root: Path) -> list[tuple[str, Path]]:
    """Return ``(skill_name, skill_dir)`` for every skill shipping both files.

    Reuses the same host resolution as the managed-skill freshness checks
    (:func:`tapps_mcp.distribution.doctor_pipeline._tapps_skill_bases`) so this
    check looks in exactly the directories ``tapps-mcp upgrade`` manages —
    never a guessed path. Dedupes by skill name across hosts (Claude/Cursor
    mirrors) so a skill present in both is audited once.
    """
    from tapps_mcp.distribution.doctor_pipeline import _tapps_skill_bases

    found: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for _host_label, base in _tapps_skill_bases(project_root):
        if not base.is_dir():
            continue
        for skill_dir in sorted(base.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name in seen:
                continue
            skill_path = skill_dir / "SKILL.md"
            learnings_path = skill_dir / "learnings.md"
            if skill_path.exists() and learnings_path.exists():
                found.append((skill_dir.name, skill_dir))
                seen.add(skill_dir.name)
    return found


def check_skill_learnings_hygiene(project_root: Path) -> CheckResult:
    """Report near-duplicate/contradiction findings for every skill's learnings pair.

    Never writes. Runs the same pure ``audit()`` the ``tapps_skill_learnings``
    MCP tool calls, so this can never drift from what that tool would report.
    A finding is reported per skill by name and finding class, not a bare
    count, so the operator knows exactly which skill and which check to
    re-run. Size/ceiling is intentionally excluded — see the module
    docstring for why that stays with the ``orchestration-prompt learnings
    ceiling`` check instead of being reported twice.
    """
    from tapps_mcp.pipeline.skill_learnings import audit

    pairs = _skill_dirs_with_learnings(project_root)
    if not pairs:
        return CheckResult(CHECK_NAME, True, "no skill learnings.md files found")

    problems: list[str] = []
    for skill_name, skill_dir in pairs:
        skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        learnings_md = (skill_dir / "learnings.md").read_text(encoding="utf-8")
        report = audit(skill_md, learnings_md)

        if report.near_duplicate:
            problems.append(
                f"{skill_name}: {len(report.near_duplicate)} near-duplicate "
                "bullet cluster(s) in learnings.md (near_duplicate)"
            )
        if report.contradictions:
            problems.append(
                f"{skill_name}: {len(report.contradictions)} contradiction(s) "
                "between SKILL.md's managed block and project region (contradiction)"
            )

    if problems:
        return CheckResult(
            CHECK_NAME,
            False,
            f"{len(problems)} finding(s) across {len(pairs)} skill(s): {'; '.join(problems)}",
            "Run tapps_skill_learnings(action='audit', skill_dir=<path>) for full detail, "
            "then 'trim' or 'promote' as the finding calls for.",
            severity="warn",
        )
    return CheckResult(
        CHECK_NAME,
        True,
        f"{len(pairs)} skill(s) with learnings.md checked, no hygiene findings",
    )


__all__ = ["check_skill_learnings_hygiene"]
