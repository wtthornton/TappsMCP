"""Regression tests for TAP-6953: derive the permission allow-list from the

project's configured MCP servers instead of a hardcoded constant list.

Covers:
- ``configured_server_permission_entries`` derivation (and its ``None``
  fallback signal for projects with no discoverable MCP server config).
- ``generate_permission_settings`` consuming that derivation.
- A prune-survives-upgrade regression: a fixture project upgraded twice,
  with an entry pruned between runs, keeps that entry absent.
- ``check_claude_settings`` (doctor) not demanding ``mcp__tapps-mcp`` for a
  project shaped like nlt-ideas-scout (six ``nlt-*`` aliases + a third-party
  server, no legacy monolith entries).
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.distribution.doctor_hooks_cursor import check_claude_settings
from tapps_mcp.distribution.nlt_mcp_config import configured_server_permission_entries
from tapps_mcp.pipeline.init_permissions import generate_permission_settings


def _write_mcp_json(project_root: Path, server_names: list[str]) -> None:
    servers = {name: {"command": "true", "args": []} for name in server_names}
    (project_root / ".mcp.json").write_text(
        json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8"
    )


class TestConfiguredServerPermissionEntries:
    """Unit tests for the shared writer/checker derivation helper."""

    def test_no_mcp_config_returns_none(self, tmp_path: Path) -> None:
        """No .mcp.json / .cursor/mcp.json / .vscode/mcp.json at all -> None."""
        assert configured_server_permission_entries(tmp_path) is None

    def test_derives_bare_and_wildcard_per_server(self, tmp_path: Path) -> None:
        _write_mcp_json(tmp_path, ["nlt-build", "agentforge"])
        entries = configured_server_permission_entries(tmp_path)
        assert entries is not None
        assert set(entries) == {
            "mcp__nlt-build",
            "mcp__nlt-build__*",
            "mcp__agentforge",
            "mcp__agentforge__*",
        }

    def test_only_configured_servers_no_hardcoded_extras(self, tmp_path: Path) -> None:
        """A project running only nlt-build never gets tapps-mcp/nlt-memory entries."""
        _write_mcp_json(tmp_path, ["nlt-build"])
        entries = configured_server_permission_entries(tmp_path)
        assert entries is not None
        assert "mcp__tapps-mcp" not in entries
        assert "mcp__nlt-memory" not in entries


class TestGeneratePermissionSettingsDerivation:
    """generate_permission_settings uses the derived list when .mcp.json exists."""

    def test_derives_from_mcp_json_instead_of_hardcoded_constants(self, tmp_path: Path) -> None:
        _write_mcp_json(tmp_path, ["nlt-build"])
        result = generate_permission_settings(tmp_path)
        allow = result["permissions"]["allow"]
        assert "mcp__nlt-build" in allow
        assert "mcp__nlt-build__*" in allow
        # None of the hardcoded NLT bundle or legacy entries for servers this
        # project does not run should be present.
        assert "mcp__tapps-mcp" not in allow
        assert "mcp__nlt-memory" not in allow
        assert "mcp__nlt-code-quality" not in allow

    def test_no_mcp_json_preserves_legacy_hardcoded_behavior(self, tmp_path: Path) -> None:
        """Projects with no discoverable MCP config keep the old default entries."""
        from tapps_mcp.pipeline.init_permissions import (
            _CLAUDE_PERMISSION_ENTRIES,
            _NLT_PERMISSION_ENTRIES,
        )

        result = generate_permission_settings(tmp_path)
        allow = result["permissions"]["allow"]
        for entry in _CLAUDE_PERMISSION_ENTRIES:
            assert entry in allow
        for entry in _NLT_PERMISSION_ENTRIES:
            assert entry in allow


class TestPruneSurvivesUpgrade:
    """A pruned permission entry for a server the project no longer runs stays pruned."""

    def test_prune_between_two_upgrades_stays_absent(self, tmp_path: Path) -> None:
        """Fixture upgraded twice; an entry pruned between runs stays absent (TAP-6953 item 4).

        The server sets below are deliberately *not* an exact match for any
        named ``NLT_BUNDLES`` combination (build+memory+setup, then
        build+setup) -- an exact match would make ``upgrade_mcp_config``
        infer and re-sync a named bundle, overwriting the hand-edited
        ``.mcp.json`` between runs. A non-matching ("custom") set is left
        alone on disk (ADR-0016 opt-down safety), which is what lets this
        test control the configured-server set precisely.
        """
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

        # Run 1: project runs nlt-build, nlt-memory, and nlt-setup.
        _write_mcp_json(tmp_path, ["nlt-build", "nlt-memory", "nlt-setup"])
        result1 = upgrade_pipeline(tmp_path, platform="claude", force=True)
        assert result1["errors"] == []

        settings_path = tmp_path / ".claude" / "settings.json"
        allow_after_run1 = json.loads(settings_path.read_text(encoding="utf-8"))["permissions"][
            "allow"
        ]
        assert "mcp__nlt-memory" in allow_after_run1
        assert "mcp__nlt-build" in allow_after_run1

        # Prune between runs: the project drops the nlt-memory server AND its
        # operator manually deletes the stale permission entries.
        _write_mcp_json(tmp_path, ["nlt-build", "nlt-setup"])
        config = json.loads(settings_path.read_text(encoding="utf-8"))
        config["permissions"]["allow"] = [
            e for e in config["permissions"]["allow"] if "nlt-memory" not in e
        ]
        settings_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

        # Run 2 (--force): the pruned entry must not come back.
        result2 = upgrade_pipeline(tmp_path, platform="claude", force=True)
        assert result2["errors"] == []

        allow_after_run2 = json.loads(settings_path.read_text(encoding="utf-8"))["permissions"][
            "allow"
        ]
        assert "mcp__nlt-memory" not in allow_after_run2
        assert "mcp__nlt-memory__*" not in allow_after_run2
        assert "mcp__nlt-build" in allow_after_run2
        assert "mcp__nlt-build__*" in allow_after_run2


class TestDoctorScoutShapedFixture:
    """nlt-ideas-scout shape (TAP-6953): six nlt-* aliases + agentforge, no legacy monolith.

    The live-scout confirmation belongs to TAP-6949's owner; this fixture only
    demonstrates that doctor's required-permission vocabulary is no longer
    hardcoded to ``mcp__tapps-mcp``.
    """

    _SCOUT_SERVERS = [
        "nlt-build",
        "nlt-memory",
        "nlt-setup",
        "nlt-linear-issues",
        "nlt-project-docs",
        "nlt-release-ship",
        "agentforge",
    ]

    def test_no_missing_permission_entries_fail(self, tmp_path: Path) -> None:
        _write_mcp_json(tmp_path, self._SCOUT_SERVERS)

        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir(parents=True, exist_ok=True)
        allow = []
        for name in self._SCOUT_SERVERS:
            allow.extend([f"mcp__{name}", f"mcp__{name}__*"])
        (settings_dir / "settings.json").write_text(
            json.dumps({"permissions": {"allow": allow}}, indent=2), encoding="utf-8"
        )

        result = check_claude_settings(tmp_path)

        assert result.ok is True
        assert "tapps-mcp" not in result.message

    def test_still_fails_when_a_configured_server_entry_is_missing(self, tmp_path: Path) -> None:
        """Sanity check: the derived requirement is still enforced, not a no-op."""
        _write_mcp_json(tmp_path, self._SCOUT_SERVERS)

        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir(parents=True, exist_ok=True)
        (settings_dir / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["mcp__nlt-build", "mcp__nlt-build__*"]}}),
            encoding="utf-8",
        )

        result = check_claude_settings(tmp_path)

        assert result.ok is False
        assert "mcp__agentforge" in result.message
