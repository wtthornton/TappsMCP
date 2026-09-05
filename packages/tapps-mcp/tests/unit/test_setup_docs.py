"""Tests for distribution.setup_docs — rules, hooks, agents, skills, and core docs."""

from pathlib import Path

import pytest

from tapps_mcp.distribution.setup_generator import (
    _generate_rules,
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


class TestGenerateRules:
    """Tests for platform rule file generation via _generate_rules."""

    def test_generates_claude_md(self, tmp_path):
        """Generates CLAUDE.md for claude-code host."""
        _generate_rules("claude-code", tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text(encoding="utf-8")
        assert "TAPPS" in content

    def test_generates_cursor_rules(self, tmp_path):
        """Generates .cursor/rules/tapps-pipeline.mdc for cursor host."""
        _generate_rules("cursor", tmp_path)
        rules = tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc"
        assert rules.exists()
        content = rules.read_text(encoding="utf-8")
        assert "TAPPS" in content

    def test_vscode_is_noop(self, tmp_path):
        """VS Code has no platform rules; _generate_rules is a no-op."""
        _generate_rules("vscode", tmp_path)
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_existing_claude_md_gets_obligations_block_appended(self, tmp_path):
        """An existing user-authored CLAUDE.md is preserved; the marker-wrapped
        TAPPS obligations block is appended (TAP-970). User content remains
        unchanged; the block lives at the bottom and can be refreshed by
        tapps_upgrade without disturbing the user's prose. TAP-2334 also
        prepends the ``<!-- tapps-claude-version: X.Y.Z -->`` stamp at the top
        of the file.
        """
        original = "# Rules\nUse TAPPS pipeline.\n"
        (tmp_path / "CLAUDE.md").write_text(original)
        _generate_rules("claude-code", tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        # TAP-2334 stamp at the very top of the file.
        assert content.startswith("<!-- tapps-claude-version: ")
        # User-authored prose preserved verbatim.
        assert original in content
        # Marker-wrapped obligations block appended (TAP-970).
        assert "<!-- BEGIN: tapps-obligations" in content
        assert "<!-- END: tapps-obligations -->" in content

    def test_skips_existing_cursor_rules(self, tmp_path):
        """Skips cursor rules if file already exists."""
        rules = tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc"
        rules.parent.mkdir(parents=True)
        rules.write_text("existing rules")
        _generate_rules("cursor", tmp_path)
        assert rules.read_text(encoding="utf-8") == "existing rules"


# ---------------------------------------------------------------------------
# Multi-host configuration tests
# ---------------------------------------------------------------------------


class TestPreviewFilesMatchGenerators:
    """VAL-08: every concrete path in _PREVIEW_FILES_BY_HOST must actually be
    written by _generate_rules for that host (TAP-6802). Directory-glob
    entries such as ".claude/hooks/ (tapps-session-start, ...)" describe a
    directory of examples rather than one file and are out of scope — they
    are identified by the " (" example-list marker and skipped.
    """

    @staticmethod
    def _concrete_paths(entries: tuple[str, ...]) -> list[str]:
        return [entry for entry in entries if " (" not in entry]

    @pytest.mark.parametrize("host", ["claude-code", "cursor", "vscode"])
    def test_every_previewed_file_is_actually_generated(self, tmp_path: Path, host: str) -> None:
        from tapps_mcp.distribution.setup_docs import (
            _PREVIEW_COMMON_FILES,
            _PREVIEW_FILES_BY_HOST,
        )

        _generate_rules(host, tmp_path)

        previewed = (
            self._concrete_paths(_PREVIEW_FILES_BY_HOST.get(host, ()))
            + self._concrete_paths(_PREVIEW_COMMON_FILES)
        )
        missing = [path for path in previewed if not (tmp_path / path).exists()]
        assert not missing, (
            f"Preview advertises files for host={host!r} that no generator "
            f"in the _generate_rules path creates: {missing}"
        )
