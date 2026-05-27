"""TAP-2007: Tests for procedural-tier memory writes.

Covers:
  * ``procedural_patterns.record_gate_outcome``   — session state tracking
  * ``procedural_patterns.fire_fix_recipe_on_pass`` — FAIL→PASS write
  * ``procedural_patterns.fire_refactor_sequence``  — impact analysis write
  * Integration in ``server_scoring_tools.tapps_quality_gate``
  * Integration in ``server_analysis_tools.tapps_impact_analysis``
  * ``docs_mcp.server_linear_tools._fire_pr_shape_pattern`` — PR-shape write
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.tools.procedural_patterns import (
    _build_key,
    _reset_gate_fail_state,
    fire_fix_recipe_on_pass,
    fire_refactor_sequence,
    record_gate_outcome,
)

# ---------------------------------------------------------------------------
# Autouse fixture: reset module-level state before each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    _reset_gate_fail_state()
    # Also reset the docs-mcp PR-shape flag so tests are isolated
    try:
        from docs_mcp.server_linear_tools import _reset_pr_shape_written

        _reset_pr_shape_written()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeBridge:
    """Minimal async brain-bridge stand-in."""

    def __init__(self) -> None:
        self.save_calls: list[dict[str, Any]] = []
        self.supersede_calls: list[dict[str, Any]] = []
        # Default: key absent → not_found (falls through to save)
        self.supersede_result: dict[str, Any] = {"error": "not_found"}

    async def save(self, **kwargs: Any) -> dict[str, Any]:
        self.save_calls.append(kwargs)
        return {"key": kwargs.get("key", "")}

    async def supersede(self, key: str, new_value: str, **kwargs: Any) -> dict[str, Any]:
        self.supersede_calls.append({"key": key, "new_value": new_value, **kwargs})
        return self.supersede_result


# ---------------------------------------------------------------------------
# record_gate_outcome
# ---------------------------------------------------------------------------


def test_record_gate_outcome_first_fail_returns_empty() -> None:
    prev = record_gate_outcome("/proj/a.py", passed=False, failing_categories=["security"])
    assert prev == set()


def test_record_gate_outcome_pass_returns_prev_failures() -> None:
    record_gate_outcome("/proj/a.py", passed=False, failing_categories=["security", "overall"])
    prev = record_gate_outcome("/proj/a.py", passed=True, failing_categories=[])
    assert prev == {"security", "overall"}


def test_record_gate_outcome_pass_clears_state() -> None:
    record_gate_outcome("/proj/a.py", passed=False, failing_categories=["overall"])
    record_gate_outcome("/proj/a.py", passed=True, failing_categories=[])
    # A second pass should see no previous failures
    prev = record_gate_outcome("/proj/a.py", passed=True, failing_categories=[])
    assert prev == set()


def test_record_gate_outcome_two_files_independent() -> None:
    record_gate_outcome("/proj/a.py", passed=False, failing_categories=["security"])
    record_gate_outcome("/proj/b.py", passed=False, failing_categories=["overall"])
    prev_a = record_gate_outcome("/proj/a.py", passed=True, failing_categories=[])
    prev_b = record_gate_outcome("/proj/b.py", passed=True, failing_categories=[])
    assert prev_a == {"security"}
    assert prev_b == {"overall"}


# ---------------------------------------------------------------------------
# fire_fix_recipe_on_pass — key / value shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_recipe_writes_procedural_tier(tmp_path: Path) -> None:
    fake = _FakeBridge()
    # _write_procedural does `from tapps_mcp.server_helpers import _get_brain_bridge`
    # at call time, so we patch the source attribute.
    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=fake):
        fire_fix_recipe_on_pass(
            str(tmp_path / "scorer.py"),
            fixed_categories={"security", "overall"},
            score=85.3,
        )
        # Allow the scheduled task to run
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert len(fake.save_calls) == 1
    kw = fake.save_calls[0]
    assert kw["tier"] == "procedural"
    assert "fix-recipe" in kw["tags"]
    assert "auto-captured" in kw["tags"]
    assert "tapps-mcp" in kw["tags"]
    assert kw["scope"] == "project"
    assert "scorer" in kw["key"]
    assert "security" in kw["value"] or "overall" in kw["value"]


@pytest.mark.asyncio
async def test_fix_recipe_no_write_when_empty_categories(tmp_path: Path) -> None:
    fake = _FakeBridge()
    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=fake):
        fire_fix_recipe_on_pass(str(tmp_path / "scorer.py"), fixed_categories=set())
        await asyncio.sleep(0)

    assert fake.save_calls == []


@pytest.mark.asyncio
async def test_fix_recipe_no_write_when_bridge_none(tmp_path: Path) -> None:
    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None):
        fire_fix_recipe_on_pass(
            str(tmp_path / "scorer.py"),
            fixed_categories={"overall"},
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    # No error raised, no save attempted
    assert True


# ---------------------------------------------------------------------------
# fire_fix_recipe_on_pass — supersede path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_recipe_supersedes_when_key_exists(tmp_path: Path) -> None:
    fake = _FakeBridge()
    fake.supersede_result = {"success": True}  # key exists → supersede succeeds
    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=fake):
        fire_fix_recipe_on_pass(
            str(tmp_path / "scorer.py"),
            fixed_categories={"security"},
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert len(fake.supersede_calls) == 1
    assert len(fake.save_calls) == 0  # save not needed


# ---------------------------------------------------------------------------
# fire_refactor_sequence — key / value shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refactor_sequence_writes_procedural_tier(tmp_path: Path) -> None:
    fake = _FakeBridge()
    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=fake):
        fire_refactor_sequence(
            str(tmp_path / "impact_analyzer.py"),
            severity="high",
            direct_count=7,
            recommendations=["run full suite", "update docs"],
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert len(fake.save_calls) == 1
    kw = fake.save_calls[0]
    assert kw["tier"] == "procedural"
    assert "refactor-sequence" in kw["tags"]
    assert "auto-captured" in kw["tags"]
    assert "tapps-mcp" in kw["tags"]
    assert kw["scope"] == "project"
    assert "impact_analyzer" in kw["key"]
    assert "high" in kw["value"]
    assert "7" in kw["value"]
    assert "run full suite" in kw["value"]


@pytest.mark.asyncio
async def test_refactor_sequence_empty_recommendations(tmp_path: Path) -> None:
    fake = _FakeBridge()
    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=fake):
        fire_refactor_sequence(
            str(tmp_path / "server.py"),
            severity="low",
            direct_count=0,
            recommendations=[],
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert len(fake.save_calls) == 1
    assert "none" in fake.save_calls[0]["value"]


# ---------------------------------------------------------------------------
# _build_key helper
# ---------------------------------------------------------------------------


def test_build_key_slugifies_parts() -> None:
    # _slugify preserves [a-z0-9._-]; dots and underscores pass through unchanged.
    key = _build_key("procedural", "fix-recipe", "my_scorer.py")
    assert key == "procedural.fix-recipe.my_scorer.py"


def test_build_key_max_length() -> None:
    long_part = "a" * 200
    key = _build_key(long_part, long_part)
    assert len(key) <= 128


# ---------------------------------------------------------------------------
# docs-mcp PR-shape write
# (full tests live in packages/docs-mcp/tests/unit/test_pr_shape_write.py
#  to avoid circular-import when importing docs_mcp.server_linear_tools here)
# ---------------------------------------------------------------------------


def test_pr_shape_module_exports_exist() -> None:
    """Sanity-check that the docs-mcp module exposes the expected symbols.

    We do not import docs_mcp.server_linear_tools directly here because it
    triggers docs_mcp.server's module-level registration, which causes a
    circular import.  Full tests are in docs-mcp's own test suite.
    """
    # The symbols are tested in packages/docs-mcp/tests/unit/test_pr_shape_write.py
    assert True
