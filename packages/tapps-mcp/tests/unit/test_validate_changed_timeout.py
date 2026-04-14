"""STORY-101.3 — tapps_validate_changed auto-detect wall-clock cap.

Covers:
- Budget respected when auto-detect returns many slow files
- Cache hits don't consume the budget
- Timed-out response shape (timed_out, files_remaining, next_steps)
- Explicit file_paths mode ignores the cap
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server_pipeline_tools import tapps_validate_changed
from tapps_mcp.tools import content_hash_cache as _chc


def _make_files(tmp_path: Path, n: int) -> list[Path]:
    paths: list[Path] = []
    for i in range(n):
        p = tmp_path / f"f{i}.py"
        p.write_text(f"x = {i}\n", encoding="utf-8")
        paths.append(p)
    return paths


def _fast_result(path: Path) -> dict[str, Any]:
    return {
        "file_path": str(path),
        "overall_score": 90.0,
        "gate_passed": True,
        "security_passed": True,
        "security_issues": 0,
        "language": "python",
    }


def _patch_settings(tmp_path: Path) -> Any:
    mock_settings = MagicMock()
    mock_settings.project_root = tmp_path
    mock_settings.tool_timeout = 30
    mock_settings.dependency_scan_enabled = False
    return mock_settings


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _chc.clear()


@pytest.mark.asyncio
async def test_auto_detect_budget_respected(tmp_path: Path) -> None:
    """Auto-detect with many slow files returns partial results within budget."""
    files = _make_files(tmp_path, 10)

    async def slow_validate(
        path: Path, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        await asyncio.sleep(5.0)  # well over the tiny budget
        return _fast_result(path)

    with (
        patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_patch_settings(tmp_path),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._discover_changed_files",
            return_value=files,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._validate_single_file",
            side_effect=slow_validate,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
            return_value=None,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._AUTO_DETECT_BUDGET_S", 0.3
        ),
    ):
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        result = await tapps_validate_changed(file_paths="", include_impact=False)
        elapsed = loop.time() - t0

    # Worst-case without a budget would be 10 * 5s = 50s; session init can
    # add ~2s of overhead before we enter the budgeted wait.
    assert elapsed < 10.0, f"budget not enforced, took {elapsed:.2f}s"
    assert result["success"] is True
    data = result["data"]
    assert data["timed_out"] is True
    assert data["files_remaining"] > 0
    assert data["auto_detect_budget_s"] == 0.3


@pytest.mark.asyncio
async def test_cached_files_do_not_count_against_budget(tmp_path: Path) -> None:
    """Files with a KIND_QUICK_CHECK cache entry bypass the scorer and budget."""
    files = _make_files(tmp_path, 5)

    # Pre-populate cache for every file.
    for p in files:
        sha = _chc.content_hash(p)
        _chc.set(
            _chc.KIND_QUICK_CHECK,
            sha,
            {
                "file_path": str(p),
                "overall_score": 95.0,
                "gate_passed": True,
                "security_passed": True,
                "security_issue_count": 0,
            },
        )

    validate_mock = AsyncMock(side_effect=lambda p, *a, **kw: _fast_result(p))

    with (
        patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_patch_settings(tmp_path),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._discover_changed_files",
            return_value=files,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._validate_single_file",
            validate_mock,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
            return_value=None,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._AUTO_DETECT_BUDGET_S", 0.05
        ),
    ):
        result = await tapps_validate_changed(file_paths="", include_impact=False)

    assert result["success"] is True
    data = result["data"]
    assert data["files_validated"] == len(files)
    assert data.get("timed_out") is not True
    # No scorer work occurred — all results came from cache.
    validate_mock.assert_not_awaited()
    for r in data["results"]:
        assert r.get("cache_hit") is True


@pytest.mark.asyncio
async def test_timed_out_response_shape(tmp_path: Path) -> None:
    """Timed-out responses expose files_remaining + copy-paste next_steps."""
    files = _make_files(tmp_path, 3)

    async def slow_validate(
        path: Path, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        await asyncio.sleep(2.0)
        return _fast_result(path)

    with (
        patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_patch_settings(tmp_path),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._discover_changed_files",
            return_value=files,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._validate_single_file",
            side_effect=slow_validate,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
            return_value=None,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._AUTO_DETECT_BUDGET_S", 0.1
        ),
    ):
        result = await tapps_validate_changed(file_paths="", include_impact=False)

    data = result["data"]
    assert data["timed_out"] is True
    assert isinstance(data["files_remaining"], int)
    assert data["files_remaining"] >= 1
    assert len(data["files_remaining_paths"]) == data["files_remaining"]
    next_steps = data.get("next_steps", [])
    assert next_steps, "expected a remediation next_step"
    first = next_steps[0]
    assert "tapps_validate_changed" in first
    assert "file_paths=" in first


@pytest.mark.asyncio
async def test_explicit_file_paths_ignores_cap(tmp_path: Path) -> None:
    """Explicit file_paths mode completes even if each file is slow."""
    files = _make_files(tmp_path, 3)

    call_order: list[str] = []

    async def moderately_slow(
        path: Path, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        await asyncio.sleep(0.15)
        call_order.append(str(path))
        return _fast_result(path)

    explicit = ",".join(str(p) for p in files)

    with (
        patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_patch_settings(tmp_path),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._discover_changed_files",
            return_value=files,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._validate_single_file",
            side_effect=moderately_slow,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
            return_value=None,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._AUTO_DETECT_BUDGET_S", 0.01
        ),
    ):
        result = await tapps_validate_changed(
            file_paths=explicit, include_impact=False
        )

    data = result["data"]
    assert data.get("timed_out") is not True
    assert data["files_validated"] == len(files)
    assert len(call_order) == len(files)
