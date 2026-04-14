"""Tests for composite tools (session_start, validate_changed, quick_check)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.common.models import (
    CacheDiagnostic,
    Context7Diagnostic,
    InstalledTool,
    KnowledgeBaseDiagnostic,
    StartupDiagnostics,
    VectorRagDiagnostic,
)
from tapps_mcp.tools.checklist import CallTracker


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:  # type: ignore[misc]
    """Reset CallTracker before every test."""
    CallTracker.reset()


# Mock tool detection to avoid spawning 6 subprocesses per test.
# On Windows, repeated asyncio subprocess calls inside pytest-asyncio
# can deadlock.  Mocking eliminates the issue and speeds up tests.
_MOCK_TOOLS = [
    InstalledTool(name=n, version=f"{n} 1.0.0", available=True, install_hint=None)
    for n in ("ruff", "mypy", "bandit", "radon", "vulture", "pip-audit")
]

_MOCK_DIAGNOSTICS = StartupDiagnostics(
    context7=Context7Diagnostic(api_key_set=False, status="no_key"),
    cache=CacheDiagnostic(cache_dir="/tmp/fake", exists=False, writable=False),
    vector_rag=VectorRagDiagnostic(
        faiss_available=False,
        sentence_transformers_available=False,
        numpy_available=False,
        status="keyword_only",
    ),
    knowledge_base=KnowledgeBaseDiagnostic(
        total_domains=0, total_files=0, expected_domains=16
    ),
)


def _build_mock_server_info() -> dict[str, Any]:
    """Build a realistic tapps_server_info return value for mocking."""
    from tapps_mcp import __version__

    return {
        "tool": "tapps_server_info",
        "success": True,
        "elapsed_ms": 1,
        "data": {
            "server": {
                "name": "TappsMCP",
                "version": __version__,
                "protocol_version": "2025-11-25",
            },
            "configuration": {
                "project_root": str(Path.cwd()),
                "quality_preset": "standard",
                "log_level": "WARNING",
            },
            "available_tools": ["tapps_session_start", "tapps_score_file"],
            "installed_checkers": [t.model_dump() for t in _MOCK_TOOLS],
            "diagnostics": _MOCK_DIAGNOSTICS.model_dump(),
            "recommended_workflow": "...",
            "quick_start": ["1. Call tapps_session_start()"],
            "critical_rules": ["BLOCKING: quality gate must pass"],
            "pipeline": {
                "name": "TAPPS Quality Pipeline",
                "stages": ["discover", "research", "develop", "validate", "verify"],
                "current_hint": "Start with discover.",
                "stage_tools": {},
                "handoff_file": "docs/TAPPS_HANDOFF.md",
                "runlog_file": "docs/TAPPS_RUNLOG.md",
                "prompts_available": True,
            },
        },
    }


def _build_mock_profile() -> dict[str, Any]:
    """Build a realistic tapps_project_profile return value for mocking."""
    return {
        "tool": "tapps_project_profile",
        "success": True,
        "elapsed_ms": 1,
        "data": {
            "project_root": str(Path.cwd()),
            "project_type": "library",
            "has_ci": False,
            "has_docker": False,
            "has_tests": True,
        },
    }


@pytest.fixture()
def _mock_tool_detection() -> Generator[None, None, None]:
    """Patch async server info to avoid subprocesses/threads.

    On Windows, asyncio.create_subprocess_exec and asyncio.to_thread inside
    pytest-asyncio can deadlock the ProactorEventLoop during teardown.
    Mocking the top-level async function eliminates subprocess and
    thread-pool operations. Session start is lightweight (server info only).
    """
    mock_info = _build_mock_server_info()

    with (
        # Mock _server_info_async (called by tapps_session_start)
        patch(
            "tapps_mcp.server._server_info_async",
            new_callable=AsyncMock,
            return_value=mock_info,
        ),
        # Mock async tool detection (used by tapps_session_start)
        patch(
            "tapps_mcp.server.detect_installed_tools_async",
            new_callable=AsyncMock,
            return_value=_MOCK_TOOLS,
        ),
        # Mock diagnostics (used by _server_info_async sync path)
        patch(
            "tapps_mcp.diagnostics.collect_diagnostics",
            return_value=_MOCK_DIAGNOSTICS,
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# tapps_session_start
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_mock_tool_detection")
class TestTappsSessionStart:
    """Tests for the tapps_session_start composite tool (async).

    Tool detection is mocked to avoid subprocess overhead and Windows
    asyncio deadlocks.
    """

    @pytest.mark.asyncio
    async def test_returns_success(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = await tapps_session_start()
        assert result["success"] is True
        assert result["tool"] == "tapps_session_start"

    @pytest.mark.asyncio
    async def test_includes_server_data(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert "server" in data
        assert "configuration" in data
        assert "pipeline" in data
        assert "quick_start" in data
        assert "critical_rules" in data

    @pytest.mark.asyncio
    async def test_records_session_start_call(self) -> None:
        from tapps_mcp.server import tapps_session_start

        await tapps_session_start()
        called = CallTracker.get_called_tools()
        assert "tapps_session_start" in called

    @pytest.mark.asyncio
    async def test_includes_next_steps(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = await tapps_session_start()
        assert "next_steps" in result["data"]

    @pytest.mark.asyncio
    async def test_includes_pipeline_progress(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = await tapps_session_start()
        progress = result["data"]["pipeline_progress"]
        assert "discover" in progress["completed_stages"]


# ---------------------------------------------------------------------------
# tapps_validate_changed
# ---------------------------------------------------------------------------


class TestTappsValidateChanged:
    """Tests for the tapps_validate_changed batch tool."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_no_files_returns_empty(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        from tapps_mcp.server import tapps_validate_changed

        mock_settings.return_value.project_root = Path("/fake")
        mock_settings.return_value.tool_timeout = 30

        with patch(
            "tapps_mcp.tools.batch_validator.detect_changed_scorable_files",
            return_value=[],
        ):
            result = await tapps_validate_changed()

        assert result["success"] is True
        assert result["data"]["files_validated"] == 0
        assert result["data"]["all_gates_passed"] is True

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_explicit_file_paths(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_validate_changed(file_paths=str(f))
        assert result["success"] is True
        assert result["data"]["files_validated"] == 1

    @pytest.mark.asyncio
    async def test_records_call(self) -> None:
        from tapps_mcp.server import tapps_validate_changed

        with (
            patch(
                "tapps_mcp.tools.batch_validator.detect_changed_python_files",
                return_value=[],
            ),
            patch("tapps_mcp.server.load_settings") as mock_settings,
        ):
            mock_settings.return_value.project_root = Path("/fake")
            await tapps_validate_changed()

        assert "tapps_validate_changed" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    async def test_parallel_execution_multiple_files(self, tmp_path: Path) -> None:
        """Multiple files are all validated (parallel gather)."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        files = []
        for name in ("a.py", "b.py", "c.py"):
            f = tmp_path / name
            f.write_text("x = 1\n", encoding="utf-8")
            files.append(f)

        mock_score = ScoreResult(
            file_path="test.py",
            categories={},
            overall_score=85.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file = AsyncMock(return_value=mock_score)

        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False
            result = await tapps_validate_changed(
                file_paths=",".join(str(f) for f in files),
                include_security=False,
                quick=False,
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 3
        assert mock_scorer.score_file.call_count == 3

    @pytest.mark.asyncio
    async def test_progress_notifications_when_ctx_provided(self, tmp_path: Path) -> None:
        """When ctx has report_progress, it is called (initial + optional heartbeat)."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path="test.py",
            categories={},
            overall_score=85.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file = AsyncMock(return_value=mock_score)
        mock_gate = MagicMock(passed=True, failures=[])
        mock_report = AsyncMock()

        ctx = MagicMock()
        ctx.report_progress = mock_report

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False
            result = await tapps_validate_changed(
                file_paths=str(f),
                include_security=False,
                quick=False,
                ctx=ctx,
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 1
        mock_report.assert_called()
        calls = mock_report.call_args_list
        assert len(calls) >= 1
        first = calls[0]
        assert first.kwargs.get("message", "").startswith("Validating ")
        assert "1 files" in first.kwargs.get("message", "")

    @pytest.mark.asyncio
    async def test_no_progress_when_ctx_is_none(self, tmp_path: Path) -> None:
        """Tool completes successfully when ctx is None (the default)."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path="test.py",
            categories={},
            overall_score=85.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file_quick = MagicMock(return_value=mock_score)
        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False
            result = await tapps_validate_changed(
                file_paths=str(f),
                include_security=False,
                quick=True,
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 1

    @pytest.mark.asyncio
    async def test_no_progress_when_ctx_lacks_report_progress(
        self, tmp_path: Path
    ) -> None:
        """Tool completes when ctx exists but has no report_progress attribute."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path="test.py",
            categories={},
            overall_score=85.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file_quick = MagicMock(return_value=mock_score)
        mock_gate = MagicMock(passed=True, failures=[])

        # ctx with no report_progress attribute
        ctx = MagicMock(spec=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False
            result = await tapps_validate_changed(
                file_paths=str(f),
                include_security=False,
                quick=True,
                ctx=ctx,
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 1

    @pytest.mark.asyncio
    async def test_progress_not_sent_when_no_files(self, tmp_path: Path) -> None:
        """report_progress is not called when there are no files to validate."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        mock_report = AsyncMock()
        ctx = MagicMock()
        ctx.report_progress = mock_report

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch(
                "tapps_mcp.tools.batch_validator.detect_changed_python_files",
                return_value=[],
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            result = await tapps_validate_changed(
                file_paths="",
                ctx=ctx,
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 0
        mock_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_python_files_from_git_fast_path_no_session_init(
        self, tmp_path: Path
    ) -> None:
        """When git returns only non-Python files, return immediately without session init.
        Guards against stall when all changes are committed and diff has no .py files.
        """
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        ensure_init = AsyncMock()

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.tools.batch_validator.detect_changed_python_files",
                return_value=[],
            ),
            patch(
                "tapps_mcp.server_helpers.ensure_session_initialized",
                ensure_init,
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            result = await tapps_validate_changed(file_paths="")

        assert result["success"] is True
        assert result["data"]["files_validated"] == 0
        assert result["data"]["summary"] == "No changed scorable files found."
        # base_ref=HEAD with auto-detect should include a warning
        assert "warnings" in result["data"]
        assert any("base_ref=HEAD" in w for w in result["data"]["warnings"])
        ensure_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_base_ref_head_zero_diff_warning(self, tmp_path: Path) -> None:
        """When base_ref=HEAD and auto-detect finds zero files, response has a warning."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.tools.batch_validator.detect_changed_scorable_files",
                return_value=[],
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            result = await tapps_validate_changed(file_paths="", base_ref="HEAD")

        assert result["success"] is True
        assert result["data"]["files_validated"] == 0
        assert result["data"]["all_gates_passed"] is True
        warnings = result["data"].get("warnings", [])
        assert len(warnings) >= 1
        assert "base_ref=HEAD" in warnings[0]
        assert "staged-but-uncommitted" in warnings[0]

    @pytest.mark.asyncio
    async def test_base_ref_non_head_no_warning(self, tmp_path: Path) -> None:
        """When base_ref is not HEAD and zero files found, no HEAD-specific warning."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.tools.batch_validator.detect_changed_scorable_files",
                return_value=[],
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            result = await tapps_validate_changed(file_paths="", base_ref="main")

        assert result["success"] is True
        assert "warnings" not in result["data"]

    @pytest.mark.asyncio
    async def test_explicit_non_python_files_returns_fast_no_scorer(
        self, tmp_path: Path
    ) -> None:
        """Explicit file_paths with only non-Python files returns immediately without scorer.
        Prevents stall when client passes changed file list that contains only .json/.md etc.
        """
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        md = tmp_path / "CLAUDE.md"
        md.write_text("# doc\n", encoding="utf-8")
        js = tmp_path / ".claude" / "settings.local.json"
        js.parent.mkdir(parents=True, exist_ok=True)
        js.write_text("{}", encoding="utf-8")

        mock_scorer = MagicMock()
        ensure_init = AsyncMock()

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch(
                "tapps_mcp.server_helpers.ensure_session_initialized",
                ensure_init,
            ),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            result = await tapps_validate_changed(
                file_paths=f"{md},{js}",
                quick=True,
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 0
        assert result["data"]["summary"] == "No changed scorable files found."
        ensure_init.assert_not_called()
        mock_scorer.score_file_quick.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_duplicate_security_scan(self, tmp_path: Path) -> None:
        """run_security_scan is NOT called; bandit results reused from score."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path=str(f),
            categories={},
            overall_score=85.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file = AsyncMock(return_value=mock_score)

        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", return_value=f),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.security.security_scanner.run_security_scan",
            ) as mock_run_sec,
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False
            result = await tapps_validate_changed(
                file_paths=str(f),
                include_security=True,
                quick=False,
            )

        # run_security_scan should NOT be called — bandit reused from score
        mock_run_sec.assert_not_called()
        assert result["data"]["files_validated"] == 1
        data = result["data"]["results"][0]
        assert data["security_passed"] is True
        assert data["security_issues"] == 0

    @pytest.mark.asyncio
    async def test_quick_mode_uses_score_file_quick(self, tmp_path: Path) -> None:
        """When quick=True, score_file_quick is used and score_file is not."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path=str(f),
            categories={},
            overall_score=80.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file_quick = MagicMock(return_value=mock_score)
        mock_scorer.score_file = AsyncMock(return_value=mock_score)
        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", return_value=f),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False
            result = await tapps_validate_changed(
                file_paths=str(f),
                quick=True,
                include_security=False,
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 1
        mock_scorer.score_file_quick.assert_called_once()
        mock_scorer.score_file.assert_not_called()
        assert "Quick mode" in result["data"]["summary"]

    @pytest.mark.asyncio
    async def test_secret_scanner_still_runs(self, tmp_path: Path) -> None:
        """SecretScanner.scan_file IS called when include_security=True."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.security.secret_scanner import SecretScanResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path=str(f),
            categories={},
            overall_score=85.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.language = "python"
        mock_scorer.score_file = AsyncMock(return_value=mock_score)

        mock_gate = MagicMock(passed=True, failures=[])
        mock_secret_result = SecretScanResult(
            total_findings=0, high_severity=0, scanned_files=1
        )
        mock_scanner_instance = MagicMock()
        mock_scanner_instance.scan_file.return_value = mock_secret_result

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", return_value=f),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.security.secret_scanner.SecretScanner",
                return_value=mock_scanner_instance,
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False
            await tapps_validate_changed(
                file_paths=str(f), include_security=True, quick=False
            )

        mock_scanner_instance.scan_file.assert_called_once_with(str(f))

    @pytest.mark.asyncio
    async def test_individual_file_error_doesnt_abort_batch(
        self, tmp_path: Path
    ) -> None:
        """One file raising an exception doesn't prevent others from validating."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        good = tmp_path / "good.py"
        good.write_text("x = 1\n", encoding="utf-8")
        bad = tmp_path / "bad.py"
        bad.write_text("y = 2\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path="test.py",
            categories={},
            overall_score=85.0,
            security_issues=[],
        )

        async def _score_side_effect(path: Path, **kwargs: object) -> ScoreResult:
            if "bad" in str(path):
                raise RuntimeError("score failed")
            return mock_score

        mock_scorer = MagicMock()
        mock_scorer.score_file = AsyncMock(side_effect=_score_side_effect)

        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False
            result = await tapps_validate_changed(
                file_paths=f"{good},{bad}",
                include_security=False,
                quick=False,
            )

        assert result["data"]["files_validated"] == 2
        results_list = result["data"]["results"]
        # One succeeded, one has errors
        errored = [r for r in results_list if "errors" in r]
        succeeded = [r for r in results_list if "overall_score" in r]
        assert len(errored) == 1
        assert len(succeeded) == 1
        assert "score failed" in errored[0]["errors"][0]

    @pytest.mark.asyncio
    async def test_security_combines_bandit_and_secrets(self, tmp_path: Path) -> None:
        """Security result aggregates bandit issues from score + secret findings."""
        from tapps_mcp.scoring.models import ScoreResult, SecurityIssue
        from tapps_mcp.security.secret_scanner import SecretScanResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        bandit_issue = SecurityIssue(
            code="B101",
            message="Use of assert",
            file=str(f),
            line=1,
            severity="low",
        )
        mock_score = ScoreResult(
            file_path=str(f),
            categories={},
            overall_score=85.0,
            security_issues=[bandit_issue],
        )
        mock_scorer = MagicMock()
        mock_scorer.language = "python"
        mock_scorer.score_file = AsyncMock(return_value=mock_score)

        mock_gate = MagicMock(passed=True, failures=[])
        mock_secret_result = SecretScanResult(
            total_findings=1, high_severity=1, scanned_files=1
        )
        mock_scanner_instance = MagicMock()
        mock_scanner_instance.scan_file.return_value = mock_secret_result

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", return_value=f),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.security.secret_scanner.SecretScanner",
                return_value=mock_scanner_instance,
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False
            result = await tapps_validate_changed(
                file_paths=str(f), include_security=True, quick=False
            )

        file_result = result["data"]["results"][0]
        # 1 bandit + 1 secret = 2 total
        assert file_result["security_issues"] == 2
        # high-severity secret makes it fail
        assert file_result["security_passed"] is False


# ---------------------------------------------------------------------------
# tapps_quick_check
# ---------------------------------------------------------------------------


class TestTappsQuickCheck:
    """Tests for the tapps_quick_check lite-mode tool."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_success(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(str(f))
        assert result["success"] is True
        data = result["data"]
        assert "overall_score" in data
        assert "gate_passed" in data
        assert "security_passed" in data

    @pytest.mark.asyncio
    async def test_invalid_path(self) -> None:
        from tapps_mcp.server import tapps_quick_check

        result = await tapps_quick_check("/nonexistent/file.py")
        assert result["success"] is False
        assert result["error"]["code"] == "path_denied"

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_records_call(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        await tapps_quick_check(str(f))
        assert "tapps_quick_check" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_includes_nudges(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(str(f))
        assert "next_steps" in result["data"]
        assert "pipeline_progress" in result["data"]

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_fix_parameter_applies_fixes(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        with patch("tapps_mcp.tools.ruff.run_ruff_fix", return_value=3) as mock_fix:
            result = await tapps_quick_check(str(f), fix=True)

        assert result["success"] is True
        assert result["data"]["fixes_applied"] == 3
        mock_fix.assert_called_once()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_fix_false_skips_fixes(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        with patch("tapps_mcp.tools.ruff.run_ruff_fix") as mock_fix:
            result = await tapps_quick_check(str(f), fix=False)

        assert result["success"] is True
        assert "fixes_applied" not in result["data"]
        mock_fix.assert_not_called()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_quick_categories_present(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(str(f))
        assert result["success"] is True
        cats = result["data"]["quick_categories"]
        assert isinstance(cats, dict)
        # Should have all 7 weighted categories
        expected = {"complexity", "security", "maintainability", "test_coverage",
                    "performance", "structure", "devex"}
        assert set(cats.keys()) == expected

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_nudge_gate_failed(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.scoring.models import CategoryScore, ScoreResult
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "strict"
        mock_settings.return_value.tool_timeout = 30
        mock_settings.return_value.memory.write_rules.max_value_length = 4096
        mock_settings.return_value.memory.write_rules.min_value_length = 20
        mock_settings.return_value.memory.enabled = True

        # Create a low-scoring result to fail the gate
        low_result = ScoreResult(
            file_path=str(f),
            categories={
                "linting": CategoryScore(name="linting", score=2.0, weight=1.0),
            },
            overall_score=20.0,
            degraded=True,
            missing_tools=["bandit", "radon", "mypy"],
        )

        from tapps_mcp.tools.checklist import CallTracker

        CallTracker.record("tapps_session_start")
        with patch(
            "tapps_mcp.server_scoring_tools._get_scorer_for_file"
        ) as mock_scorer_fn:
            mock_scorer = MagicMock()
            mock_scorer.language = "python"
            mock_scorer.score_file_quick_enriched.return_value = low_result
            mock_scorer_fn.return_value = mock_scorer
            result = await tapps_quick_check(str(f), preset="strict")

        data = result["data"]
        # Gate should fail with a 20.0 score on strict preset
        assert data["gate_passed"] is False
        # Nudge should mention gate failure (session_start seeded so SESSION_INIT
        # does not crowd it out in top-1 selection — STORY-101.5).
        next_steps = data.get("next_steps", [])
        assert any("Gate FAILED" in s for s in next_steps)

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_nudge_security_failed(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        # Mock security scan to return a failure
        from tapps_mcp.security.security_scanner import SecurityScanResult

        failed_sec = SecurityScanResult(
            passed=False,
            total_issues=2,
            critical_count=1,
            bandit_available=True,
        )

        from tapps_mcp.tools.checklist import CallTracker

        CallTracker.record("tapps_session_start")
        with patch(
            "tapps_mcp.security.security_scanner.run_security_scan",
            return_value=failed_sec,
        ):
            result = await tapps_quick_check(str(f))

        data = result["data"]
        assert data["security_passed"] is False
        next_steps = data.get("next_steps", [])
        # session_start seeded so SESSION_INIT does not crowd out the security
        # nudge in top-1 selection (STORY-101.5).
        assert any("Security issues" in s or "security" in s.lower() for s in next_steps)

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_uncached_libraries_hint(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("import requests\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        with (
            patch(
                "tapps_mcp.knowledge.import_analyzer.extract_external_imports",
                return_value=["requests"],
            ),
            patch(
                "tapps_mcp.knowledge.import_analyzer.find_uncached_libraries",
                return_value=["requests"],
            ),
            patch("tapps_mcp.knowledge.cache.KBCache"),
        ):
            result = await tapps_quick_check(str(f))

        data = result["data"]
        assert "docs_hint" in data
        assert "requests" in data["docs_hint"]

    @pytest.mark.asyncio
    async def test_structured_output_new_fields(self) -> None:
        from tapps_mcp.common.output_schemas import QuickCheckOutput

        output = QuickCheckOutput(
            file_path="/test.py",
            overall_score=75.0,
            gate_passed=True,
            gate_preset="standard",
            security_passed=True,
            lint_issue_count=0,
            security_issue_count=0,
            complexity_hint={"max_cc_estimate": 12, "level": "moderate"},
            gate_failures=[{"category": "overall", "actual": 65.0, "threshold": 70.0}],
            quick_categories={"complexity": 5.0, "security": 8.0},
            fixes_applied=2,
        )
        content = output.to_structured_content()
        assert content["complexity_hint"]["max_cc_estimate"] == 12
        assert len(content["gate_failures"]) == 1
        assert content["quick_categories"]["security"] == 8.0
        assert content["fixes_applied"] == 2


# ---------------------------------------------------------------------------
# Checklist equivalence
# ---------------------------------------------------------------------------


class TestChecklistEquivalence:
    """Test that composite tools satisfy individual tool requirements."""

    def test_quick_check_satisfies_score_and_gate(self) -> None:
        CallTracker.record("tapps_quick_check")
        result = CallTracker.evaluate("feature")
        # feature requires: tapps_score_file, tapps_quality_gate
        assert result.complete is True

    def test_validate_changed_satisfies_review(self) -> None:
        CallTracker.record("tapps_validate_changed")
        result = CallTracker.evaluate("review")
        # review requires: tapps_score_file, tapps_security_scan, tapps_quality_gate
        assert result.complete is True


# ---------------------------------------------------------------------------
# batch_validator module
# ---------------------------------------------------------------------------


class TestBatchValidator:
    """Tests for the batch_validator module."""

    @patch("tapps_mcp.tools.batch_validator.subprocess.run")
    def test_detect_changed_filters_py_only(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.tools.batch_validator import detect_changed_python_files

        # Create test files
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.txt").write_text("hello\n")
        (tmp_path / "c.py").write_text("y = 2\n")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="a.py\nb.txt\nc.py\n",
        )

        result = detect_changed_python_files(tmp_path)
        assert len(result) == 2
        assert all(p.suffix == ".py" for p in result)

    @patch("tapps_mcp.tools.batch_validator.subprocess.run")
    def test_detect_changed_empty_diff(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.tools.batch_validator import detect_changed_python_files

        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = detect_changed_python_files(tmp_path)
        assert result == []

    @patch("tapps_mcp.tools.batch_validator.subprocess.run")
    def test_detect_changed_deduplicates(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.tools.batch_validator import detect_changed_python_files

        (tmp_path / "a.py").write_text("x = 1\n")

        # Both unstaged and staged return the same file
        mock_run.return_value = MagicMock(returncode=0, stdout="a.py\n")
        result = detect_changed_python_files(tmp_path)
        assert len(result) == 1

    def test_format_batch_summary(self) -> None:
        from tapps_mcp.tools.batch_validator import format_batch_summary

        results = [
            {"gate_passed": True, "security_issues": 0},
            {"gate_passed": False, "security_issues": 2},
        ]
        summary = format_batch_summary(results)
        assert "2 files" in summary
        assert "1 passed" in summary
        assert "1 failed" in summary
        assert "2 security" in summary


# ---------------------------------------------------------------------------
# tapps_quick_check - batch mode (Story 74.1)
# ---------------------------------------------------------------------------


class TestTappsQuickCheckBatch:
    """Tests for the tapps_quick_check batch mode (file_paths parameter)."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server_scoring_tools.load_settings")
    async def test_batch_single_file(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(file_path="", file_paths=str(f))
        assert result["success"] is True
        data = result["data"]
        assert data["files_checked"] == 1
        assert isinstance(data["results"], list)
        assert len(data["results"]) == 1
        assert data["results"][0]["success"] is True
        assert "all_passed" in data

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server_scoring_tools.load_settings")
    async def test_batch_multiple_files(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("x = 1\n", encoding="utf-8")
        f2.write_text("y = 2\n", encoding="utf-8")

        def _validate_side_effect(fp: str) -> Path:
            if "a.py" in fp:
                return f1
            return f2

        mock_validate.side_effect = _validate_side_effect
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(
            file_path="", file_paths=f"{f1},{f2}"
        )
        assert result["success"] is True
        data = result["data"]
        assert data["files_checked"] == 2
        assert len(data["results"]) == 2
        assert all(r["success"] for r in data["results"])

    @pytest.mark.asyncio
    async def test_batch_empty_string(self) -> None:
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        result = await tapps_quick_check(file_path="", file_paths="  ,  , ")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_input"

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server_scoring_tools.load_settings")
    async def test_batch_mixed_pass_fail(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f_good = tmp_path / "good.py"
        f_good.write_text("x = 1\n", encoding="utf-8")

        def _validate_side_effect(fp: str) -> Path:
            if "good.py" in fp:
                return f_good
            raise FileNotFoundError(f"not found: {fp}")

        mock_validate.side_effect = _validate_side_effect
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(
            file_path="", file_paths=f"{f_good},/nonexistent/bad.py"
        )
        assert result["success"] is True
        data = result["data"]
        assert data["files_checked"] == 2
        assert data["all_passed"] is False
        assert data["failure_count"] >= 1
        successes = [r for r in data["results"] if r.get("success")]
        failures = [r for r in data["results"] if not r.get("success")]
        assert len(successes) == 1
        assert len(failures) == 1

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server_scoring_tools.load_settings")
    async def test_batch_file_paths_takes_precedence(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When both file_path and file_paths are provided, file_paths wins."""
        from tapps_mcp.server_scoring_tools import tapps_quick_check

        f = tmp_path / "batch.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(
            file_path="/ignored/single.py", file_paths=str(f)
        )
        assert result["success"] is True
        data = result["data"]
        assert "files_checked" in data
        assert "results" in data


# ---------------------------------------------------------------------------
# correlation_id traceability (Story 74.4)
# ---------------------------------------------------------------------------


class TestValidateChangedCorrelationId:
    """Tests for optional correlation_id parameter on tapps_validate_changed."""

    @pytest.mark.asyncio
    async def test_validate_changed_correlation_id_no_changed_files(
        self, tmp_path: Path
    ) -> None:
        """correlation_id is included even when no files are changed."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[],
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed(
                correlation_id="empty-run-456",
            )

        assert result["success"] is True
        assert result["data"]["correlation_id"] == "empty-run-456"

    @pytest.mark.asyncio
    async def test_validate_changed_without_correlation_id(self, tmp_path: Path) -> None:
        """When correlation_id is empty (default), it is absent from response data."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[],
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed()

        assert result["success"] is True
        assert "correlation_id" not in result["data"]

    @pytest.mark.asyncio
    async def test_validate_changed_correlation_id_stripped(self, tmp_path: Path) -> None:
        """correlation_id with whitespace is stripped before inclusion."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[],
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed(
                correlation_id="  spaces-trimmed  ",
            )

        assert result["data"]["correlation_id"] == "spaces-trimmed"
