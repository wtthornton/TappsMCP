"""End-to-end integration tests for the Linear routing gate (TAP-981).

Exercises the full bootstrap → hook generation → script execution chain to
prove a fresh ``tapps_init --engagement high`` produces a project where the
gate fires correctly: blocks raw save_issue without a sentinel, allows after
docs_validate_linear_issue, allows update-only flows, respects bypass.

Skipped on Windows since the bash variants are exercised here; the PowerShell
behavior is covered by the unit-level static checks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="bash gate scripts only"),
]


def _bootstrap_high_engagement_project(root: Path) -> dict[str, object]:
    from tapps_mcp.pipeline.init import BootstrapConfig, bootstrap_pipeline

    cfg = BootstrapConfig(
        platform="claude",
        verify_server=False,
        llm_engagement_level="high",
        # Explicitly pass True — mirrors what the tapps_init server entry
        # would resolve via linear_enforce_gate_resolved() at high engagement.
        linear_enforce_gate=True,
        # minimal must be False so platform generators (incl. hooks) run.
        minimal=False,
        create_handoff=False,
        create_runlog=False,
        create_agents_md=False,
        create_tech_stack_md=False,
        include_karpathy=False,
    )
    return bootstrap_pipeline(root, config=cfg)


def _run_hook(script: Path, stdin: str, project_root: Path) -> tuple[int, str]:
    full_env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_root)}
    proc = subprocess.run(
        ["/usr/bin/env", "bash", str(script)],
        input=stdin,
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(project_root),
        timeout=10,
    )
    return proc.returncode, proc.stderr


class TestFreshInitProducesWorkingGate:
    """A fresh tapps_init at engagement=high lands a gate that blocks the
    raw save_issue path and allows the validated path."""

    def test_hook_files_land_on_disk(self, tmp_path: Path) -> None:
        _bootstrap_high_engagement_project(tmp_path)
        assert (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh").exists()
        assert (tmp_path / ".claude" / "hooks" / "tapps-post-docs-validate.sh").exists()

    def test_settings_json_wires_matchers(self, tmp_path: Path) -> None:
        _bootstrap_high_engagement_project(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        pre_matchers = [e.get("matcher") for e in settings["hooks"].get("PreToolUse", [])]
        post_matchers = [e.get("matcher") for e in settings["hooks"].get("PostToolUse", [])]
        assert "mcp__plugin_linear_linear__save_issue" in pre_matchers
        assert "mcp__docs-mcp__docs_validate_linear_issue" in post_matchers

    def test_raw_save_issue_blocked(self, tmp_path: Path) -> None:
        _bootstrap_high_engagement_project(tmp_path)
        rc, stderr = _run_hook(
            tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh",
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {
                        "title": "raw create without validate",
                        "description": "body",
                        "team": "TAP",
                    },
                }
            ),
            tmp_path,
        )
        assert rc == 2
        assert "linear-issue" in stderr

    def test_validated_save_issue_allowed(self, tmp_path: Path) -> None:
        _bootstrap_high_engagement_project(tmp_path)
        # 1. PostToolUse on docs_validate_linear_issue writes the sentinel.
        # TAP-1328: hook now requires tool_response.data.agent_ready==true
        # before writing — pre-1328 callers would silently fail to gate.
        rc, _ = _run_hook(
            tmp_path / ".claude" / "hooks" / "tapps-post-docs-validate.sh",
            json.dumps(
                {
                    "tool_name": "mcp__docs-mcp__docs_validate_linear_issue",
                    "tool_response": {"data": {"agent_ready": True}},
                }
            ),
            tmp_path,
        )
        assert rc == 0
        sentinel = tmp_path / ".tapps-mcp" / ".linear-validate-sentinel"
        assert sentinel.exists()

        # 2. PreToolUse on save_issue now allows.
        rc, _ = _run_hook(
            tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh",
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {
                        "title": "validated create",
                        "description": "body",
                    },
                }
            ),
            tmp_path,
        )
        assert rc == 0

    def test_update_only_status_change_allowed_without_sentinel(self, tmp_path: Path) -> None:
        """FP-reduction allow-list: status updates skip validation (TAP-981)."""
        _bootstrap_high_engagement_project(tmp_path)
        rc, _ = _run_hook(
            tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh",
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {"id": "TAP-123", "state": "Done"},
                }
            ),
            tmp_path,
        )
        assert rc == 0

    def test_bypass_env_allows_and_logs(self, tmp_path: Path) -> None:
        _bootstrap_high_engagement_project(tmp_path)
        full_env = {
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "TAPPS_LINEAR_SKIP_VALIDATE": "1",
        }
        proc = subprocess.run(
            [
                "/usr/bin/env",
                "bash",
                str(tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh"),
            ],
            input=json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {"title": "emergency", "description": "x"},
                }
            ),
            capture_output=True,
            text=True,
            env=full_env,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert proc.returncode == 0
        bypass_log = tmp_path / ".tapps-mcp" / ".bypass-log.jsonl"
        assert bypass_log.exists()
        entry = json.loads(bypass_log.read_text().strip())
        assert entry["bypass"] == "TAPPS_LINEAR_SKIP_VALIDATE"


class TestStaleSentinelStillBlocks:
    """Sentinel older than 1800s must block — proves the freshness window
    survives the full bootstrap → script chain end-to-end."""

    def test_sentinel_older_than_30min_blocks(self, tmp_path: Path) -> None:
        _bootstrap_high_engagement_project(tmp_path)
        (tmp_path / ".tapps-mcp").mkdir(exist_ok=True)
        (tmp_path / ".tapps-mcp" / ".linear-validate-sentinel").write_text(
            str(int(time.time()) - 31 * 60)
        )
        rc, stderr = _run_hook(
            tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh",
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {"title": "stale create", "description": "x"},
                }
            ),
            tmp_path,
        )
        assert rc == 2
        assert "1800s" in stderr or "freshness" in stderr
