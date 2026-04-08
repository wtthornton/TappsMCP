"""Tests for tools.radon — parsing, scoring, and direct-library fallback."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.tools.radon import (
    _is_radon_importable,
    _radon_cc_direct,
    _radon_hal_direct,
    _radon_mi_direct,
    calculate_complexity_score,
    calculate_maintainability_score,
    parse_radon_cc_json,
    parse_radon_hal_json,
    parse_radon_mi_json,
    run_radon_cc,
    run_radon_cc_async,
    run_radon_hal,
    run_radon_hal_async,
    run_radon_mi,
    run_radon_mi_async,
)
from tapps_mcp.tools.subprocess_utils import CommandResult

SAMPLE_CC_JSON = json.dumps(
    {
        "test.py": [
            {"name": "foo", "complexity": 3, "type": "function", "lineno": 1},
            {"name": "bar", "complexity": 8, "type": "function", "lineno": 10},
        ]
    }
)

SAMPLE_MI_JSON = json.dumps({"test.py": {"mi": 72.5, "rank": "A"}})
SAMPLE_MI_SCALAR = json.dumps({"test.py": 65.0})


class TestParseRadonCcJson:
    def test_valid_output(self):
        entries = parse_radon_cc_json(SAMPLE_CC_JSON)
        assert len(entries) == 2
        assert entries[0]["name"] == "foo"
        assert entries[1]["complexity"] == 8

    def test_empty_string(self):
        assert parse_radon_cc_json("") == []

    def test_whitespace(self):
        assert parse_radon_cc_json("   ") == []

    def test_invalid_json(self):
        assert parse_radon_cc_json("not json") == []

    def test_empty_dict(self):
        assert parse_radon_cc_json("{}") == []

    def test_multiple_files(self):
        raw = json.dumps(
            {
                "a.py": [{"name": "f", "complexity": 2}],
                "b.py": [{"name": "g", "complexity": 5}],
            }
        )
        entries = parse_radon_cc_json(raw)
        assert len(entries) == 2

    def test_non_list_value_skipped(self):
        raw = json.dumps({"test.py": "not a list"})
        entries = parse_radon_cc_json(raw)
        assert entries == []


class TestCalculateComplexityScore:
    def test_empty_entries(self):
        assert calculate_complexity_score([]) == 1.0

    def test_low_complexity(self):
        entries = [{"complexity": 2}]
        score = calculate_complexity_score(entries)
        # 2 / 5.0 = 0.4
        assert abs(score - 0.4) < 0.01

    def test_high_complexity(self):
        entries = [{"complexity": 25}]
        score = calculate_complexity_score(entries)
        # 25 / 5.0 = 5.0
        assert abs(score - 5.0) < 0.01

    def test_very_high_clamps_to_max(self):
        entries = [{"complexity": 100}]
        score = calculate_complexity_score(entries)
        # 100 / 5.0 = 20.0 → clamped to 10.0
        assert score == 10.0

    def test_uses_blended_complexity(self):
        entries = [{"complexity": 2}, {"complexity": 8}]
        score = calculate_complexity_score(entries)
        # max=8, avg=5, blended = 0.7*8 + 0.3*5 = 7.1, score = 7.1/5.0 = 1.42
        assert abs(score - 1.42) < 0.01

    def test_missing_complexity_defaults_to_zero(self):
        entries = [{}]
        score = calculate_complexity_score(entries)
        assert score == 0.0


class TestParseRadonMiJson:
    def test_dict_value(self):
        result = parse_radon_mi_json(SAMPLE_MI_JSON)
        assert "test.py" in result
        assert abs(result["test.py"] - 72.5) < 0.01

    def test_scalar_value(self):
        result = parse_radon_mi_json(SAMPLE_MI_SCALAR)
        assert abs(result["test.py"] - 65.0) < 0.01

    def test_empty_string(self):
        assert parse_radon_mi_json("") == {}

    def test_invalid_json(self):
        assert parse_radon_mi_json("bad") == {}


class TestCalculateMaintainabilityScore:
    def test_perfect_mi(self):
        assert calculate_maintainability_score(100.0) == 10.0

    def test_zero_mi(self):
        assert calculate_maintainability_score(0.0) == 0.0

    def test_mid_mi(self):
        assert abs(calculate_maintainability_score(50.0) - 5.0) < 0.01

    def test_above_100_clamps(self):
        assert calculate_maintainability_score(120.0) == 10.0

    def test_negative_clamps(self):
        assert calculate_maintainability_score(-10.0) == 0.0


class TestRunRadonCc:
    @patch("tapps_mcp.tools.radon.run_command")
    def test_success(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout=SAMPLE_CC_JSON, stderr="")
        entries = run_radon_cc("test.py")
        assert len(entries) == 2

    @patch("tapps_mcp.tools.radon.run_command")
    def test_timeout(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=-1, stdout="", stderr="", timed_out=True)
        entries = run_radon_cc("test.py")
        assert entries == []

    @patch("tapps_mcp.tools.radon.run_command")
    def test_empty_output(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="", stderr="")
        entries = run_radon_cc("test.py")
        assert entries == []


class TestRunRadonMi:
    @patch("tapps_mcp.tools.radon.run_command")
    def test_success(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout=SAMPLE_MI_JSON, stderr="")
        mi = run_radon_mi("test.py")
        assert abs(mi - 72.5) < 0.01

    @patch("tapps_mcp.tools.radon.run_command")
    def test_timeout_returns_default(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=-1, stdout="", stderr="", timed_out=True)
        mi = run_radon_mi("test.py")
        assert mi == 50.0

    @patch("tapps_mcp.tools.radon.run_command")
    def test_empty_output_returns_default(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="", stderr="")
        mi = run_radon_mi("test.py")
        assert mi == 50.0

    @patch("tapps_mcp.tools.radon.run_command")
    def test_empty_json_returns_default(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="{}", stderr="")
        mi = run_radon_mi("test.py")
        assert mi == 50.0


class TestBlendedComplexity:
    """Tests for the blended CC formula (0.7*max + 0.3*avg)."""

    def test_single_entry_max_equals_avg(self):
        entries = [{"complexity": 10}]
        score = calculate_complexity_score(entries)
        # blended = 0.7*10 + 0.3*10 = 10, score = 10/5 = 2.0
        assert abs(score - 2.0) < 0.01

    def test_many_low_one_high(self):
        entries = [{"complexity": 1}] * 9 + [{"complexity": 20}]
        score = calculate_complexity_score(entries)
        # max=20, avg=(9*1+20)/10=2.9, blended=0.7*20+0.3*2.9=14.87
        # score = 14.87 / 5.0 = 2.974
        assert abs(score - 2.974) < 0.01

    def test_all_same_complexity(self):
        entries = [{"complexity": 5}] * 5
        score = calculate_complexity_score(entries)
        # max=5, avg=5, blended=5, score=1.0
        assert abs(score - 1.0) < 0.01


class TestRadonAsyncFallback:
    """Tests for subprocess-to-library fallback in async functions."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.radon.run_command_async", new_callable=AsyncMock)
    @patch("tapps_mcp.tools.radon._radon_cc_direct")
    async def test_cc_falls_back_on_empty_output(self, mock_direct, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="", stderr="")
        mock_direct.return_value = [{"name": "f", "complexity": 3}]
        result = await run_radon_cc_async("test.py")
        mock_direct.assert_called_once_with("test.py")
        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.radon.run_command_async", new_callable=AsyncMock)
    @patch("tapps_mcp.tools.radon._radon_cc_direct")
    async def test_cc_falls_back_on_timeout(self, mock_direct, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=-1, stdout="", stderr="", timed_out=True)
        mock_direct.return_value = []
        result = await run_radon_cc_async("test.py")
        mock_direct.assert_called_once()
        assert result == []

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.radon.run_command_async", new_callable=AsyncMock)
    async def test_cc_uses_subprocess_when_available(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout=SAMPLE_CC_JSON, stderr="")
        result = await run_radon_cc_async("test.py")
        assert len(result) == 2

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.radon.run_command_async", new_callable=AsyncMock)
    @patch("tapps_mcp.tools.radon._radon_mi_direct")
    async def test_mi_falls_back_on_empty_output(self, mock_direct, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="", stderr="")
        mock_direct.return_value = 72.5
        result = await run_radon_mi_async("test.py")
        mock_direct.assert_called_once_with("test.py")
        assert result == 72.5

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.radon.run_command_async", new_callable=AsyncMock)
    @patch("tapps_mcp.tools.radon._radon_mi_direct")
    async def test_mi_falls_back_on_empty_json(self, mock_direct, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="{}", stderr="")
        mock_direct.return_value = 65.0
        result = await run_radon_mi_async("test.py")
        mock_direct.assert_called_once()
        assert result == 65.0


class TestRadonDirectFallback:
    """Tests for direct radon library usage."""

    @patch("tapps_mcp.tools.radon._is_radon_importable", return_value=False)
    def test_cc_direct_returns_empty_when_unavailable(self, _mock):
        assert _radon_cc_direct("test.py") == []

    @patch("tapps_mcp.tools.radon._is_radon_importable", return_value=False)
    def test_mi_direct_returns_default_when_unavailable(self, _mock):
        assert _radon_mi_direct("test.py") == 50.0

    @patch("tapps_mcp.tools.radon._is_radon_importable", return_value=True)
    @patch("tapps_mcp.tools.radon._read_source", return_value=None)
    def test_cc_direct_returns_empty_on_read_failure(self, _mock_read, _mock_avail):
        assert _radon_cc_direct("missing.py") == []

    @patch("tapps_mcp.tools.radon._is_radon_importable", return_value=True)
    @patch("tapps_mcp.tools.radon._read_source", return_value=None)
    def test_mi_direct_returns_default_on_read_failure(self, _mock_read, _mock_avail):
        assert _radon_mi_direct("missing.py") == 50.0

    def test_is_radon_importable_caches(self):
        import tapps_mcp.tools.radon as radon_mod

        # Reset cache
        radon_mod._RADON_AVAILABLE = None
        result = _is_radon_importable()
        assert isinstance(result, bool)
        # Second call should use cached value
        result2 = _is_radon_importable()
        assert result == result2


# ---------------------------------------------------------------------------
# Halstead metrics tests
# ---------------------------------------------------------------------------

SAMPLE_HAL_JSON = json.dumps(
    {
        "test.py": {
            "total": [11, 15, 51.89, 2.86, 148.26, 8.24, 0.017],
            "functions": [
                ["fibonacci", {"volume": 23.26, "difficulty": 1.5, "effort": 34.90, "bugs": 0.008, "vocabulary": 6, "length": 9}],
                ["complex_func", {"volume": 2500.0, "difficulty": 35.0, "effort": 120000.0, "bugs": 1.5, "vocabulary": 20, "length": 150}],
            ],
        }
    }
)


class TestParseRadonHalJson:
    def test_valid_output(self):
        entries = parse_radon_hal_json(SAMPLE_HAL_JSON)
        assert len(entries) == 2
        assert entries[0]["name"] == "fibonacci"
        assert abs(float(entries[0]["volume"]) - 23.26) < 0.01

    def test_complex_function_values(self):
        entries = parse_radon_hal_json(SAMPLE_HAL_JSON)
        assert abs(float(entries[1]["volume"]) - 2500.0) < 0.01
        assert abs(float(entries[1]["difficulty"]) - 35.0) < 0.01
        assert abs(float(entries[1]["effort"]) - 120000.0) < 0.01
        assert abs(float(entries[1]["bugs"]) - 1.5) < 0.01

    def test_empty_string(self):
        assert parse_radon_hal_json("") == []

    def test_whitespace(self):
        assert parse_radon_hal_json("   ") == []

    def test_invalid_json(self):
        assert parse_radon_hal_json("not json") == []

    def test_empty_dict(self):
        assert parse_radon_hal_json("{}") == []

    def test_no_functions_key(self):
        raw = json.dumps({"test.py": {"total": [1, 2, 3]}})
        entries = parse_radon_hal_json(raw)
        assert entries == []

    def test_non_dict_content_skipped(self):
        raw = json.dumps({"test.py": "not a dict"})
        entries = parse_radon_hal_json(raw)
        assert entries == []


class TestRunRadonHal:
    @patch("tapps_mcp.tools.radon.run_command")
    def test_success(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout=SAMPLE_HAL_JSON, stderr="")
        entries = run_radon_hal("test.py")
        assert len(entries) == 2

    @patch("tapps_mcp.tools.radon.run_command")
    def test_timeout(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=-1, stdout="", stderr="", timed_out=True)
        entries = run_radon_hal("test.py")
        assert entries == []

    @patch("tapps_mcp.tools.radon.run_command")
    def test_empty_output(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="", stderr="")
        entries = run_radon_hal("test.py")
        assert entries == []


class TestRadonHalAsyncFallback:
    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.radon.run_command_async", new_callable=AsyncMock)
    @patch("tapps_mcp.tools.radon._radon_hal_direct")
    async def test_falls_back_on_empty_output(self, mock_direct, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="", stderr="")
        mock_direct.return_value = [{"name": "f", "volume": 10.0}]
        result = await run_radon_hal_async("test.py")
        mock_direct.assert_called_once_with("test.py")
        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.radon.run_command_async", new_callable=AsyncMock)
    @patch("tapps_mcp.tools.radon._radon_hal_direct")
    async def test_falls_back_on_timeout(self, mock_direct, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=-1, stdout="", stderr="", timed_out=True)
        mock_direct.return_value = []
        result = await run_radon_hal_async("test.py")
        mock_direct.assert_called_once()
        assert result == []

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.radon.run_command_async", new_callable=AsyncMock)
    async def test_uses_subprocess_when_available(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout=SAMPLE_HAL_JSON, stderr="")
        result = await run_radon_hal_async("test.py")
        assert len(result) == 2


class TestRadonHalDirectFallback:
    @patch("tapps_mcp.tools.radon._is_radon_importable", return_value=False)
    def test_returns_empty_when_unavailable(self, _mock):
        assert _radon_hal_direct("test.py") == []

    @patch("tapps_mcp.tools.radon._is_radon_importable", return_value=True)
    @patch("tapps_mcp.tools.radon._read_source", return_value=None)
    def test_returns_empty_on_read_failure(self, _mock_read, _mock_avail):
        assert _radon_hal_direct("missing.py") == []
