"""Tests for bootstrap_pipeline content-return mode — Epic 87 Story 87.2."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from tapps_core.common.file_operations import WriteMode
from tapps_mcp.pipeline.init import BootstrapConfig, _BootstrapState, bootstrap_pipeline

# ---------------------------------------------------------------------------
# _BootstrapState content-return tests
# ---------------------------------------------------------------------------


class TestBootstrapStateContentReturn:
    """Test _BootstrapState behavior in content-return mode."""

    def test_content_return_property(self, tmp_path: Path) -> None:
        state = _BootstrapState(
            project_root=tmp_path,
            write_mode=WriteMode.CONTENT_RETURN,
        )
        assert state.content_return is True

    def test_direct_write_property(self, tmp_path: Path) -> None:
        state = _BootstrapState(project_root=tmp_path)
        assert state.content_return is False

    def test_safe_write_accumulates_file_ops(self, tmp_path: Path) -> None:
        state = _BootstrapState(
            project_root=tmp_path,
            write_mode=WriteMode.CONTENT_RETURN,
        )
        state.safe_write("README.md", "# Hello\n")

        assert len(state.file_ops) == 1
        assert state.file_ops[0].path == "README.md"
        assert state.file_ops[0].content == "# Hello\n"
        assert state.file_ops[0].mode == "create"
        assert "README.md" in state.created

    def test_safe_write_no_disk_write(self, tmp_path: Path) -> None:
        """Content-return mode must NOT write files to disk."""
        state = _BootstrapState(
            project_root=tmp_path,
            write_mode=WriteMode.CONTENT_RETURN,
        )
        state.safe_write("test.txt", "content")

        assert not (tmp_path / "test.txt").exists()

    def test_safe_write_skips_existing_in_direct_mode(self, tmp_path: Path) -> None:
        """Direct-write mode skips existing files (backward compat)."""
        (tmp_path / "existing.md").write_text("old", encoding="utf-8")
        state = _BootstrapState(project_root=tmp_path)
        state.safe_write("existing.md", "new")

        assert "existing.md" in state.skipped
        assert len(state.file_ops) == 0

    def test_safe_write_content_return_ignores_existing(self, tmp_path: Path) -> None:
        """Content-return mode generates FileOps regardless of existing files."""
        (tmp_path / "existing.md").write_text("old", encoding="utf-8")
        state = _BootstrapState(
            project_root=tmp_path,
            write_mode=WriteMode.CONTENT_RETURN,
        )
        state.safe_write("existing.md", "new")

        # In content-return mode, we generate the FileOp anyway
        assert len(state.file_ops) == 1
        assert state.file_ops[0].content == "new"

    def test_safe_write_or_overwrite_content_return(self, tmp_path: Path) -> None:
        state = _BootstrapState(
            project_root=tmp_path,
            write_mode=WriteMode.CONTENT_RETURN,
        )
        action = state.safe_write_or_overwrite("config.yaml", "key: val\n")

        assert action == "created"
        assert len(state.file_ops) == 1
        assert state.file_ops[0].mode == "create"
        assert not (tmp_path / "config.yaml").exists()

    def test_safe_write_or_overwrite_existing_content_return(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("old: val\n", encoding="utf-8")
        state = _BootstrapState(
            project_root=tmp_path,
            write_mode=WriteMode.CONTENT_RETURN,
        )
        action = state.safe_write_or_overwrite("config.yaml", "new: val\n")

        assert action == "updated"
        assert state.file_ops[0].mode == "overwrite"
        # Original file unchanged
        assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == "old: val\n"

    def test_safe_write_path_traversal_blocked(self, tmp_path: Path) -> None:
        state = _BootstrapState(
            project_root=tmp_path,
            write_mode=WriteMode.CONTENT_RETURN,
        )
        state.safe_write("../../etc/passwd", "bad")

        assert len(state.file_ops) == 0
        assert any("escapes project root" in e for e in state.errors)

    def test_build_manifest(self, tmp_path: Path) -> None:
        state = _BootstrapState(
            project_root=tmp_path,
            write_mode=WriteMode.CONTENT_RETURN,
        )
        state.safe_write("AGENTS.md", "# AGENTS\n")
        state.safe_write("TECH_STACK.md", "# Tech\n")

        manifest = state.build_manifest()
        assert len(manifest.files) == 2
        assert "TappsMCP init" in manifest.summary
        assert manifest.source_version
        assert "scaffolding" in manifest.agent_instructions.persona
        assert len(manifest.agent_instructions.verification_steps) >= 1
        assert len(manifest.agent_instructions.warnings) >= 1


# ---------------------------------------------------------------------------
# bootstrap_pipeline content-return integration tests
# ---------------------------------------------------------------------------


class TestBootstrapPipelineContentReturn:
    """Integration tests for bootstrap_pipeline in content-return mode."""

    def test_content_return_via_env_var(self, tmp_path: Path) -> None:
        """TAPPS_WRITE_MODE=content triggers content-return mode."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = bootstrap_pipeline(
                tmp_path,
                config=BootstrapConfig(
                    platform="",
                    verify_server=False,
                    warm_cache_from_tech_stack=False,
                    warm_expert_rag_from_tech_stack=False,
                    minimal=True,
                ),
            )

        assert result.get("content_return") is True
        assert "file_manifest" in result
        manifest = result["file_manifest"]
        assert manifest["mode"] == "content_return"
        assert manifest["file_count"] > 0
        assert "agent_instructions" in manifest

    def test_content_return_no_files_written(self, tmp_path: Path) -> None:
        """Content-return mode must not write any files."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            bootstrap_pipeline(
                tmp_path,
                config=BootstrapConfig(
                    platform="",
                    verify_server=False,
                    warm_cache_from_tech_stack=False,
                    warm_expert_rag_from_tech_stack=False,
                    minimal=True,
                ),
            )

        # Only pre-existing files should be in tmp_path
        created_files = list(tmp_path.rglob("*"))
        # Filter to actual files (not dirs)
        actual_files = [f for f in created_files if f.is_file()]
        assert actual_files == [], f"Unexpected files written: {actual_files}"

    def test_content_return_with_claude_platform(self, tmp_path: Path) -> None:
        """Content-return mode generates CLAUDE.md as a FileOperation."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = bootstrap_pipeline(
                tmp_path,
                config=BootstrapConfig(
                    platform="claude",
                    verify_server=False,
                    warm_cache_from_tech_stack=False,
                    warm_expert_rag_from_tech_stack=False,
                    minimal=True,
                ),
            )

        manifest = result["file_manifest"]
        file_paths = [f["path"] for f in manifest["files"]]
        assert "CLAUDE.md" in file_paths
        assert result["platform_rules"]["action"] == "content_return"

    def test_content_return_with_cursor_platform(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = bootstrap_pipeline(
                tmp_path,
                config=BootstrapConfig(
                    platform="cursor",
                    verify_server=False,
                    warm_cache_from_tech_stack=False,
                    warm_expert_rag_from_tech_stack=False,
                    minimal=True,
                ),
            )

        manifest = result["file_manifest"]
        file_paths = [f["path"] for f in manifest["files"]]
        assert ".cursor/rules/tapps-pipeline.md" in file_paths

    def test_content_return_includes_agents_md(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = bootstrap_pipeline(
                tmp_path,
                config=BootstrapConfig(
                    create_agents_md=True,
                    platform="",
                    verify_server=False,
                    warm_cache_from_tech_stack=False,
                    warm_expert_rag_from_tech_stack=False,
                    minimal=True,
                ),
            )

        manifest = result["file_manifest"]
        file_paths = [f["path"] for f in manifest["files"]]
        assert "AGENTS.md" in file_paths

    def test_content_return_skips_cache_warming(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = bootstrap_pipeline(
                tmp_path,
                config=BootstrapConfig(
                    platform="",
                    verify_server=False,
                    warm_cache_from_tech_stack=True,
                    warm_expert_rag_from_tech_stack=True,
                    minimal=True,
                ),
            )

        assert result["cache_warming"]["skipped"] == "content_return"
        assert result["expert_rag_warming"]["skipped"] == "content_return"

    def test_content_return_manifest_has_full_content(self, tmp_path: Path) -> None:
        """Manifest files should include actual content, not just metadata."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = bootstrap_pipeline(
                tmp_path,
                config=BootstrapConfig(
                    create_agents_md=True,
                    platform="",
                    verify_server=False,
                    warm_cache_from_tech_stack=False,
                    warm_expert_rag_from_tech_stack=False,
                    minimal=True,
                ),
            )

        manifest = result["file_manifest"]
        for f in manifest["files"]:
            assert "content" in f, f"File {f['path']} missing content"
            assert len(f["content"]) > 0, f"File {f['path']} has empty content"

    def test_content_return_platform_generators_skipped(self, tmp_path: Path) -> None:
        """Platform generators (hooks, skills) are noted as skipped."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = bootstrap_pipeline(
                tmp_path,
                config=BootstrapConfig(
                    platform="claude",
                    verify_server=False,
                    warm_cache_from_tech_stack=False,
                    warm_expert_rag_from_tech_stack=False,
                    minimal=False,
                ),
            )

        skipped = result.get("platform_generators_skipped")
        assert skipped is not None
        assert skipped["reason"] == "content_return"
        assert "hooks" in skipped["skipped_components"]

    def test_direct_write_unchanged(self, tmp_path: Path) -> None:
        """Direct-write mode (default) still writes files normally."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            result = bootstrap_pipeline(
                tmp_path,
                config=BootstrapConfig(
                    create_agents_md=True,
                    platform="",
                    verify_server=False,
                    warm_cache_from_tech_stack=False,
                    warm_expert_rag_from_tech_stack=False,
                    minimal=True,
                ),
            )

        assert result.get("content_return") is not True
        assert "file_manifest" not in result
        # Files should actually exist on disk
        assert (tmp_path / "AGENTS.md").exists()

    def test_dry_run_unaffected(self, tmp_path: Path) -> None:
        """dry_run=True still works as before (no content_return)."""
        result = bootstrap_pipeline(
            tmp_path,
            config=BootstrapConfig(
                platform="",
                verify_server=False,
                warm_cache_from_tech_stack=False,
                warm_expert_rag_from_tech_stack=False,
                minimal=True,
                dry_run=True,
            ),
        )

        assert result.get("content_return") is not True
        assert "file_manifest" not in result
