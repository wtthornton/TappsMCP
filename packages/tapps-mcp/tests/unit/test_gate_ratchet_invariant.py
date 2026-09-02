"""The ratchet's scoring invariant, checked with the *real* scorer (TAP-6921).

``test_gate_ratchet.py`` covers the three rules with ``_FakeScorer``, whose
score is "the file's text parsed as a float" -- path-independent by
construction. That stub is exactly blind to the class of defect TAP-6921
found: :func:`~tapps_mcp.gates.ratchet._score_base_content` scored the
baseline copy from a scratch directory, and three of the seven weighted
categories (``test_coverage``, ``structure``, ``devex``) are derived from
the path rather than the bytes. The baseline therefore came out 5.20 points
low on 107 of this repo's 577 source files, handing every one of them that
much free downward headroom.

The deliverable here is not a test for that one category. It is the
invariant that makes any future path-derived category safe:

    For a file whose content is unchanged between the baseline ref and the
    working tree, ``evaluate_ratchet`` must return
    ``base_score == current_score``, exactly.

Probes are real files from this repo (so real ``tests/`` layout, real
project root, real workspace members), chosen at collection time rather
than hardcoded: one whose ``test_coverage`` comes from the import-scan
branch (4.0 -- the branch the scratch directory destroyed) and one whose
does not, so the invariant is checked on both sides of that branch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tapps_mcp.gates.ratchet import (
    RULE_RATCHETED_FAIL,
    SAME_FILE_SIMILARITY_PCT,
    evaluate_ratchet,
)
from tapps_mcp.scoring.ast_metrics import AstMetricsMixin
from tapps_mcp.server_helpers import _get_scorer_for_file

# Any threshold works for the invariant (both rule 2 and rule 3 report a
# base score); 70.0 is the ``standard`` preset's real overall minimum.
THRESHOLD = 70.0

# The import-scan branch of ``_coverage_heuristic``: "no test file is named
# after this module, but some test imports it". Worth 4.0/10 at weight 0.13,
# i.e. 5.20 points of the /100 overall score.
_IMPORT_SCAN_COVERAGE = 4.0


def _git_out(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout


def _repo_root() -> Path:
    return Path(_git_out(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel").strip())


def _tracked_unchanged_sources(repo: Path) -> list[Path]:
    """Tracked ``packages/*/src/**/*.py`` files identical to their HEAD content.

    The invariant only says anything about files whose content did not
    change, so anything this branch is editing is filtered out -- otherwise
    the lane's own working tree would decide whether its regression test
    passes.
    """
    changed = set(_git_out(repo, "diff", "--name-only", "HEAD", "--", "packages").split())
    out: list[Path] = []
    for rel in _git_out(repo, "ls-files", "--", "packages").splitlines():
        parts = rel.split("/")
        if rel in changed or not rel.endswith(".py"):
            continue
        if len(parts) < 4 or parts[2] != "src":
            continue
        out.append(repo / rel)
    return out


def _pick_probes(repo: Path) -> list[Path]:
    """One file on each side of the ``_coverage_heuristic`` import-scan branch.

    Picked by scanning rather than hardcoded: a hardcoded path silently
    stops exercising the 4.0 branch the day somebody adds a
    ``test_<stem>.py`` next to it, and the test would keep passing while
    covering nothing.
    """
    on_branch: Path | None = None
    off_branch: Path | None = None
    for path in _tracked_unchanged_sources(repo):
        coverage = AstMetricsMixin._coverage_heuristic(path)
        if coverage == _IMPORT_SCAN_COVERAGE:
            on_branch = on_branch or path
        else:
            off_branch = off_branch or path
        if on_branch is not None and off_branch is not None:
            break
    return [p for p in (on_branch, off_branch) if p is not None]


async def _current_score(path: Path, scorer: Any, *, quick: bool) -> float:
    """Score *path* exactly the way ``validate_changed`` does in this mode.

    The ratchet compares against whatever the caller measured, so the
    baseline and the current score must come from the same seam --
    ``score_and_scan_quick`` for ``--quick``, ``scorer.score_file``
    otherwise.
    """
    from tapps_core.config.settings import load_settings
    from tapps_mcp.server_scoring_tools import score_and_scan_quick

    if quick:
        score_result, _sec = await score_and_scan_quick(path.resolve(), scorer, load_settings())
    else:
        score_result = await scorer.score_file(path.resolve())
    return round(score_result.overall_score, 2)


@pytest.mark.parametrize("quick", [True, False], ids=["quick", "full"])
async def test_unchanged_content_scores_identically_at_baseline_and_in_tree(
    quick: bool,
) -> None:
    """The invariant: unchanged content => ``base_score == current_score``.

    Runs both scoring modes because ``_score_base_content`` has a separate
    seam for each (``score_and_scan_quick`` vs ``scorer.score_file``), and a
    fix applied to only one of them would leave the other permissive.
    """
    repo = _repo_root()
    probes = _pick_probes(repo)
    assert len(probes) == 2, (
        "expected one source file on each side of the import-scan coverage branch; "
        f"found {[str(p) for p in probes]}"
    )
    assert AstMetricsMixin._coverage_heuristic(probes[0]) == _IMPORT_SCAN_COVERAGE, (
        "first probe must exercise the import-scan branch"
    )

    for path in probes:
        scorer = _get_scorer_for_file(path)
        assert scorer is not None
        current = await _current_score(path, scorer, quick=quick)
        outcome = await evaluate_ratchet(
            path=path,
            repo_root=repo,
            baseline_ref="HEAD",
            current_score=current,
            threshold=THRESHOLD,
            scorer=scorer,
            quick=quick,
        )
        rel = path.relative_to(repo)
        assert outcome.base_score is not None, f"{rel}: no baseline score ({outcome.rule})"
        assert outcome.base_score == current, (
            f"{rel}: content is byte-identical to HEAD, but the ratchet scored the "
            f"baseline {outcome.base_score} against a current {current} "
            f"(delta {round(outcome.base_score - current, 2)}) -- the baseline is being "
            "scored as if it lived somewhere other than this file's real path"
        )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


_CLEAN_MODULE = '''"""A small, tidy module."""

from __future__ import annotations


def add(left: int, right: int) -> int:
    """Return the sum of two integers."""
    return left + right


def scale(values: list[int], factor: int) -> list[int]:
    """Return *values* with every element multiplied by *factor*."""
    return [value * factor for value in values]
'''

# The *same* module, degraded: an eval() (bandit) and a bare except
# (ruff/security), grafted onto the clean module's own lines.
#
# TAP-6922: "same module" has to be true line-for-line now, not just in
# spirit. This fixture used to swap in an unrelated body that shared 11.8% of
# its lines with the baseline, which rule 1 correctly classifies as materially
# new code -- so the test would have stopped exercising rule 3 at all. The
# degradation is therefore applied in place, and
# ``test_rule_three_regression_is_caught_by_the_real_scorer`` asserts the
# overlap stays on the rule-3 side of ``SAME_FILE_SIMILARITY_PCT`` so this
# cannot drift back without the test saying so.
_DEGRADED_MODULE = '''"""A small, tidy module."""

from __future__ import annotations


def add(left: int, right: int) -> int:
    """Return the sum of two integers."""
    return eval(f"{left} + {right}")


def scale(values: list[int], factor: int) -> list[int]:
    """Return *values* with every element multiplied by *factor*."""
    try:
        return [value * factor for value in values]
    except:
        return []
'''


async def test_rule_three_regression_is_caught_by_the_real_scorer(tmp_path: Path) -> None:
    """Rule 3 (negative) end to end with the real scorer, not ``_FakeScorer``.

    ``test_gate_ratchet.py`` proves the rule *arithmetic* with a stub. This
    proves the rule still fires when the numbers on both sides come from the
    scorer the gate actually runs -- which is where TAP-6921 hid, because a
    silently-deflated baseline turns this regression into a pass.
    """
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    module = repo / "pkg" / "module.py"
    module.write_text(_CLEAN_MODULE, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "clean")

    module.write_text(_DEGRADED_MODULE, encoding="utf-8")
    scorer = _get_scorer_for_file(module)
    assert scorer is not None
    current = await _current_score(module, scorer, quick=True)

    outcome = await evaluate_ratchet(
        path=module,
        repo_root=repo,
        baseline_ref="HEAD",
        current_score=current,
        # 100.0 keeps rule 2 out of the way: nothing is "passing at base",
        # so the comparison under test is always current-vs-baseline.
        threshold=100.0,
        scorer=scorer,
        quick=True,
    )

    assert outcome.shared_pct is not None
    assert outcome.shared_pct >= SAME_FILE_SIMILARITY_PCT, (
        f"the degraded fixture shares only {outcome.shared_pct}% of its lines with the "
        f"baseline, so rule 1 judges it materially new code and this test no longer "
        f"exercises rule 3 at all (rule fired: {outcome.rule})"
    )
    assert outcome.base_score is not None
    assert outcome.current_score < outcome.base_score, (
        f"the degraded module scored {outcome.current_score} against a baseline of "
        f"{outcome.base_score}; the fixture is no longer degrading the score"
    )
    assert outcome.rule == RULE_RATCHETED_FAIL
    assert outcome.passes is False
