"""Tests for Tier 3 config/state writers content-return — Epic 87 Story 87.5."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestSetEngagementLevelContentReturn:
    """Test tapps_set_engagement_level in content-return mode."""

    def test_content_return_via_env(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = tapps_set_engagement_level("high")

        data = result["data"]
        assert data.get("content_return") is True
        assert "file_manifest" in data
        manifest = data["file_manifest"]
        assert manifest["file_count"] == 1
        assert manifest["files"][0]["path"] == ".tapps-mcp.yaml"
        assert "high" in manifest["files"][0]["content"]

    def test_direct_write_no_manifest(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            result = tapps_set_engagement_level("medium")

        data = result["data"]
        assert data.get("content_return") is None
        assert "file_manifest" not in data


class _TestManageExpertsContentReturn_REMOVED:
    """Test tapps_manage_experts add/scaffold in content-return mode."""

    def test_add_content_return(self, tmp_path: Path) -> None:
        from tapps_mcp.server_expert_tools import _handle_add

        # Create the experts.yaml first
        experts_dir = tmp_path / ".tapps-mcp"
        experts_dir.mkdir(parents=True)
        (experts_dir / "experts.yaml").write_text(
            "experts: []\n", encoding="utf-8"
        )

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = _handle_add(
                tmp_path,
                expert_id="expert-test",
                expert_name="Test Expert",
                primary_domain="testing",
                description="A test expert",
                keywords=["test"],
                rag_enabled=True,
                knowledge_dir="",
            )

        assert result.get("content_return") is True
        assert "file_manifest" in result
        manifest = result["file_manifest"]
        assert manifest["file_count"] == 1
        assert ".tapps-mcp/experts.yaml" in manifest["files"][0]["path"]

    def test_scaffold_content_return(self, tmp_path: Path) -> None:
        import yaml

        from tapps_mcp.server_expert_tools import _handle_scaffold

        # Create experts.yaml with an expert
        experts_dir = tmp_path / ".tapps-mcp"
        experts_dir.mkdir(parents=True)
        data = {
            "experts": [
                {
                    "expert_id": "expert-test",
                    "expert_name": "Test Expert",
                    "primary_domain": "testing",
                },
            ],
        }
        (experts_dir / "experts.yaml").write_text(
            yaml.dump(data), encoding="utf-8"
        )

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = _handle_scaffold(tmp_path, "expert-test")

        assert result.get("content_return") is True
        assert "file_manifest" in result
        manifest = result["file_manifest"]
        assert manifest["file_count"] == 2  # README.md + overview.md
        paths = [f["path"] for f in manifest["files"]]
        assert any("README.md" in p for p in paths)
        assert any("overview.md" in p for p in paths)


class TestMemoryExportContentReturn:
    """Test tapps_memory export in content-return mode."""

    def _make_params(self, **overrides: object) -> object:
        """Create a _Params with sensible defaults for export tests."""
        from tapps_mcp.server_memory_tools import _Params

        defaults = {
            "key": "",
            "value": "",
            "tier": "pattern",
            "source": "agent",
            "source_agent": "test",
            "scope": "project",
            "tag_list": [],
            "branch": "",
            "query": "",
            "confidence": -1.0,
            "ranked": True,
            "limit": 0,
            "include_summary": True,
            "file_path": "",
            "overwrite": False,
            "entries": "",
            "entry_ids": [],
            "dry_run": False,
            "include_sources": False,
            "export_format": "json",
            "include_frontmatter": True,
            "export_group_by": "tier",
        }
        defaults.update(overrides)
        return _Params(**defaults)  # type: ignore[arg-type]

    def test_export_content_return_json(self, tmp_path: Path) -> None:
        from tapps_mcp.server_memory_tools import _handle_export

        from tapps_core.memory.store import MemoryStore

        store = MemoryStore(project_root=tmp_path)
        p = self._make_params(export_format="json")

        with patch.dict(os.environ, {"TAPPS_WRITE_MODE": "content"}):
            result = _handle_export(store, p)

        assert result.get("content_return") is True
        assert "file_manifest" in result
        manifest = result["file_manifest"]
        assert manifest["file_count"] == 1
        assert manifest["files"][0]["path"].endswith(".json")

    def test_export_direct_write(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        from tapps_mcp.server_memory_tools import _handle_export

        from tapps_core.memory.store import MemoryStore

        store = MemoryStore(project_root=tmp_path)
        p = self._make_params(
            export_format="json",
            file_path=str(tmp_path / "export.json"),
        )

        # Patch load_settings to return tmp_path as project_root
        mock_settings = MagicMock()
        mock_settings.project_root = tmp_path

        with (
            patch.dict(os.environ, {}, clear=False),
            patch(
                "tapps_mcp.server_memory_tools._handle_export.__module__",
                create=True,
            ),
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
        ):
            os.environ.pop("TAPPS_WRITE_MODE", None)
            result = _handle_export(store, p)

        assert result.get("content_return") is None
        assert "file_manifest" not in result
        assert result["action"] == "export"
