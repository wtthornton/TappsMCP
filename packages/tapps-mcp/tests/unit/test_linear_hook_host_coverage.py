"""Host-agnostic Linear hook coverage (TAP-5452 / TAP-5457) — kept small for gate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_generators import generate_claude_hooks


class TestLinearHookMatcherDrift:
    """TAP-5457: generated Linear matchers must cover known MCP server ids."""

    def test_cache_and_write_matchers_cover_known_hosts(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.linear_mcp_names import (
            LINEAR_PLUGIN_SERVER_IDS,
            matcher_covers_linear_leaf,
        )

        generate_claude_hooks(
            tmp_path,
            force_windows=False,
            linear_enforce_gate=True,
            linear_enforce_cache_gate="warn",
        )
        settings = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        matchers: list[str] = []
        for entries in settings.get("hooks", {}).values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("matcher"), str):
                    matchers.append(entry["matcher"])

        assert matcher_covers_linear_leaf(matchers, "list_issues")
        assert matcher_covers_linear_leaf(matchers, "save_issue")
        for sid in LINEAR_PLUGIN_SERVER_IDS:
            assert f"mcp__{sid}__list_issues" in matchers
            assert f"mcp__{sid}__save_issue" in matchers


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only behavioral tests")
class TestClaudeAiLinearHostGate:
    """TAP-5452: in-hook guards fire for claude_ai_Linear, not only plugin_*."""

    def test_pre_list_claude_ai_linear_host_gated(self, tmp_path: Path) -> None:
        generate_claude_hooks(
            tmp_path, force_windows=False, linear_enforce_cache_gate="block"
        )
        script = tmp_path / ".claude" / "hooks" / "tapps-pre-linear-list.sh"
        stdin = json.dumps(
            {
                "tool_name": "mcp__claude_ai_Linear__list_issues",
                "tool_input": {"team": "T", "project": "P", "state": "open"},
            }
        )
        proc = subprocess.run(
            ["/usr/bin/env", "bash", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=str(tmp_path),
            timeout=10,
        )
        assert proc.returncode == 2
        assert "linear-read" in proc.stderr or "snapshot_get" in proc.stderr
