"""Tests for the description-eval harness under scripts/eval-descriptions/.

The harness measures tool-selection accuracy across description-rewrite
git refs. These tests cover the pure-logic functions (parsing, scoring,
diffing) — the Claude-CLI-dependent flow is covered by manual eval runs,
not unit tests, because it requires OAuth + the live MCP catalog.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL_DIR = REPO_ROOT / "scripts" / "eval-descriptions"


def _load_module(name: str) -> "ModuleType":
    """Load a sibling script as a module (path-based import).

    The module must be registered in ``sys.modules`` BEFORE ``exec_module``,
    otherwise dataclass(es) defined inside fail with
    ``AttributeError: 'NoneType' object has no attribute '__dict__'`` —
    the dataclass decorator looks up ``cls.__module__`` in ``sys.modules``
    and crashes on the missing entry.
    """
    path = EVAL_DIR / f"{name}.py"
    assert path.exists(), f"missing {path}"
    # The compare module imports `report` as a sibling — ensure EVAL_DIR is
    # on sys.path so that resolution works during test collection.
    if str(EVAL_DIR) not in sys.path:
        sys.path.insert(0, str(EVAL_DIR))
    mod_name = f"eval_descriptions_{name}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def run_mod() -> "ModuleType":
    return _load_module("run")


@pytest.fixture
def compare_mod() -> "ModuleType":
    return _load_module("compare")


@pytest.fixture
def report_mod() -> "ModuleType":
    return _load_module("report")


class TestScore:
    """Pure scoring function: exact / acceptable / wrong / no_tool."""

    def test_exact_match(self, run_mod) -> None:
        assert run_mod.score("tapps_lookup_docs", [], "tapps_lookup_docs") == "exact"

    def test_acceptable_alternative(self, run_mod) -> None:
        assert (
            run_mod.score("tapps_quick_check", ["tapps_score_file"], "tapps_score_file")
            == "acceptable"
        )

    def test_wrong_tool(self, run_mod) -> None:
        assert (
            run_mod.score("tapps_lookup_docs", [], "tapps_security_scan") == "wrong"
        )

    def test_no_tool_called(self, run_mod) -> None:
        assert run_mod.score("tapps_lookup_docs", [], None) == "no_tool"

    def test_acceptable_takes_priority_over_wrong(self, run_mod) -> None:
        # If the actual tool is in alternatives, that's acceptable — never wrong.
        verdict = run_mod.score("expected_x", ["alt_y", "alt_z"], "alt_z")
        assert verdict == "acceptable"


class TestFirstMcpToolCall:
    """Parses Claude CLI stream-json events for the first MCP tool_use."""

    def test_finds_mcp_tool_use(self, run_mod) -> None:
        events = [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "thinking..."},
                        {"type": "tool_use", "name": "mcp__tapps-mcp__tapps_lookup_docs"},
                    ]
                }
            }
        ]
        assert run_mod.first_mcp_tool_call(events) == "mcp__tapps-mcp__tapps_lookup_docs"

    def test_skips_non_mcp_tools(self, run_mod) -> None:
        # Built-in tools like TodoWrite must NOT count — we only score MCP picks.
        events = [
            {"message": {"content": [{"type": "tool_use", "name": "TodoWrite"}]}},
            {"message": {"content": [{"type": "tool_use", "name": "mcp__tapps-mcp__tapps_doctor"}]}},
        ]
        assert run_mod.first_mcp_tool_call(events) == "mcp__tapps-mcp__tapps_doctor"

    def test_returns_none_when_no_tool_used(self, run_mod) -> None:
        events = [
            {"message": {"content": [{"type": "text", "text": "I don't know which tool."}]}}
        ]
        assert run_mod.first_mcp_tool_call(events) is None

    def test_handles_empty_event_stream(self, run_mod) -> None:
        assert run_mod.first_mcp_tool_call([]) is None

    def test_handles_malformed_event(self, run_mod) -> None:
        # Stream-json sometimes emits events without `content` or with wrong shape.
        events = [
            {"type": "system", "message": "hello"},
            {"message": {"content": "not a list"}},
            {},
            {"message": {"content": [{"type": "tool_use"}]}},  # no name
            {"message": {"content": [{"type": "tool_use", "name": "mcp__x__y"}]}},
        ]
        assert run_mod.first_mcp_tool_call(events) == "mcp__x__y"


class TestFilterScenarios:
    """`_filter_scenarios` narrows the scenarios list when --only is set."""

    def test_returns_all_when_filter_empty(self, run_mod) -> None:
        scenarios = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        assert run_mod._filter_scenarios(scenarios, "") == scenarios

    def test_filters_to_named_ids(self, run_mod) -> None:
        scenarios = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        kept = run_mod._filter_scenarios(scenarios, "a,c")
        assert [s["id"] for s in kept] == ["a", "c"]

    def test_handles_whitespace_in_filter(self, run_mod) -> None:
        scenarios = [{"id": "a"}, {"id": "b"}]
        kept = run_mod._filter_scenarios(scenarios, " a , b ")
        assert [s["id"] for s in kept] == ["a", "b"]


class TestBuildSummary:
    """`build_summary` aggregates verdicts into pass-rate metrics."""

    def _result(self, run_mod, verdict: str, sid: str = "x") -> object:
        return run_mod.ScenarioResult(
            scenario_id=sid, category="cat", expected_tool="t",
            acceptable_alternatives=[], actual_tool=None,
            verdict=verdict, elapsed_ms=10,
        )

    def test_empty_results(self, run_mod, tmp_path) -> None:
        s = run_mod.build_summary([], ref_label="X", cwd=tmp_path, mcp_config=None)
        assert s["total"] == 0
        assert s["accuracy_strict"] == 0
        assert s["accuracy_lenient"] == 0

    def test_mixed_verdicts(self, run_mod, tmp_path) -> None:
        results = [
            self._result(run_mod, "exact", "a"),
            self._result(run_mod, "exact", "b"),
            self._result(run_mod, "acceptable", "c"),
            self._result(run_mod, "wrong", "d"),
        ]
        s = run_mod.build_summary(results, ref_label="X", cwd=tmp_path, mcp_config=None)
        assert s["by_verdict"]["exact"] == 2
        assert s["by_verdict"]["acceptable"] == 1
        assert s["by_verdict"]["wrong"] == 1
        assert s["accuracy_strict"] == 0.5
        assert s["accuracy_lenient"] == 0.75


class TestScenarioTimeoutAndPrewarm:
    """Phase A harness changes — generous timeout + MCP pre-warm hook."""

    def test_scenario_timeout_is_240s(self, run_mod) -> None:
        # Cold-start MCP + uv venv can spend 30-50s; 120s was too tight and
        # produced 4 timeouts per side in the baseline run. 240s gives headroom.
        assert run_mod._SCENARIO_TIMEOUT_SECONDS == 240

    def test_prewarm_timeout_is_bounded(self, run_mod) -> None:
        # Pre-warm timing out is not fatal, but it must be bounded so a hung
        # MCP server doesn't block the eval indefinitely.
        assert 60 <= run_mod._PREWARM_TIMEOUT_SECONDS <= 240

    def test_prewarm_skips_when_no_mcp_config(self, run_mod, tmp_path) -> None:
        # With no MCP config we have nothing to warm — function returns 0
        # without spawning any subprocess.
        with patch.object(run_mod.subprocess, "run") as mock_run:
            elapsed = run_mod.prewarm_mcp(None, tmp_path)
        assert elapsed == 0
        mock_run.assert_not_called()

    def test_prewarm_invokes_claude_p_with_mcp_config(
        self, run_mod, tmp_path,
    ) -> None:
        mcp_config = tmp_path / ".mcp.json"
        mcp_config.write_text("{}", encoding="utf-8")
        with patch.object(run_mod.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            run_mod.prewarm_mcp(mcp_config, tmp_path)
        assert mock_run.called
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "claude"
        assert "--strict-mcp-config" in cmd
        assert "--mcp-config" in cmd
        assert str(mcp_config) in cmd
        # Must use the same disallowed-tools set as real scenarios so a
        # pre-warm cannot accidentally do useful work that skews timing.
        for builtin in run_mod._DISALLOWED_BUILTINS:
            assert builtin in cmd

    def test_prewarm_swallows_timeout(self, run_mod, tmp_path) -> None:
        mcp_config = tmp_path / ".mcp.json"
        mcp_config.write_text("{}", encoding="utf-8")
        with patch.object(run_mod.subprocess, "run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["claude"], timeout=run_mod._PREWARM_TIMEOUT_SECONDS,
            )
            # Must not raise — a timed-out pre-warm is best-effort.
            elapsed = run_mod.prewarm_mcp(mcp_config, tmp_path)
        assert elapsed >= 0


class TestSafeRefLabel:
    """Filename-safe encoding of git refs (`^`, `~` are special chars)."""

    def test_plain_ref(self, compare_mod) -> None:
        assert compare_mod.safe_ref_label("HEAD") == "HEAD"

    def test_parent_ref(self, compare_mod) -> None:
        assert compare_mod.safe_ref_label("cc1d340^") == "cc1d340-parent"

    def test_tilde_ref(self, compare_mod) -> None:
        assert compare_mod.safe_ref_label("HEAD~3") == "HEAD-tilde3"

    def test_branch_with_slash(self, compare_mod) -> None:
        assert compare_mod.safe_ref_label("feature/foo") == "feature-foo"


class TestDiffResults:
    """`diff_results` partitions scenarios into regressions / improvements /
    stable_correct / stable_wrong and computes accuracy deltas."""

    def _make_summary(self, ref_label: str, results: list[dict]) -> dict:
        n = max(len(results), 1)
        passes_strict = sum(1 for r in results if r["verdict"] == "exact")
        passes_lenient = sum(1 for r in results if r["verdict"] in ("exact", "acceptable"))
        return {
            "ref_label": ref_label,
            "results": results,
            "accuracy_strict": passes_strict / n,
            "accuracy_lenient": passes_lenient / n,
        }

    def _r(self, sid: str, verdict: str, expected: str = "t", actual: str | None = None) -> dict:
        return {
            "scenario_id": sid, "verdict": verdict,
            "expected_tool": expected, "actual_tool": actual,
        }

    def test_pure_regression(self, compare_mod) -> None:
        base = self._make_summary("base", [self._r("a", "exact", actual="t")])
        head = self._make_summary("head", [self._r("a", "wrong", actual="other")])
        d = compare_mod.diff_results(base, head)
        assert len(d["regressions"]) == 1
        assert d["regressions"][0]["scenario_id"] == "a"
        assert d["accuracy_delta_strict"] == -1.0

    def test_pure_improvement(self, compare_mod) -> None:
        base = self._make_summary("base", [self._r("a", "wrong", actual="other")])
        head = self._make_summary("head", [self._r("a", "exact", actual="t")])
        d = compare_mod.diff_results(base, head)
        assert len(d["improvements"]) == 1
        assert d["accuracy_delta_strict"] == 1.0

    def test_stable_correct(self, compare_mod) -> None:
        base = self._make_summary("base", [self._r("a", "exact", actual="t")])
        head = self._make_summary("head", [self._r("a", "exact", actual="t")])
        d = compare_mod.diff_results(base, head)
        assert d["stable_correct"] == ["a"]
        assert d["regressions"] == []
        assert d["improvements"] == []

    def test_stable_wrong(self, compare_mod) -> None:
        base = self._make_summary("base", [self._r("a", "no_tool", actual=None)])
        head = self._make_summary("head", [self._r("a", "wrong", actual="x")])
        d = compare_mod.diff_results(base, head)
        assert d["stable_wrong"] == ["a"]

    def test_acceptable_counts_as_pass(self, compare_mod) -> None:
        # Going from exact to acceptable is NOT a regression — both pass.
        base = self._make_summary("base", [self._r("a", "exact", actual="t")])
        head = self._make_summary("head", [self._r("a", "acceptable", actual="alt")])
        d = compare_mod.diff_results(base, head)
        assert d["stable_correct"] == ["a"]
        assert d["regressions"] == []


class TestRenderMarkdown:
    """`render_markdown` emits a human-readable report with both raw and
    noise-adjusted numbers."""

    def test_contains_headline_sections(self, report_mod) -> None:
        comparison = {
            "baseline_label": "base", "head_label": "head",
            "baseline_sha": "aaa", "head_sha": "bbb",
            "baseline_strict": 0.8, "baseline_lenient": 0.9,
            "head_strict": 0.85, "head_lenient": 0.95,
            "accuracy_delta_strict": 0.05, "accuracy_delta_lenient": 0.05,
            "regressions": [], "improvements": [],
            "stable_correct": ["a", "b"], "stable_wrong": [],
            "total_scenarios": 2,
        }
        baseline = {
            "ref_label": "base", "by_verdict": {"exact": 1, "acceptable": 1},
            "accuracy_strict": 0.8, "accuracy_lenient": 0.9,
            "results": [
                {"scenario_id": "a", "category": "cat", "verdict": "exact",
                 "expected_tool": "t", "actual_tool": "t"},
                {"scenario_id": "b", "category": "cat", "verdict": "acceptable",
                 "expected_tool": "t", "actual_tool": "alt"},
            ],
        }
        head = {
            "ref_label": "head", "by_verdict": {"exact": 1, "acceptable": 1},
            "accuracy_strict": 0.85, "accuracy_lenient": 0.95,
            "results": [
                {"scenario_id": "a", "category": "cat", "verdict": "exact",
                 "expected_tool": "t", "actual_tool": "t"},
                {"scenario_id": "b", "category": "cat", "verdict": "exact",
                 "expected_tool": "t", "actual_tool": "t"},
            ],
        }
        md = report_mod.render_markdown(comparison, baseline, head)
        assert "Tool-Description Eval" in md
        assert "Headline (raw)" in md
        assert "Per-category accuracy" in md
        assert "True regressions" in md
        assert "True improvements" in md
        assert "Reproduce" in md

    def test_separates_error_noise_from_signal(self, report_mod) -> None:
        # baseline OK, head error → goes into "Error-introduced" bucket, NOT true regressions.
        comparison = {
            "baseline_label": "base", "head_label": "head",
            "baseline_sha": "aaa", "head_sha": "bbb",
            "baseline_strict": 1.0, "baseline_lenient": 1.0,
            "head_strict": 0.0, "head_lenient": 0.0,
            "accuracy_delta_strict": -1.0, "accuracy_delta_lenient": -1.0,
            "regressions": [{
                "scenario_id": "x", "expected": "t",
                "baseline_verdict": "exact", "baseline_tool": "t",
                "head_verdict": "error", "head_tool": None,
            }],
            "improvements": [],
            "stable_correct": [], "stable_wrong": [],
            "total_scenarios": 1,
        }
        baseline = {
            "ref_label": "base", "by_verdict": {"exact": 1},
            "accuracy_strict": 1.0, "accuracy_lenient": 1.0,
            "results": [{
                "scenario_id": "x", "category": "cat", "verdict": "exact",
                "expected_tool": "t", "actual_tool": "t",
            }],
        }
        head = {
            "ref_label": "head", "by_verdict": {"error": 1},
            "accuracy_strict": 0.0, "accuracy_lenient": 0.0,
            "results": [{
                "scenario_id": "x", "category": "cat", "verdict": "error",
                "expected_tool": "t", "actual_tool": None,
            }],
        }
        md = report_mod.render_markdown(comparison, baseline, head)
        # The "true regression" section should be empty; the error went into
        # "Error-introduced" noise bucket.
        assert "True regressions (0)" in md
        assert "Error-introduced (1)" in md
