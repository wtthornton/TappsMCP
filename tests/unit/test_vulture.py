"""Tests for tools.vulture - dead code detection wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tapps_mcp.tools.subprocess_utils import CommandResult
from tapps_mcp.tools.vulture import (
    DeadCodeFinding,
    is_vulture_available,
    parse_vulture_output,
    run_vulture_async,
    _matches_whitelist,
)

# ---------------------------------------------------------------------------
# Sample vulture output
# ---------------------------------------------------------------------------
SAMPLE_VULTURE_OUTPUT = """\
app.py:10: unused function 'helper' (90% confidence)
app.py:25: unused class 'OldManager' (80% confidence)
app.py:42: unused import 'os' (90% confidence)
app.py:55: unused variable 'tmp' (60% confidence)
app.py:70: unused attribute 'legacy_flag' (80% confidence)
"""

UNREACHABLE_CODE_OUTPUT = """\
app.py:100: unused function 'dead_branch' (60% confidence)
"""


# ---------------------------------------------------------------------------
# DeadCodeFinding dataclass
# ---------------------------------------------------------------------------
class TestDeadCodeFinding:
    def test_defaults(self) -> None:
        finding = DeadCodeFinding()
        assert finding.file_path == ""
        assert finding.line == 0
        assert finding.name == ""
        assert finding.finding_type == ""
        assert finding.confidence == 0
        assert finding.message == ""

    def test_all_fields(self) -> None:
        finding = DeadCodeFinding(
            file_path="mod.py",
            line=42,
            name="helper",
            finding_type="function",
            confidence=90,
            message="unused function 'helper' (90% confidence)",
        )
        assert finding.file_path == "mod.py"
        assert finding.line == 42
        assert finding.name == "helper"
        assert finding.finding_type == "function"
        assert finding.confidence == 90
        assert finding.message == "unused function 'helper' (90% confidence)"


# ---------------------------------------------------------------------------
# parse_vulture_output
# ---------------------------------------------------------------------------
class TestParseVultureOutput:
    def test_parse_all_finding_types(self) -> None:
        findings = parse_vulture_output(SAMPLE_VULTURE_OUTPUT)
        assert len(findings) == 5

        assert findings[0].finding_type == "function"
        assert findings[0].name == "helper"
        assert findings[0].line == 10
        assert findings[0].confidence == 90

        assert findings[1].finding_type == "class"
        assert findings[1].name == "OldManager"
        assert findings[1].line == 25
        assert findings[1].confidence == 80

        assert findings[2].finding_type == "import"
        assert findings[2].name == "os"
        assert findings[2].line == 42
        assert findings[2].confidence == 90

        assert findings[3].finding_type == "variable"
        assert findings[3].name == "tmp"
        assert findings[3].line == 55
        assert findings[3].confidence == 60

        assert findings[4].finding_type == "attribute"
        assert findings[4].name == "legacy_flag"
        assert findings[4].line == 70
        assert findings[4].confidence == 80

    def test_empty_string(self) -> None:
        assert parse_vulture_output("") == []

    def test_whitespace_only(self) -> None:
        assert parse_vulture_output("   \n  \n") == []

    def test_non_matching_lines(self) -> None:
        raw = "some random text\nanother line\n"
        assert parse_vulture_output(raw) == []

    def test_confidence_filtering(self) -> None:
        findings = parse_vulture_output(SAMPLE_VULTURE_OUTPUT, min_confidence=80)
        # Should exclude the 60% confidence variable finding
        assert len(findings) == 4
        assert all(f.confidence >= 80 for f in findings)

    def test_confidence_filtering_high(self) -> None:
        findings = parse_vulture_output(SAMPLE_VULTURE_OUTPUT, min_confidence=90)
        assert len(findings) == 2
        assert all(f.confidence >= 90 for f in findings)

    def test_message_generated(self) -> None:
        findings = parse_vulture_output("mod.py:5: unused function 'foo' (95% confidence)\n")
        assert len(findings) == 1
        assert findings[0].message == "unused function 'foo' (95% confidence)"

    def test_finding_type_function(self) -> None:
        raw = "x.py:1: unused function 'fn' (80% confidence)\n"
        findings = parse_vulture_output(raw)
        assert findings[0].finding_type == "function"

    def test_finding_type_class(self) -> None:
        raw = "x.py:1: unused class 'Cls' (80% confidence)\n"
        findings = parse_vulture_output(raw)
        assert findings[0].finding_type == "class"

    def test_finding_type_import(self) -> None:
        raw = "x.py:1: unused import 'os' (90% confidence)\n"
        findings = parse_vulture_output(raw)
        assert findings[0].finding_type == "import"

    def test_finding_type_variable(self) -> None:
        raw = "x.py:1: unused variable 'x' (60% confidence)\n"
        findings = parse_vulture_output(raw)
        assert findings[0].finding_type == "variable"

    def test_finding_type_attribute(self) -> None:
        raw = "x.py:1: unused attribute 'attr' (60% confidence)\n"
        findings = parse_vulture_output(raw)
        assert findings[0].finding_type == "attribute"


# ---------------------------------------------------------------------------
# is_vulture_available
# ---------------------------------------------------------------------------
class TestIsVultureAvailable:
    @patch("tapps_mcp.tools.vulture.shutil.which", return_value="/usr/bin/vulture")
    def test_available(self, _mock_which: object) -> None:
        assert is_vulture_available() is True

    @patch("tapps_mcp.tools.vulture.shutil.which", return_value=None)
    def test_not_available(self, _mock_which: object) -> None:
        assert is_vulture_available() is False


# ---------------------------------------------------------------------------
# run_vulture_async
# ---------------------------------------------------------------------------
class TestRunVultureAsync:
    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=False)
    async def test_not_installed(self, _mock_avail: object) -> None:
        result = await run_vulture_async("test.py")
        assert result == []

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.vulture.run_command_async")
    @patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True)
    async def test_empty_output(self, _mock_avail: object, mock_cmd: object) -> None:
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=0, stdout="", stderr=""
        )
        result = await run_vulture_async("test.py")
        assert result == []

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.vulture.run_command_async")
    @patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True)
    async def test_timeout(self, _mock_avail: object, mock_cmd: object) -> None:
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=-1, stdout="", stderr="Timed out", timed_out=True
        )
        result = await run_vulture_async("test.py")
        assert result == []

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.vulture.run_command_async")
    @patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True)
    async def test_success(self, _mock_avail: object, mock_cmd: object) -> None:
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=1, stdout=SAMPLE_VULTURE_OUTPUT, stderr=""
        )
        result = await run_vulture_async("test.py", min_confidence=60)
        assert len(result) == 5
        assert result[0].name == "helper"
        assert result[0].finding_type == "function"

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.vulture.run_command_async")
    @patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True)
    async def test_min_confidence_filters(self, _mock_avail: object, mock_cmd: object) -> None:
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=1, stdout=SAMPLE_VULTURE_OUTPUT, stderr=""
        )
        # Default min_confidence=80 should filter the 60% finding
        result = await run_vulture_async("test.py")
        assert len(result) == 4
        assert all(f.confidence >= 80 for f in result)

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.vulture.run_command_async")
    @patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True)
    async def test_passes_correct_command(self, _mock_avail: object, mock_cmd: object) -> None:
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=0, stdout="", stderr=""
        )
        await run_vulture_async("myfile.py", min_confidence=70, cwd="/tmp", timeout=15)
        mock_cmd.assert_called_once_with(  # type: ignore[union-attr]
            ["vulture", "myfile.py", "--min-confidence=70"],
            cwd="/tmp",
            timeout=15,
        )


# ---------------------------------------------------------------------------
# _matches_whitelist
# ---------------------------------------------------------------------------
class TestMatchesWhitelist:
    def test_matches_test_star(self) -> None:
        assert _matches_whitelist("tests/test_foo.py", ["test_*"]) is True
        assert _matches_whitelist("test_bar.py", ["test_*"]) is True
        assert _matches_whitelist("src/foo.py", ["test_*"]) is False

    def test_matches_conftest(self) -> None:
        assert _matches_whitelist("conftest.py", ["conftest.py"]) is True
        assert _matches_whitelist("tests/conftest.py", ["conftest.py"]) is True

    def test_empty_patterns(self) -> None:
        assert _matches_whitelist("test.py", []) is False


# ---------------------------------------------------------------------------
# whitelist_patterns filtering
# ---------------------------------------------------------------------------
class TestWhitelistFiltering:
    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.vulture.run_command_async")
    @patch("tapps_mcp.tools.vulture.is_vulture_available", return_value=True)
    async def test_whitelist_filters_test_files(
        self, _mock_avail: object, mock_cmd: object
    ) -> None:
        """Findings from test_*.py files are filtered when whitelist_patterns is set."""
        mock_cmd.return_value = CommandResult(  # type: ignore[union-attr]
            returncode=1,
            stdout="tests/test_foo.py:10: unused function 'helper' (90% confidence)\n"
            "src/main.py:5: unused import 'os' (80% confidence)\n",
            stderr="",
        )
        result = await run_vulture_async(
            "tests/test_foo.py",
            min_confidence=80,
            whitelist_patterns=["test_*", "conftest.py"],
        )
        # test_foo.py finding filtered; main.py kept
        assert len(result) == 1
        assert result[0].file_path == "src/main.py"
        assert result[0].name == "os"
