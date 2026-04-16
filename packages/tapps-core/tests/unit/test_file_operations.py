"""Tests for tapps_core.common.file_operations — Epic 87 Story 87.1."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_core.common.file_operations import (
    AgentInstructions,
    FileManifest,
    FileOperation,
    WriteMode,
    detect_write_mode,
)

# ---------------------------------------------------------------------------
# WriteMode enum
# ---------------------------------------------------------------------------


class TestWriteMode:
    def test_values(self) -> None:
        assert WriteMode.DIRECT_WRITE.value == "direct_write"
        assert WriteMode.CONTENT_RETURN.value == "content_return"

    def test_members(self) -> None:
        assert set(WriteMode) == {WriteMode.DIRECT_WRITE, WriteMode.CONTENT_RETURN}


# ---------------------------------------------------------------------------
# detect_write_mode
# ---------------------------------------------------------------------------


class TestDetectWriteMode:
    def test_env_override_direct(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "direct"}):
            assert detect_write_mode(tmp_path) == WriteMode.DIRECT_WRITE

    def test_env_override_content(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            assert detect_write_mode(tmp_path) == WriteMode.CONTENT_RETURN

    def test_env_override_case_insensitive(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "DIRECT"}):
            assert detect_write_mode(tmp_path) == WriteMode.DIRECT_WRITE

    def test_env_override_with_whitespace(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "  content  "}):
            assert detect_write_mode(tmp_path) == WriteMode.CONTENT_RETURN

    def test_writable_directory(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            assert detect_write_mode(tmp_path) == WriteMode.DIRECT_WRITE

    def test_nonexistent_directory(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            result = detect_write_mode(Path("/nonexistent/path/that/does/not/exist"))
            assert result == WriteMode.CONTENT_RETURN

    def test_read_only_directory(self, tmp_path: Path) -> None:
        """Simulate read-only by patching NamedTemporaryFile to raise OSError."""
        with (
            patch.dict(os.environ, {}, clear=False),
            patch(
                "tapps_core.common.file_operations.tempfile.NamedTemporaryFile",
                side_effect=OSError("Read-only filesystem"),
            ),
        ):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            assert detect_write_mode(tmp_path) == WriteMode.CONTENT_RETURN

    def test_env_override_takes_precedence_over_probe(self, tmp_path: Path) -> None:
        """Even if the directory is writable, env var wins."""
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            assert detect_write_mode(tmp_path) == WriteMode.CONTENT_RETURN

    def test_unknown_env_value_falls_through_to_probe(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "unknown"}):
            # Falls through to probe — tmp_path is writable
            assert detect_write_mode(tmp_path) == WriteMode.DIRECT_WRITE


# ---------------------------------------------------------------------------
# FileOperation model
# ---------------------------------------------------------------------------


class TestFileOperation:
    def test_minimal_creation(self) -> None:
        op = FileOperation(path="README.md", content="# Hello", mode="create")
        assert op.path == "README.md"
        assert op.content == "# Hello"
        assert op.mode == "create"
        assert op.encoding == "utf-8"
        assert op.description == ""
        assert op.priority == 10

    def test_full_creation(self) -> None:
        op = FileOperation(
            path=".claude/hooks/tapps-pre-edit.sh",
            content="#!/bin/bash\necho hello",
            mode="overwrite",
            encoding="utf-8",
            description="Pre-edit hook",
            priority=3,
        )
        assert op.path == ".claude/hooks/tapps-pre-edit.sh"
        assert op.mode == "overwrite"
        assert op.priority == 3

    def test_serialization_round_trip(self) -> None:
        op = FileOperation(path="test.py", content="pass\n", mode="create")
        data = op.model_dump(mode="json")
        restored = FileOperation.model_validate(data)
        assert restored == op

    def test_json_schema(self) -> None:
        schema = FileOperation.model_json_schema()
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "content" in schema["properties"]
        assert "mode" in schema["properties"]
        assert set(schema["required"]) == {"path", "content", "mode"}


# ---------------------------------------------------------------------------
# AgentInstructions model
# ---------------------------------------------------------------------------


class TestAgentInstructions:
    def test_defaults(self) -> None:
        instr = AgentInstructions()
        assert "scaffolding" in instr.persona
        assert "Write tool" in instr.tool_preference
        assert len(instr.verification_steps) >= 1
        assert instr.warnings == []

    def test_custom_values(self) -> None:
        instr = AgentInstructions(
            persona="You are a release manager.",
            tool_preference="Use Edit for all files.",
            verification_steps=["Check changelog"],
            warnings=["Breaking change"],
        )
        assert instr.persona == "You are a release manager."
        assert instr.warnings == ["Breaking change"]

    def test_serialization(self) -> None:
        instr = AgentInstructions(warnings=["test warning"])
        data = instr.model_dump(mode="json")
        assert data["warnings"] == ["test warning"]
        restored = AgentInstructions.model_validate(data)
        assert restored == instr


# ---------------------------------------------------------------------------
# FileManifest model
# ---------------------------------------------------------------------------


class TestFileManifest:
    @pytest.fixture()
    def sample_manifest(self) -> FileManifest:
        return FileManifest(
            summary="Test upgrade: 3 files",
            source_version="1.4.1",
            files=[
                FileOperation(
                    path="AGENTS.md",
                    content="# AGENTS\n",
                    mode="overwrite",
                    description="Agent guidance",
                    priority=1,
                ),
                FileOperation(
                    path=".claude/hooks/tapps-pre-edit.sh",
                    content="#!/bin/bash\n",
                    mode="create",
                    description="Pre-edit hook",
                    priority=10,
                ),
                FileOperation(
                    path=".tapps-mcp.yaml",
                    content="preset: standard\n",
                    mode="create",
                    description="Config",
                    priority=2,
                ),
            ],
            agent_instructions=AgentInstructions(
                warnings=["Backup first"],
            ),
        )

    def test_sorted_files(self, sample_manifest: FileManifest) -> None:
        sorted_files = sample_manifest.sorted_files()
        priorities = [f.priority for f in sorted_files]
        assert priorities == [1, 2, 10]
        assert sorted_files[0].path == "AGENTS.md"
        assert sorted_files[1].path == ".tapps-mcp.yaml"
        assert sorted_files[2].path == ".claude/hooks/tapps-pre-edit.sh"

    def test_to_structured_content(self, sample_manifest: FileManifest) -> None:
        sc = sample_manifest.to_structured_content()
        assert sc["mode"] == "content_return"
        assert sc["source_version"] == "1.4.1"
        assert len(sc["files"]) == 3
        assert sc["agent_instructions"]["warnings"] == ["Backup first"]
        # Verify it's JSON-serializable
        json.dumps(sc)

    def test_to_text_content(self, sample_manifest: FileManifest) -> None:
        text = sample_manifest.to_text_content()
        assert "Test upgrade: 3 files" in text
        assert "content_return" in text
        assert "AGENTS.md" in text
        assert "# AGENTS" in text
        assert "Agent Instructions" in text
        assert "Backup first" in text

    def test_to_text_content_respects_priority_order(self, sample_manifest: FileManifest) -> None:
        text = sample_manifest.to_text_content()
        agents_pos = text.index("AGENTS.md")
        config_pos = text.index(".tapps-mcp.yaml")
        hook_pos = text.index("tapps-pre-edit.sh")
        assert agents_pos < config_pos < hook_pos

    def test_to_response_data(self, sample_manifest: FileManifest) -> None:
        data = sample_manifest.to_response_data()
        assert data["mode"] == "content_return"
        assert data["file_count"] == 3
        assert data["summary"] == "Test upgrade: 3 files"
        # Response data (non-full) should have content_length, not content
        for f in data["files"]:
            assert "content_length" in f
            assert "content" not in f

    def test_to_full_response_data(self, sample_manifest: FileManifest) -> None:
        data = sample_manifest.to_full_response_data()
        assert data["file_count"] == 3
        # Full response includes actual content
        for f in data["files"]:
            assert "content" in f
            assert isinstance(f["content"], str)

    def test_empty_manifest(self) -> None:
        manifest = FileManifest()
        assert manifest.mode == "content_return"
        assert manifest.files == []
        assert manifest.summary == ""
        sc = manifest.to_structured_content()
        assert sc["files"] == []

    def test_json_round_trip(self, sample_manifest: FileManifest) -> None:
        json_str = sample_manifest.model_dump_json()
        restored = FileManifest.model_validate_json(json_str)
        assert restored == sample_manifest

    def test_model_json_schema(self) -> None:
        """Verify the schema is suitable for MCP outputSchema."""
        schema = FileManifest.model_json_schema()
        assert schema["type"] == "object"
        assert "files" in schema["properties"]
        assert "agent_instructions" in schema["properties"]
        assert "summary" in schema["properties"]


# ---------------------------------------------------------------------------
# Import re-exports
# ---------------------------------------------------------------------------


class TestReExports:
    def test_tapps_core_common_exports(self) -> None:
        from tapps_core.common import (
            AgentInstructions,
            FileManifest,
            FileOperation,
            WriteMode,
            detect_write_mode,
        )

        assert FileOperation is not None
        assert FileManifest is not None
        assert AgentInstructions is not None
        assert WriteMode is not None
        assert callable(detect_write_mode)

    def test_tapps_mcp_common_reexports(self) -> None:
        # Verify identity — same objects, not copies
        from tapps_core.common.file_operations import (
            FileManifest as CoreFileManifest,
        )
        from tapps_core.common.file_operations import (
            FileOperation as CoreFileOperation,
        )
        from tapps_mcp.common import (
            FileManifest,
            FileOperation,
        )

        assert FileOperation is CoreFileOperation
        assert FileManifest is CoreFileManifest
