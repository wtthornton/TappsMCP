"""Tests for the semgrep deterministic-offline security checker (TAP-4529).

Covers: JSON parsing, graceful skip when the binary is absent, cross-checker
dedupe with bandit (no double-count), and an integration path that adapts to
whether the semgrep binary is actually installed in the environment.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.scoring.dependency_security import merge_security_findings
from tapps_mcp.scoring.models import SecurityIssue
from tapps_mcp.tools.parallel import run_all_tools
from tapps_mcp.tools.semgrep import (
    SEMGREP_RULESET,
    _semgrep_env,
    parse_semgrep_json,
    run_semgrep_check,
    semgrep_available,
)
from tapps_mcp.tools.subprocess_utils import CommandResult

# A semgrep --json result flagging subprocess shell=True (the same class of bug
# bandit reports as B602), plus an eval finding, so we can prove provenance and
# dedupe behaviour.
SAMPLE_SEMGREP_JSON = json.dumps(
    {
        "results": [
            {
                "check_id": "tapps.python.dangerous-subprocess-shell-true",
                "path": "app.py",
                "start": {"line": 20},
                "extra": {
                    "message": "subprocess call with shell=True",
                    "severity": "ERROR",
                    "metadata": {"owasp": "A03:2021-Injection"},
                },
            },
            {
                "check_id": "tapps.python.dangerous-eval-exec",
                "path": "app.py",
                "start": {"line": 42},
                "extra": {
                    "message": "eval on dynamic input",
                    "severity": "ERROR",
                    "metadata": {"owasp": ["A03:2021-Injection"]},
                },
            },
        ]
    }
)


class TestRuleset:
    def test_ruleset_bundled_in_repo(self):
        # AC2: the pinned ruleset must ship as a file in the package.
        assert SEMGREP_RULESET.is_file()
        assert SEMGREP_RULESET.suffix in {".yml", ".yaml"}

    def test_ruleset_has_no_remote_config(self):
        # No network fetch: reject registry packs / auto config sneaking in.
        # Inspect non-comment lines only (comments legitimately mention `p/`).
        code_lines = [
            ln
            for ln in SEMGREP_RULESET.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "config: auto" not in code
        assert "registry" not in code
        # No `extends:` pulling a remote pack.
        assert "extends" not in code


class TestSemgrepEnv:
    def test_disables_network(self):
        # Belt-and-suspenders: version check + metrics off so nothing egresses.
        env = _semgrep_env()
        assert env["SEMGREP_ENABLE_VERSION_CHECK"] == "0"
        assert env["SEMGREP_SEND_METRICS"] == "off"
        assert env["SEMGREP_METRICS"] == "off"


class TestParseSemgrepJson:
    def test_valid_output(self):
        issues = parse_semgrep_json(SAMPLE_SEMGREP_JSON)
        assert issues is not None
        assert len(issues) == 2
        assert issues[0].code == "tapps.python.dangerous-subprocess-shell-true"
        assert issues[0].line == 20
        assert issues[0].severity == "high"  # ERROR -> high
        assert issues[0].source == "semgrep"
        assert issues[0].owasp == "A03:2021-Injection"
        # owasp given as a list should still resolve to a string
        assert issues[1].owasp == "A03:2021-Injection"

    def test_empty_string_is_skip(self):
        assert parse_semgrep_json("") is None

    def test_invalid_json_is_skip(self):
        assert parse_semgrep_json("not json") is None

    def test_empty_results(self):
        assert parse_semgrep_json('{"results": []}') == []


class TestGracefulSkip:
    def test_returns_none_when_binary_absent(self):
        # AC3: absence degrades gracefully — None, never a crash.
        with patch("tapps_mcp.tools.semgrep.semgrep_available", return_value=False):
            assert run_semgrep_check("whatever.py") is None

    @patch("tapps_mcp.tools.semgrep.run_command")
    @patch("tapps_mcp.tools.semgrep.semgrep_available", return_value=True)
    def test_returns_none_on_not_found_sentinel(self, _avail, mock_cmd):
        # run_command returns returncode=-1 on FileNotFoundError/timeout.
        mock_cmd.return_value = CommandResult(returncode=-1, stdout="", stderr="not found")
        assert run_semgrep_check("whatever.py") is None

    @patch("tapps_mcp.tools.semgrep.run_command")
    @patch("tapps_mcp.tools.semgrep.semgrep_available", return_value=True)
    def test_parses_findings_when_available(self, _avail, mock_cmd):
        mock_cmd.return_value = CommandResult(returncode=1, stdout=SAMPLE_SEMGREP_JSON, stderr="")
        issues = run_semgrep_check("app.py")
        assert issues is not None
        assert len(issues) == 2
        assert all(i.source == "semgrep" for i in issues)


class TestMergeDedupe:
    def _bandit_shell(self) -> SecurityIssue:
        return SecurityIssue(
            code="B602",
            message="subprocess with shell=True",
            file="app.py",
            line=20,
            severity="high",
            source="bandit",
        )

    def _semgrep_shell(self, line: int = 20) -> SecurityIssue:
        return SecurityIssue(
            code="tapps.python.dangerous-subprocess-shell-true",
            message="subprocess call with shell=True",
            file="app.py",
            line=line,
            severity="high",
            source="semgrep",
        )

    def test_overlap_deduped_bandit_wins(self):
        # AC4: same taint at the same location must NOT be double-counted.
        merged = merge_security_findings([self._bandit_shell()], [self._semgrep_shell()])
        assert len(merged) == 1
        assert merged[0].source == "bandit"
        assert merged[0].code == "B602"

    def test_distinct_locations_both_survive(self):
        merged = merge_security_findings(
            [self._bandit_shell()], [self._semgrep_shell(line=99)]
        )
        assert len(merged) == 2
        sources = sorted(i.source for i in merged)
        assert sources == ["bandit", "semgrep"]

    def test_semgrep_only_finding_survives(self):
        semgrep_eval = SecurityIssue(
            code="tapps.python.dangerous-eval-exec",
            message="eval",
            file="app.py",
            line=42,
            severity="high",
            source="semgrep",
        )
        merged = merge_security_findings([], [semgrep_eval])
        assert len(merged) == 1
        assert merged[0].source == "semgrep"

    def test_deterministic_ordering(self):
        bandit = [self._bandit_shell()]
        semgrep = [self._semgrep_shell(line=99), self._semgrep_shell(line=100)]
        first = merge_security_findings(bandit, semgrep)
        second = merge_security_findings(bandit, semgrep)
        assert [i.code for i in first] == [i.code for i in second]
        # bandit findings come first, deterministically.
        assert first[0].source == "bandit"


@pytest.mark.asyncio
async def test_taint_pattern_reported_and_not_double_counted(tmp_path: Path):
    """End-to-end: a known taint pattern is reported and not double-counted.

    When the semgrep binary is installed, run the real pinned ruleset against a
    shell=True fixture and assert (a) semgrep reports it and (b) it is not
    double-counted with bandit in the merged security_issues. When the binary
    is absent, assert the graceful-skip path instead (semgrep in skipped_tools),
    proving AC3.
    """
    fixture = tmp_path / "taint.py"
    fixture.write_text(
        "import subprocess\n"
        "def run(cmd):\n"
        "    return subprocess.run(cmd, shell=True)\n",
        encoding="utf-8",
    )

    # Only run bandit + semgrep to keep the test fast and focused.
    results = await run_all_tools(
        str(fixture),
        cwd=str(tmp_path),
        timeout=60,
        run_ruff=False,
        run_mypy=False,
        run_bandit=True,
        run_radon=False,
        run_vulture=False,
        run_perflint=False,
        run_semgrep=True,
        mode="subprocess",
    )

    if not semgrep_available():
        # AC3 graceful-skip path — no crash, semgrep noted as skipped.
        assert "semgrep" in results.skipped_tools
        assert results.semgrep_issues == []
        return

    # Binary present: semgrep must report the shell=True taint.
    assert any(
        "dangerous-subprocess-shell-true" in i.code for i in results.semgrep_issues
    ), "semgrep should flag subprocess shell=True against the pinned ruleset"

    # AC4: the shell-injection class must appear exactly once in the merged
    # security_issues (bandit B602 + semgrep collapse to one at the same line).
    shell_findings = [
        i
        for i in results.security_issues
        if i.code in {"B602", "B603", "B604"}
        or "dangerous-subprocess-shell-true" in i.code
    ]
    # Group by (file, line) — no location should carry two shell findings.
    by_loc: dict[tuple[str, int], int] = {}
    for f in shell_findings:
        by_loc[(f.file, f.line)] = by_loc.get((f.file, f.line), 0) + 1
    assert all(count == 1 for count in by_loc.values()), (
        f"shell-injection double-counted across bandit+semgrep: {by_loc}"
    )


def test_semgrep_available_requires_binary_and_ruleset():
    # Sanity: availability gate needs both the binary and the pinned ruleset.
    with patch("tapps_mcp.tools.semgrep.shutil.which", return_value=None):
        assert semgrep_available() is False
    if shutil.which("semgrep"):
        assert semgrep_available() is True


def test_async_and_sync_wrappers_consistent():
    # Both wrappers short-circuit to None when the binary is absent.
    with patch("tapps_mcp.tools.semgrep.semgrep_available", return_value=False):
        from tapps_mcp.tools.semgrep import run_semgrep_check_async

        assert run_semgrep_check("x.py") is None
        assert asyncio.run(run_semgrep_check_async("x.py")) is None
