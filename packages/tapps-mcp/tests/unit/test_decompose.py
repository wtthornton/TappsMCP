"""Tests for tapps_decompose tool (TAP-479)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_pipeline_tools import (
    TaskUnit,
    _classify_model_tier,
    _classify_risk,
    _decompose_task,
    _split_task_into_phrases,
)


class TestClassifyModelTier:
    def test_design_keyword_returns_opus(self) -> None:
        tier, reason = _classify_model_tier("design the authentication architecture")
        assert tier == "opus"
        assert "opus" not in reason or "design" in reason.lower() or "architectural" in reason.lower()

    def test_implement_keyword_returns_sonnet(self) -> None:
        tier, _ = _classify_model_tier("implement JWT token refresh")
        assert tier == "sonnet"

    def test_search_keyword_returns_haiku(self) -> None:
        tier, _ = _classify_model_tier("search for unused imports")
        assert tier == "haiku"

    def test_no_signal_defaults_to_sonnet(self) -> None:
        tier, _ = _classify_model_tier("do something vague")
        assert tier == "sonnet"

    def test_audit_returns_opus(self) -> None:
        tier, _ = _classify_model_tier("audit the security configuration")
        assert tier == "opus"


class TestClassifyRisk:
    def test_security_is_high(self) -> None:
        assert _classify_risk("security review of auth module") == "high"

    def test_read_is_low(self) -> None:
        assert _classify_risk("read the config file") == "low"

    def test_implement_is_medium(self) -> None:
        assert _classify_risk("implement the new feature") == "medium"


class TestSplitTaskIntoPhrases:
    def test_single_phrase(self) -> None:
        phrases = _split_task_into_phrases("implement authentication")
        assert len(phrases) >= 1
        assert "implement authentication" in phrases[0]

    def test_comma_separated(self) -> None:
        phrases = _split_task_into_phrases("design module, implement logic, test it")
        assert len(phrases) >= 2

    def test_semicolon_separated(self) -> None:
        phrases = _split_task_into_phrases("step one; step two; step three")
        assert len(phrases) == 3

    def test_newline_separated(self) -> None:
        phrases = _split_task_into_phrases("first task\nsecond task")
        assert len(phrases) == 2


class TestDecomposeTask:
    def test_single_unit_task(self) -> None:
        units = _decompose_task("implement authentication", [])
        assert len(units) >= 1
        assert all(isinstance(u, TaskUnit) for u in units)

    def test_multi_unit_task(self) -> None:
        units = _decompose_task(
            "design auth module, implement JWT login, test endpoints, search for issues", []
        )
        assert len(units) >= 3

    def test_risk_first_ordering(self) -> None:
        units = _decompose_task(
            "search config, design architecture, implement feature", []
        )
        risks = [u.dominant_risk for u in units]
        _RISK_ORDER = {"high": 0, "medium": 1, "low": 2}
        for i in range(len(risks) - 1):
            assert _RISK_ORDER[risks[i]] <= _RISK_ORDER[risks[i + 1]], (
                f"Units not risk-first: {risks}"
            )

    def test_sequential_ids(self) -> None:
        units = _decompose_task("design, implement, test", [])
        for idx, unit in enumerate(units, start=1):
            assert unit.id == f"u{idx}"

    def test_context_files_appear_in_first_unit(self) -> None:
        units = _decompose_task("implement auth", ["auth.py", "models.py"])
        assert len(units) >= 1
        assert "auth.py" in units[0].description

    def test_model_tier_values_valid(self) -> None:
        units = _decompose_task("search, design, implement, test", [])
        valid_tiers = {"haiku", "sonnet", "opus"}
        for unit in units:
            assert unit.model_tier in valid_tiers

    def test_done_condition_not_empty(self) -> None:
        units = _decompose_task("implement login", [])
        for unit in units:
            assert unit.done_condition

    def test_depends_on_sequential(self) -> None:
        units = _decompose_task("design, implement, test, deploy", [])
        # First unit has no deps, subsequent units depend on previous
        assert units[0].depends_on == []
        for idx, unit in enumerate(units[1:], start=2):
            assert unit.depends_on == [f"u{idx - 1}"]


class TestDecomposeToolHandler:
    @pytest.mark.asyncio
    async def test_empty_task_returns_error(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_decompose

        with (
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda *a, **kw: a[1]),
        ):
            result = await tapps_decompose(task="")
        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_valid_task_returns_units(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_decompose

        with (
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda *a, **kw: a[1]),
        ):
            result = await tapps_decompose(task="implement JWT authentication")

        assert result.get("success") is True
        data = result.get("data", {})
        assert data["unit_count"] >= 1
        assert len(data["units"]) == data["unit_count"]

    @pytest.mark.asyncio
    async def test_context_files_in_response(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_decompose

        f = tmp_path / "auth.py"
        f.write_text("def login(): pass")

        with (
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda *a, **kw: a[1]),
        ):
            result = await tapps_decompose(
                task="implement authentication",
                context_files=[str(f)],
            )

        data = result.get("data", {})
        assert data["context_files"][0]["exists"] is True
        assert data["context_files"][0]["size_bytes"] is not None
