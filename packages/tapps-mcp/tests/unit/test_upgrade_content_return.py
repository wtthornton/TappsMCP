"""Tests for upgrade pipeline content-return mode — Epic 87 Story 87.3."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_core.common.file_operations import WriteMode
from tapps_mcp.pipeline.upgrade import (
    _build_upgrade_manifest,
    _detect_platform,
    _upgrade_agents_md_content_return,
    _upgrade_content_return,
    _upgrade_platform_content_return,
    upgrade_pipeline,
)


# ---------------------------------------------------------------------------
# _upgrade_agents_md_content_return tests
# ---------------------------------------------------------------------------


class TestUpgradeAgentsMdContentReturn:
    """Test AGENTS.md generation in content-return mode."""

    def test_creates_when_missing(self, tmp_path: Path) -> None:
        op, result = _upgrade_agents_md_content_return(tmp_path)

        assert result["action"] == "created"
        assert op.mode == "create"
        assert op.path == "AGENTS.md"
        assert len(op.content) > 0

    def test_up_to_date_when_current(self, tmp_path: Path) -> None:
        """When AGENTS.md matches the template, returns up-to-date."""
        from tapps_mcp.prompts.prompt_loader import load_agents_template

        template = load_agents_template()
        (tmp_path / "AGENTS.md").write_text(template, encoding="utf-8")

        op, result = _upgrade_agents_md_content_return(tmp_path)

        assert result["action"] == "up-to-date"
        assert op.mode == "overwrite"
        assert op.content == template

    def test_merge_when_outdated(self, tmp_path: Path) -> None:
        """When AGENTS.md is outdated, returns merged content."""
        # Write a minimal AGENTS.md that will be outdated
        (tmp_path / "AGENTS.md").write_text(
            "# AGENTS.md\n\nMinimal placeholder.\n",
            encoding="utf-8",
        )

        op, result = _upgrade_agents_md_content_return(tmp_path)

        assert result["action"] == "merged"
        assert op.mode == "merge"
        assert "changes" in result
        assert len(op.content) > 0

    def test_no_disk_writes(self, tmp_path: Path) -> None:
        """Content-return must not write AGENTS.md to disk."""
        _upgrade_agents_md_content_return(tmp_path)
        assert not (tmp_path / "AGENTS.md").exists()

    def test_merge_preserves_existing_on_disk(self, tmp_path: Path) -> None:
        """Existing AGENTS.md on disk must not be modified."""
        original = "# AGENTS.md\n\nCustom user content.\n"
        (tmp_path / "AGENTS.md").write_text(original, encoding="utf-8")

        _upgrade_agents_md_content_return(tmp_path)

        assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# _upgrade_platform_content_return tests
# ---------------------------------------------------------------------------


class TestUpgradePlatformContentReturn:
    """Test platform file generation in content-return mode."""

    def test_claude_platform(self, tmp_path: Path) -> None:
        ops, result = _upgrade_platform_content_return(
            "claude-code", tmp_path
        )

        assert len(ops) >= 1
        claude_op = ops[0]
        assert claude_op.path == "CLAUDE.md"
        assert len(claude_op.content) > 0
        assert result["components"]["claude_md"] == "content_return"
        assert "generators_skipped" in result["components"]

    def test_cursor_platform(self, tmp_path: Path) -> None:
        ops, result = _upgrade_platform_content_return(
            "cursor", tmp_path
        )

        assert len(ops) >= 1
        cursor_op = ops[0]
        assert cursor_op.path == ".cursor/rules/tapps-pipeline.md"
        assert result["components"]["cursor_rules"] == "content_return"

    def test_vscode_no_ops(self, tmp_path: Path) -> None:
        ops, result = _upgrade_platform_content_return(
            "vscode", tmp_path
        )

        assert len(ops) == 0
        assert result["components"]["note"] == "no platform rules to upgrade"

    def test_existing_claude_md_uses_overwrite(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("old", encoding="utf-8")

        ops, _result = _upgrade_platform_content_return(
            "claude-code", tmp_path
        )

        assert ops[0].mode == "overwrite"

    def test_new_claude_md_uses_create(self, tmp_path: Path) -> None:
        ops, _result = _upgrade_platform_content_return(
            "claude-code", tmp_path
        )

        assert ops[0].mode == "create"

    def test_no_disk_writes(self, tmp_path: Path) -> None:
        _upgrade_platform_content_return("claude-code", tmp_path)
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_generators_skipped_note(self, tmp_path: Path) -> None:
        _ops, result = _upgrade_platform_content_return(
            "claude-code", tmp_path
        )

        skipped = result["components"]["generators_skipped"]
        assert skipped["reason"] == "content_return"
        assert "hooks" in skipped["skipped"]


# ---------------------------------------------------------------------------
# _build_upgrade_manifest tests
# ---------------------------------------------------------------------------


class TestBuildUpgradeManifest:
    """Test manifest construction for upgrade pipeline."""

    def test_manifest_structure(self) -> None:
        from tapps_core.common.file_operations import FileOperation

        ops = [
            FileOperation(
                path="AGENTS.md",
                content="# AGENTS\n",
                mode="merge",
                priority=1,
            ),
            FileOperation(
                path="CLAUDE.md",
                content="# CLAUDE\n",
                mode="overwrite",
                priority=2,
            ),
        ]

        manifest = _build_upgrade_manifest(ops, "1.4.1")

        assert manifest.source_version == "1.4.1"
        assert len(manifest.files) == 2
        assert "upgrade" in manifest.agent_instructions.persona.lower()
        assert "merge" in manifest.agent_instructions.tool_preference.lower()
        assert len(manifest.agent_instructions.verification_steps) >= 1
        assert len(manifest.agent_instructions.warnings) >= 1
        assert "1.4.1" in manifest.summary


# ---------------------------------------------------------------------------
# upgrade_pipeline content-return integration tests
# ---------------------------------------------------------------------------


class TestUpgradePipelineContentReturn:
    """Integration tests for upgrade_pipeline in content-return mode."""

    def test_content_return_via_env_var(self, tmp_path: Path) -> None:
        """TAPPS_WRITE_MODE=content triggers content-return mode."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = upgrade_pipeline(tmp_path)

        assert result.get("content_return") is True
        assert "file_manifest" in result
        manifest = result["file_manifest"]
        assert manifest["mode"] == "content_return"
        assert manifest["file_count"] > 0
        assert "agent_instructions" in manifest

    def test_content_return_no_files_written(self, tmp_path: Path) -> None:
        """Content-return mode must not write any files."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            upgrade_pipeline(tmp_path)

        actual_files = [f for f in tmp_path.rglob("*") if f.is_file()]
        assert actual_files == [], f"Unexpected files: {actual_files}"

    def test_content_return_includes_agents_md(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = upgrade_pipeline(tmp_path)

        manifest = result["file_manifest"]
        file_paths = [f["path"] for f in manifest["files"]]
        assert "AGENTS.md" in file_paths

    def test_content_return_with_claude_platform(self, tmp_path: Path) -> None:
        """Content-return with claude platform includes CLAUDE.md."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = upgrade_pipeline(tmp_path, platform="claude")

        manifest = result["file_manifest"]
        file_paths = [f["path"] for f in manifest["files"]]
        assert "AGENTS.md" in file_paths
        assert "CLAUDE.md" in file_paths

    def test_content_return_with_cursor_platform(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = upgrade_pipeline(tmp_path, platform="cursor")

        manifest = result["file_manifest"]
        file_paths = [f["path"] for f in manifest["files"]]
        assert ".cursor/rules/tapps-pipeline.md" in file_paths

    def test_content_return_merge_existing_agents(self, tmp_path: Path) -> None:
        """When AGENTS.md exists and is outdated, file op has mode='merge'."""
        (tmp_path / "AGENTS.md").write_text(
            "# AGENTS.md\n\nMinimal.\n", encoding="utf-8"
        )

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = upgrade_pipeline(tmp_path)

        manifest = result["file_manifest"]
        agents_ops = [f for f in manifest["files"] if f["path"] == "AGENTS.md"]
        assert len(agents_ops) == 1
        assert agents_ops[0]["mode"] == "merge"
        assert result["components"]["agents_md"]["action"] == "merged"

    def test_content_return_github_artifacts_skipped(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = upgrade_pipeline(tmp_path)

        for component in ("ci_workflows", "github_copilot", "github_templates", "governance"):
            assert result["components"][component]["action"] == "skipped"

    def test_content_return_manifest_has_full_content(self, tmp_path: Path) -> None:
        """Manifest files should include actual content."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = upgrade_pipeline(tmp_path)

        manifest = result["file_manifest"]
        for f in manifest["files"]:
            assert "content" in f, f"File {f['path']} missing content"
            assert len(f["content"]) > 0, f"File {f['path']} has empty content"

    def test_content_return_no_backup(self, tmp_path: Path) -> None:
        """Content-return mode should not create backups."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = upgrade_pipeline(tmp_path)

        assert "backup" not in result

    def test_direct_write_unchanged(self, tmp_path: Path) -> None:
        """Direct-write mode (default) still writes files normally."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            result = upgrade_pipeline(tmp_path, platform="")

        assert result.get("content_return") is not True
        assert "file_manifest" not in result
        # AGENTS.md should exist on disk
        assert (tmp_path / "AGENTS.md").exists()

    def test_dry_run_unaffected(self, tmp_path: Path) -> None:
        """dry_run=True still works as before (no content_return)."""
        result = upgrade_pipeline(tmp_path, dry_run=True)

        assert result.get("content_return") is not True
        assert "file_manifest" not in result
        assert result["dry_run"] is True
