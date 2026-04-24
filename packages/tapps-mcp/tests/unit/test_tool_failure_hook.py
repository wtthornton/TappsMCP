"""Behavioral tests for the PostToolUseFailure hook (TAP-976).

The static-content checks live in ``test_platform_generators.py`` —
this file shells out to the rendered bash script to prove the noisy
(tapps tool failure) and silent (non-tapps failure) paths actually
behave as documented and that the jsonl log gets a structured entry.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only hook script")
class TestToolFailureHookBehavior:
    """End-to-end: write the script, invoke it with crafted inputs."""

    def _setup(self, tmp_path: Path) -> Path:
        # engagement=high is the only level that includes PostToolUseFailure.
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="high")
        return tmp_path / ".claude" / "hooks" / "tapps-tool-failure.sh"

    def _run(
        self,
        script: Path,
        stdin: str,
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> tuple[int, str]:
        full_env = {**os.environ, **(env or {})}
        proc = subprocess.run(
            ["/usr/bin/env", "bash", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            env=full_env,
            cwd=str(cwd or script.parent.parent.parent),
            timeout=10,
        )
        return proc.returncode, proc.stderr

    def test_high_engagement_writes_script(self, tmp_path: Path) -> None:
        script = self._setup(tmp_path)
        assert script.exists()

    def test_tapps_failure_writes_stderr_and_jsonl(self, tmp_path: Path) -> None:
        script = self._setup(tmp_path)
        rc, stderr = self._run(
            script,
            json.dumps(
                {
                    "tool_name": "mcp__tapps-mcp__tapps_score_file",
                    "error": "boom: connection refused",
                }
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0  # advisory only — never blocks
        assert "mcp__tapps-mcp__tapps_score_file" in stderr
        assert "tapps_doctor" in stderr
        log = tmp_path / ".tapps-mcp" / ".failure-log.jsonl"
        assert log.exists()
        lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["tool"] == "mcp__tapps-mcp__tapps_score_file"
        assert "boom" in entry["error"]
        assert entry["ts"]  # ISO-8601 timestamp present

    def test_non_tapps_failure_is_silent(self, tmp_path: Path) -> None:
        script = self._setup(tmp_path)
        rc, stderr = self._run(
            script,
            json.dumps({"tool_name": "Bash", "error": "rm -rf failed"}),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        assert stderr.strip() == ""
        log = tmp_path / ".tapps-mcp" / ".failure-log.jsonl"
        assert not log.exists()

    def test_underscore_namespace_also_logged(self, tmp_path: Path) -> None:
        """Both mcp__tapps-mcp__ and mcp__tapps_mcp__ are tapps namespaces."""
        script = self._setup(tmp_path)
        rc, stderr = self._run(
            script,
            json.dumps(
                {"tool_name": "mcp__tapps_mcp__tapps_quality_gate", "error": "x"}
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        assert "mcp__tapps_mcp__tapps_quality_gate" in stderr

    def test_repeated_failures_append_to_log(self, tmp_path: Path) -> None:
        script = self._setup(tmp_path)
        for i in range(3):
            self._run(
                script,
                json.dumps(
                    {
                        "tool_name": "mcp__tapps-mcp__tapps_lookup_docs",
                        "error": f"fail {i}",
                    }
                ),
                env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
                cwd=tmp_path,
            )
        log = tmp_path / ".tapps-mcp" / ".failure-log.jsonl"
        lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
        assert len(lines) == 3
        entries = [json.loads(ln) for ln in lines]
        assert [e["error"] for e in entries] == ["fail 0", "fail 1", "fail 2"]


class TestToolFailureEngagementGating:
    """The script ships only at engagement=high — silent at medium/low."""

    def test_high_writes_script(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="high")
        assert (tmp_path / ".claude" / "hooks" / "tapps-tool-failure.sh").exists()

    def test_medium_does_not_write_script(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="medium")
        assert not (
            tmp_path / ".claude" / "hooks" / "tapps-tool-failure.sh"
        ).exists()

    def test_low_does_not_write_script(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="low")
        assert not (
            tmp_path / ".claude" / "hooks" / "tapps-tool-failure.sh"
        ).exists()

    def test_high_settings_includes_matcher(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="high")
        settings = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        entries = settings["hooks"].get("PostToolUseFailure", [])
        assert any(e.get("matcher") == "mcp__tapps-mcp__.*" for e in entries)

    def test_medium_settings_omits_event(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="medium")
        settings = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        assert "PostToolUseFailure" not in settings.get("hooks", {})
