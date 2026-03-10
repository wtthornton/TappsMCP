"""Tests for MCP server config validation."""

from __future__ import annotations

import json

import pytest

from tapps_mcp.validators.base import detect_config_type, validate_config
from tapps_mcp.validators.mcp_config import validate_mcp_config


class TestValidateMcpConfig:
    """Tests for the MCP config validator."""

    def test_mcp_config_valid(self) -> None:
        """Valid MCP config passes with no critical findings."""
        config = {
            "mcpServers": {
                "my-server": {
                    "command": "npx",
                    "args": ["-y", "@my/server"],
                    "env": {"API_KEY": "xxx"},
                }
            }
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True
        assert result.config_type == "mcp"
        assert not any(f.severity == "critical" for f in result.findings)

    def test_mcp_config_invalid_json(self) -> None:
        """Invalid JSON gives a critical finding."""
        result = validate_mcp_config("mcp.json", "{not valid json")
        assert result.valid is False
        assert len(result.findings) == 1
        assert result.findings[0].severity == "critical"
        assert "Invalid JSON" in result.findings[0].message

    def test_mcp_config_not_object(self) -> None:
        """Non-object JSON gives a critical finding."""
        result = validate_mcp_config("mcp.json", json.dumps([1, 2, 3]))
        assert result.valid is False
        assert result.findings[0].severity == "critical"
        assert "JSON object" in result.findings[0].message

    def test_mcp_config_missing_command(self) -> None:
        """Missing command field gives a critical finding."""
        config = {
            "mcpServers": {
                "bad-server": {
                    "args": ["--port", "8080"],
                }
            }
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is False
        critical = [f for f in result.findings if f.severity == "critical"]
        assert len(critical) == 1
        assert "missing 'command'" in critical[0].message

    def test_mcp_config_missing_args(self) -> None:
        """Missing args field gives a warning."""
        config = {
            "mcpServers": {
                "minimal-server": {
                    "command": "my-server",
                }
            }
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert len(warnings) == 1
        assert "no 'args'" in warnings[0].message

    def test_mcp_config_args_not_list(self) -> None:
        """Non-list args gives a warning."""
        config = {
            "mcpServers": {
                "bad-args": {
                    "command": "my-server",
                    "args": "--port 8080",
                }
            }
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert any("should be a list" in w.message for w in warnings)

    def test_mcp_config_empty_env_suggestion(self) -> None:
        """Empty env object gets a suggestion."""
        config = {
            "mcpServers": {
                "my-server": {
                    "command": "npx",
                    "args": ["-y", "@my/server"],
                    "env": {},
                }
            }
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True
        assert any("empty 'env'" in s for s in result.suggestions)

    def test_mcp_config_flat_format(self) -> None:
        """Flat format (no mcpServers wrapper) works but suggests wrapping."""
        config = {
            "my-server": {
                "command": "npx",
                "args": ["-y", "@my/server"],
            }
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True
        assert any("mcpServers" in s for s in result.suggestions)

    def test_mcp_config_server_not_object(self) -> None:
        """Server entry that is not an object gives a warning."""
        config = {
            "mcpServers": {
                "broken": "not-an-object",
            }
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert any("not an object" in w.message for w in warnings)

    def test_mcp_config_no_servers(self) -> None:
        """Empty servers dict gives a warning."""
        config = {"mcpServers": {}}
        result = validate_mcp_config("mcp.json", json.dumps(config))
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert any("No servers defined" in w.message for w in warnings)

    def test_mcp_config_multiple_servers(self) -> None:
        """Multiple valid servers all pass."""
        config = {
            "mcpServers": {
                "server-a": {"command": "node", "args": ["a.js"]},
                "server-b": {"command": "python", "args": ["-m", "b"]},
            }
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True
        assert not result.findings


class TestMcpConfigAutoDetect:
    """Tests for auto-detection of MCP config files."""

    @pytest.mark.parametrize(
        "path",
        [
            "mcp.json",
            ".mcp.json",
            ".cursor/mcp.json",
            "some/path/mcp.json",
        ],
    )
    def test_mcp_config_auto_detect(self, path: str) -> None:
        """Auto-detection identifies mcp.json files."""
        assert detect_config_type(path) == "mcp"

    def test_mcp_config_auto_detect_negative(self) -> None:
        """Non-MCP JSON files are not detected as MCP."""
        assert detect_config_type("package.json") != "mcp"
        assert detect_config_type("tsconfig.json") != "mcp"


class TestMcpConfigViaValidateConfig:
    """Tests that MCP config routes through validate_config correctly."""

    def test_validate_config_explicit_type(self) -> None:
        """Explicit config_type='mcp' routes to MCP validator."""
        config = {
            "mcpServers": {
                "srv": {"command": "node", "args": ["srv.js"]},
            }
        }
        result = validate_config("test.json", json.dumps(config), config_type="mcp")
        assert result.config_type == "mcp"
        assert result.valid is True

    def test_validate_config_auto_detect(self) -> None:
        """Auto-detection routes mcp.json to MCP validator."""
        config = {
            "mcpServers": {
                "srv": {"command": "node", "args": ["srv.js"]},
            }
        }
        result = validate_config("mcp.json", json.dumps(config))
        assert result.config_type == "mcp"
        assert result.valid is True
