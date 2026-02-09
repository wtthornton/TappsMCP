"""Tests for tools.radon — parsing and scoring."""

import json
from unittest.mock import patch

from tapps_mcp.tools.radon import (
    calculate_complexity_score,
    calculate_maintainability_score,
    parse_radon_cc_json,
    parse_radon_mi_json,
    run_radon_cc,
    run_radon_mi,
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

    def test_uses_max_complexity(self):
        entries = [{"complexity": 2}, {"complexity": 8}]
        score = calculate_complexity_score(entries)
        # max=8, 8/5.0 = 1.6
        assert abs(score - 1.6) < 0.01

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
