"""Tests for malformed managed-JSON resilience in the upgrade pipeline.

Covers the bug where a ``.claude/settings.json`` / ``.cursor/hooks.json`` with a
dropped opening ``{`` brace raised a bare ``JSONDecodeError`` that aborted an
entire platform scope. The fixes:

- ``_load_managed_json`` raises a typed ``ManagedJsonError`` with a remediation
  hint instead of a bare ``JSONDecodeError``.
- ``_upgrade_*_live`` isolate the failure to the ``hooks`` component so the rest
  of the scope (agents / skills / rules) still upgrades.
- ``check_managed_json_parseable`` (doctor) flags the malformed file with a
  one-line repair hint.
"""

from __future__ import annotations

import json

import pytest

from tapps_mcp.distribution.doctor import check_managed_json_parseable
from tapps_mcp.pipeline.platform_hooks import (
    ManagedJsonError,
    _load_managed_json,
    _write_managed_json,
    dry_run_managed_json_status,
)

# A file missing its opening brace — line 2 begins directly with the first key,
# which is exactly the corruption reported from PowerShell-generated configs.
MALFORMED_JSON = '\n    "version":  1,\n    "hooks": {}\n}\n'


class TestLoadManagedJson:
    def test_missing_file_returns_empty(self, tmp_path):
        assert _load_managed_json(tmp_path / "absent.json") == {}

    def test_empty_file_returns_empty(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("   \n", encoding="utf-8")
        assert _load_managed_json(path) == {}

    def test_valid_file_round_trips(self, tmp_path):
        path = tmp_path / "ok.json"
        path.write_text(json.dumps({"version": 1, "hooks": {}}), encoding="utf-8")
        assert _load_managed_json(path) == {"version": 1, "hooks": {}}

    def test_non_object_top_level_returns_empty(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        assert _load_managed_json(path) == {}

    def test_malformed_raises_managed_json_error(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text(MALFORMED_JSON, encoding="utf-8")
        with pytest.raises(ManagedJsonError) as exc_info:
            _load_managed_json(path)
        err = exc_info.value
        assert err.path == path
        assert str(path) in str(err)
        assert "invalid JSON" in str(err)
        assert "'{' brace" in err.remediation


class TestDoctorCheck:
    def test_passes_when_files_absent(self, tmp_path):
        result = check_managed_json_parseable(tmp_path)
        assert result.ok

    def test_passes_on_valid_files(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text(
            json.dumps({"hooks": {}}), encoding="utf-8"
        )
        result = check_managed_json_parseable(tmp_path)
        assert result.ok

    def test_fails_on_malformed_cursor_hooks(self, tmp_path):
        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".cursor" / "hooks.json").write_text(MALFORMED_JSON, encoding="utf-8")
        result = check_managed_json_parseable(tmp_path)
        assert not result.ok
        assert "hooks.json" in result.message
        assert "brace" in result.detail


class TestUpgradeScopeIsolation:
    def test_malformed_cursor_hooks_does_not_lose_agents(self, tmp_path):
        """A broken .cursor/hooks.json isolates to the hooks component; agents
        and skills still generate, and the failure surfaces at the top level."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        (cursor_dir / "hooks.json").write_text(MALFORMED_JSON, encoding="utf-8")
        # Mark the project as cursor so the cursor scope runs.
        (cursor_dir / "rules").mkdir()
        (cursor_dir / "rules" / "placeholder.mdc").write_text("x", encoding="utf-8")

        result = upgrade_pipeline(project_root=tmp_path, platform="cursor")

        platforms = result["components"]["platforms"]
        cursor = next(p for p in platforms if p.get("host") == "cursor")
        # Scope was NOT aborted: cursor still has component results beyond hooks.
        assert "agents" in cursor["components"]
        assert "skills" in cursor["components"]
        # Hooks component carries the isolated, actionable error.
        hooks = cursor["components"]["hooks"]
        assert hooks["action"] == "error"
        assert "hooks.json" in hooks["error"]
        assert hooks["hint"]
        # Failure is surfaced at the top level (success=False).
        assert result["success"] is False
        assert any("hooks.json" in e for e in result["errors"])


class TestWriteManagedJson:
    def test_round_trip_writes_valid_document(self, tmp_path):
        path = tmp_path / "out.json"
        payload = {"version": 1, "hooks": {"stop": [{"command": "echo ok"}]}}
        _write_managed_json(path, payload)
        assert path.read_text(encoding="utf-8").startswith("{\n")
        assert json.loads(path.read_text(encoding="utf-8")) == payload


class TestDryRunParse:
    def test_malformed_claude_settings_blocks_dry_run(self, tmp_path):
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        (tmp_path / ".claude").mkdir()
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        (tmp_path / ".claude" / "settings.json").write_text(MALFORMED_JSON, encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        claude = result["components"]["platforms"][0]
        settings = claude["components"]["settings"]
        assert isinstance(settings, dict)
        assert settings["action"] == "error"
        assert "settings.json" in settings["error"]
        summary = result["dry_run_summary"]
        assert summary["verdict"] == "blocked"
        assert summary["parse_errors"]
        assert result["success"] is False

    def test_malformed_cursor_hooks_blocks_dry_run(self, tmp_path):
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".cursor" / "hooks.json").write_text(MALFORMED_JSON, encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="cursor", dry_run=True)
        cursor = next(p for p in result["components"]["platforms"] if p["host"] == "cursor")
        hooks = cursor["components"]["hooks"]
        assert hooks["action"] == "error"
        assert "hooks.json" in hooks["error"]
        assert result["dry_run_summary"]["verdict"] == "blocked"
        assert result["success"] is False

    def test_dry_run_status_ok_on_valid_file(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
        status = dry_run_managed_json_status(path, ok_message="would-merge")
        assert status == "would-merge"
