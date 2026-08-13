"""TAP-5965 — tapps_validate_changed must not wedge under concurrency.

Root cause covered here: ``heavy_cpu()`` is a process-wide, non-reentrant
semaphore (limit 2).  ``_validate_single_file`` holds a slot while it calls
``CodeScorer.score_file``, which acquires a *second* slot for its category
build.  With ``_VALIDATE_CONCURRENCY == 2`` every slot ends up held by an
outer waiter that can only progress by acquiring an inner slot, so the batch
deadlocks — and the explicit-``file_paths`` gather had no wall-clock bound,
so the MCP caller hung forever instead of getting a verdict.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_pipeline_tools import tapps_validate_changed
from tapps_mcp.tools import content_hash_cache as _chc
from tapps_mcp.tools import event_loop_guard as guard
from tapps_mcp.tools.parallel import ParallelResults

# Wall-clock ceiling for the two-root acceptance run. Real scoring is stubbed
# at the subprocess boundary, so a healthy run is sub-second; anything near
# this bound means the batch is wedged.
_BOTH_RETURN_BOUND_S = 20.0


@pytest.fixture(autouse=True)
def _clear_state() -> Any:
    _chc.clear()
    guard.reset_heavy_cpu_semaphore_for_tests()
    yield
    _chc.clear()
    guard.reset_heavy_cpu_semaphore_for_tests()


def _make_root(tmp_path: Path, name: str, n_files: int) -> tuple[Path, list[str]]:
    root = tmp_path / name
    root.mkdir()
    names = []
    for i in range(n_files):
        (root / f"mod{i}.py").write_text(f"def f{i}(x: int) -> int:\n    return x + {i}\n")
        names.append(f"mod{i}.py")
    return root, names


def _settings_for(root: Path) -> Any:
    settings = MagicMock()
    settings.project_root = root
    settings.tool_timeout = 30
    settings.dependency_scan_enabled = False
    settings.quality_preset = "standard"
    settings.validate_changed.judges = []
    settings.validate_changed.missing_file_paths_mode = "off"
    settings.memory.recall_on_validate = False
    settings.model_copy.return_value = settings
    return settings


async def _no_subprocess_tools(*_args: Any, **_kwargs: Any) -> ParallelResults:
    """Stand in for the ruff/mypy/bandit/radon fan-out.

    Keeps ``CodeScorer.score_file`` — and therefore its nested ``heavy_cpu()``
    acquisition — on the real code path while removing subprocess latency.
    """
    return ParallelResults()


@pytest.mark.asyncio
async def test_two_concurrent_roots_full_mode_both_return(tmp_path: Path) -> None:
    """Two concurrent full-mode calls from distinct roots must both return."""
    root_a, files_a = _make_root(tmp_path, "repo_a", 2)
    root_b, files_b = _make_root(tmp_path, "repo_b", 2)

    # Pin the guard to its shipped limit so the test reproduces the field
    # geometry (2 heavy slots vs 2 concurrent files per call) regardless of
    # TAPPS_MCP_HEAVY_CPU_LIMIT in the developer's environment.
    with (
        patch.object(guard, "_LIMIT", 2),
        patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            side_effect=_no_subprocess_tools,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            side_effect=lambda *a, **k: _settings_for(root_a),
        ),
    ):
        guard.reset_heavy_cpu_semaphore_for_tests()
        loop = asyncio.get_running_loop()
        started = loop.time()
        results = await asyncio.wait_for(
            asyncio.gather(
                tapps_validate_changed(
                    file_paths=",".join(files_a),
                    project_root=str(root_a),
                    quick=False,
                    include_security=False,
                ),
                tapps_validate_changed(
                    file_paths=",".join(files_b),
                    project_root=str(root_b),
                    quick=False,
                    include_security=False,
                ),
            ),
            timeout=_BOTH_RETURN_BOUND_S,
        )
        elapsed = loop.time() - started

    assert elapsed < _BOTH_RETURN_BOUND_S
    for result in results:
        assert result["tool"] == "tapps_validate_changed"
        data = result["data"]
        assert data.get("timed_out") is not True
        assert data["files_validated"] == 2


@pytest.mark.asyncio
async def test_explicit_paths_batch_is_wall_clock_bounded(tmp_path: Path) -> None:
    """A stuck file yields a structured timeout envelope, never a hang."""
    files = []
    for i in range(2):
        p = tmp_path / f"stuck{i}.py"
        p.write_text(f"x = {i}\n", encoding="utf-8")
        files.append(p)

    async def never_returns(path: Path, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    with (
        patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_settings_for(tmp_path),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._discover_changed_files",
            return_value=files,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._validate_single_file",
            side_effect=never_returns,
        ),
        patch(
            "tapps_mcp.tools.validate_changed_orchestrator._EXPLICIT_PATHS_BUDGET_S",
            0.25,
        ),
    ):
        result = await asyncio.wait_for(
            tapps_validate_changed(
                file_paths=",".join(str(p) for p in files),
                include_impact=False,
            ),
            timeout=30,
        )

    data = result["data"]
    assert data["timed_out"] is True
    assert data["code"] == "validate_changed_timeout"
    assert data["files_remaining"] == 2
    assert data["all_gates_passed"] is False
