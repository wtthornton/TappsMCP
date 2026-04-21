"""P3 hardening sweep: TAP-613/686/689/615/698/690 regression tests."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestTap615PepParser:
    """PEP 508 dependency names extracted correctly via packaging."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("uvicorn[standard]>=0.30", "uvicorn"),
            ('pytest; python_version >= "3.12"', "pytest"),
            ("fastapi>=0.110", "fastapi"),
            ("httpx~=0.27", "httpx"),
            ('fastapi; extra == "api"', "fastapi"),
            ("pydantic==2.0.0", "pydantic"),
            ("simple-package", "simple-package"),
        ],
    )
    def test_strip_version_specifier_handles_pep_508(
        self, raw: str, expected: str
    ) -> None:
        from tapps_mcp.tools.session_start_helpers import _strip_version_specifier

        assert _strip_version_specifier(raw) == expected


class TestTap613ImportGraphExcludes:
    """Worktree / cache dirs excluded from the dep graph walker."""

    def test_worktrees_is_in_default_excludes(self) -> None:
        from tapps_mcp.project.import_graph import _DEFAULT_EXCLUDES

        assert "worktrees" in _DEFAULT_EXCLUDES
        assert ".tapps-mcp-cache" in _DEFAULT_EXCLUDES
        assert ".tapps-agents" in _DEFAULT_EXCLUDES

    def test_build_graph_skips_worktree_subtree(self, tmp_path: Path) -> None:
        from tapps_mcp.project.import_graph import build_import_graph

        # Real module the graph should pick up.
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "main.py").write_text("x = 1\n")

        # Agent worktree that must NOT be scanned.
        wt = tmp_path / ".claude" / "worktrees" / "agent-abc" / "myapp"
        wt.mkdir(parents=True)
        (wt / "__init__.py").write_text("")
        (wt / "main.py").write_text("y = 2\n")

        graph = build_import_graph(tmp_path)
        assert not any("worktrees" in m for m in graph.modules)
        assert any("myapp" in m for m in graph.modules)


class TestTap686PythonSignals:
    """_has_python_signals prunes skip dirs in-place and caps its budget."""

    def test_marker_file_short_circuits(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import _has_python_signals

        (tmp_path / "pyproject.toml").write_text("")
        assert _has_python_signals(tmp_path) is True

    def test_walk_skips_node_modules_subtree(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import _has_python_signals

        nm = tmp_path / "node_modules" / "big"
        nm.mkdir(parents=True)
        (nm / "buried.py").write_text("x = 1\n")
        (tmp_path / "README.md").write_text("")

        assert _has_python_signals(tmp_path) is False

    def test_real_python_file_detected(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import _has_python_signals

        (tmp_path / "app.py").write_text("x = 1\n")
        assert _has_python_signals(tmp_path) is True


class TestTap689RulesBackup:
    """Pre-upgrade backup includes .claude/rules/*.md and .cursor/rules/*.md."""

    def test_collect_targets_includes_rule_files(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import _collect_upgrade_targets

        claude_rules = tmp_path / ".claude" / "rules"
        claude_rules.mkdir(parents=True)
        pq = claude_rules / "python-quality.md"
        pq.write_text("# user edits\n")

        cursor_rules = tmp_path / ".cursor" / "rules"
        cursor_rules.mkdir(parents=True)
        cq = cursor_rules / "tapps-pipeline.md"
        cq.write_text("# user edits\n")

        targets = _collect_upgrade_targets(tmp_path)

        assert pq in targets
        assert cq in targets

    def test_collect_targets_ok_when_rules_missing(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import _collect_upgrade_targets

        # No .claude/rules, no .cursor/rules — must not crash.
        assert _collect_upgrade_targets(tmp_path) == []


class TestTap698StrictConfig:
    """Env-gated extra='forbid' for TappsMCPSettings."""

    def test_default_mode_ignores_unknown_fields(self) -> None:
        from tapps_core.config.settings import _extra_mode

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAPPS_MCP_STRICT_CONFIG", None)
            assert _extra_mode() == "ignore"

    @pytest.mark.parametrize("v", ["1", "true", "TRUE", "yes"])
    def test_strict_env_flips_to_forbid(self, v: str) -> None:
        from tapps_core.config.settings import _extra_mode

        with patch.dict(os.environ, {"TAPPS_MCP_STRICT_CONFIG": v}):
            assert _extra_mode() == "forbid"


class TestTap690ContentReturnMcpOnly:
    """_upgrade_content_return honors mcp_only."""

    def test_mcp_only_skips_agents_md_and_platforms(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import _upgrade_content_return

        result = _upgrade_content_return(tmp_path, mcp_only=True)

        assert result["success"] is True
        assert "mcp_only_skipped" in result["components"]
        assert "agents_md" not in result["components"]
        assert "platforms" not in result["components"]
        # Manifest is present but empty.
        ops = result["file_manifest"].get("file_operations", [])
        claude_md_ops = [
            op for op in ops if "CLAUDE.md" in op.get("target_path", "")
        ]
        assert not claude_md_ops
