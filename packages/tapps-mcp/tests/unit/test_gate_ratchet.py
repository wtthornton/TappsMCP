"""Tests for the monotonic quality-gate ratchet (TAP-6904).

``validate_changed`` applies one absolute overall-score threshold to every
changed file, including a file that was already below it before the change
existed -- there is no honest way to remediate such a file because
remediating it means touching it. These tests cover the three ratchet rules
that make remediation possible (:mod:`tapps_mcp.gates.ratchet`), plus the
two structural guarantees the design depends on: omitting ``baseline_ref``
is a strict no-op (today's behaviour, unchanged), and an already-passing
file is never touched by the ratchet at all.

Rule tests exercise :func:`evaluate_ratchet` against a *real* git repo (the
part worth verifying for real is the git plumbing -- "does this file exist
at this ref, and what did it look like"). Scoring itself is stubbed via
``_FakeScorer`` so these tests don't depend on ruff/radon/bandit output;
the scorer's own correctness is covered by ``test_gate_evaluator.py`` and
the scorer suite.

``_FakeScorer`` is deliberately path-independent, so it is blind to how the
ratchet scores the baseline copy -- the defect TAP-6921 found. The rules are
therefore *also* covered against the real scorer, plus the
unchanged-content scoring invariant, in ``test_gate_ratchet_invariant.py``.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from tapps_mcp.gates.models import GateFailure, GateResult, GateThresholds
from tapps_mcp.gates.ratchet import (
    RULE_NEW_FILE,
    RULE_PASSING_AT_BASE,
    RULE_RATCHET_HOLD_OR_IMPROVE,
    RULE_RATCHETED_FAIL,
    apply_ratchet_to_gate,
    evaluate_ratchet,
)
from tapps_mcp.scoring.models import ScoreResult
from tapps_mcp.tools.validate_changed_orchestrator import _validate_single_file

THRESHOLD = 70.0


class _FakeScorer:
    """Scorer stub: overall score is just the file's text content, as a float.

    Path-independent by construction, which is the point here (these tests
    are about the rule arithmetic and the git plumbing) and also the reason
    it cannot see TAP-6921 -- see ``test_gate_ratchet_invariant.py``, which
    covers the same rules with the real scorer.
    """

    language = "python"

    async def score_file(self, path: Path, *, identity_path: Path | None = None) -> ScoreResult:
        """Score the bytes at *path*, reporting them as *identity_path*.

        The stub mirrors the real scorer's split (TAP-6921): content is read
        from where it actually sits, while the identity the caller supplies
        is what the result is labelled with.
        """
        overall = float(path.read_text(encoding="utf-8").strip())
        return ScoreResult(
            file_path=str(identity_path or path), categories={}, overall_score=overall
        )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _sha(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    return proc.stdout.strip()


def _make_repo(tmp_path: Path) -> Path:
    """A tiny real git repo with one commit: pkg/module.py scored 65.0 (below threshold)."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")

    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "module.py").write_text("65.0", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "below-threshold-65")
    return root


class TestEvaluateRatchetRules:
    """The three TAP-6904 rules, checked against a real git repo."""

    async def test_new_file_absent_at_baseline_fails_regardless_of_score(
        self, tmp_path: Path
    ) -> None:
        """Rule 1 (negative): a file absent at baseline is never grandfathered."""
        repo = _make_repo(tmp_path)
        baseline = _sha(repo)
        never_committed = repo / "pkg" / "brand_new.py"
        never_committed.write_text("99.0", encoding="utf-8")  # even a "great" score...

        outcome = await evaluate_ratchet(
            path=never_committed,
            repo_root=repo,
            baseline_ref=baseline,
            current_score=99.0,
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

        assert outcome.rule == RULE_NEW_FILE
        assert outcome.passes is False
        assert outcome.base_score is None

    async def test_file_passing_at_baseline_that_regresses_fails(self, tmp_path: Path) -> None:
        """Rule 2 (negative): a file passing at baseline may never fall through the ratchet."""
        repo = _make_repo(tmp_path)
        (repo / "pkg" / "module.py").write_text("82.0", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "passing-82")
        baseline = _sha(repo)

        outcome = await evaluate_ratchet(
            path=repo / "pkg" / "module.py",
            repo_root=repo,
            baseline_ref=baseline,
            current_score=65.0,  # regressed from 82 to 65
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

        assert outcome.rule == RULE_PASSING_AT_BASE
        assert outcome.passes is False
        assert outcome.base_score == 82.0
        assert outcome.current_score == 65.0

    async def test_below_baseline_that_drops_further_fails_and_shows_the_drop(
        self, tmp_path: Path
    ) -> None:
        """Rule 3 (negative): below threshold and scores lower than baseline -> FAIL."""
        repo = _make_repo(tmp_path)
        baseline = _sha(repo)  # base score 65.0, below THRESHOLD

        outcome = await evaluate_ratchet(
            path=repo / "pkg" / "module.py",
            repo_root=repo,
            baseline_ref=baseline,
            current_score=60.0,  # dropped from 65.0
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

        assert outcome.rule == RULE_RATCHETED_FAIL
        assert outcome.passes is False
        assert outcome.base_score == 65.0
        assert outcome.current_score == 60.0
        # legibility requirement: the drop must be visible in the message
        assert "60.0" in outcome.message
        assert "65.0" in outcome.message

    async def test_below_baseline_that_improves_but_stays_under_passes(
        self, tmp_path: Path
    ) -> None:
        """Rule 3 (positive): below threshold but holds/improves -> ratcheted PASS."""
        repo = _make_repo(tmp_path)
        baseline = _sha(repo)  # base score 65.0

        outcome = await evaluate_ratchet(
            path=repo / "pkg" / "module.py",
            repo_root=repo,
            baseline_ref=baseline,
            current_score=68.0,  # improved from 65.0, still < 70 threshold
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

        assert outcome.rule == RULE_RATCHET_HOLD_OR_IMPROVE
        assert outcome.passes is True
        assert outcome.base_score == 65.0
        assert outcome.current_score == 68.0


class TestApplyRatchetToGate:
    """Structural guarantees the ratchet design depends on."""

    async def test_no_baseline_ref_is_a_strict_noop(self, tmp_path: Path) -> None:
        """Positive control: omitting --baseline-ref must not touch the gate at all."""
        repo = _make_repo(tmp_path)
        gate = GateResult(
            passed=False,
            failures=[
                GateFailure(category="overall", actual=65.0, threshold=THRESHOLD, message="x")
            ],
            thresholds=GateThresholds(overall_min=THRESHOLD),
        )
        original_failures = list(gate.failures)
        score = ScoreResult(file_path="x", categories={}, overall_score=65.0)

        result = await apply_ratchet_to_gate(
            gate,
            score=score,
            path=repo / "pkg" / "module.py",
            scorer=_FakeScorer(),
            quick=False,
            baseline_ref="",  # the default -- ratchet off
            repo_root=repo,
        )

        assert result is None
        assert gate.passed is False
        assert gate.failures == original_failures

    async def test_comfortably_passing_file_is_unaffected(self, tmp_path: Path) -> None:
        """Positive control: a file above threshold is untouched, identical to today,
        even with --baseline-ref set -- there is nothing for the ratchet to override."""
        repo = _make_repo(tmp_path)
        gate = GateResult(
            passed=True, failures=[], thresholds=GateThresholds(overall_min=THRESHOLD)
        )
        score = ScoreResult(file_path="x", categories={}, overall_score=95.0)

        result = await apply_ratchet_to_gate(
            gate,
            score=score,
            path=repo / "pkg" / "module.py",
            scorer=_FakeScorer(),
            quick=False,
            baseline_ref=_sha(repo),  # ratchet ON, but gate already passed
            repo_root=repo,
        )

        assert result is None
        assert gate.passed is True
        assert gate.failures == []

    async def test_ratcheted_pass_never_clears_a_non_overall_absolute_failure(
        self, tmp_path: Path
    ) -> None:
        """A category-minimum / security-floor failure is never ratcheted away --
        only the overall-score failure can be relaxed."""
        repo = _make_repo(tmp_path)
        baseline = _sha(repo)  # base score 65.0, below threshold
        gate = GateResult(
            passed=False,
            failures=[
                GateFailure(category="overall", actual=68.0, threshold=THRESHOLD, message="x"),
                GateFailure(
                    category="security", actual=3.0, threshold=5.0, message="CRITICAL: floor"
                ),
            ],
            thresholds=GateThresholds(overall_min=THRESHOLD),
        )
        score = ScoreResult(file_path="x", categories={}, overall_score=68.0)

        result = await apply_ratchet_to_gate(
            gate,
            score=score,
            path=repo / "pkg" / "module.py",
            scorer=_FakeScorer(),
            quick=False,
            baseline_ref=baseline,
            repo_root=repo,
        )

        assert result is not None
        assert result["rule"] == RULE_RATCHET_HOLD_OR_IMPROVE
        # the overall failure was cleared, but the gate still fails on security
        assert gate.passed is False
        assert [f.category for f in gate.failures] == ["security"]


async def test_validate_single_file_without_baseline_ref_carries_no_ratchet_key(
    tmp_path: Path,
) -> None:
    """Wiring check: the no-flag path through the real orchestrator is untouched.

    ``_validate_single_file`` only reaches the ratchet inside ``if
    baseline_ref:`` -- calling it without the parameter (the CLI/MCP
    default) must produce a result with no "ratchet" key at all, proving the
    ratchet is byte-identical no-ops into today's behaviour rather than
    merely "usually a no-op".
    """
    repo = _make_repo(tmp_path)
    target = repo / "pkg" / "real.py"
    target.write_text("x = 1\n", encoding="utf-8")
    sem = asyncio.Semaphore(1)

    result = await _validate_single_file(
        target, preset="standard", quick=True, do_security_full=False, sem=sem
    )

    assert "ratchet" not in result
