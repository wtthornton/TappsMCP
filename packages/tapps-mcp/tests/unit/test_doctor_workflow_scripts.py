"""Tests for check_workflow_scripts_current (TAP-6890).

The population fixture at ``tests/fixtures/nlt_workflows_20260901/`` is a
byte-for-byte copy of the 10 ``.claude/workflows/*.js`` files in
``nlt-orchestrator`` as measured on 2026-09-01 — copied here because the
check cannot run against that live repo directly. A clean result on these
inputs would mean the checker is broken: the defects are real and present.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tapps_mcp.distribution.doctor_skills import check_workflow_scripts_current
from tapps_mcp.pipeline.platform_workflow_scripts import generate_workflow_scripts

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "nlt_workflows_20260901"

# The 4 files carrying a GREEN/RED verdict schema (measured 2026-09-01).
VERDICT_PATTERN_FILES = frozenset(
    {
        "ceg-hub-verify.js",
        "ceg-logo-pack-verify.js",
        "memory-hardening-verify.js",
        "tmcp-handoff-verify.js",
    }
)
# All 10 files, population for the budget.remaining( invariant.
ALL_FIXTURE_FILES = frozenset(
    {
        "ceg-hub-verify.js",
        "ceg-logo-pack-verify.js",
        "ceg-wave1-gate.js",
        "epic-4145.js",
        "fleet-audit.js",
        "licensed-oracle-sweeps.js",
        "memory-hardening-verify.js",
        "remove-ralph.js",
        "tmcp-handoff-verify.js",
        "webstoredna-linear-cleanup.js",
    }
)
# Of the 10, these 5 have no budget.remaining( call (evidence item 1).
NO_BUDGET_FILES = frozenset(
    {
        "ceg-wave1-gate.js",
        "licensed-oracle-sweeps.js",
        "memory-hardening-verify.js",
        "fleet-audit.js",
        "webstoredna-linear-cleanup.js",
    }
)
# Of the 4 verdict-pattern files, these 3 have no positive_control (evidence item 2).
NO_POSITIVE_CONTROL_FILES = frozenset(
    {"ceg-hub-verify.js", "ceg-logo-pack-verify.js", "memory-hardening-verify.js"}
)


@pytest.fixture()
def nlt_population_project(tmp_path: Path) -> Path:
    workflows_dir = tmp_path / ".claude" / "workflows"
    workflows_dir.mkdir(parents=True)
    for src in FIXTURE_DIR.glob("*.js"):
        shutil.copy(src, workflows_dir / src.name)
    return tmp_path


def test_fixture_population_is_10_files() -> None:
    """Sub-goal-0-style control: confirm the copy matches the measured population."""
    fixture_files = {p.name for p in FIXTURE_DIR.glob("*.js")}
    assert fixture_files == ALL_FIXTURE_FILES
    assert len(fixture_files) == 10


def test_flags_real_defects_on_nlt_population(nlt_population_project: Path) -> None:
    """A clean result here means the checker is broken — these defects are real."""
    result = check_workflow_scripts_current(nlt_population_project)
    assert result.ok is False
    assert result.severity == "warn"

    for fname in NO_BUDGET_FILES:
        assert fname in result.message, f"{fname} (missing budget.remaining() ) not reported"
    for fname in NO_POSITIVE_CONTROL_FILES:
        assert fname in result.message, f"{fname} (missing positive_control_result) not reported"

    # Denominator: 10 files total, and the message states how many are flagged.
    assert "/10 workflow(s)" in result.message


def test_population_breakdown_matches_evidence_bar(nlt_population_project: Path) -> None:
    """State the denominator on every count: budget is checked over 10, controls over 4."""
    budget_short = {
        p.name
        for p in FIXTURE_DIR.glob("*.js")
        if "budget.remaining(" not in p.read_text(encoding="utf-8")
    }
    assert budget_short == NO_BUDGET_FILES  # 5 of 10

    verdict_files = {
        p.name
        for p in FIXTURE_DIR.glob("*.js")
        if "'GREEN', 'RED'" in p.read_text(encoding="utf-8")
        or '"GREEN", "RED"' in p.read_text(encoding="utf-8")
    }
    assert verdict_files == VERDICT_PATTERN_FILES  # exactly the 4 val-verify-pattern files

    no_positive = {
        p.name
        for p in FIXTURE_DIR.glob("*.js")
        if p.name in verdict_files
        and "positive_control_result" not in p.read_text(encoding="utf-8")
    }
    assert no_positive == NO_POSITIVE_CONTROL_FILES  # 3 of the 4


def test_negative_control_clean_fixture_passes(tmp_path: Path) -> None:
    """A checker that always fires is not a checker — show a clean fixture passes."""
    workflows_dir = tmp_path / ".claude" / "workflows"
    workflows_dir.mkdir(parents=True)
    clean = """\
export const meta = { name: 'clean-verify', description: 'fixture', phases: [] }
if (budget.total && budget.remaining() < 1000) { return { aborted: true } }
const VERDICT = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['GREEN', 'RED'] },
    negative_control_result: { type: 'string' },
    positive_control_result: { type: 'string' },
    green_by_suppression: { type: 'boolean' },
  },
}
return { ok: true }
"""
    (workflows_dir / "clean-verify.js").write_text(clean, encoding="utf-8")

    result = check_workflow_scripts_current(tmp_path)
    assert result.ok is True
    assert result.severity == "pass"


def test_scaffolded_workflows_pass_their_own_check(tmp_path: Path) -> None:
    """The two shipped scripts should not immediately trip their own checker."""
    generate_workflow_scripts(tmp_path)
    result = check_workflow_scripts_current(tmp_path)
    assert result.ok is True, result.message


def test_no_workflows_dir_passes(tmp_path: Path) -> None:
    result = check_workflow_scripts_current(tmp_path)
    assert result.ok is True
    assert "no .claude/workflows/" in result.message


def test_non_verdict_workflow_is_not_required_to_carry_control_invariants(tmp_path: Path) -> None:
    """A read-only evidence pipeline has no negative/positive control concept to carry."""
    workflows_dir = tmp_path / ".claude" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "evidence-only.js").write_text(
        "export const meta = { name: 'evidence-only', description: 'x', phases: [] }\n"
        "if (budget.total && budget.remaining() < 1000) { return { aborted: true } }\n"
        "return { ok: true }\n",
        encoding="utf-8",
    )
    result = check_workflow_scripts_current(tmp_path)
    assert result.ok is True, result.message
