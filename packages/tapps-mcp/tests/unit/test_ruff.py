"""Tests for tools.ruff — parsing and scoring."""

from unittest.mock import patch

from tapps_mcp.scoring.models import LintIssue
from tapps_mcp.tools.ruff import (
    calculate_lint_score,
    parse_ruff_json,
    run_ruff_check,
)
from tapps_mcp.tools.subprocess_utils import CommandResult

# -----------------------------------------------------------------------
# Sample ruff JSON output
# -----------------------------------------------------------------------

SAMPLE_RUFF_JSON = """[
  {
    "code": "E501",
    "message": "Line too long (120 > 100)",
    "filename": "test.py",
    "location": {"row": 10, "column": 101},
    "end_location": {"row": 10, "column": 120}
  },
  {
    "code": "F401",
    "message": "Unused import",
    "filename": "test.py",
    "location": {"row": 1, "column": 1}
  }
]"""

SAMPLE_RUFF_DICT_CODE = """[
  {
    "code": {"name": "E501", "code": "E501"},
    "message": "Line too long",
    "filename": "test.py",
    "location": {"row": 5, "column": 1}
  }
]"""


class TestParseRuffJson:
    def test_valid_output(self):
        issues = parse_ruff_json(SAMPLE_RUFF_JSON)
        assert len(issues) == 2
        assert issues[0].code == "E501"
        assert issues[0].line == 10
        assert issues[0].column == 101
        assert issues[0].severity == "error"
        assert issues[1].code == "F401"
        assert issues[1].severity == "error"

    def test_empty_string(self):
        assert parse_ruff_json("") == []

    def test_whitespace_only(self):
        assert parse_ruff_json("   \n  ") == []

    def test_invalid_json(self):
        assert parse_ruff_json("not json at all") == []

    def test_empty_array(self):
        assert parse_ruff_json("[]") == []

    def test_dict_code_object(self):
        issues = parse_ruff_json(SAMPLE_RUFF_DICT_CODE)
        assert len(issues) == 1
        assert issues[0].code == "E501"

    def test_null_code_fallback(self):
        raw = '[{"code": null, "message": "test", "filename": "f.py", "location": {"row": 1}}]'
        issues = parse_ruff_json(raw)
        assert len(issues) == 1
        assert issues[0].code == "unknown"

    def test_warning_severity_for_non_e_f(self):
        raw = (
            '[{"code": "W291", "message": "Trailing ws", "filename": "f.py", '
            '"location": {"row": 1}}]'
        )
        issues = parse_ruff_json(raw)
        assert issues[0].severity == "warning"

    def test_missing_location(self):
        raw = '[{"code": "E501", "message": "test", "filename": "f.py"}]'
        issues = parse_ruff_json(raw)
        assert issues[0].line == 0
        assert issues[0].column == 0


class TestCalculateLintScore:
    def test_no_issues(self):
        assert calculate_lint_score([]) == 10.0

    def test_fatal_issues(self):
        issues = [
            LintIssue(code="F401", message="Unused import", file="t.py", line=1),
            LintIssue(code="F811", message="Redefined", file="t.py", line=2),
        ]
        score = calculate_lint_score(issues)
        assert score == 10.0 - 3.0 - 3.0  # 4.0

    def test_error_issues(self):
        issues = [
            LintIssue(code="E501", message="Line too long", file="t.py", line=1),
        ]
        score = calculate_lint_score(issues)
        assert score == 10.0 - 2.0  # 8.0

    def test_warning_issues(self):
        issues = [
            LintIssue(code="W291", message="Trailing ws", file="t.py", line=1),
        ]
        score = calculate_lint_score(issues)
        assert score == 10.0 - 0.5  # 9.5

    def test_mixed_issues(self):
        issues = [
            LintIssue(code="F401", message="Unused", file="t.py", line=1),
            LintIssue(code="E501", message="Long", file="t.py", line=2),
            LintIssue(code="W291", message="Ws", file="t.py", line=3),
        ]
        score = calculate_lint_score(issues)
        expected = 10.0 - 3.0 - 2.0 - 0.5  # 4.5
        assert abs(score - expected) < 0.01

    def test_clamps_to_zero(self):
        issues = [LintIssue(code="F401", message="u", file="t.py", line=i) for i in range(10)]
        score = calculate_lint_score(issues)
        assert score == 0.0


class TestRunRuffCheck:
    @patch("tapps_mcp.tools.ruff.run_command")
    def test_success(self, mock_cmd):
        mock_cmd.return_value = CommandResult(
            returncode=1,
            stdout=SAMPLE_RUFF_JSON,
            stderr="",
        )
        issues = run_ruff_check("test.py")
        assert len(issues) == 2
        mock_cmd.assert_called_once()

    @patch("tapps_mcp.tools.ruff.run_command")
    def test_no_output(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=1, stdout="", stderr="error")
        issues = run_ruff_check("test.py")
        assert issues == []

    @patch("tapps_mcp.tools.ruff.run_command")
    def test_clean_file(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="[]", stderr="")
        issues = run_ruff_check("test.py")
        assert issues == []
