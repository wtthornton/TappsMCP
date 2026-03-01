"""Tests for the docs_config MCP tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def _seed_cache(project_root: Path) -> Any:
    """Pre-populate the load_docs_settings cache with the given root.

    docs_config calls ``load_docs_settings()`` (no args) which returns
    a cached singleton.  We seed it once per test so the tool operates
    against the temp directory.
    """
    import docs_mcp.config.settings as _mod

    _mod._cached_settings = _mod.DocsMCPSettings(project_root=project_root)
    return _mod._cached_settings


@pytest.mark.asyncio
class TestDocsConfigView:
    """Tests for docs_config with action='view'."""

    async def test_view_returns_success(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        result = await docs_config(action="view")

        assert result["success"] is True
        assert result["tool"] == "docs_config"

    async def test_view_data_shape(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        result = await docs_config(action="view")

        data = result["data"]
        assert "config" in data
        assert "config_file" in data
        assert "config_exists" in data
        assert data["config_file"] == ".docsmcp.yaml"

    async def test_view_config_keys(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        result = await docs_config(action="view")

        config = result["data"]["config"]
        assert "output_dir" in config
        assert "default_style" in config
        assert "default_format" in config
        assert "include_toc" in config
        assert "include_badges" in config
        assert "changelog_format" in config
        assert "adr_format" in config
        assert "diagram_format" in config
        assert "git_log_limit" in config

    async def test_view_config_defaults(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        result = await docs_config(action="view")

        config = result["data"]["config"]
        assert config["output_dir"] == "docs"
        assert config["default_style"] == "standard"
        assert config["default_format"] == "markdown"

    async def test_view_elapsed_ms(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        result = await docs_config(action="view")

        assert "elapsed_ms" in result
        assert isinstance(result["elapsed_ms"], int)
        assert result["elapsed_ms"] >= 0


@pytest.mark.asyncio
class TestDocsConfigSet:
    """Tests for docs_config with action='set'."""

    async def test_set_updates_value(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        result = await docs_config(
            action="set", key="default_style", value="comprehensive"
        )

        assert result["success"] is True
        data = result["data"]
        assert data["key"] == "default_style"
        assert data["new_value"] == "comprehensive"
        assert data["config_file"] == ".docsmcp.yaml"

    async def test_set_creates_yaml_file(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        yaml_path = sample_project / ".docsmcp.yaml"
        assert not yaml_path.exists()

        _seed_cache(sample_project)
        await docs_config(action="set", key="output_dir", value="documentation")

        assert yaml_path.exists()

    async def test_set_invalid_key_fails(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        result = await docs_config(
            action="set", key="nonexistent_key", value="foo"
        )

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_KEY"

    async def test_set_missing_key_fails(self) -> None:
        from docs_mcp.server import docs_config

        result = await docs_config(action="set", key="", value="foo")

        assert result["success"] is False
        assert result["error"]["code"] == "MISSING_KEY"

    async def test_set_missing_value_fails(self) -> None:
        from docs_mcp.server import docs_config

        result = await docs_config(action="set", key="output_dir", value="")

        assert result["success"] is False
        assert result["error"]["code"] == "MISSING_VALUE"

    async def test_set_bool_key(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        result = await docs_config(
            action="set", key="include_toc", value="false"
        )

        assert result["success"] is True
        assert result["data"]["new_value"] is False

    async def test_set_int_key(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        result = await docs_config(
            action="set", key="git_log_limit", value="1000"
        )

        assert result["success"] is True
        assert result["data"]["new_value"] == 1000

    async def test_set_preserves_existing_keys(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_config

        _seed_cache(sample_project)
        await docs_config(action="set", key="output_dir", value="my-docs")

        # Re-seed because docs_config resets the cache after writing
        _seed_cache(sample_project)
        await docs_config(action="set", key="default_style", value="minimal")

        # Both should be in the YAML
        import yaml

        with (sample_project / ".docsmcp.yaml").open() as f:
            data = yaml.safe_load(f)

        assert data["output_dir"] == "my-docs"
        assert data["default_style"] == "minimal"


@pytest.mark.asyncio
class TestDocsConfigInvalidAction:
    """Tests for docs_config with invalid actions."""

    async def test_invalid_action_fails(self) -> None:
        from docs_mcp.server import docs_config

        result = await docs_config(action="delete")

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ACTION"
