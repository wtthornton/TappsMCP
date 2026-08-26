"""TAP-5271: validate_changed warm budget + missing file_paths guard."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.validate_changed import (
    VALIDATE_CHANGED_WARM_BUDGET_MS,
    tapps_validate_changed,
)
from tapps_mcp.tools.validate_changed_collection import count_tracked_scorable_files

pytestmark = pytest.mark.usefixtures("envelope_guard")


class TestWarmBudgetConstant:
    def test_warm_budget_is_15s(self) -> None:
        assert VALIDATE_CHANGED_WARM_BUDGET_MS == 15_000


class TestCountTrackedScorable:
    def test_counts_python_files_without_git(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
        (tmp_path / "b.ts").write_text(" console.log(1)\n".replace(" ", ""), encoding="utf-8")
        (tmp_path / "readme.md").write_text("# hi\n", encoding="utf-8")
        # No .git — falls back to rglob
        assert count_tracked_scorable_files(tmp_path) == 2


class TestMissingFilePathsGuard:
    @pytest.mark.asyncio
    async def test_error_mode_refuses_empty_paths_in_large_repo(
        self, tmp_path: Path
    ) -> None:
        for i in range(5):
            (tmp_path / f"m{i}.py").write_text("x=1\n", encoding="utf-8")

        settings = MagicMock()
        settings.project_root = tmp_path
        settings.validate_changed.missing_file_paths_mode = "error"
        settings.validate_changed.require_explicit_paths_above = 3
        settings.validate_changed.judges = []
        settings.tool_timeout = 30
        settings.dependency_scan_enabled = False

        with patch("tapps_mcp.server_pipeline_tools.load_settings", return_value=settings):
            result = await tapps_validate_changed(file_paths="")

        assert result["success"] is False
        # error_response embeds code under error / error_code depending on envelope
        blob = str(result)
        assert "missing_file_paths" in blob
        assert "file_paths" in blob.lower() or "omitted" in blob.lower()

    @pytest.mark.asyncio
    async def test_warn_mode_continues_with_warning(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"m{i}.py").write_text("x=1\n", encoding="utf-8")
        target = tmp_path / "m0.py"

        settings = MagicMock()
        settings.project_root = tmp_path
        settings.validate_changed.missing_file_paths_mode = "warn"
        settings.validate_changed.require_explicit_paths_above = 3
        settings.validate_changed.judges = []
        settings.tool_timeout = 30
        settings.dependency_scan_enabled = False

        score = MagicMock(
            overall=90.0,
            categories={},
            degraded=False,
            issues=[],
            file_path=str(target),
        )
        scorer = MagicMock()
        scorer.score_file = AsyncMock(return_value=score)
        gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings", return_value=settings),
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[target],
            ),
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
            patch(
                "tapps_mcp.server_helpers.ensure_session_initialized",
                new_callable=AsyncMock,
            ),
        ):
            result = await tapps_validate_changed(file_paths="")

        assert result["success"] is True
        warnings = result["data"].get("warnings") or []
        assert any("file_paths was omitted" in str(w) for w in warnings)


class TestWarmPathBudget:
    @pytest.mark.asyncio
    async def test_explicit_paths_mocked_stay_under_warm_budget(
        self, tmp_path: Path
    ) -> None:
        """Warm-path smoke: mocked I/O for 5 explicit files stays under 15s."""
        files = []
        for i in range(5):
            p = tmp_path / f"f{i}.py"
            p.write_text(f"x = {i}\n", encoding="utf-8")
            files.append(p)

        settings = MagicMock()
        settings.project_root = tmp_path
        settings.validate_changed.missing_file_paths_mode = "off"
        settings.validate_changed.require_explicit_paths_above = 50
        settings.validate_changed.judges = []
        settings.tool_timeout = 30
        settings.dependency_scan_enabled = False

        score = MagicMock(
            overall=90.0,
            categories={},
            degraded=False,
            issues=[],
            file_path="f0.py",
        )
        scorer = MagicMock()
        scorer.score_file = AsyncMock(return_value=score)
        gate = MagicMock(passed=True, failures=[])

        joined = ",".join(str(p) for p in files)
        t0 = time.perf_counter()
        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings", return_value=settings),
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
            patch(
                "tapps_mcp.server_helpers.ensure_session_initialized",
                new_callable=AsyncMock,
            ),
        ):
            result = await tapps_validate_changed(
                file_paths=joined,
                include_impact=False,
                quick=True,
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert result["success"] is True
        assert elapsed_ms < VALIDATE_CHANGED_WARM_BUDGET_MS
        profile = result["data"].get("timing_profile")
        assert isinstance(profile, dict)
        assert profile["warm_budget_ms"] == VALIDATE_CHANGED_WARM_BUDGET_MS
        assert profile["auto_detect"] is False
