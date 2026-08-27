"""TAP-6598 VAL-12: PostToolUse write-lint for managed skill BEGIN/END blocks.

A PostToolUse/Edit hook surface already exists (``tapps-post-edit.sh`` and its
Cursor bash/PowerShell counterparts) — this ships the write-lint per binding
ruling 6 rather than filing a follow-up. The guard is advisory (warn), not a
refusal, matching every other check in these hooks.

Executing the shared parser is deliberate, not incidental: string-presence
checks alone would not have caught the pre-existing ``js_import`` regex bug
(escaped quotes surviving the outer non-raw triple-quoted string as bare
``"``, which terminated the embedded heredoc's ``r"..."`` early and made the
whole parser a ``SyntaxError`` at hook-execution time for every file type).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.agent_contract import MANAGED_SKILL_BLOCK_EDIT_WARNING_BASH
from tapps_mcp.pipeline.platform_hook_templates import (
    _CURSOR_AFTER_EDIT_IMPORT_PARSE_PY,
    CLAUDE_HOOK_SCRIPTS,
    CURSOR_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_skills import generate_skills

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32",
    reason="bash/python subprocess execution required",
)


def _write_skill(tmp_path: Path) -> Path:
    """Generate a real orchestration-prompt SKILL.md into *tmp_path*."""
    generate_skills(tmp_path, "claude")
    return tmp_path / ".claude" / "skills" / "orchestration-prompt" / "SKILL.md"


def _run_parser(tmp_path: Path, hook_input: dict) -> list[str]:
    parser = tmp_path / "parse_only.py"
    parser.write_text(_CURSOR_AFTER_EDIT_IMPORT_PARSE_PY, encoding="utf-8")
    env = dict(os.environ, TAPPS_HOOK_INPUT=json.dumps(hook_input))
    proc = subprocess.run(
        [sys.executable, str(parser)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=10,
    )
    assert proc.returncode == 0, f"parser crashed: {proc.stderr}"
    return proc.stdout.splitlines()


class TestSharedParserSyntax:
    """Regression: the embedded heredoc python must itself be valid Python.

    ``bash -n`` (test_hook_script_syntax.py) cannot see this — a heredoc body
    is opaque text to bash's parser. This is the check that would have caught
    the pre-existing js_import SyntaxError.
    """

    def test_parser_compiles(self) -> None:
        compile(_CURSOR_AFTER_EDIT_IMPORT_PARSE_PY, "<parser>", "exec")

    def test_parser_runs_on_empty_input(self, tmp_path: Path) -> None:
        lines = _run_parser(tmp_path, {})
        assert lines == ["", "", "0", ""]

    def test_parser_detects_ts_import(self, tmp_path: Path) -> None:
        """Regression for the fixed js_import quote-escaping bug."""
        lines = _run_parser(
            tmp_path,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "src/sample.ts",
                    "new_string": "import { foo } from 'bar';\n",
                },
            },
        )
        assert lines[1] == "bar"


class TestPowerShellRenderSyntax:
    """TAP-6598 round 2: PowerShell parse-time interpolation regression guard.

    ``$var:`` inside a double-quoted PowerShell string is parsed as a
    scope/drive-qualified variable reference. When the name before the colon
    is empty (e.g. ``"$file: ..."`` after Python-side interpolation),
    PowerShell raises a *parse* error and the ENTIRE script fails to load —
    not just that line. ``$env:`` is the only legitimate drive-qualifier
    used in these templates (``$env:TEMP``, ``$env:CLAUDE_PROJECT_DIR``).

    ``bash -n`` / ``test_hook_script_syntax.py`` cannot catch this — it only
    covers the ``.sh`` outputs. This is the PowerShell analogue of
    ``TestSharedParserSyntax.test_parser_compiles`` above.
    """

    _INTERPOLATION_PATTERN = re.compile(r'"\$([A-Za-z_][A-Za-z0-9_]*):')
    _VALID_DRIVE_QUALIFIERS = {"env"}

    def _all_rendered_ps1_scripts(self) -> dict[str, str]:
        from tapps_mcp.pipeline import platform_hook_templates as templates

        scripts: dict[str, str] = {}
        for dict_name in (
            "CLAUDE_HOOK_SCRIPTS_PS",
            "CURSOR_HOOK_SCRIPTS_PS",
            "LINEAR_GATE_SCRIPTS_PS",
            "LINEAR_CACHE_GATE_SCRIPTS_PS",
            "SESSION_START_GATE_SCRIPTS_PS",
            "CLAUDE_REACTIVE_HOOK_SCRIPTS_PS",
            "CLAUDE_HOOK_SCRIPTS_BLOCKING_PS",
        ):
            scripts.update(getattr(templates, dict_name))
        return scripts

    def test_no_empty_name_variable_interpolation(self) -> None:
        offenders: list[str] = []
        for script_name, src in self._all_rendered_ps1_scripts().items():
            for match in self._INTERPOLATION_PATTERN.finditer(src):
                if match.group(1) in self._VALID_DRIVE_QUALIFIERS:
                    continue
                line_no = src.count("\n", 0, match.start()) + 1
                offenders.append(f"{script_name}:{line_no}: {match.group(0)}")
        assert not offenders, (
            "PowerShell parse-time bug: '\"$var:' is parsed as a "
            "scope/drive-qualified variable reference; PowerShell rejects it "
            "at parse time when the name is not a known drive. Use "
            "'\"${var}:' instead. Offenders: " + ", ".join(offenders)
        )

    @pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")
    def test_after_edit_ps1_parses_under_pwsh(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import CURSOR_HOOK_SCRIPTS_PS

        target = tmp_path / "tapps-after-edit.ps1"
        target.write_text(CURSOR_HOOK_SCRIPTS_PS["tapps-after-edit.ps1"], encoding="utf-8")
        wrapper = tmp_path / "parse_only.ps1"
        wrapper.write_text(
            "param($Path)\n"
            "[ScriptBlock]::Create((Get-Content -Raw -LiteralPath $Path)) | Out-Null\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(wrapper), "-Path", str(target)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 0, proc.stderr


class TestManagedSkillBlockGuard:
    def test_edit_inside_block_flags_guard(self, tmp_path: Path) -> None:
        skill_path = _write_skill(tmp_path)
        content = skill_path.read_text(encoding="utf-8")
        marker = "# orchestration-prompt"
        assert marker in content
        lines = _run_parser(
            tmp_path,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(skill_path.relative_to(tmp_path)),
                    "old_string": marker,
                    "new_string": marker,
                },
            },
        )
        assert lines[3] == "1"

    def test_edit_below_end_marker_does_not_flag(self, tmp_path: Path) -> None:
        skill_path = _write_skill(tmp_path)
        skill_path.write_text(
            skill_path.read_text(encoding="utf-8") + "\n## Project notes\nplaceholder line\n",
            encoding="utf-8",
        )
        lines = _run_parser(
            tmp_path,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(skill_path.relative_to(tmp_path)),
                    "old_string": "placeholder line",
                    "new_string": "my project customization",
                },
            },
        )
        assert lines[3] == ""

    def test_write_tool_always_flags(self, tmp_path: Path) -> None:
        skill_path = _write_skill(tmp_path)
        lines = _run_parser(
            tmp_path,
            {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(skill_path.relative_to(tmp_path)),
                    "content": skill_path.read_text(encoding="utf-8"),
                },
            },
        )
        assert lines[3] == "1"

    def test_edit_on_non_skill_file_does_not_flag(self, tmp_path: Path) -> None:
        target = tmp_path / "README.md"
        target.write_text("# hello\n", encoding="utf-8")
        lines = _run_parser(
            tmp_path,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "README.md",
                    "old_string": "hello",
                    "new_string": "hello world",
                },
            },
        )
        assert lines[3] == ""


class TestPostEditHookEmitsWarning:
    """End-to-end: the shipped hook script itself warns on stderr."""

    def _run_hook(
        self, tmp_path: Path, script: str, hook_input: dict
    ) -> subprocess.CompletedProcess:
        rendered = tmp_path / "post-edit.sh"
        rendered.write_text(script, encoding="utf-8")
        env = dict(os.environ, TAPPS_MCP_PROJECT_ROOT=str(tmp_path))
        return subprocess.run(
            ["bash", str(rendered)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
            timeout=10,
        )

    def test_claude_bash_warns_on_inside_block_edit(self, tmp_path: Path) -> None:
        skill_path = _write_skill(tmp_path)
        marker = "# orchestration-prompt"
        proc = self._run_hook(
            tmp_path,
            CLAUDE_HOOK_SCRIPTS["tapps-post-edit.sh"],
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(skill_path.relative_to(tmp_path)),
                    "old_string": marker,
                    "new_string": marker,
                },
            },
        )
        assert proc.returncode == 0
        assert "BEGIN/END managed block" in proc.stderr
        assert "below the END marker" in proc.stderr

    def test_claude_bash_silent_below_end_marker(self, tmp_path: Path) -> None:
        skill_path = _write_skill(tmp_path)
        skill_path.write_text(
            skill_path.read_text(encoding="utf-8") + "\n## Project notes\nplaceholder line\n",
            encoding="utf-8",
        )
        proc = self._run_hook(
            tmp_path,
            CLAUDE_HOOK_SCRIPTS["tapps-post-edit.sh"],
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(skill_path.relative_to(tmp_path)),
                    "old_string": "placeholder line",
                    "new_string": "my project customization",
                },
            },
        )
        assert proc.returncode == 0
        assert "BEGIN/END managed block" not in proc.stderr

    def test_cursor_bash_warns_on_inside_block_edit(self, tmp_path: Path) -> None:
        skill_path = _write_skill(tmp_path)
        marker = "# orchestration-prompt"
        proc = self._run_hook(
            tmp_path,
            CURSOR_HOOK_SCRIPTS["tapps-after-edit.sh"],
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(skill_path.relative_to(tmp_path)),
                    "old_string": marker,
                    "new_string": marker,
                },
            },
        )
        assert proc.returncode == 0
        assert "BEGIN/END managed block" in proc.stderr


class TestWarningMessageContent:
    def test_names_the_correct_location(self) -> None:
        assert "below the END marker" in MANAGED_SKILL_BLOCK_EDIT_WARNING_BASH

    def test_states_the_edit_is_lost(self) -> None:
        assert "lost" in MANAGED_SKILL_BLOCK_EDIT_WARNING_BASH
