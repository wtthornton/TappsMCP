"""Unit tests for tapps_manage_experts MCP tool handler (Epic 45, Story 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tapps_mcp.server_expert_tools import (
    _atomic_write_yaml,
    tapps_manage_experts,
)


def _make_settings(project_root: Path) -> MagicMock:
    """Build a mock TappsMCPSettings with the given project_root."""
    settings = MagicMock()
    settings.project_root = project_root
    return settings


def _write_experts_yaml(tmp_path: Path, data: dict[str, Any]) -> Path:
    """Write a test experts.yaml and return its path."""
    yaml_dir = tmp_path / ".tapps-mcp"
    yaml_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = yaml_dir / "experts.yaml"
    yaml_path.write_text(yaml.safe_dump(data, default_flow_style=False), encoding="utf-8")
    return yaml_path


@pytest.fixture(autouse=True)
def _mock_settings(tmp_path: Path) -> Any:
    """Patch load_settings to use tmp_path as project_root."""
    settings = _make_settings(tmp_path)
    with patch(
        "tapps_core.config.settings.load_settings",
        return_value=settings,
    ):
        yield settings


@pytest.mark.asyncio()
class TestTappsManageExperts:
    """Tests for the tapps_manage_experts MCP tool handler."""

    # ------------------------------------------------------------------
    # Invalid action
    # ------------------------------------------------------------------

    async def test_invalid_action_rejected(self) -> None:
        result = await tapps_manage_experts(action="invalid")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_action"

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    async def test_list_no_config_returns_empty(self, tmp_path: Path) -> None:
        result = await tapps_manage_experts(action="list")
        assert result["success"] is True
        assert result["data"]["action"] == "list"
        assert result["data"]["experts"] == []
        assert result["data"]["count"] == 0

    async def test_list_with_config_returns_experts(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-finops",
                    "expert_name": "FinOps Expert",
                    "primary_domain": "finops",
                    "description": "Cloud financial operations.",
                    "keywords": ["cost", "budget"],
                },
            ],
        })
        result = await tapps_manage_experts(action="list")
        assert result["success"] is True
        assert result["data"]["count"] == 1
        expert = result["data"]["experts"][0]
        assert expert["expert_id"] == "expert-finops"
        assert expert["expert_name"] == "FinOps Expert"
        assert expert["knowledge_exists"] is False
        assert expert["knowledge_file_count"] == 0

    # ------------------------------------------------------------------
    # add
    # ------------------------------------------------------------------

    async def test_add_creates_new_yaml(self, tmp_path: Path) -> None:
        result = await tapps_manage_experts(
            action="add",
            expert_id="expert-retail",
            expert_name="Retail Expert",
            primary_domain="retail",
            description="Retail domain knowledge.",
        )
        assert result["success"] is True
        assert result["data"]["action"] == "add"
        assert result["data"]["expert_id"] == "expert-retail"

        # Verify YAML was created
        yaml_path = tmp_path / ".tapps-mcp" / "experts.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert len(data["experts"]) == 1
        assert data["experts"][0]["expert_id"] == "expert-retail"

    async def test_add_appends_to_existing(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-first",
                    "expert_name": "First Expert",
                    "primary_domain": "first-domain",
                },
            ],
        })
        result = await tapps_manage_experts(
            action="add",
            expert_id="expert-second",
            expert_name="Second Expert",
            primary_domain="second-domain",
        )
        assert result["success"] is True

        yaml_path = tmp_path / ".tapps-mcp" / "experts.yaml"
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert len(data["experts"]) == 2

    async def test_add_rejects_duplicate_expert_id(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-dup",
                    "expert_name": "Dup Expert",
                    "primary_domain": "dup-domain",
                },
            ],
        })
        result = await tapps_manage_experts(
            action="add",
            expert_id="expert-dup",
            expert_name="Another Name",
            primary_domain="another-domain",
        )
        assert result["success"] is False
        assert result["error"]["code"] == "duplicate_expert_id"

    async def test_add_rejects_builtin_collision(self) -> None:
        result = await tapps_manage_experts(
            action="add",
            expert_id="expert-security",
            expert_name="My Security Expert",
            primary_domain="my-security",
        )
        assert result["success"] is False
        assert result["error"]["code"] == "builtin_collision"

    async def test_add_rejects_missing_required_fields(self) -> None:
        # Missing expert_id
        result = await tapps_manage_experts(
            action="add",
            expert_name="Name",
            primary_domain="domain",
        )
        assert result["success"] is False
        assert "missing_expert_id" in result["error"]["code"]

        # Missing expert_name
        result = await tapps_manage_experts(
            action="add",
            expert_id="expert-test",
            primary_domain="domain",
        )
        assert result["success"] is False
        assert "missing_expert_name" in result["error"]["code"]

        # Missing primary_domain
        result = await tapps_manage_experts(
            action="add",
            expert_id="expert-test",
            expert_name="Name",
        )
        assert result["success"] is False
        assert "missing_primary_domain" in result["error"]["code"]

    async def test_add_rejects_invalid_expert_id_prefix(self) -> None:
        result = await tapps_manage_experts(
            action="add",
            expert_id="bad-prefix",
            expert_name="Name",
            primary_domain="domain",
        )
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_expert_id"

    # ------------------------------------------------------------------
    # remove
    # ------------------------------------------------------------------

    async def test_remove_removes_expert(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-remove-me",
                    "expert_name": "Remove Me",
                    "primary_domain": "removable",
                },
                {
                    "expert_id": "expert-keep-me",
                    "expert_name": "Keep Me",
                    "primary_domain": "keepable",
                },
            ],
        })
        result = await tapps_manage_experts(
            action="remove",
            expert_id="expert-remove-me",
        )
        assert result["success"] is True
        assert result["data"]["action"] == "remove"
        assert result["data"]["remaining_count"] == 1

        yaml_path = tmp_path / ".tapps-mcp" / "experts.yaml"
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert len(data["experts"]) == 1
        assert data["experts"][0]["expert_id"] == "expert-keep-me"

    async def test_remove_not_found(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {"experts": []})
        result = await tapps_manage_experts(
            action="remove",
            expert_id="expert-nonexistent",
        )
        assert result["success"] is False
        assert "not_found" in result["error"]["code"]

    # ------------------------------------------------------------------
    # scaffold
    # ------------------------------------------------------------------

    async def test_scaffold_creates_directory(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-scaffold",
                    "expert_name": "Scaffold Expert",
                    "primary_domain": "scaffoldable",
                },
            ],
        })
        result = await tapps_manage_experts(
            action="scaffold",
            expert_id="expert-scaffold",
        )
        assert result["success"] is True
        assert result["data"]["action"] == "scaffold"
        knowledge_path = Path(result["data"]["knowledge_path"])
        assert knowledge_path.exists()
        assert (knowledge_path / "README.md").exists()

    async def test_scaffold_is_idempotent(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-idem",
                    "expert_name": "Idempotent Expert",
                    "primary_domain": "idempotent",
                },
            ],
        })
        result1 = await tapps_manage_experts(action="scaffold", expert_id="expert-idem")
        result2 = await tapps_manage_experts(action="scaffold", expert_id="expert-idem")
        assert result1["success"] is True
        assert result2["success"] is True
        assert result1["data"]["knowledge_path"] == result2["data"]["knowledge_path"]

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    async def test_validate_reports_missing_knowledge_dirs(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-missing",
                    "expert_name": "Missing Knowledge",
                    "primary_domain": "missing-domain",
                },
            ],
        })
        result = await tapps_manage_experts(action="validate")
        assert result["success"] is True
        assert result["data"]["action"] == "validate"
        assert "missing-domain" in result["data"]["missing"]

    async def test_validate_reports_valid_setup(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-valid",
                    "expert_name": "Valid Expert",
                    "primary_domain": "valid-domain",
                },
            ],
        })
        # Create knowledge dir with a .md file
        knowledge_dir = tmp_path / ".tapps-mcp" / "knowledge" / "valid-domain"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "guide.md").write_text("# Guide", encoding="utf-8")

        result = await tapps_manage_experts(action="validate")
        assert result["success"] is True
        assert "valid-domain" in result["data"]["valid"]
        assert result["data"]["missing"] == []



class TestAtomicYamlWrite:
    """Tests for the _atomic_write_yaml helper."""

    def test_atomic_write_produces_valid_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "test.yaml"
        data = {
            "experts": [
                {"expert_id": "expert-test", "expert_name": "Test", "primary_domain": "test"},
            ],
        }
        _atomic_write_yaml(yaml_path, data)
        assert yaml_path.exists()
        loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert loaded["experts"][0]["expert_id"] == "expert-test"
