"""Performance budget regression tests for tapps_quick_check (STORY-101.6).

Verifies that:
1. The 2-second budget constant is defined and correct.
2. Cache hits short-circuit before invoking the scorer — the content-hash
   cache from STORY-101.1 is the primary mechanism that keeps quick_check
   fast on unchanged files.
3. A timed smoke run with all I/O mocked stays within the budget.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server_scoring_tools import QUICK_CHECK_BUDGET_MS, tapps_quick_check


# ---------------------------------------------------------------------------
# 101.6-A: budget constant
# ---------------------------------------------------------------------------


class TestBudgetConstant:
    def test_budget_constant_defined(self) -> None:
        assert QUICK_CHECK_BUDGET_MS == 2000

    def test_budget_constant_is_positive(self) -> None:
        assert QUICK_CHECK_BUDGET_MS > 0


# ---------------------------------------------------------------------------
# 101.6-B: cache-hit path skips scorer
# ---------------------------------------------------------------------------


@pytest.fixture
def py_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text('"""module."""\n\ndef add(a: int, b: int) -> int:\n    return a + b\n')
    return p


_CACHED_DATA: dict[str, Any] = {
    "file_path": "sample.py",
    "overall_score": 88,
    "gate_passed": True,
    "security_passed": True,
    "elapsed_ms": 12,
}


@pytest.mark.asyncio
async def test_cache_hit_skips_scorer(py_file: Path) -> None:
    """When the content-hash cache has a fresh result, the scorer is never called."""
    mock_scorer = MagicMock()

    with (
        patch(
            "tapps_mcp.server._validate_file_path",
            return_value=py_file,
        ),
        patch(
            "tapps_mcp.server_scoring_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.server_scoring_tools._get_scorer_for_file",
            return_value=mock_scorer,
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.content_hash",
            return_value="abc123",
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.get",
            return_value=_CACHED_DATA,
        ),
        patch("tapps_mcp.server._record_call", MagicMock()),
        patch("tapps_mcp.server._record_execution", MagicMock()),
        patch("tapps_mcp.server._with_nudges", lambda _tool, resp, _ctx=None: resp),
    ):
        resp = await tapps_quick_check(file_path=str(py_file))

    # Scorer must not be invoked — the cache short-circuits before it.
    mock_scorer.score_file_quick.assert_not_called()
    mock_scorer.score_file_quick_enriched.assert_not_called()
    assert resp.get("success") is True
    assert resp.get("data", {}).get("cache_hit") is True


@pytest.mark.asyncio
async def test_cache_hit_returns_within_budget(py_file: Path) -> None:
    """Cache-hit response time is well within QUICK_CHECK_BUDGET_MS."""
    with (
        patch(
            "tapps_mcp.server._validate_file_path",
            return_value=py_file,
        ),
        patch(
            "tapps_mcp.server_scoring_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.content_hash",
            return_value="abc123",
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.get",
            return_value=_CACHED_DATA,
        ),
        patch("tapps_mcp.server._record_call", MagicMock()),
        patch("tapps_mcp.server._record_execution", MagicMock()),
        patch("tapps_mcp.server._with_nudges", lambda _tool, resp, _ctx=None: resp),
    ):
        t0 = time.perf_counter()
        await tapps_quick_check(file_path=str(py_file))
        elapsed_ms = (time.perf_counter() - t0) * 1000

    # Cache hit should be orders of magnitude below the 2-second budget.
    assert elapsed_ms < QUICK_CHECK_BUDGET_MS, (
        f"Cache-hit path took {elapsed_ms:.0f}ms — exceeds {QUICK_CHECK_BUDGET_MS}ms budget"
    )
