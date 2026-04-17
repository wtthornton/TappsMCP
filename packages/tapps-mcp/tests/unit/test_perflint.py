"""Tests for tools.perflint — parsing, scoring, and graceful degradation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.tools.perflint import (
    PERFLINT_CODES,
    PerflintFinding,
    parse_perflint_json,
    run_perflint_check,
    run_perflint_check_async,
)
from tapps_mcp.tools.subprocess_utils import CommandResult

SAMPLE_PERFLINT_JSON = json.dumps(
    [
        {
            "type": "warning",
            "module": "test_mod",
            "obj": "",
            "line": 4,
            "column": 12,
            "endLine": 4,
            "endColumn": 16,
            "path": "/tmp/test.py",
            "symbol": "loop-global-usage",
            "message": "Lookups of global names within a loop is inefficient.",
            "message-id": "W8202",
        },
        {
            "type": "warning",
            "module": "test_mod",
            "obj": "",
            "line": 8,
            "column": 4,
            "endLine": 8,
            "endColumn": 10,
            "path": "/tmp/test.py",
            "symbol": "use-list-comprehension",
            "message": "Use a list comprehension instead of a for-loop",
            "message-id": "W8401",
        },
    ]
)

# Mixed output: includes a non-perflint pylint message that should be filtered
SAMPLE_MIXED_JSON = json.dumps(
    [
        {
            "type": "warning",
            "line": 1,
            "column": 0,
            "path": "Command line",
            "symbol": "unknown-option-value",
            "message": "Unknown option value",
            "message-id": "W0012",
        },
        {
            "type": "warning",
            "line": 4,
            "column": 12,
            "path": "/tmp/test.py",
            "symbol": "unnecessary-list-cast",
            "message": "Unnecessary using of list()",
            "message-id": "W8101",
        },
    ]
)


class TestPerflintCodes:
    def test_all_codes_start_with_w8(self):
        for code in PERFLINT_CODES:
            assert code.startswith("W8"), f"{code} does not start with W8"

    def test_code_count(self):
        assert len(PERFLINT_CODES) == 10


class TestPerflintFinding:
    def test_label_auto_assigned(self):
        finding = PerflintFinding(code="W8202", symbol="loop-global-usage")
        assert finding.label == "perflint_loop_global_usage"

    def test_label_for_comprehension_codes(self):
        for code in ("W8401", "W8402", "W8403"):
            finding = PerflintFinding(code=code, symbol="use-list-comprehension")
            assert finding.label == "perflint_use_comprehension"

    def test_unknown_code_uses_symbol(self):
        finding = PerflintFinding(code="W8999", symbol="future-check")
        assert finding.label == "perflint_future-check"

    def test_explicit_label_preserved(self):
        finding = PerflintFinding(code="W8101", symbol="x", label="custom_label")
        assert finding.label == "custom_label"


class TestParsePerflintJson:
    def test_valid_output(self):
        findings = parse_perflint_json(SAMPLE_PERFLINT_JSON)
        assert len(findings) == 2
        assert findings[0].code == "W8202"
        assert findings[0].symbol == "loop-global-usage"
        assert findings[0].line == 4
        assert findings[1].code == "W8401"

    def test_filters_non_w8_codes(self):
        findings = parse_perflint_json(SAMPLE_MIXED_JSON)
        assert len(findings) == 1
        assert findings[0].code == "W8101"

    def test_empty_string(self):
        assert parse_perflint_json("") == []

    def test_whitespace(self):
        assert parse_perflint_json("   ") == []

    def test_invalid_json(self):
        assert parse_perflint_json("not json") == []

    def test_non_list_json(self):
        assert parse_perflint_json('{"key": "value"}') == []

    def test_empty_list(self):
        assert parse_perflint_json("[]") == []

    def test_non_dict_entries_skipped(self):
        raw = json.dumps(["not a dict", 42])
        assert parse_perflint_json(raw) == []


class TestRunPerflintCheck:
    @patch("tapps_mcp.tools.perflint.run_command")
    def test_success(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=4, stdout=SAMPLE_PERFLINT_JSON, stderr="")
        findings = run_perflint_check("test.py")
        assert len(findings) == 2

    @patch("tapps_mcp.tools.perflint.run_command")
    def test_no_issues(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="[]", stderr="")
        findings = run_perflint_check("test.py")
        assert findings == []

    @patch("tapps_mcp.tools.perflint.run_command")
    def test_timeout_returns_empty(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=-1, stdout="", stderr="", timed_out=True)
        findings = run_perflint_check("test.py")
        assert findings == []


class TestRunPerflintCheckAsync:
    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.perflint.run_command_async", new_callable=AsyncMock)
    async def test_success(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=4, stdout=SAMPLE_PERFLINT_JSON, stderr="")
        findings = await run_perflint_check_async("test.py")
        assert len(findings) == 2

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.perflint.run_command_async", new_callable=AsyncMock)
    async def test_empty_output(self, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=0, stdout="", stderr="")
        findings = await run_perflint_check_async("test.py")
        assert findings == []
