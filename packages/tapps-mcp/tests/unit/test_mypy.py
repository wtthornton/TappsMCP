"""Tests for tools.mypy — parsing and scoring."""

from unittest.mock import patch

from tapps_mcp.scoring.models import TypeIssue
from tapps_mcp.tools.mypy import (
    calculate_type_score,
    parse_mypy_output,
    run_mypy_check,
)
from tapps_mcp.tools.subprocess_utils import CommandResult

SAMPLE_MYPY_OUTPUT = """\
src/test.py:10: error: Incompatible types in assignment [assignment]
src/test.py:20: error: Missing return statement [return]
src/test.py:30: warning: Unused type: ignore comment [unused-ignore]
src/test.py:40: note: Revealed type is "int"
"""


class TestParseMypyOutput:
    def test_basic_parsing(self):
        issues = parse_mypy_output(SAMPLE_MYPY_OUTPUT)
        assert len(issues) == 4

    def test_error_severity(self):
        issues = parse_mypy_output(SAMPLE_MYPY_OUTPUT)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 2
        assert errors[0].line == 10
        assert errors[0].error_code == "assignment"
        assert errors[1].error_code == "return"

    def test_warning_severity(self):
        issues = parse_mypy_output(SAMPLE_MYPY_OUTPUT)
        warnings = [i for i in issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert warnings[0].error_code == "unused-ignore"

    def test_note_severity(self):
        issues = parse_mypy_output(SAMPLE_MYPY_OUTPUT)
        notes = [i for i in issues if i.severity == "note"]
        assert len(notes) == 1

    def test_empty_output(self):
        assert parse_mypy_output("") == []

    def test_whitespace_output(self):
        assert parse_mypy_output("  \n  ") == []

    def test_summary_line_ignored(self):
        raw = "Found 5 errors in 2 files\n"
        assert parse_mypy_output(raw) == []

    def test_filter_by_target_file(self):
        issues = parse_mypy_output(SAMPLE_MYPY_OUTPUT, target_file="src/test.py")
        assert len(issues) == 4

    def test_filter_excludes_other_files(self):
        raw = "other.py:10: error: Bad [assignment]\nsrc/test.py:5: error: Also bad [assignment]\n"
        issues = parse_mypy_output(raw, target_file="src/test.py")
        assert len(issues) == 1
        assert issues[0].file == "src/test.py"

    def test_filter_absolute_target_vs_relative_mypy_output(self):
        """Absolute target path must match mypy's relative filename output (TAP-1742).

        When mypy is invoked with an absolute path it may still emit a relative
        path in its output.  The old substring check silently dropped all findings
        in that case; the fix uses path-resolution + suffix matching.
        """
        raw = "src/foo.py:5: error: Incompatible types [assignment]\n"
        # Caller passes an absolute target; mypy emits only the relative suffix.
        target = "/some/project/root/src/foo.py"
        issues = parse_mypy_output(raw, target_file=target)
        assert len(issues) == 1, (
            "Finding dropped when target is absolute but mypy emits a relative path"
        )
        assert issues[0].line == 5

    def test_filter_absolute_target_drops_unrelated_file(self):
        """Findings for other files must still be excluded (TAP-1742 regression guard)."""
        raw = "other/file.py:10: error: Bad [assignment]\n"
        target = "/some/project/root/src/foo.py"
        issues = parse_mypy_output(raw, target_file=target)
        assert issues == []

    def test_message_without_error_code(self):
        raw = "test.py:1: error: Something wrong\n"
        issues = parse_mypy_output(raw)
        assert len(issues) == 1
        assert issues[0].error_code is None
        assert "Something wrong" in issues[0].message

    def test_malformed_line_skipped(self):
        # Use a truly malformed line (no file:line:level pattern)
        raw2 = "just some text\n"
        assert parse_mypy_output(raw2) == []

    def test_non_numeric_line_number_skipped(self):
        raw = "test.py:abc: error: Something wrong\n"
        issues = parse_mypy_output(raw)
        assert issues == []


class TestCalculateTypeScore:
    def test_no_issues(self):
        assert calculate_type_score([]) == 10.0

    def test_some_errors(self):
        issues = [
            TypeIssue(file="t.py", line=1, message="err", severity="error"),
            TypeIssue(file="t.py", line=2, message="err", severity="error"),
        ]
        # Each error costs 0.5
        assert calculate_type_score(issues) == 9.0

    def test_warnings_not_penalised(self):
        issues = [
            TypeIssue(file="t.py", line=1, message="warn", severity="warning"),
        ]
        assert calculate_type_score(issues) == 10.0

    def test_many_errors_clamp_to_zero(self):
        issues = [
            TypeIssue(file="t.py", line=i, message="err", severity="error") for i in range(30)
        ]
        assert calculate_type_score(issues) == 0.0

    def test_mixed_severities(self):
        issues = [
            TypeIssue(file="t.py", line=1, message="err", severity="error"),
            TypeIssue(file="t.py", line=2, message="note", severity="note"),
            TypeIssue(file="t.py", line=3, message="warn", severity="warning"),
        ]
        # Only 1 error at 0.5 penalty
        assert calculate_type_score(issues) == 9.5


class TestRunMypyCheck:
    @patch("tapps_mcp.tools.mypy.run_command")
    def test_success(self, mock_cmd):
        mock_cmd.return_value = CommandResult(
            returncode=1,
            stdout=SAMPLE_MYPY_OUTPUT,
            stderr="",
        )
        issues = run_mypy_check("src/test.py")
        assert len(issues) == 4

    @patch("tapps_mcp.tools.mypy.run_command")
    def test_timeout(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=-1, stdout="", stderr="", timed_out=True)
        issues = run_mypy_check("test.py")
        assert issues is None
        mock_cmd.return_value = CommandResult(
            returncode=0, stdout="Success: no issues found\n", stderr=""
        )
        issues = run_mypy_check("test.py")
        assert issues == []
