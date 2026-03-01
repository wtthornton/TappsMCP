"""Tests for server_scoring_tools — tapps_score_file, tapps_quality_gate, tapps_quick_check."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.gates.models import GateFailure, GateResult, GateThresholds
from tapps_mcp.scoring.models import CategoryScore, LintIssue, ScoreResult, SecurityIssue
from tapps_mcp.security.security_scanner import SecurityScanResult
from tapps_mcp.server_scoring_tools import (
    _build_quality_gate_data,
    _build_quick_check_data,
    _build_score_file_data,
    _compute_complexity_hint,
    _resolve_preset,
    ast_quick_complexity,
    tapps_quality_gate,
    tapps_quick_check,
    tapps_score_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_score_result(
    file_path: str = "test.py",
    overall_score: float = 85.0,
    lint_issues: list[LintIssue] | None = None,
    security_issues: list[SecurityIssue] | None = None,
    degraded: bool = False,
) -> ScoreResult:
    """Build a ScoreResult with sensible defaults."""
    return ScoreResult(
        file_path=file_path,
        overall_score=overall_score,
        categories={
            "linting": CategoryScore(name="linting", score=8.5, weight=0.3, suggestions=[]),
            "complexity": CategoryScore(name="complexity", score=9.0, weight=0.2, suggestions=[]),
            "security": CategoryScore(
                name="security", score=8.0, weight=0.2, suggestions=["Fix X"]
            ),
        },
        lint_issues=lint_issues or [],
        type_issues=[],
        security_issues=security_issues or [],
        degraded=degraded,
    )


def _make_gate_result(passed: bool = True, preset: str = "standard") -> GateResult:
    failures = []
    if not passed:
        failures = [
            GateFailure(
                category="security",
                actual=3.0,
                threshold=5.0,
                message="Security below threshold",
            ),
        ]
    return GateResult(
        passed=passed,
        preset=preset,
        failures=failures,
        scores={"security": 3.0 if not passed else 8.0, "linting": 8.5},
        thresholds=GateThresholds(),
    )


def _make_security_scan_result(
    passed: bool = True, total_issues: int = 0
) -> SecurityScanResult:
    return SecurityScanResult(
        passed=passed,
        total_issues=total_issues,
        bandit_available=True,
    )


# Standard patches — _record_call, _record_execution, _validate_file_path, _with_nudges
# are imported inside function bodies from tapps_mcp.server, so we patch at source.
# ensure_session_initialized and _get_scorer are imported at module level from server_helpers.
_PATCH_RECORD_CALL = patch(
    "tapps_mcp.server._record_call", side_effect=lambda _: None
)
_PATCH_RECORD_EXEC = patch(
    "tapps_mcp.server._record_execution", side_effect=lambda *a, **kw: None
)
_PATCH_WITH_NUDGES = patch(
    "tapps_mcp.server._with_nudges", side_effect=lambda _t, resp, _c: resp
)
_PATCH_SESSION = patch(
    "tapps_mcp.server_scoring_tools.ensure_session_initialized",
    new_callable=AsyncMock,
)
_PATCH_VALIDATE = "tapps_mcp.server._validate_file_path"
_PATCH_LOGGER = patch("tapps_mcp.server_scoring_tools._logger", new_callable=MagicMock)


# ---------------------------------------------------------------------------
# tapps_score_file
# ---------------------------------------------------------------------------


class TestTappsScoreFile:
    @pytest.mark.asyncio
    async def test_score_clean_file(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f))

        scorer_mock = MagicMock()
        scorer_mock.score_file = AsyncMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
        ):
            result = await tapps_score_file(str(f))

        assert result["success"] is True
        assert result["data"]["overall_score"] == 85.0

    @pytest.mark.asyncio
    async def test_score_invalid_path(self) -> None:
        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(
                _PATCH_VALIDATE,
                side_effect=FileNotFoundError("not found"),
            ),
        ):
            result = await tapps_score_file("/no/such/file.py")

        assert result["success"] is False
        assert result["error"]["code"] == "path_denied"

    @pytest.mark.asyncio
    async def test_score_quick_mode(self, tmp_path: Path) -> None:
        f = tmp_path / "quick.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f))

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick = MagicMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
        ):
            result = await tapps_score_file(str(f), quick=True)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_score_quick_with_fix(self, tmp_path: Path) -> None:
        f = tmp_path / "fixable.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f))

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick = MagicMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.tools.ruff.run_ruff_fix", return_value=3),
        ):
            result = await tapps_score_file(str(f), quick=True, fix=True)

        assert result["success"] is True
        assert result["data"]["fixes_applied"] == 3

    @pytest.mark.asyncio
    async def test_score_includes_lint_issues(self, tmp_path: Path) -> None:
        f = tmp_path / "lint.py"
        f.write_text("x = 1\n", encoding="utf-8")
        issues = [LintIssue(code="E501", message="Line too long", file=str(f), line=1)]
        score = _make_score_result(file_path=str(f), lint_issues=issues)

        scorer_mock = MagicMock()
        scorer_mock.score_file = AsyncMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
        ):
            result = await tapps_score_file(str(f))

        assert result["data"]["lint_issue_count"] == 1
        assert "lint_issues" in result["data"]

    @pytest.mark.asyncio
    async def test_score_scoring_exception(self, tmp_path: Path) -> None:
        f = tmp_path / "error.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer_mock = MagicMock()
        scorer_mock.score_file = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            _PATCH_LOGGER,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
        ):
            result = await tapps_score_file(str(f))

        assert result["success"] is False
        assert result["error"]["code"] == "scoring_failed"

    @pytest.mark.asyncio
    async def test_score_degraded_flag(self, tmp_path: Path) -> None:
        f = tmp_path / "degraded.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f), degraded=True)

        scorer_mock = MagicMock()
        scorer_mock.score_file = AsyncMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
        ):
            result = await tapps_score_file(str(f))

        assert result["success"] is True
        assert result["degraded"] is True


# ---------------------------------------------------------------------------
# tapps_quality_gate
# ---------------------------------------------------------------------------


class TestTappsQualityGate:
    @pytest.mark.asyncio
    async def test_gate_pass(self, tmp_path: Path) -> None:
        f = tmp_path / "pass.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f), overall_score=90.0)
        gate = _make_gate_result(passed=True)

        scorer_mock = MagicMock()
        scorer_mock.score_file = AsyncMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
        ):
            result = await tapps_quality_gate(str(f), preset="standard")

        assert result["success"] is True
        assert result["data"]["passed"] is True

    @pytest.mark.asyncio
    async def test_gate_fail(self, tmp_path: Path) -> None:
        f = tmp_path / "fail.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f), overall_score=50.0)
        gate = _make_gate_result(passed=False)

        scorer_mock = MagicMock()
        scorer_mock.score_file = AsyncMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
        ):
            result = await tapps_quality_gate(str(f), preset="standard")

        assert result["success"] is True  # Tool succeeded, gate failed
        assert result["data"]["passed"] is False
        assert len(result["data"]["failures"]) > 0

    @pytest.mark.asyncio
    async def test_gate_invalid_path(self) -> None:
        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(
                _PATCH_VALIDATE,
                side_effect=ValueError("outside root"),
            ),
        ):
            result = await tapps_quality_gate("/outside/root.py")

        assert result["success"] is False
        assert result["error"]["code"] == "path_denied"

    @pytest.mark.asyncio
    async def test_gate_scoring_error(self, tmp_path: Path) -> None:
        f = tmp_path / "error.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer_mock = MagicMock()
        scorer_mock.score_file = AsyncMock(side_effect=RuntimeError("scorer crash"))

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            _PATCH_LOGGER,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
        ):
            result = await tapps_quality_gate(str(f), preset="standard")

        assert result["success"] is False
        assert result["error"]["code"] == "scoring_failed"

    @pytest.mark.asyncio
    async def test_gate_default_preset(self, tmp_path: Path) -> None:
        """When preset is empty and ctx is None, defaults to 'standard'."""
        f = tmp_path / "default.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f))
        gate = _make_gate_result(passed=True, preset="standard")

        scorer_mock = MagicMock()
        scorer_mock.score_file = AsyncMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
        ):
            result = await tapps_quality_gate(str(f), preset="")

        assert result["data"]["preset"] == "standard"


# ---------------------------------------------------------------------------
# tapps_quick_check
# ---------------------------------------------------------------------------


class TestTappsQuickCheck:
    @pytest.mark.asyncio
    async def test_quick_check_pass(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f))
        gate = _make_gate_result(passed=True)
        sec = _make_security_scan_result()

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick_enriched = MagicMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.server_scoring_tools.load_settings") as mock_settings,
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
            patch(
                "tapps_mcp.security.security_scanner.run_security_scan", return_value=sec
            ),
        ):
            mock_settings.return_value = MagicMock(
                project_root=tmp_path, tool_timeout=30
            )
            result = await tapps_quick_check(str(f))

        assert result["success"] is True
        assert result["data"]["gate_passed"] is True
        assert result["data"]["security_passed"] is True

    @pytest.mark.asyncio
    async def test_quick_check_with_fix(self, tmp_path: Path) -> None:
        f = tmp_path / "fixme.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f))
        gate = _make_gate_result(passed=True)
        sec = _make_security_scan_result()

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick_enriched = MagicMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.server_scoring_tools.load_settings") as mock_settings,
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
            patch(
                "tapps_mcp.security.security_scanner.run_security_scan", return_value=sec
            ),
            patch("tapps_mcp.tools.ruff.run_ruff_fix", return_value=5),
        ):
            mock_settings.return_value = MagicMock(
                project_root=tmp_path, tool_timeout=30
            )
            result = await tapps_quick_check(str(f), fix=True)

        assert result["success"] is True
        assert result["data"]["fixes_applied"] == 5

    @pytest.mark.asyncio
    async def test_quick_check_invalid_path(self) -> None:
        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(
                _PATCH_VALIDATE,
                side_effect=FileNotFoundError("gone"),
            ),
        ):
            result = await tapps_quick_check("/missing.py")

        assert result["success"] is False
        assert result["error"]["code"] == "path_denied"

    @pytest.mark.asyncio
    async def test_quick_check_scoring_error(self, tmp_path: Path) -> None:
        f = tmp_path / "crash.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick_enriched = MagicMock(side_effect=RuntimeError("boom"))

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            _PATCH_LOGGER,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.server_scoring_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.security.security_scanner.run_security_scan",
                return_value=_make_security_scan_result(),
            ),
        ):
            mock_settings.return_value = MagicMock(
                project_root=tmp_path, tool_timeout=30
            )
            result = await tapps_quick_check(str(f))

        assert result["success"] is False
        assert result["error"]["code"] == "scoring_failed"

    @pytest.mark.asyncio
    async def test_quick_check_gate_failures_included(self, tmp_path: Path) -> None:
        f = tmp_path / "gfail.py"
        f.write_text("x = 1\n", encoding="utf-8")
        score = _make_score_result(file_path=str(f), overall_score=50.0)
        gate = _make_gate_result(passed=False)
        sec = _make_security_scan_result()

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick_enriched = MagicMock(return_value=score)

        with (
            _PATCH_RECORD_CALL,
            _PATCH_RECORD_EXEC,
            _PATCH_WITH_NUDGES,
            _PATCH_SESSION,
            patch(_PATCH_VALIDATE, return_value=f),
            patch("tapps_mcp.server_scoring_tools._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.server_scoring_tools.load_settings") as mock_settings,
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
            patch(
                "tapps_mcp.security.security_scanner.run_security_scan", return_value=sec
            ),
        ):
            mock_settings.return_value = MagicMock(
                project_root=tmp_path, tool_timeout=30
            )
            result = await tapps_quick_check(str(f))

        assert result["data"]["gate_passed"] is False
        assert "gate_failures" in result["data"]


# ---------------------------------------------------------------------------
# ast_quick_complexity
# ---------------------------------------------------------------------------


class TestAstQuickComplexity:
    def test_simple_function(self) -> None:
        code = "def foo():\n    return 1\n"
        cc = ast_quick_complexity(code)
        assert cc == 1

    def test_function_with_branches(self) -> None:
        code = (
            "def foo(x):\n"
            "    if x > 0:\n"
            "        return x\n"
            "    elif x < 0:\n"
            "        return -x\n"
            "    return 0\n"
        )
        cc = ast_quick_complexity(code)
        assert cc is not None
        assert cc >= 3  # 1 base + 2 if/elif

    def test_function_with_loop_and_if(self) -> None:
        code = (
            "def foo(items):\n"
            "    for item in items:\n"
            "        if item:\n"
            "            pass\n"
        )
        cc = ast_quick_complexity(code)
        assert cc is not None
        assert cc >= 3

    def test_syntax_error_returns_none(self) -> None:
        cc = ast_quick_complexity("def foo(:\n")
        assert cc is None

    def test_empty_code(self) -> None:
        cc = ast_quick_complexity("")
        assert cc == 0

    def test_no_functions(self) -> None:
        cc = ast_quick_complexity("x = 1\ny = 2\n")
        assert cc == 0

    def test_boolean_operator_adds_branches(self) -> None:
        code = "def foo(a, b, c):\n    if a and b and c:\n        return True\n"
        cc = ast_quick_complexity(code)
        assert cc is not None
        assert cc >= 3  # 1 base + 1 if + 2 bool ops

    def test_async_function(self) -> None:
        code = (
            "async def foo(x):\n"
            "    if x:\n"
            "        return 1\n"
            "    return 0\n"
        )
        cc = ast_quick_complexity(code)
        assert cc is not None
        assert cc >= 2


# ---------------------------------------------------------------------------
# _resolve_preset
# ---------------------------------------------------------------------------


class TestResolvePreset:
    @pytest.mark.asyncio
    async def test_returns_preset_when_provided(self) -> None:
        result = await _resolve_preset("strict", None)
        assert result == "strict"

    @pytest.mark.asyncio
    async def test_defaults_to_standard_when_empty(self) -> None:
        result = await _resolve_preset("", None)
        assert result == "standard"

    @pytest.mark.asyncio
    async def test_elicitation_used_when_ctx_provided(self) -> None:
        ctx_mock = MagicMock()
        with patch(
            "tapps_mcp.common.elicitation.elicit_preset",
            new_callable=AsyncMock,
            return_value="framework",
        ):
            result = await _resolve_preset("", ctx_mock)
        assert result == "framework"

    @pytest.mark.asyncio
    async def test_elicitation_returns_none_falls_back(self) -> None:
        ctx_mock = MagicMock()
        with patch(
            "tapps_mcp.common.elicitation.elicit_preset",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await _resolve_preset("", ctx_mock)
        assert result == "standard"


# ---------------------------------------------------------------------------
# _build_quality_gate_data
# ---------------------------------------------------------------------------


class TestBuildQualityGateData:
    def test_builds_data_passing_gate(self, tmp_path: Path) -> None:
        resolved = tmp_path / "test.py"
        score = _make_score_result(file_path=str(resolved))
        gate = _make_gate_result(passed=True)

        data, suggestions = _build_quality_gate_data(resolved, score, gate)

        assert data["passed"] is True
        assert data["file_path"] == str(resolved)
        assert data["overall_score"] == 85.0
        assert suggestions == []

    def test_collects_suggestions_for_failing_categories(self, tmp_path: Path) -> None:
        resolved = tmp_path / "test.py"
        score = _make_score_result(file_path=str(resolved), overall_score=50.0)
        gate = _make_gate_result(passed=False)  # fails on "security"

        data, suggestions = _build_quality_gate_data(resolved, score, gate)

        assert data["passed"] is False
        assert "Fix X" in suggestions  # from security category

    def test_includes_tool_errors_when_present(self, tmp_path: Path) -> None:
        resolved = tmp_path / "test.py"
        score = _make_score_result(file_path=str(resolved))
        score.tool_errors = {"mypy": "not installed"}
        gate = _make_gate_result(passed=True)

        data, _ = _build_quality_gate_data(resolved, score, gate)

        assert data["tool_errors"] == {"mypy": "not installed"}

    def test_omits_tool_errors_when_empty(self, tmp_path: Path) -> None:
        resolved = tmp_path / "test.py"
        score = _make_score_result(file_path=str(resolved))
        gate = _make_gate_result(passed=True)

        data, _ = _build_quality_gate_data(resolved, score, gate)

        assert "tool_errors" not in data


# ---------------------------------------------------------------------------
# _build_score_file_data
# ---------------------------------------------------------------------------


class TestBuildScoreFileData:
    def test_basic_data_fields(self) -> None:
        score = _make_score_result()
        data, suggestions = _build_score_file_data(score, quick=False, fix=False, fixes_applied=0)

        assert data["file_path"] == "test.py"
        assert data["overall_score"] == 85.0
        assert "linting" in data["categories"]
        assert "Fix X" in suggestions

    def test_quick_fix_includes_fixes_applied(self) -> None:
        score = _make_score_result()
        data, _ = _build_score_file_data(score, quick=True, fix=True, fixes_applied=7)

        assert data["fixes_applied"] == 7

    def test_no_fixes_applied_without_quick_fix(self) -> None:
        score = _make_score_result()
        data, _ = _build_score_file_data(score, quick=False, fix=False, fixes_applied=0)

        assert "fixes_applied" not in data


# ---------------------------------------------------------------------------
# _build_quick_check_data
# ---------------------------------------------------------------------------


class TestBuildQuickCheckData:
    def test_basic_quick_check_data(self, tmp_path: Path) -> None:
        resolved = tmp_path / "test.py"
        score = _make_score_result(file_path=str(resolved))
        gate = _make_gate_result(passed=True)
        sec = _make_security_scan_result()

        data, suggestions = _build_quick_check_data(
            resolved, score, sec, gate, "standard", None, 0, False,
        )

        assert data["gate_passed"] is True
        assert data["security_passed"] is True
        assert data["overall_score"] == 85.0
        assert "fixes_applied" not in data

    def test_includes_complexity_hint(self, tmp_path: Path) -> None:
        resolved = tmp_path / "test.py"
        score = _make_score_result(file_path=str(resolved))
        gate = _make_gate_result(passed=True)
        sec = _make_security_scan_result()
        hint = {"max_cc_estimate": 15, "level": "high"}

        data, suggestions = _build_quick_check_data(
            resolved, score, sec, gate, "standard", hint, 0, False,
        )

        assert data["complexity_hint"] == hint
        assert any("CC~15" in s for s in suggestions)


# ---------------------------------------------------------------------------
# _compute_complexity_hint
# ---------------------------------------------------------------------------


class TestComputeComplexityHint:
    def test_returns_none_for_simple_code(self, tmp_path: Path) -> None:
        f = tmp_path / "simple.py"
        f.write_text("def foo():\n    return 1\n", encoding="utf-8")
        assert _compute_complexity_hint(f) is None

    def test_returns_hint_for_complex_code(self, tmp_path: Path) -> None:
        lines = ["def foo(x):"]
        for i in range(12):
            lines.append(f"    if x == {i}:")
            lines.append(f"        return {i}")
        lines.append("    return -1\n")
        f = tmp_path / "complex.py"
        f.write_text("\n".join(lines), encoding="utf-8")

        hint = _compute_complexity_hint(f)
        assert hint is not None
        assert hint["max_cc_estimate"] > 10
        assert hint["level"] in ("moderate", "high")

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.py"
        assert _compute_complexity_hint(f) is None
