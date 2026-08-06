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

    def test_mcp_config_vscode_servers_key(self) -> None:
        """TAP-5359: VS Code `servers` key is accepted without rewrap suggestion."""
        config = {
            "servers": {
                "nlt-build": {
                    "command": "nlt-build-serve",
                    "args": [],
                }
            }
        }
        result = validate_mcp_config(".vscode/mcp.json", json.dumps(config))
        assert result.valid is True
        assert not any(f.severity == "critical" for f in result.findings)
        assert not any("mcpServers" in s for s in result.suggestions)
        assert not any("Server 'servers'" in f.message for f in result.findings)

    def test_mcp_config_vscode_malformed_server_still_reported(self) -> None:
        """TAP-5359: genuine missing command still fails under `servers` key."""
        config = {
            "servers": {
                "broken": {
                    "args": ["--port", "8080"],
                }
            }
        }
        result = validate_mcp_config(".vscode/mcp.json", json.dumps(config))
        assert result.valid is False
        assert any("missing 'command'" in f.message for f in result.findings)

    def test_mcp_config_http_server_needs_no_command(self) -> None:
        """Remote `http` servers carry url/headers, not command/args.

        Regression: the validator used to demand `command` from every
        server, so a working all-remote config reported one critical and
        one warning per server. NLTWeb's six `nlt-*` servers produced 12
        findings on a config that had always worked.
        """
        config = {
            "mcpServers": {
                "nlt-build": {
                    "type": "http",
                    "url": "http://localhost:8720/mcp",
                    "headers": {"Authorization": "Bearer x"},
                },
                "nlt-memory": {
                    "type": "http",
                    "url": "http://localhost:8720/mcp",
                    "headers": {"Authorization": "Bearer x"},
                },
            }
        }
        result = validate_mcp_config(".mcp.json", json.dumps(config))
        assert result.valid is True
        assert result.findings == []

    def test_mcp_config_sse_server_needs_no_command(self) -> None:
        """`sse` is a remote transport too."""
        config = {"mcpServers": {"remote": {"type": "sse", "url": "https://example.com/sse"}}}
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True
        assert not any(f.severity == "critical" for f in result.findings)

    def test_mcp_config_http_server_missing_url_is_critical(self) -> None:
        """A remote server without `url` is genuinely broken."""
        config = {"mcpServers": {"remote": {"type": "http"}}}
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is False
        critical = [f for f in result.findings if f.severity == "critical"]
        assert len(critical) == 1
        assert "missing 'url'" in critical[0].message

    @pytest.mark.parametrize(
        "type_value",
        ["http", "sse", "streamable-http", "streamableHttp", "streamable_http", "HTTP"],
    )
    def test_mcp_config_remote_transport_spellings(self, type_value: str) -> None:
        """Hosts spell remote transports differently; all mean 'no command'.

        Cursor writes `streamableHttp`, which an enumerated list of
        lowercase names would miss.
        """
        config = {
            "mcpServers": {"remote": {"type": type_value, "url": "http://127.0.0.1:8760/mcp"}}
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True, f"{type_value} should not require 'command'"
        assert result.findings == []

    @pytest.mark.parametrize("url_value", ["", "   ", None, 123])
    def test_mcp_config_remote_blank_url_is_critical(self, url_value: object) -> None:
        """A blank or non-string `url` is as unusable as a missing one.

        A bare `"url" in config` presence check scored these clean, which is
        the same false-negative the transport fix exists to avoid — inverted.
        """
        config = {"mcpServers": {"remote": {"type": "http", "url": url_value}}}
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is False
        assert any(f.severity == "critical" and "'url'" in f.message for f in result.findings)

    @pytest.mark.parametrize("command_value", ["", "   ", None, 123])
    def test_mcp_config_stdio_blank_command_is_critical(self, command_value: object) -> None:
        """Same tightening on the stdio side; an empty `command` cannot spawn."""
        config = {"mcpServers": {"local": {"type": "stdio", "command": command_value, "args": []}}}
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is False
        assert any(f.severity == "critical" and "'command'" in f.message for f in result.findings)

    def test_mcp_config_unrecognized_transport_infers_from_url(self) -> None:
        """An unknown `type` spelling falls back to shape, not to stdio.

        Matching normalized letters still leaves `sse` an exact compare, so a
        variant like `server-sent-events` would otherwise be demanded a
        `command` it will never have.
        """
        config = {"mcpServers": {"remote": {"type": "server-sent-events", "url": "https://x/mcp"}}}
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True
        assert not any("missing 'command'" in f.message for f in result.findings)

    def test_mcp_config_explicit_stdio_with_url_still_needs_command(self) -> None:
        """An explicit `type: stdio` is never overridden by shape inference."""
        config = {"mcpServers": {"local": {"type": "stdio", "url": "https://x/mcp"}}}
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is False
        assert any("missing 'command'" in f.message for f in result.findings)

    def test_mcp_config_transport_inferred_from_url(self) -> None:
        """`type` is optional; presence of `url` implies a remote server."""
        config = {"mcpServers": {"remote": {"url": "https://example.com/mcp"}}}
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True
        assert not any("missing 'command'" in f.message for f in result.findings)

    def test_mcp_config_remote_server_with_command_warns(self) -> None:
        """`command` on a remote server is ignored at runtime; flag it."""
        config = {
            "mcpServers": {
                "confused": {
                    "type": "http",
                    "url": "https://example.com/mcp",
                    "command": "npx",
                }
            }
        }
        result = validate_mcp_config("mcp.json", json.dumps(config))
        assert result.valid is True
        assert any(
            f.severity == "warning" and "ignored for remote transports" in f.message
            for f in result.findings
        )

    def test_mcp_config_mixed_transports(self) -> None:
        """A stdio server and a remote server coexist without false positives."""
        config = {
            "mcpServers": {
                "agentforge": {
                    "type": "stdio",
                    "command": "uvx",
                    "args": ["--from", "/path", "agentforge-mcp"],
                },
                "nlt-build": {"type": "http", "url": "http://localhost:8720/mcp"},
            }
        }
        result = validate_mcp_config(".mcp.json", json.dumps(config))
        assert result.valid is True
        assert result.findings == []

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
