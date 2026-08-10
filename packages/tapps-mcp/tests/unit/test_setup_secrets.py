"""Tests for distribution.setup_secrets — secret detection and cross-scope env migration."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.distribution.setup_generator import (
    _collect_plaintext_secrets,
    _ensure_gitignore_entry,
    _generate_config,
    _load_existing_env_from_other_scope,
    _looks_like_secret_key,
    _value_is_plaintext_secret,
)


@pytest.fixture(autouse=True)
def _isolate_operator_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep tests off the developer machine's real ~/.local/bin MCP shims."""
    fake_home = tmp_path / "isolated-home"
    fake_home.mkdir()
    monkeypatch.setattr("tapps_mcp.distribution.setup_generator.Path.home", lambda: fake_home)
    monkeypatch.setattr(
        "tapps_mcp.distribution.blue_green.CURRENT_LINK",
        fake_home / ".tapps-mcp" / "current",
    )


class TestEnvMigrationAcrossScopes:
    """Issue #80.2 — init --scope project preserves env from user-scope config."""

    def test_load_existing_env_from_other_scope_user_to_project(self, tmp_path):
        """Project-scope init picks up env vars from ~/.claude.json."""
        home = tmp_path / "home"
        home.mkdir()
        user_cfg = home / ".claude.json"
        user_cfg.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "tapps-mcp",
                            "args": ["serve"],
                            "env": {
                                "CONTEXT7_API_KEY": "ctx7sk-test",
                                "TAPPS_MCP_PROJECT_ROOT": "/old/path",
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        project = tmp_path / "proj"
        project.mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=home):
            env = _load_existing_env_from_other_scope("claude-code", project, "project")
        assert env == {"CONTEXT7_API_KEY": "ctx7sk-test"}

    def test_load_existing_env_returns_empty_when_missing(self, tmp_path):
        """Missing other-scope file → empty dict."""
        home = tmp_path / "home"
        home.mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=home):
            env = _load_existing_env_from_other_scope("claude-code", tmp_path / "proj", "project")
        assert env == {}

    def test_load_existing_env_skips_non_claude_hosts(self, tmp_path):
        """Non-claude hosts have no alternate scope."""
        assert _load_existing_env_from_other_scope("cursor", tmp_path, "project") == {}

    def test_generate_config_migrates_env_from_user_scope(self, tmp_path):
        """Creating new project .mcp.json merges env from ~/.claude.json."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".claude.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "tapps-mcp",
                            "args": ["serve"],
                            "env": {"CONTEXT7_API_KEY": "ctx7sk-migrated"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        project = tmp_path / "proj"
        project.mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=home):
            ok = _generate_config("claude-code", project, scope="project", force=True)
        assert ok
        data = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
        env = data["mcpServers"]["tapps-mcp"]["env"]
        assert env["CONTEXT7_API_KEY"] == "ctx7sk-migrated"
        # Scope-specific key still set
        assert env["TAPPS_MCP_PROJECT_ROOT"] == "."


# ---------------------------------------------------------------------------
# Issue #80.3: plaintext secret detection
# ---------------------------------------------------------------------------


class TestPlaintextSecretDetection:
    def test_looks_like_secret_key_matches_common_patterns(self):
        assert _looks_like_secret_key("CONTEXT7_API_KEY")
        assert _looks_like_secret_key("GITHUB_TOKEN")
        assert _looks_like_secret_key("my_secret")
        assert _looks_like_secret_key("db_password")

    def test_looks_like_secret_key_ignores_known_benign(self):
        assert not _looks_like_secret_key("TAPPS_MCP_PROJECT_ROOT")
        assert not _looks_like_secret_key("DOCS_MCP_PROJECT_ROOT")
        assert not _looks_like_secret_key("VIRTUAL_ENV")
        assert not _looks_like_secret_key("FOO")

    def test_looks_like_secret_key_ignores_file_and_path_suffixes(self):
        assert not _looks_like_secret_key("AGENTFORGE_API_KEY_FILE")
        assert not _looks_like_secret_key("OPENAI_API_KEY_PATH")
        assert not _looks_like_secret_key("db_password_file")
        # Still flags real secrets without the suffix.
        assert _looks_like_secret_key("AGENTFORGE_API_KEY")

    def test_value_is_plaintext_secret_excludes_interpolation(self):
        assert _value_is_plaintext_secret("ctx7sk-abc123")
        assert not _value_is_plaintext_secret("${CONTEXT7_API_KEY}")
        assert not _value_is_plaintext_secret("$CONTEXT7_API_KEY")
        assert not _value_is_plaintext_secret("")
        assert not _value_is_plaintext_secret(None)

    def test_collect_plaintext_secrets(self):
        entry = {
            "env": {
                "TAPPS_MCP_PROJECT_ROOT": ".",
                "CONTEXT7_API_KEY": "ctx7sk-xyz",
                "SAFE_TOKEN": "${SAFE_TOKEN}",
            }
        }
        secrets = _collect_plaintext_secrets(entry)
        assert secrets == ["CONTEXT7_API_KEY"]

    def test_collect_plaintext_secrets_skips_file_pointer_and_path_values(self):
        entry = {
            "env": {
                "AGENTFORGE_API_KEY_FILE": "/home/user/WebStoreDNA/.env",
                "CONTEXT7_API_KEY": "/home/user/keys/ctx7.secret",
                "REAL_API_KEY": "sk-live-plain",
            }
        }
        secrets = _collect_plaintext_secrets(entry)
        assert secrets == ["REAL_API_KEY"]

    def test_generate_config_warns_on_plaintext_secret(self, tmp_path, capsys):
        """_generate_config prints a warning when env has plaintext secrets."""
        project = tmp_path / "proj"
        project.mkdir()
        existing = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "args": ["serve"],
                    "env": {
                        "TAPPS_MCP_PROJECT_ROOT": ".",
                        "CONTEXT7_API_KEY": "ctx7sk-plain",
                    },
                }
            }
        }
        (project / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")
        ok = _generate_config("claude-code", project, scope="project", force=True)
        assert ok
        out = capsys.readouterr().out
        assert "plaintext secret" in out.lower()
        assert "CONTEXT7_API_KEY" in out

    def test_ensure_gitignore_entry_appends(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules\n", encoding="utf-8")
        result = _ensure_gitignore_entry(tmp_path, ".mcp.json")
        assert result is True
        assert ".mcp.json" in gi.read_text(encoding="utf-8")

    def test_ensure_gitignore_entry_detects_existing(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text(".mcp.json\n", encoding="utf-8")
        assert _ensure_gitignore_entry(tmp_path, ".mcp.json") is False

    def test_ensure_gitignore_entry_returns_none_when_missing(self, tmp_path):
        assert _ensure_gitignore_entry(tmp_path, ".mcp.json") is None

    def test_ensure_tapps_runtime_gitignore_adds_backups(self, tmp_path):
        from tapps_mcp.distribution.setup_generator import ensure_tapps_runtime_gitignore

        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules\n", encoding="utf-8")
        added = ensure_tapps_runtime_gitignore(tmp_path)
        text = gi.read_text(encoding="utf-8")
        assert ".tapps-mcp/backups/" in added
        assert ".tapps-mcp/hook-backups/" in added
        assert ".tapps-mcp/backups/" in text
        assert ".tapps-mcp-cache/" in text

    def test_ensure_tapps_runtime_gitignore_skips_when_tree_ignored(self, tmp_path):
        from tapps_mcp.distribution.setup_generator import ensure_tapps_runtime_gitignore

        gi = tmp_path / ".gitignore"
        gi.write_text(".tapps-mcp/\n.tapps-mcp-cache/\n", encoding="utf-8")
        added = ensure_tapps_runtime_gitignore(tmp_path)
        assert added == []
        assert gi.read_text(encoding="utf-8").count(".tapps-mcp/backups/") == 0

    def test_ensure_tapps_runtime_gitignore_creates_file_when_absent(self, tmp_path):
        from tapps_mcp.distribution.setup_secrets import (
            _TAPPS_RUNTIME_GITIGNORE_ENTRIES,
            ensure_tapps_runtime_gitignore,
        )

        gi = tmp_path / ".gitignore"
        assert not gi.exists()
        added = ensure_tapps_runtime_gitignore(tmp_path)
        assert added == list(_TAPPS_RUNTIME_GITIGNORE_ENTRIES)
        text = gi.read_text(encoding="utf-8")
        assert ".tapps-mcp/backups/" in text
        assert ".tapps-mcp/hook-backups/" in text
        assert ".tapps-mcp-cache/" in text

    def test_ensure_tapps_runtime_gitignore_create_failure_returns_empty(
        self, tmp_path, monkeypatch
    ):
        from tapps_mcp.distribution import setup_secrets

        def _raise(*args: object, **kwargs: object) -> None:
            raise OSError("read-only filesystem")

        monkeypatch.setattr(setup_secrets.Path, "write_text", _raise)
        assert setup_secrets.ensure_tapps_runtime_gitignore(tmp_path) == []
        assert not (tmp_path / ".gitignore").exists()


# ---------------------------------------------------------------------------
# Issue #77: uv context detection
# ---------------------------------------------------------------------------
