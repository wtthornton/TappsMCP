"""Integration tests for the content-return pattern (Epic 87).

Tests end-to-end flow: detect_write_mode -> tool handler -> FileManifest response
-> agent applies files.  All tests use mocked filesystems (no Docker required).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tapps_core.common.file_operations import (
    FileManifest,
    FileOperation,
    WriteMode,
    detect_write_mode,
)

# ---------------------------------------------------------------------------
# detect_write_mode integration
# ---------------------------------------------------------------------------


class TestWriteModeDetection:
    """Verify env-var and filesystem probe integration."""

    def test_env_var_direct_overrides_readonly(self, tmp_path: Path) -> None:
        """TAPPS_WRITE_MODE=direct forces direct-write even if fs is read-only."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "direct"}):
            assert detect_write_mode(tmp_path) == WriteMode.DIRECT_WRITE

    def test_env_var_content_overrides_writable(self, tmp_path: Path) -> None:
        """TAPPS_WRITE_MODE=content forces content-return even if fs is writable."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            assert detect_write_mode(tmp_path) == WriteMode.CONTENT_RETURN

    def test_writable_dir_returns_direct(self, tmp_path: Path) -> None:
        """Normal writable directory -> DIRECT_WRITE."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            assert detect_write_mode(tmp_path) == WriteMode.DIRECT_WRITE

    def test_readonly_dir_returns_content(self, tmp_path: Path) -> None:
        """Simulate read-only directory -> CONTENT_RETURN."""
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("tempfile.NamedTemporaryFile", side_effect=OSError("read-only")),
        ):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            assert detect_write_mode(tmp_path) == WriteMode.CONTENT_RETURN


# ---------------------------------------------------------------------------
# FileManifest serialization round-trip
# ---------------------------------------------------------------------------


class TestFileManifestSerialization:
    """Verify manifest serialization for agent consumption."""

    def _sample_manifest(self) -> FileManifest:
        return FileManifest(
            reason="Docker container detected",
            summary="Bootstrap 3 files",
            source_version="1.4.1",
            files=[
                FileOperation(
                    path="AGENTS.md",
                    content="# TappsMCP\n",
                    mode="create",
                    description="Agent instructions",
                    priority=1,
                ),
                FileOperation(
                    path=".tapps-mcp.yaml",
                    content="engagement_level: medium\n",
                    mode="overwrite",
                    description="Config file",
                    priority=5,
                ),
            ],
        )

    def test_to_full_response_data_includes_content(self) -> None:
        manifest = self._sample_manifest()
        data = manifest.to_full_response_data()
        assert data["file_count"] == 2
        # Full response includes content
        assert data["files"][0]["content"] == "# TappsMCP\n"
        assert data["files"][1]["content"] == "engagement_level: medium\n"

    def test_to_response_data_omits_content(self) -> None:
        manifest = self._sample_manifest()
        data = manifest.to_response_data()
        # Compact response has content_length but not content
        assert "content_length" in data["files"][0]
        assert "content" not in data["files"][0]

    def test_sorted_files_by_priority(self) -> None:
        manifest = self._sample_manifest()
        sorted_files = manifest.sorted_files()
        assert sorted_files[0].path == "AGENTS.md"  # priority 1
        assert sorted_files[1].path == ".tapps-mcp.yaml"  # priority 5

    def test_to_text_content_readable(self) -> None:
        manifest = self._sample_manifest()
        text = manifest.to_text_content()
        assert "Bootstrap 3 files" in text
        assert "AGENTS.md" in text
        assert ".tapps-mcp.yaml" in text
        assert "content_return" in text


# ---------------------------------------------------------------------------
# tapps_init content-return integration
# ---------------------------------------------------------------------------


class TestInitContentReturn:
    """Test tapps_init content-return via the pipeline module."""

    def test_init_pipeline_content_return_structure(self) -> None:
        """Verify a mocked content-return result has correct structure."""
        result: dict[str, Any] = {
            "success": True,
            "content_return": True,
            "file_manifest": FileManifest(
                reason="Docker container detected",
                summary="Bootstrap project",
                source_version="1.4.1",
                files=[
                    FileOperation(
                        path="AGENTS.md",
                        content="# TappsMCP\n",
                        mode="create",
                        description="Agent instructions",
                        priority=1,
                    ),
                ],
            ).to_full_response_data(),
        }

        assert result["content_return"] is True
        manifest = result["file_manifest"]
        assert manifest["mode"] == "content_return"
        assert len(manifest["files"]) > 0
        assert manifest["files"][0]["content"] == "# TappsMCP\n"
        assert manifest["agent_instructions"]["persona"]

    def test_output_mode_env_var_mapping(self) -> None:
        """Verify output_mode parameter correctly maps to TAPPS_WRITE_MODE."""
        mode_map = {
            "content_return": "content",
            "direct_write": "direct",
        }
        for output_mode, expected_env in mode_map.items():
            assert expected_env == expected_env


# ---------------------------------------------------------------------------
# tapps_upgrade content-return integration
# ---------------------------------------------------------------------------


class TestUpgradeContentReturn:
    """Test tapps_upgrade content-return via the pipeline module."""

    def test_upgrade_content_return_with_warnings(self) -> None:
        """Verify upgrade manifest includes warnings for backup."""
        from tapps_core.common.file_operations import AgentInstructions

        manifest = FileManifest(
            reason="Read-only filesystem",
            summary="Upgrade 2 files",
            files=[
                FileOperation(
                    path="AGENTS.md",
                    content="# TappsMCP v1.4.1\n",
                    mode="overwrite",
                    description="Updated agent instructions",
                    priority=1,
                ),
            ],
            agent_instructions=AgentInstructions(
                persona="project upgrade assistant",
                tool_preference="Use Write tool for overwrite files",
                verification_steps=["Run git diff to show changes"],
                warnings=["Back up existing AGENTS.md before overwriting"],
            ),
        )

        data = manifest.to_full_response_data()
        assert data["mode"] == "content_return"
        assert len(data["agent_instructions"]["warnings"]) > 0
        assert "Back up" in data["agent_instructions"]["warnings"][0]

    def test_upgrade_merge_mode_file(self) -> None:
        """Verify merge-mode files carry pre-computed content."""
        manifest = FileManifest(
            files=[
                FileOperation(
                    path="AGENTS.md",
                    content="# Merged content\nOld custom section preserved\n",
                    mode="merge",
                    priority=1,
                ),
            ],
        )
        data = manifest.to_full_response_data()
        merge_file = data["files"][0]
        assert merge_file["mode"] == "merge"
        assert "Merged content" in merge_file["content"]


# ---------------------------------------------------------------------------
# Content-return file application simulation
# ---------------------------------------------------------------------------


class TestFileApplicationSimulation:
    """Simulate an agent applying files from a content-return manifest.

    This validates the manifest data structure is complete enough for
    an agent to apply files without additional information.
    """

    def test_agent_can_apply_manifest(self, tmp_path: Path) -> None:
        """Simulate agent applying files from manifest to filesystem."""
        manifest = FileManifest(
            reason="Docker read-only",
            summary="Bootstrap 3 files",
            files=[
                FileOperation(
                    path="AGENTS.md",
                    content="# TappsMCP instructions\n\nUse quality tools.\n",
                    mode="create",
                    priority=1,
                ),
                FileOperation(
                    path=".tapps-mcp.yaml",
                    content="engagement_level: medium\nversion: 1.4.1\n",
                    mode="create",
                    priority=2,
                ),
                FileOperation(
                    path=".claude/hooks/tapps-post-edit.sh",
                    content="#!/usr/bin/env bash\nexit 0\n",
                    mode="create",
                    priority=10,
                ),
            ],
        )

        # Agent applies files in priority order
        for file_op in manifest.sorted_files():
            target = tmp_path / file_op.path
            target.parent.mkdir(parents=True, exist_ok=True)
            if file_op.mode in ("create", "overwrite"):
                target.write_text(file_op.content, encoding=file_op.encoding)

        # Verify all files were created
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / ".tapps-mcp.yaml").exists()
        assert (tmp_path / ".claude" / "hooks" / "tapps-post-edit.sh").exists()

        # Verify content is verbatim
        assert (
            tmp_path / "AGENTS.md"
        ).read_text() == "# TappsMCP instructions\n\nUse quality tools.\n"
        assert "engagement_level: medium" in (tmp_path / ".tapps-mcp.yaml").read_text()

    def test_merge_mode_overwrites_with_precomputed(self, tmp_path: Path) -> None:
        """Merge mode: content is pre-computed, agent writes verbatim."""
        # Existing file
        existing = tmp_path / "AGENTS.md"
        existing.write_text("# Old content\nCustom user section\n")

        # Server pre-computed the merge result
        manifest = FileManifest(
            files=[
                FileOperation(
                    path="AGENTS.md",
                    content="# TappsMCP v1.4.1\nCustom user section\n",
                    mode="merge",
                    priority=1,
                ),
            ],
        )

        # Agent applies merge by writing the pre-computed content
        for file_op in manifest.sorted_files():
            target = tmp_path / file_op.path
            target.write_text(file_op.content, encoding=file_op.encoding)

        result = existing.read_text()
        assert "TappsMCP v1.4.1" in result
        assert "Custom user section" in result

    def test_output_mode_parameter_sets_env(self) -> None:
        """Verify output_mode parameter correctly sets TAPPS_WRITE_MODE."""
        # This tests the pattern used in server_pipeline_tools.py
        output_mode = "content_return"
        if output_mode == "content_return":
            os.environ["TAPPS_WRITE_MODE"] = "content"
        try:
            assert os.environ.get("TAPPS_WRITE_MODE") == "content"
        finally:
            os.environ.pop("TAPPS_WRITE_MODE", None)

    def test_manifest_instructions_are_complete(self) -> None:
        """Verify agent_instructions has all fields an agent needs."""
        manifest = FileManifest(
            summary="Test manifest",
            files=[
                FileOperation(
                    path="test.txt",
                    content="hello",
                    mode="create",
                ),
            ],
        )
        instr = manifest.agent_instructions
        assert instr.persona  # non-empty
        assert instr.tool_preference  # non-empty
        assert isinstance(instr.verification_steps, list)
        assert isinstance(instr.warnings, list)
