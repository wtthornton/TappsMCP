"""Tests for shared HTTP MCP fleet config (ADR-0024)."""

from __future__ import annotations

from pathlib import Path

from tapps_core.http.request_context import PROJECT_ROOT_HEADER
from tapps_mcp.distribution.nlt_http_fleet import (
    DEFAULT_FLEET_EXTRA_ROOTS_ENV,
    NLT_HTTP_FLEET_PORTS,
    build_http_fleet_url,
    build_nlt_http_mcp_entry,
    resolve_fleet_consumer_roots,
    resolve_fleet_extra_roots,
    resolve_http_project_root_header,
    resolve_mcp_transport,
    sample_fleet_env_content,
)


class TestNltHttpFleet:
    def test_ports_cover_all_servers(self) -> None:
        assert set(NLT_HTTP_FLEET_PORTS) == {
            "nlt-build",
            "nlt-memory",
            "nlt-setup",
            "nlt-linear-issues",
            "nlt-project-docs",
            "nlt-release-ship",
        }

    def test_build_url(self) -> None:
        assert build_http_fleet_url("nlt-build") == "http://127.0.0.1:8760/mcp"

    def test_http_mcp_entry(self, tmp_path: Path) -> None:
        entry = build_nlt_http_mcp_entry("nlt-memory", project_root=tmp_path)
        assert entry["type"] == "streamableHttp"
        assert entry["url"] == "http://127.0.0.1:8761/mcp"
        assert entry["headers"][PROJECT_ROOT_HEADER] == str(tmp_path.resolve())

    def test_http_mcp_entry_type_is_host_aware(self, tmp_path: Path) -> None:
        """Claude Code / VS Code reject ``streamableHttp`` ("unknown MCP server
        type") and silently drop the server — they require ``http``. Cursor
        keeps its historical ``streamableHttp`` spelling.
        """
        for host in ("claude-code", "vscode"):
            entry = build_nlt_http_mcp_entry("nlt-memory", project_root=tmp_path, host=host)
            assert entry["type"] == "http", host
        cursor = build_nlt_http_mcp_entry("nlt-memory", project_root=tmp_path, host="cursor")
        assert cursor["type"] == "streamableHttp"

    def test_validates_http_entry(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.nlt_http_fleet import is_valid_http_fleet_mcp_entry

        entry = build_nlt_http_mcp_entry("nlt-build", project_root=tmp_path)
        assert is_valid_http_fleet_mcp_entry(entry) is True
        claude_entry = build_nlt_http_mcp_entry(
            "nlt-build", project_root=tmp_path, host="claude-code"
        )
        assert is_valid_http_fleet_mcp_entry(claude_entry) is True
        assert is_valid_http_fleet_mcp_entry({"type": "stdio", "command": "x"}) is False

    def test_is_remote_mcp_entry_covers_transport_spellings(self) -> None:
        """TAP-5723: hosts spell remote transports differently; all mean 'no command'."""
        from tapps_mcp.distribution.nlt_http_fleet import is_remote_mcp_entry

        for spelling in ("http", "sse", "streamable-http", "streamableHttp", "HTTP"):
            assert is_remote_mcp_entry({"type": spelling, "url": "http://x/mcp"}) is True, spelling
        assert is_remote_mcp_entry({"type": "stdio", "command": "tapps-mcp"}) is False
        # `type` is optional; a bare `url` implies remote, a bare command stdio.
        assert is_remote_mcp_entry({"url": "http://x/mcp"}) is True
        assert is_remote_mcp_entry({"command": "tapps-mcp", "args": []}) is False
        # An explicit stdio type is never overridden by shape.
        assert is_remote_mcp_entry({"type": "stdio", "url": "http://x/mcp"}) is False

    def test_describe_problem_names_the_real_defect(self, tmp_path: Path) -> None:
        """TAP-5723: a remote entry has no `command` to be 'unexpected'."""
        from tapps_mcp.distribution.nlt_http_fleet import describe_http_fleet_entry_problem

        assert "no usable 'url'" in describe_http_fleet_entry_problem({"type": "http"})
        assert "Streamable HTTP" in describe_http_fleet_entry_problem(
            {"type": "sse", "url": "http://x/mcp"}
        )
        assert PROJECT_ROOT_HEADER in describe_http_fleet_entry_problem(
            {"type": "http", "url": "http://x/mcp"}
        )
        assert "unexpanded template" in describe_http_fleet_entry_problem(
            {
                "type": "http",
                "url": "http://x/mcp",
                "headers": {PROJECT_ROOT_HEADER: "${workspaceFolder}"},
            }
        )

    def test_doctor_does_not_blame_command_on_remote_entry(self, tmp_path: Path) -> None:
        """TAP-5723: doctor reported "Unexpected command: ''" for every remote entry."""
        from tapps_mcp.distribution.doctor_mcp import _validate_mcp_entry_command

        valid = build_nlt_http_mcp_entry("nlt-build", project_root=tmp_path)
        assert _validate_mcp_entry_command(valid, tmp_path / ".mcp.json") is None

        headerless = {"type": "http", "url": "http://127.0.0.1:8760/mcp"}
        error = _validate_mcp_entry_command(headerless, tmp_path / ".mcp.json")
        assert error is not None, "a fleet entry missing its project-root header is still broken"
        assert "Unexpected command" not in error
        assert PROJECT_ROOT_HEADER in error

    def test_stdio_entry_still_validated_by_command(self, tmp_path: Path) -> None:
        """The transport branch must not loosen the stdio path."""
        from tapps_mcp.distribution.doctor_mcp import _validate_mcp_entry_command

        error = _validate_mcp_entry_command({"command": "not-tapps", "args": []}, tmp_path / "m")
        assert error is not None
        assert "Unexpected command" in error

    def test_resolve_transport_explicit(self) -> None:
        assert resolve_mcp_transport(None, explicit="http") == "http"

    def test_project_root_header_is_absolute(self, tmp_path: Path) -> None:
        value = resolve_http_project_root_header(tmp_path)
        assert value == str(tmp_path.resolve())
        assert "${" not in value

    def test_extra_roots_from_env(self, tmp_path: Path, monkeypatch) -> None:
        outside = tmp_path / "NewCompanyIdeas"
        outside.mkdir()
        monkeypatch.setenv(DEFAULT_FLEET_EXTRA_ROOTS_ENV, str(outside))
        assert resolve_fleet_extra_roots() == [outside.resolve()]
        roots = resolve_fleet_consumer_roots()
        assert outside.resolve() in roots
        assert roots[0] == roots[0]  # code root first

    def test_sample_fleet_env_documents_extra_roots(self) -> None:
        sample = sample_fleet_env_content()
        assert DEFAULT_FLEET_EXTRA_ROOTS_ENV in sample
        assert "NewCompanyIdeas" in sample
