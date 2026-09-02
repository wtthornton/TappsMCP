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
from typing import Any

import pytest

from tapps_mcp.gates.models import GateFailure, GateResult, GateThresholds
from tapps_mcp.gates.ratchet import (
    RULE_MATERIALLY_NEW_CONTENT,
    RULE_NEW_FILE,
    RULE_PASSING_AT_BASE,
    RULE_RATCHET_HOLD_OR_IMPROVE,
    RULE_RATCHETED_FAIL,
    SAME_FILE_SIMILARITY_PCT,
    RenameIndex,
    apply_ratchet_to_gate,
    evaluate_ratchet,
)
from tapps_mcp.scoring.models import ScoreResult
from tapps_mcp.tools.validate_changed_orchestrator import _validate_single_file

THRESHOLD = 70.0


class _FakeScorer:
    """Scorer stub: overall score is the file's *first* line, as a float.

    Path-independent by construction, which is the point here (these tests
    are about the rule arithmetic and the git plumbing) and also the reason
    it cannot see TAP-6921 -- see ``test_gate_ratchet_invariant.py``, which
    covers the same rules with the real scorer.

    Only the first line is read (TAP-6922) so a fixture can carry a score
    *and* a body. Rule 1 now keys on how much of the content survives from
    the baseline, which is not a question a one-line fixture can pose.
    """

    language = "python"

    async def score_file(self, path: Path, *, identity_path: Path | None = None) -> ScoreResult:
        """Score the bytes at *path*, reporting them as *identity_path*.

        The stub mirrors the real scorer's split (TAP-6921): content is read
        from where it actually sits, while the identity the caller supplies
        is what the result is labelled with.
        """
        overall = float(path.read_text(encoding="utf-8").splitlines()[0].strip())
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


def _lines(score: str, body: list[str]) -> str:
    """A fixture file: ``score`` on line 1 (what ``_FakeScorer`` reads), then ``body``."""
    return "\n".join([score, *body]) + "\n"


def _make_repo_with_body(tmp_path: Path, score: str, body: list[str]) -> Path:
    """A real git repo whose single commit holds ``pkg/module.py`` = ``score`` + ``body``."""
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "pkg" / "module.py").write_text(_lines(score, body), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline")
    return root


class TestRuleOneKeysOnContentNotPath:
    """TAP-6922: rule 1 asks "is this materially new code", not "is this a new path".

    The path key produced two holes pointing opposite ways -- too generous to
    a file whose content was replaced, too harsh on a file that only moved --
    and each of these is a control for one of them. The controls that matter
    are the ones the *old* code fails: ``test_wholly_replaced_content_...``
    passed (ratcheted) before this change, and ``test_below_threshold_file_
    moved_unchanged_...`` failed (absolute) before it.
    """

    async def test_wholly_replaced_content_does_not_inherit_the_old_baseline(
        self, tmp_path: Path
    ) -> None:
        """NEGATIVE (hole A): replacing a below-threshold file's content wholesale
        must not hand the new code the old content's low baseline.

        Against ``c1e381ad`` this returned a ratcheted PASS: the path still
        resolved at the baseline, so rule 3 compared brand-new code against a
        score derived from content that no longer existed anywhere.
        """
        repo = _make_repo_with_body(tmp_path, "65.0", [f"legacy_line_{i}" for i in range(20)])
        baseline = _sha(repo)
        # Every line replaced; the only survivor is the score line the stub reads.
        (repo / "pkg" / "module.py").write_text(
            _lines("65.0", [f"unrelated_new_line_{i}" for i in range(20)]), encoding="utf-8"
        )

        outcome = await evaluate_ratchet(
            path=repo / "pkg" / "module.py",
            repo_root=repo,
            baseline_ref=baseline,
            current_score=68.0,  # better than the 65.0 baseline, still under 70
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

        assert outcome.passes is False
        assert outcome.rule == RULE_MATERIALLY_NEW_CONTENT
        assert outcome.shared_pct is not None
        assert outcome.shared_pct < SAME_FILE_SIMILARITY_PCT

    async def test_genuinely_new_path_still_gets_the_absolute_threshold(
        self, tmp_path: Path
    ) -> None:
        """NEGATIVE (no-regression): new code at a new path is still never grandfathered.

        Deliberately run in a repo where a *different* file was renamed, so
        the rename map is non-empty. A map lookup that fell through to "some
        rename, therefore an ancestor" would grandfather this file; the map
        must be keyed strictly on this path.
        """
        repo = _make_repo_with_body(tmp_path, "65.0", [f"legacy_line_{i}" for i in range(20)])
        baseline = _sha(repo)
        _git(repo, "mv", "pkg/module.py", "pkg/moved.py")  # unrelated rename, same run

        brand_new = repo / "pkg" / "brand_new.py"
        brand_new.write_text(_lines("99.0", ["something = 1"]), encoding="utf-8")

        outcome = await evaluate_ratchet(
            path=brand_new,
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
        assert outcome.base_path is None

    async def test_below_threshold_file_moved_unchanged_is_judged_against_its_content(
        self, tmp_path: Path
    ) -> None:
        """POSITIVE (hole B): a move must not re-deadlock a legacy file.

        Against ``c1e381ad`` the new path was absent at the baseline, so rule
        1 fired and the absolute threshold was applied to code that did not
        change -- the exact deadlock TAP-6904 was filed to remove, reachable
        by any refactor that relocates a legacy module.
        """
        repo = _make_repo_with_body(tmp_path, "65.0", [f"legacy_line_{i}" for i in range(20)])
        baseline = _sha(repo)
        (repo / "pkg" / "relocated").mkdir()
        _git(repo, "mv", "pkg/module.py", "pkg/relocated/module.py")

        outcome = await evaluate_ratchet(
            path=repo / "pkg" / "relocated" / "module.py",
            repo_root=repo,
            baseline_ref=baseline,
            current_score=65.0,  # unchanged content, unchanged score
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

        assert outcome.rule == RULE_RATCHET_HOLD_OR_IMPROVE
        assert outcome.passes is True
        assert outcome.base_score == 65.0
        assert outcome.base_path == "pkg/module.py"
        assert outcome.shared_pct == 100.0

    async def test_moved_file_that_regresses_still_fails(self, tmp_path: Path) -> None:
        """A move is not an amnesty: rules 2 and 3 apply normally to the moved content.

        Without this, closing hole B would open a new one -- move a file and
        degrade it in the same commit, and the ratchet would have nothing to
        compare against.
        """
        repo = _make_repo_with_body(tmp_path, "65.0", [f"legacy_line_{i}" for i in range(20)])
        baseline = _sha(repo)
        (repo / "pkg" / "relocated").mkdir()
        _git(repo, "mv", "pkg/module.py", "pkg/relocated/module.py")

        outcome = await evaluate_ratchet(
            path=repo / "pkg" / "relocated" / "module.py",
            repo_root=repo,
            baseline_ref=baseline,
            current_score=60.0,  # moved *and* degraded
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

        assert outcome.rule == RULE_RATCHETED_FAIL
        assert outcome.passes is False
        assert outcome.base_score == 65.0

    async def test_deleting_most_of_a_file_is_not_materially_new_code(self, tmp_path: Path) -> None:
        """A megafile split leaves a small remnant at the original path. Nothing
        new arrived there, so rule 1 must not fire -- which is why the measure
        is directional rather than a symmetric diff percentage."""
        repo = _make_repo_with_body(tmp_path, "65.0", [f"legacy_line_{i}" for i in range(40)])
        baseline = _sha(repo)
        # 36 of 40 body lines moved out to sibling modules; the rest untouched.
        (repo / "pkg" / "module.py").write_text(
            _lines("65.0", [f"legacy_line_{i}" for i in range(4)]), encoding="utf-8"
        )

        outcome = await evaluate_ratchet(
            path=repo / "pkg" / "module.py",
            repo_root=repo,
            baseline_ref=baseline,
            current_score=66.0,
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

        assert outcome.shared_pct == 100.0
        assert outcome.rule == RULE_RATCHET_HOLD_OR_IMPROVE
        assert outcome.passes is True


class TestSimilarityThresholdBoundary:
    """One case each side of ``SAME_FILE_SIMILARITY_PCT``.

    Both fixtures hold exactly 20 significant lines in the working tree, so
    each shared line is worth 5 percentage points and the two cases sit one
    line apart across the boundary. ``SAME_FILE_SIMILARITY_PCT`` is inclusive:
    at exactly half surviving, it is still the same file.
    """

    @staticmethod
    def _repo_with_survivors(tmp_path: Path, survivors: int) -> Path:
        """Baseline of 20 body lines; working tree keeps ``survivors`` of them
        and fills the rest with new lines, for 20 lines either way."""
        repo = _make_repo_with_body(tmp_path, "65.0", [f"legacy_line_{i}" for i in range(19)])
        body = [f"legacy_line_{i}" for i in range(survivors - 1)]
        body += [f"new_line_{i}" for i in range(20 - survivors)]
        (repo / "pkg" / "module.py").write_text(_lines("65.0", body), encoding="utf-8")
        return repo

    async def _judge(self, repo: Path, baseline: str) -> Any:
        return await evaluate_ratchet(
            path=repo / "pkg" / "module.py",
            repo_root=repo,
            baseline_ref=baseline,
            current_score=68.0,  # above the 65.0 baseline, below the 70.0 threshold
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

    async def test_exactly_at_the_threshold_is_still_the_same_file(self, tmp_path: Path) -> None:
        """10 of 20 lines survive -> 50.0%, the threshold itself -> rule 3 applies."""
        repo = self._repo_with_survivors(tmp_path, survivors=10)
        outcome = await self._judge(repo, _sha(repo))

        assert outcome.shared_pct == float(SAME_FILE_SIMILARITY_PCT)
        assert outcome.rule == RULE_RATCHET_HOLD_OR_IMPROVE
        assert outcome.passes is True

    async def test_one_line_below_the_threshold_is_materially_new(self, tmp_path: Path) -> None:
        """9 of 20 lines survive -> 45.0%, one line under -> rule 1 applies."""
        repo = self._repo_with_survivors(tmp_path, survivors=9)
        outcome = await self._judge(repo, _sha(repo))

        assert outcome.shared_pct == 45.0
        assert outcome.rule == RULE_MATERIALLY_NEW_CONTENT
        assert outcome.passes is False


class TestRenameInformationCost:
    """How rename information is obtained, and what happens without it."""

    async def test_rename_map_is_built_once_for_a_whole_batch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule 1 must not cost a subprocess per file.

        The index is lazy *and* shared: judging three moved files through one
        :class:`RenameIndex` shells out to git once, not three times.
        """
        repo = _make_repo_with_body(tmp_path, "65.0", [f"legacy_line_{i}" for i in range(20)])
        for name in ("b", "c"):
            src = repo / "pkg" / f"{name}.py"
            src.write_text(
                _lines("65.0", [f"legacy_line_{i}" for i in range(20)]), encoding="utf-8"
            )
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "three-below-threshold-files")
        baseline = _sha(repo)
        for name in ("module", "b", "c"):
            _git(repo, "mv", f"pkg/{name}.py", f"pkg/moved_{name}.py")

        renames = RenameIndex(repo, baseline)
        builds = 0
        real_build = RenameIndex._build

        def counting_build(self: RenameIndex) -> dict[str, str]:
            nonlocal builds
            builds += 1
            return real_build(self)

        monkeypatch.setattr(RenameIndex, "_build", counting_build)

        for name in ("module", "b", "c"):
            outcome = await evaluate_ratchet(
                path=repo / "pkg" / f"moved_{name}.py",
                repo_root=repo,
                baseline_ref=baseline,
                current_score=65.0,
                threshold=THRESHOLD,
                scorer=_FakeScorer(),
                quick=False,
                renames=renames,
            )
            assert outcome.rule == RULE_RATCHET_HOLD_OR_IMPROVE
            assert outcome.base_path == f"pkg/{name}.py"

        assert builds == 1

    async def test_unchanged_run_never_shells_out_for_renames(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Laziness: every path resolves at the baseline, so nothing is asked of git."""
        repo = _make_repo_with_body(tmp_path, "65.0", [f"legacy_line_{i}" for i in range(20)])
        baseline = _sha(repo)

        renames = RenameIndex(repo, baseline)

        def fail_build(self: RenameIndex) -> dict[str, str]:
            raise AssertionError("rename detection ran for a file that never moved")

        monkeypatch.setattr(RenameIndex, "_build", fail_build)

        outcome = await evaluate_ratchet(
            path=repo / "pkg" / "module.py",
            repo_root=repo,
            baseline_ref=baseline,
            current_score=66.0,
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
            renames=renames,
        )

        assert outcome.rule == RULE_RATCHET_HOLD_OR_IMPROVE

    async def test_without_rename_information_it_degrades_to_the_path_lookup(
        self, tmp_path: Path
    ) -> None:
        """``validate-changed`` accepts an arbitrary ``--file-paths`` list that need
        not be a git diff at all. When git cannot answer -- here the baseline ref
        does not resolve -- rule 1 falls back to the pre-TAP-6922 path lookup and
        applies the absolute threshold, which is the stricter of the two answers.
        """
        repo = _make_repo_with_body(tmp_path, "65.0", [f"legacy_line_{i}" for i in range(20)])

        outcome = await evaluate_ratchet(
            path=repo / "pkg" / "module.py",
            repo_root=repo,
            baseline_ref="refs/heads/no-such-branch",
            current_score=66.0,
            threshold=THRESHOLD,
            scorer=_FakeScorer(),
            quick=False,
        )

        assert outcome.rule == RULE_NEW_FILE
        assert outcome.passes is False
